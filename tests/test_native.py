import tempfile
import unittest
from pathlib import Path

from fastapi import HTTPException

from hsuh.native import NativeManager


class Gateway:
    def __init__(self):
        self.calls = []
        self.runs = {}
        self.fail_accept = False

    async def request(self, method, path, body=None, key=None):
        self.calls.append((method, path, body, key))
        if path == '/api/sessions':
            return {'session': {'id': body['id']}}
        if '/messages?' in path:
            return {'data': [{'id': 7, 'role': 'assistant', 'content': 'Safe answer',
                              'reasoning': 'private reasoning', 'timestamp': 10}], 'session_id': path.split('/')[3]}
        if path.startswith('/api/sessions/'):
            return {'session': {'id': path.split('/')[3], 'title': 'Existing conversation', 'source': 'telegram'}}
        if path == '/v1/runs':
            run = self.runs.setdefault(key, {'run_id': 'run_'+key, 'status': 'running', 'session_id': body['session_id']})
            if self.fail_accept:
                self.fail_accept = False
                raise HTTPException(503, 'Gateway unavailable')
            return run
        if path.startswith('/v1/runs/'):
            run_id = path.split('/')[3]
            run = next(r for r in self.runs.values() if r['run_id'] == run_id)
            if path.endswith('/stop'):
                run['status'] = 'stopping'
            if path.endswith('/approval'):
                run['status'] = 'running'
            return run
        raise AssertionError(path)

    async def close(self):
        pass

    async def events(self, run_id, after):
        if False:
            yield {}


class NativeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.gateway = Gateway()
        self.path = Path(self.tmp.name)/'control.sqlite3'
        self.manager = NativeManager(self.gateway, self.path, watch=False)

    async def asyncTearDown(self):
        await self.manager.shutdown()
        self.tmp.cleanup()

    async def test_lost_admission_replays_same_key_after_restart(self):
        chat = await self.manager.create()
        self.gateway.fail_accept = True
        await self.manager.submit(chat['id'], 'Read a test file', 'request-1')
        await self.manager.shutdown()
        self.manager = NativeManager(self.gateway, self.path, watch=False)
        chat = await self.manager.get(chat['id'])
        admissions = [c for c in self.gateway.calls if c[1] == '/v1/runs']
        self.assertEqual(len(self.gateway.runs), 1)
        self.assertEqual(admissions[0][3], admissions[1][3])
        self.assertEqual(chat['task']['state'], 'running')
        self.assertNotIn('private reasoning', str(chat))

    async def test_stop_is_bound_to_exact_run_and_waits_for_native_settlement(self):
        chat = await self.manager.create()
        first = await self.manager.submit(chat['id'], 'Harmless work', 'request-1')
        await self.manager.stop(chat['id'], first['task']['id'])
        chat = await self.manager.get(chat['id'])
        self.assertEqual(chat['task']['state'], 'stopping')
        with self.assertRaises(HTTPException):
            await self.manager.submit(chat['id'], 'Another turn', 'request-2')
        native = next(iter(self.gateway.runs.values()))
        native['status'] = 'cancelled'
        await self.manager.get(chat['id'])
        second = await self.manager.submit(chat['id'], 'Another turn', 'request-2')
        with self.assertRaises(HTTPException):
            await self.manager.stop(chat['id'], first['task']['id'])
        self.assertNotEqual(first['task']['id'], second['task']['id'])

    async def test_approvals_require_exact_pending_request(self):
        chat = await self.manager.create()
        chat = await self.manager.submit(chat['id'], 'Harmless work', 'request-1')
        native = next(iter(self.gateway.runs.values()))
        native.update(status='waiting_for_approval', approval={
            'request_id':'approval-1', 'command':'test operation', 'choices':['once','deny']})
        chat = await self.manager.get(chat['id'])
        for request, choice in [('older','once'), ('approval-1','always')]:
            with self.assertRaises(HTTPException):
                await self.manager.approve(chat['id'], chat['task']['id'], request, choice)
        await self.manager.approve(chat['id'], chat['task']['id'], 'approval-1', 'once')
        calls = [c for c in self.gateway.calls if c[1].endswith('/approval')]
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][2], {'request_id':'approval-1','choice':'once'})

    async def test_events_drop_reasoning_and_tool_arguments(self):
        chat = await self.manager.create()
        chat = await self.manager.submit(chat['id'], 'Harmless work', 'request-1')
        task = chat['task']['id']
        self.manager.record_event(task, {'event':'reasoning.available','text':'private'})
        self.manager.record_event(task, {'seq':1,'event':'tool.started','tool':'terminal','preview':'secret arguments'})
        chat = await self.manager.get(chat['id'])
        self.assertEqual(chat['task']['events'][0]['tool'], 'terminal')
        self.assertNotIn('secret arguments', str(chat))
        self.assertNotIn('private', str(chat))

    async def test_repeated_submission_is_idempotent_but_changed_payload_conflicts(self):
        chat = await self.manager.create()
        a = await self.manager.submit(chat['id'], 'Harmless work', 'request-1')
        b = await self.manager.submit(chat['id'], 'Harmless work', 'request-1')
        self.assertEqual(a['task']['id'], b['task']['id'])
        with self.assertRaises(HTTPException):
            await self.manager.submit(chat['id'], 'Changed work', 'request-1')
        self.assertEqual(len(self.gateway.runs), 1)

    async def test_list_never_exports_outbox_or_internal_submission_fields(self):
        chat = await self.manager.create()
        self.gateway.fail_accept = True
        self.gateway.request_original = self.gateway.request
        async def unavailable(method, path, body=None, key=None):
            if path == '/v1/runs':
                raise HTTPException(503, 'Unavailable')
            return await self.gateway.request_original(method,path,body,key)
        self.gateway.request = unavailable
        await self.manager.submit(chat['id'], 'Private pending message', 'request-1')
        listing = str(await self.manager.list())
        for internal in ('outbox', 'instructions', 'request_key', 'fingerprint'):
            self.assertNotIn(internal, listing)

    async def test_native_controls_keep_cookie_origin_and_body_guards(self):
        from unittest.mock import patch
        import httpx
        from hsuh.app import create_app
        with patch.dict('os.environ', {'HSUH_NATIVE_CONTROL':'1'}), patch('hsuh.native.NativeManager', return_value=self.manager):
            app = create_app()
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://127.0.0.1:8110') as client:
            self.assertEqual((await client.get('/api/control')).status_code, 401)
            await client.get('/')
            self.assertEqual((await client.post('/api/sessions/open',json={'session_id':'existing'})).status_code, 403)
            headers={'Origin':'http://127.0.0.1:8110','X-HSUH-Request':'1'}
            chat=(await client.post('/api/chats',json={},headers=headers)).json()
            chat=(await client.post('/api/chats/'+chat['id']+'/messages', json={'message':'Test native tools','request_id':'r1'},headers=headers)).json()
            self.assertTrue(chat['native'])
            self.assertEqual((await client.post('/api/chats/'+chat['id']+'/stop',json={'task_id':'stale'},headers=headers)).status_code,409)
            self.assertEqual((await client.post('/api/chats/'+chat['id']+'/approval',json={'task_id':chat['task']['id'],'request_id':'x','choice':'always'},headers=headers)).status_code,422)
            self.assertFalse((await client.get('/api/status')).json()['credentials']['enabled'])
