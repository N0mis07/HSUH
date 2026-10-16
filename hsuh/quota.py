"""Read-only quota sources; no balances inferred from token or dollar estimates."""
import asyncio
from datetime import datetime, timezone
import json
import os
import time
from urllib.parse import urlsplit

import httpx


def native_projection(raw):
    windows = []
    for w in raw.get('windows', [])[:12]:
        p = w.get('used_percent')
        if isinstance(p, (int,float)) and 0 <= p <= 100:
            windows.append({'label':str(w.get('label','Limit'))[:80], 'used_percent':p,
                            'resets_at':w.get('resets_at')})
    return {'provider':str(raw.get('provider','unknown'))[:80], 'source':str(raw.get('source','unknown'))[:80],
            'plan':str(raw.get('plan') or 'Unknown')[:80], 'fetched_at':raw.get('fetched_at'), 'windows':windows,
            'available':bool(windows), 'note':None if windows else 'No numeric quota windows returned by Hermes.'}


class QuotaReader:
    def __init__(self):
        self.cached = None
        self.updated = 0
        self.lock = asyncio.Lock()

    async def native(self):
        p = None
        try:
            env = {k:v for k,v in os.environ.items() if not k.startswith('HERMES_')}
            from pathlib import Path
            env['HERMES_HOME'] = str(Path.home()/'.hermes')
            p = await asyncio.create_subprocess_exec('hermes','usage','--json',
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL, env=env)
            out, _ = await asyncio.wait_for(p.communicate(), 20)
            if p.returncode != 0 or len(out) > 100000:
                raise ValueError()
            return native_projection(json.loads(out))
        except Exception:
            return {'available':False, 'source':'hermes usage --json', 'windows':[],
                    'note':'Native provider quota is unavailable. No balance estimated.'}
        finally:
            if p and p.returncode is None:
                p.kill()
                await p.wait()

    async def aperture(self):
        base = os.environ.get('HSUH_APERTURE_URL','').rstrip('/')
        u = urlsplit(base)
        if not base or u.scheme != 'https' or not u.hostname or u.username or u.path or u.query or u.fragment:
            return {'available':False, 'source':'Aperture', 'note':'Aperture URL is not configured; no quota inferred.'}
        try:
            async with httpx.AsyncClient(timeout=8, follow_redirects=False) as client:
                r = await client.get(base+'/api/quotas')
                r.raise_for_status()
                if len(r.content) > 1000000:
                    raise ValueError()
                buckets = r.json()['buckets']
                if not isinstance(buckets,list):
                    raise ValueError()
                # Do not guess raw bucket semantics from a version-dependent management API.
                return {'available':True,'source':base+'/api/quotas','bucket_count':len(buckets),
                        'dashboard':base+'/chat/quotas',
                        'note':'No quota buckets configured.' if not buckets else 'Quota buckets exist; see Aperture for authoritative balances. HSUH does not yet parse their version-specific schema.'}
        except Exception:
            return {'available':False,'source':base+'/api/quotas','note':'Aperture quota could not be fetched. No balance estimated.'}

    async def read(self):
        async with self.lock:
            if self.cached and time.monotonic()-self.updated < 60:
                return self.cached
            native, aperture = await asyncio.gather(self.native(), self.aperture())
            self.cached = {'checked_at':datetime.now(timezone.utc).isoformat(), 'native':native, 'aperture':aperture,
                           'note':'Account-wide provider limits are not per-chat costs. Aperture budgets are not subscription quotas.'}
            self.updated = time.monotonic()
            return self.cached
