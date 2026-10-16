"""Generated-key passkey SSO round trips; no real accounts or provider calls."""
import asyncio
from http.cookies import SimpleCookie
import time
import unittest
from urllib.parse import parse_qs, urlsplit
from unittest.mock import AsyncMock

from cryptography.hazmat.primitives.asymmetric import ec
import httpx
import jwt

from hsuh.app import create_app
from hsuh.sso import PASS_COOKIE, STATE_COOKIE

ORIGIN = 'https://hsuh.example.test'
ISSUER = 'https://login.example.test'


class SSOTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.app = create_app(public_origin=ORIGIN, auth_mode='zeroframe',
                              sso_issuer=ISSUER, sso_owner_id='fixture-owner')
        self.gate = self.app.state.sso
        self.key = ec.generate_private_key(ec.SECP256R1())
        jwk = jwt.algorithms.ECAlgorithm.to_jwk(self.key.public_key(), as_dict=True)
        self.gate._fetch_keys = AsyncMock(return_value=[jwk | {'kid': 'fixture-key'}])
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url=ORIGIN)

    async def asyncTearDown(self):
        await self.client.aclose()

    async def start(self):
        response = await self.client.get('/')
        self.assertEqual(response.status_code, 302)
        url = urlsplit(response.headers['location'])
        self.assertEqual(url.scheme + '://' + url.netloc + url.path, ISSUER + '/sso')
        values = parse_qs(url.query)
        self.assertEqual(values['to'], [ORIGIN])
        self.assertEqual(values['next'], ['/'])
        state = values['state'][0]
        self.assertEqual(self.client.cookies.get(STATE_COOKIE), state)
        self.assertIn('HttpOnly', response.headers['set-cookie'])
        self.assertIn('Secure', response.headers['set-cookie'])
        return state

    def token(self, state, changes=None, key=None):
        now = int(time.time())
        claims = {'iss': ISSUER, 'aud': ORIGIN, 'sub': 'fixture-owner',
                  'iat': now, 'exp': now + 3600, 'role': 'admin', 'nonce': state}
        claims.update(changes or {})
        return jwt.encode(claims, key or self.key, algorithm='ES256', headers={'kid': 'fixture-key'})

    async def callback(self, state, token=None, origin=ISSUER):
        return await self.client.post('/sso/callback', data={
            'token': token or self.token(state), 'state': state, 'next': 'https://evil.example.test',
        }, headers={'Origin': origin})

    async def test_complete_login_then_same_origin_api_and_renewal(self):
        state = await self.start()
        response = await self.callback(state)
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers['location'], '/')
        self.assertIsNone(self.client.cookies.get(STATE_COOKIE))
        self.assertTrue(self.client.cookies.get(PASS_COOKIE))
        self.assertEqual((await self.client.get('/')).status_code, 200)
        status = await self.client.get('/api/status')
        self.assertEqual(status.status_code, 200)
        self.assertEqual(status.json()['access'], 'ZeroFrame passkey')
        self.assertEqual((await self.client.post('/api/chats', json={}, headers={
            'Origin': ORIGIN, 'X-HSUH-Request': '1',
        })).status_code, 200)
        self.assertEqual((await self.client.post('/api/chats', json={}, headers={
            'Origin': ISSUER, 'X-HSUH-Request': '1',
        })).status_code, 403)
        self.gate._fetch_keys.assert_awaited_once()

    async def test_anonymous_assets_and_apis_and_forged_access_headers_are_denied(self):
        for path in ['/api/status', '/api/chats', '/api/telemetry', '/api/quota', '/api/activity',
                     '/assets/app.js', '/assets/openui.js', '/assets/stats.css', '/manifest.webmanifest', '/sw.js']:
            response = await self.client.get(path, headers={'Cf-Access-Jwt-Assertion': 'forged'})
            self.assertEqual(response.status_code, 401, path)
        self.assertEqual((await self.client.get('/', headers={'Host': '127.0.0.1:8110'})).status_code, 400)
        self.assertEqual((await self.client.post('/api/chats', json={})).status_code, 401)

    async def test_wrong_owner_signature_issuer_audience_expiry_and_role(self):
        state = await self.start()
        bad = [{'sub': 'another-owner'}, {'iss': 'https://evil.example.test'},
               {'aud': 'https://another.example.test'}, {'aud': [ORIGIN]},
               {'exp': int(time.time()) - 1}, {'iat': int(time.time()) + 30},
               {'exp': int(time.time()) + 7200}, {'role': 'guest'}, {'nonce': 'x' * 32},
               {'exp': str(int(time.time()) + 3600)}]
        for change in bad:
            response = await self.callback(state, self.token(state, change))
            self.assertEqual(response.status_code, 403, str(change))
        foreign = ec.generate_private_key(ec.SECP256R1())
        self.assertEqual((await self.callback(state, self.token(state, key=foreign))).status_code, 403)
        unsigned = jwt.encode({'sub': 'fixture-owner'}, '', algorithm='none')
        self.assertEqual((await self.callback(state, unsigned)).status_code, 403)
        self.assertIsNone(self.client.cookies.get(PASS_COOKIE))

    async def test_browser_binding_cross_origin_expired_state_and_replay(self):
        state = await self.start()
        self.assertEqual((await self.callback(state, origin='https://evil.example.test')).status_code, 403)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url=ORIGIN) as stranger:
            response = await stranger.post('/sso/callback', data={'state': state, 'token': self.token(state)},
                                           headers={'Origin': ISSUER})
            self.assertEqual(response.status_code, 403)
        self.gate.pending[state] = (time.monotonic() - 1, '/')
        self.assertEqual((await self.callback(state)).status_code, 403)
        state = await self.start()
        token = self.token(state)
        self.assertEqual((await self.callback(state, token)).status_code, 303)
        self.client.cookies.set(STATE_COOKIE, state, domain='hsuh.example.test', path='/')
        self.assertEqual((await self.callback(state, token)).status_code, 403)

    async def test_expired_pass_protects_every_request_and_navigation_restarts_login(self):
        state = await self.start()
        self.assertEqual((await self.callback(state)).status_code, 303)
        await self.client.get('/')
        expired = self.token(state, {'iat': int(time.time()) - 60, 'exp': int(time.time()) - 1})
        self.client.cookies.set(PASS_COOKIE, expired, domain='hsuh.example.test', path='/')
        self.assertEqual((await self.client.get('/api/status')).status_code, 401)
        self.assertEqual((await self.client.get('/')).status_code, 302)

    async def test_unavailable_key_server_and_unknown_kid_fail_closed_and_are_throttled(self):
        self.gate._fetch_keys.side_effect = httpx.ConnectError('fixture unavailable')
        state = await self.start()
        for _ in range(3):
            self.assertEqual((await self.callback(state)).status_code, 403)
        self.gate._fetch_keys.assert_awaited_once()

    async def test_callback_body_bounds_content_type_duplicate_fields_and_get(self):
        self.assertEqual((await self.client.get('/sso/callback')).status_code, 403)
        for body, content_type in [('x' * 20001, 'application/x-www-form-urlencoded'),
                                   ('state=a&state=b', 'application/x-www-form-urlencoded'),
                                   ('{}', 'application/json')]:
            response = await self.client.post('/sso/callback', content=body,
                headers={'Origin': ISSUER, 'Content-Type': content_type})
            self.assertEqual(response.status_code, 403)

    async def test_simultaneous_callback_is_consumed_once(self):
        state = await self.start()
        responses = await asyncio.gather(self.callback(state), self.callback(state))
        self.assertEqual(sorted(r.status_code for r in responses), [303, 403])

    def test_configuration_is_explicit_and_never_falls_back_to_loopback(self):
        for values in [{}, {'sso_issuer': ISSUER},
                       {'sso_issuer': ISSUER, 'sso_owner_id': '*'},
                       {'sso_issuer': 'http://login.example.test', 'sso_owner_id': 'fixture-owner'}]:
            with self.assertRaises(ValueError):
                create_app(auth_mode='zeroframe', public_origin=ORIGIN, **values)
        with self.assertRaises(ValueError):
            create_app(auth_mode='zeroframe', sso_issuer=ISSUER, sso_owner_id='fixture-owner')


if __name__ == '__main__':
    unittest.main()
