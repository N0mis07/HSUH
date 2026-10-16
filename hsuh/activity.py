"""Read native Hermes metadata without messages, prompts, credentials or DB writes."""
from datetime import datetime
from contextlib import closing
import json
from pathlib import Path
import re
import sqlite3
import threading
import time


def label(value, length=120):
    text = re.sub(r'[\x00-\x1f\x7f\u202a-\u202e\u2066-\u2069]', '', str(value or ''))
    text = re.sub(r'\b(?:sk-|ghp_|github_pat_|xox[baprs]-)[A-Za-z0-9_-]+', '[redacted]', text)
    return text[:length]


class ActivityReader:
    def __init__(self, home=None):
        self.home = Path(home) if home else Path.home() / '.hermes'
        self.cached, self.updated = None, 0
        self.lock = threading.Lock()

    def read(self):
        with self.lock:
            now = time.time()
            if self.cached is not None and time.monotonic() - self.updated < 10:
                return self.cached
            result = {'sampled_at': now, 'source': 'Hermes metadata database (read-only)',
                      'available': False, 'gateway': self.gateway(now),
                      'note': 'Open sessions include idle conversations. Running agents and live turn leases are separate observations. Token totals are recorded metadata, not subscription spend.'}
            path = self.home / 'state.db'
            try:
                with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True, timeout=1)) as db:
                    db.row_factory = sqlite3.Row
                    db.execute('PRAGMA query_only=ON')
                    deadline = time.monotonic() + 1
                    db.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
                    row = db.execute('''SELECT COUNT(*) total, SUM(ended_at IS NULL) open,
                        SUM(started_at >= ?) started_24h, SUM(COALESCE(input_tokens,0)) input_tokens,
                        SUM(COALESCE(output_tokens,0)) output_tokens,
                        SUM(COALESCE(cache_read_tokens,0)) cache_read_tokens,
                        SUM(COALESCE(reasoning_tokens,0)) reasoning_tokens,
                        SUM(COALESCE(api_call_count,0)) api_calls,
                        SUM(COALESCE(tool_call_count,0)) tool_calls FROM sessions''', (now-86400,)).fetchone()
                    result['totals'] = {k: int(row[k] or 0) for k in row.keys()}
                    result['sessions'] = [dict(row) for row in db.execute('''SELECT id,title,source,model,started_at,
                        ended_at,last_activity_at,api_call_count,tool_call_count,input_tokens,output_tokens,
                        parent_session_id FROM sessions ORDER BY COALESCE(last_activity_at,started_at) DESC LIMIT 24''')]
                    for session in result['sessions']:
                        for key in ('title', 'source', 'model'):
                            session[key] = label(session[key])
                        session['state'] = 'open' if session['ended_at'] is None else 'closed'
                    result['sources'] = [dict(row) for row in db.execute('SELECT source,COUNT(*) count FROM sessions GROUP BY source ORDER BY count DESC LIMIT 12')]
                    for row in result['sources']:
                        row['source'] = label(row['source'], 40)
                    try:
                        result['turn_leases'] = db.execute('SELECT COUNT(*) FROM session_turn_leases WHERE expires_at > ?', (now,)).fetchone()[0]
                    except sqlite3.Error:
                        result['turn_leases'] = None
                    try:
                        result['delegations'] = [dict(row) for row in db.execute('SELECT state,COUNT(*) count FROM async_delegations GROUP BY state LIMIT 12')]
                    except sqlite3.Error:
                        result['delegations'] = None
                result['available'] = True
            except (sqlite3.Error, OSError, ValueError):
                result['note'] = 'Native session metadata is unavailable or incompatible. No active-work count is inferred.'
            self.cached, self.updated = result, time.monotonic()
            return result

    def gateway(self, now):
        try:
            path = self.home / 'gateway_state.json'
            if path.stat().st_size > 65536:
                raise ValueError()
            data = json.loads(path.read_text())
            updated = datetime.fromisoformat(data['updated_at']).timestamp()
            agents = data.get('active_agents')
            return {'available': True, 'state': label(data.get('gateway_state'), 32),
                    'active_agents': agents if type(agents) is int and agents >= 0 else None,
                    'version': label(data.get('code_version'), 40), 'updated_at': updated,
                    'stale': now - updated > 120,
                    'platforms': [{'name': label(k, 32), 'state': label(v.get('state'), 32)}
                                  for k, v in list(data.get('platforms', {}).items())[:12]]}
        except (OSError, ValueError, KeyError, TypeError):
            return {'available': False, 'state': 'unavailable', 'active_agents': None, 'stale': True}
