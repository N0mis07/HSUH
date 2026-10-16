import asyncio
import unittest

import httpx


class AppTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from hsuh.app import create_app
        self.app = create_app()
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url='http://127.0.0.1:8110')
        await self.client.get('/')
        self.headers = {'Origin': 'http://127.0.0.1:8110', 'X-HSUH-Request': '1'}

    async def asyncTearDown(self):
        await self.client.aclose()

    async def test_live_memory_has_honest_units_and_no_command_lines(self):
        r = await self.client.get('/api/telemetry')
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertGreater(d['memory']['total'], 0)
        self.assertEqual(d['memory']['used'], d['memory']['total'] - d['memory']['available'])
        self.assertEqual(d['memory']['unit'], 'bytes')
        self.assertTrue(d['processes'])
        self.assertNotIn('cmdline', str(d))

    async def test_cross_origin_and_wrong_host_are_denied(self):
        self.assertEqual((await self.client.post('/api/chats', json={}, headers={'Origin':'https://evil.test', 'X-HSUH-Request':'1'})).status_code, 403)
        self.assertEqual((await self.client.get('/api/telemetry', headers={'Host':'evil.test'})).status_code, 400)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url='http://127.0.0.1:8110') as stranger:
            self.assertEqual((await stranger.get('/api/chats')).status_code, 401)

    async def test_credential_submission_fails_closed(self):
        r = await self.client.post('/api/credentials', json={'password':'fictional-test-only'}, headers=self.headers)
        self.assertEqual(r.status_code, 501)
        self.assertFalse((await self.client.get('/api/status')).json()['credentials']['enabled'])

    async def test_chat_ids_are_server_owned_and_isolated(self):
        a = (await self.client.post('/api/chats', json={}, headers=self.headers)).json()
        b = (await self.client.post('/api/chats', json={}, headers=self.headers)).json()
        self.assertNotEqual(a['id'], b['id'])
        self.assertEqual((await self.client.get('/api/chats/'+a['id'])).json()['messages'], [])
        self.assertEqual((await self.client.get('/api/chats/../../etc/passwd')).status_code, 404)

    async def test_body_bound_and_sensitive_fields_rejected(self):
        r = await self.client.post('/api/chats', content='x'*70000, headers=self.headers)
        self.assertEqual(r.status_code, 413)
        a = (await self.client.post('/api/chats', json={}, headers=self.headers)).json()
        r = await self.client.post('/api/chats/'+a['id']+'/messages', json={'message':'hello','password':'not-real'}, headers=self.headers)
        self.assertEqual(r.status_code, 422)


if __name__ == '__main__':
    unittest.main()
