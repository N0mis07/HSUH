import asyncio
import unittest
from unittest.mock import patch


class ChatTests(unittest.IsolatedAsyncioTestCase):
    async def test_new_chat_tasks_remain_attached_when_switching(self):
        from hsuh.chat import ChatManager
        m = ChatManager()
        a, b = m.create(), m.create()
        async def bounded_wait(chat, message, task):
            await asyncio.sleep(10)
        with patch.object(m, '_run', bounded_wait):
            m.submit(a['id'], 'Explain event loops')
            self.assertEqual(m.get(a['id'])['task']['state'], 'queued')
            self.assertIsNone(m.get(b['id'])['task'])
            self.assertEqual(m.list()[0]['id'], a['id'])
            await m.stop(a['id'])
            self.assertEqual(m.get(a['id'])['task']['state'], 'cancelled')
        await m.shutdown()

    async def test_duplicate_turn_and_unknown_chat_fail_closed(self):
        from hsuh.chat import ChatManager
        from fastapi import HTTPException
        m = ChatManager()
        a = m.create()
        with patch.object(m, '_run', lambda *args: asyncio.sleep(10)):
            m.submit(a['id'], 'Hello')
            with self.assertRaises(HTTPException) as e:
                m.submit(a['id'], 'Again')
            self.assertEqual(e.exception.status_code, 409)
            with self.assertRaises(HTTPException):
                m.get('not-an-id')
            await m.shutdown()


if __name__ == '__main__':
    unittest.main()
