"""Owner-only sign-in through an existing ZeroFrame passkey issuer.

The issuer keeps the passkeys and device invitations. This app receives only a
short-lived ES256 pass, addressed to this origin and bound to this browser.
"""
import asyncio
from http.cookies import SimpleCookie
import re
import secrets
import time
from urllib.parse import urlencode, urlsplit

import httpx
import jwt
from starlette.responses import JSONResponse, RedirectResponse


PASS_COOKIE = '__Host-hsuh_pass'
STATE_COOKIE = '__Host-hsuh_state'
STATE_TTL = 600


def exact_origin(value):
    u = urlsplit(value or '')
    if (u.scheme != 'https' or not u.hostname or u.path or u.query or u.fragment
            or u.username or u.password or u.port or u.netloc != u.hostname):
        raise ValueError('SSO requires exact HTTPS origins without paths or ports')
    return value


def cookies(headers):
    result = SimpleCookie()
    try:
        result.load(headers.get(b'cookie', b'').decode('latin1'))
    except Exception:
        return {}
    return {k: v.value for k, v in result.items()}


def local_path(value):
    if not isinstance(value, str) or not re.fullmatch(r'/(?![/\\])[^\s\\#]{0,500}', value):
        return '/'
    if urlsplit(value).path.startswith(('/auth/', '/sso/')):
        return '/'
    return value


class ZeroFrameGate:
    def __init__(self, origin, issuer, owner_id):
        self.origin = exact_origin(origin)
        self.host = urlsplit(self.origin).netloc
        self.issuer = exact_origin(issuer)
        if self.issuer == self.origin:
            raise ValueError('The SSO issuer must be separate from HSUH')
        if not owner_id or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', owner_id):
            raise ValueError('ZeroFrame mode requires HSUH_SSO_OWNER_ID')
        self.owner_id = owner_id
        self.pending = {}
        self.keys = {}
        self.keys_at = 0
        self.last_fetch = float('-inf')
        self.lock = asyncio.Lock()

    async def _fetch_keys(self):
        async with httpx.AsyncClient(timeout=5, follow_redirects=False) as client:
            response = await client.get(self.issuer + '/.well-known/zf-sso')
            response.raise_for_status()
            if len(response.content) > 65536:
                raise ValueError('Oversized issuer response')
            data = response.json()
        if data.get('issuer') != self.issuer or len(data.get('keys', [])) > 8:
            raise ValueError('Unexpected issuer key set')
        return data['keys']

    async def _key(self, kid):
        async with self.lock:
            now = time.monotonic()
            if (kid not in self.keys or now - self.keys_at > 600) and now - self.last_fetch >= 60:
                self.last_fetch = now
                try:
                    keys = await self._fetch_keys()
                    self.keys = {
                        k['kid']: jwt.PyJWK.from_dict({
                            'kty': 'EC', 'crv': 'P-256', 'x': k['x'], 'y': k['y'],
                        }, algorithm='ES256').key
                        for k in keys if (k.get('kty') == 'EC' and k.get('crv') == 'P-256'
                                          and isinstance(k.get('kid'), str) and 'd' not in k)
                    }
                    self.keys_at = now
                except Exception:
                    # An expired cache cannot keep accepting passes indefinitely.
                    if now - self.keys_at > 600:
                        self.keys = {}
            return self.keys.get(kid)

    async def verify(self, token):
        if not isinstance(token, str) or not 1 <= len(token) <= 16000:
            return None
        try:
            header = jwt.get_unverified_header(token)
            kid = header.get('kid')
            if header.get('alg') != 'ES256' or not isinstance(kid, str) or len(kid) > 128:
                return None
            key = await self._key(kid)
            if key is None:
                return None
            claims = jwt.decode(token, key, algorithms=['ES256'], issuer=self.issuer,
                                audience=self.origin, options={
                                    'require': ['iss', 'aud', 'sub', 'iat', 'exp', 'nonce', 'role'],
                                    'strict_aud': True,
                                })
            if (claims['sub'] != self.owner_id or claims['role'] not in {'user', 'admin'}
                    or type(claims['iat']) is not int or type(claims['exp']) is not int
                    or not 0 < claims['exp'] - claims['iat'] <= 3600
                    or not isinstance(claims['nonce'], str)
                    or not re.fullmatch(r'[A-Za-z0-9_-]{24,128}', claims['nonce'])):
                return None
            return claims
        except Exception:
            return None

    def start(self, next_path='/'):
        now = time.monotonic()
        self.pending = {k: v for k, v in self.pending.items() if v[0] > now}
        if len(self.pending) >= 128:
            return JSONResponse({'detail': 'Too many pending sign-ins; try again shortly'}, status_code=429)
        state = secrets.token_urlsafe(32)
        self.pending[state] = (now + STATE_TTL, local_path(next_path))
        response = RedirectResponse(self.issuer + '/sso?' + urlencode({
            'to': self.origin, 'state': state, 'next': local_path(next_path),
        }), status_code=302, headers={'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer'})
        response.set_cookie(STATE_COOKIE, state, max_age=STATE_TTL, httponly=True,
                            secure=True, samesite='lax', path='/')
        return response

    async def callback(self, scope, headers, receive):
        def denied():
            return JSONResponse({'detail': 'Sign-in refused. Reopen HSUH to try again.'}, status_code=403,
                                headers={'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer'})
        if scope['method'] != 'POST' or headers.get(b'origin') != self.issuer.encode():
            return denied()
        if headers.get(b'content-type', b'').split(b';')[0].strip() != b'application/x-www-form-urlencoded':
            return denied()
        body = bytearray()
        while True:
            part = await receive()
            if part['type'] == 'http.disconnect':
                return denied()
            body.extend(part.get('body', b''))
            if len(body) > 20000:
                return denied()
            if not part.get('more_body'):
                break
        try:
            from urllib.parse import parse_qs
            form = parse_qs(body.decode('utf-8'), max_num_fields=4, strict_parsing=True)
            if any(len(v) != 1 for v in form.values()):
                return denied()
            state = form['state'][0]
            pinned = cookies(headers).get(STATE_COOKIE, '')
            if not pinned or not secrets.compare_digest(state, pinned):
                return denied()
            pending = self.pending.get(state)
            if not pending or pending[0] <= time.monotonic():
                return denied()
            claims = await self.verify(form['token'][0])
            if not claims or not secrets.compare_digest(claims['nonce'], state):
                return denied()
            # Claim after the await: two simultaneous callbacks cannot both succeed.
            if self.pending.pop(state, None) != pending:
                return denied()
        except Exception:
            return denied()
        response = RedirectResponse(pending[1], status_code=303,
                                    headers={'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer'})
        response.set_cookie(PASS_COOKIE, form['token'][0], max_age=max(0, claims['exp'] - int(time.time())),
                            httponly=True, secure=True, samesite='lax', path='/')
        response.delete_cookie(STATE_COOKIE, secure=True, httponly=True, samesite='lax', path='/')
        return response
