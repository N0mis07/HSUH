import unittest
from unittest.mock import patch
import httpx


class PublicTests(unittest.IsolatedAsyncioTestCase):
    async def test_public_mode_refuses_missing_access_configuration(self):
        from hsuh.app import create_app
        with self.assertRaises(ValueError):
            create_app(public_origin='https://hsuh.example.test')

    async def test_public_requests_require_validated_access_assertion(self):
        from hsuh.app import create_app
        app = create_app(public_origin='https://hsuh.example.test', access_team='fixture-team', access_audience='fixture-audience', owner_email='owner@example.test')
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='https://hsuh.example.test') as client:
            for path in ['/', '/api/telemetry', '/api/chats', '/api/quota']:
                self.assertEqual((await client.get(path)).status_code, 401)
                self.assertEqual((await client.get(path, headers={'Cf-Access-Jwt-Assertion':'not-a-real-jwt'})).status_code, 401)

    async def test_manifest_and_worker_do_not_cache_conversations(self):
        from hsuh.app import create_app
        app = create_app()
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://127.0.0.1:8110') as client:
            r = await client.get('/manifest.webmanifest')
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.json()['display'], 'standalone')
            r = await client.get('/sw.js')
            self.assertEqual(r.status_code, 200)
            self.assertNotIn('cache.put', r.text)
            self.assertNotIn('addAll', r.text)


class QuotaTests(unittest.TestCase):
    def test_quota_projection_keeps_only_numeric_limits_and_provenance(self):
        from hsuh.quota import native_projection
        d = native_projection({'provider':'openai-codex','source':'usage_api','fetched_at':'fixture-time',
              'plan':'Pro','windows':[{'label':'Weekly','used_percent':26.0,'resets_at':'fixture-reset'}],
              'details':['private text'], 'token':'fictional-secret'})
        self.assertEqual(d['windows'][0]['used_percent'], 26)
        self.assertNotIn('details', d)
        self.assertNotIn('token', d)
        self.assertEqual(d['fetched_at'], 'fixture-time')


if __name__ == '__main__':
    unittest.main()
