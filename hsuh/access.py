"""Fail-closed Cloudflare Access validation for the optional public HTTPS origin."""
import asyncio
import re
from urllib.parse import urlsplit

import jwt


class AccessGate:
    def __init__(self, origin, team, audience, owner_email):
        u = urlsplit(origin)
        if u.scheme != 'https' or not u.hostname or u.path or u.query or u.fragment or u.username or u.port:
            raise ValueError('HSUH_PUBLIC_ORIGIN must be an exact HTTPS origin without a path or port')
        if not team or not audience or not re.fullmatch(r'[a-zA-Z0-9-]{1,63}', team):
            raise ValueError('Public mode requires HSUH_ACCESS_TEAM and HSUH_ACCESS_AUDIENCE')
        if not owner_email or '@' not in owner_email:
            raise ValueError('Public mode requires an explicit HSUH_OWNER_EMAIL allowlist entry')
        self.origin, self.host = origin, u.netloc
        self.owner_email = owner_email.strip().casefold()
        self.issuer = f'https://{team}.cloudflareaccess.com'
        self.audience = audience
        self.jwks = jwt.PyJWKClient(self.issuer+'/cdn-cgi/access/certs', cache_jwk_set=True, lifespan=300, timeout=5)
        self.lock = asyncio.Lock()

    def _check(self, token):
        key = self.jwks.get_signing_key_from_jwt(token)
        claims = jwt.decode(token, key.key, algorithms=['RS256'], audience=self.audience, issuer=self.issuer,
                   options={'require':['exp','iat','iss','aud','sub']})
        if str(claims.get('email') or '').strip().casefold() != self.owner_email:
            raise ValueError('Not the owner')

    async def allows(self, token):
        if not token or len(token) > 16000:
            return False
        try:
            async with self.lock:
                await asyncio.to_thread(self._check, token)
            return True
        except Exception:
            return False
