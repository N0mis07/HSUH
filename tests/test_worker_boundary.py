import asyncio
import unittest
from unittest.mock import patch


class WorkerBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_native_runtime_fails_without_an_assistant_message(self):
        from hsuh.chat import ChatManager
        m = ChatManager()
        c = m.create()
        try:
            with patch.dict('os.environ', {'HSUH_HERMES_ROOT':'/nonexistent-hsuh-fixture-root'}):
                m.submit(c['id'], 'This is a fictional fixture; do not call a provider.')
                await asyncio.wait_for(m.work[c['id']], 5)
            state = m.get(c['id'])
            self.assertEqual(state['task']['state'], 'failed')
            self.assertEqual([i['role'] for i in state['messages']], ['user'])
            self.assertIn('no response was fabricated', state['task']['summary'])
            self.assertNotIn(c['id'], m.processes)
        finally:
            await m.shutdown()

    async def test_real_process_group_is_stopped_without_provider_access(self):
        from hsuh.chat import ChatManager
        m = ChatManager()
        c = m.create()
        spawned = asyncio.Event()
        original = asyncio.create_subprocess_exec
        async def slow_worker(*args, **kwargs):
            # Replace only the external runtime boundary with a real sleeping OS process.
            import sys
            p = await original(sys.executable, '-c', 'import time; time.sleep(60)',
                               stdin=kwargs['stdin'], stdout=kwargs['stdout'], stderr=kwargs['stderr'], start_new_session=True)
            spawned.set()
            return p
        try:
            with patch('asyncio.create_subprocess_exec', slow_worker):
                m.submit(c['id'], 'Fictional cancellation fixture')
                await asyncio.wait_for(spawned.wait(), 5)
                await asyncio.sleep(.02)
                p = m.processes[c['id']]
                await asyncio.wait_for(m.stop(c['id']), 5)
                self.assertIsNotNone(p.returncode)
                self.assertEqual(m.get(c['id'])['task']['state'], 'cancelled')
                self.assertEqual(len(m.get(c['id'])['messages']), 1)
        finally:
            await m.shutdown()


if __name__=='__main__':
    unittest.main()
