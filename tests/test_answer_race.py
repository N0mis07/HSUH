import asyncio
import unittest
from types import SimpleNamespace
from fastapi import HTTPException


class AnswerRaceTests(unittest.IsolatedAsyncioTestCase):
    async def test_late_pipe_drain_does_not_overwrite_a_terminal_state(self):
        from hsuh.chat import ChatManager
        m=ChatManager()
        chat=m.create()
        c=m.chats[chat['id']]
        c['task']={'state':'pending_input'}
        c['question']={'id':'fixture-question','questions':[{'qid':'q0','question':'Name?'}]}
        async def drain():
            c['task']['state']='completed'
        m.processes[c['id']]=SimpleNamespace(returncode=None, stdin=SimpleNamespace(write=lambda _:None,drain=drain))
        result=await m.answer(c['id'],'fixture-question',{'q0':'Birch'})
        self.assertEqual(result['task']['state'],'completed')

    async def test_question_is_claimed_before_slow_pipe_drain(self):
        from hsuh.chat import ChatManager
        m=ChatManager()
        chat=m.create()
        c=m.chats[chat['id']]
        c['task']={'state':'pending_input'}
        c['question']={'id':'fixture-question','questions':[{'qid':'q0','question':'Choose a fictional name'}]}
        waiting=asyncio.Event()
        release=asyncio.Event()
        writes=[]
        async def drain():
            waiting.set()
            await release.wait()
        p=SimpleNamespace(returncode=None, stdin=SimpleNamespace(write=writes.append,drain=drain))
        m.processes[c['id']]=p
        first=asyncio.create_task(m.answer(c['id'],'fixture-question',{'q0':'Birch'}))
        try:
            await asyncio.wait_for(waiting.wait(),1)
            with self.assertRaises(HTTPException) as e:
                # Do not await a hung drain on a duplicate: the question must already be consumed.
                await asyncio.wait_for(m.answer(c['id'],'fixture-question',{'q0':'Cedar'}),.2)
            self.assertEqual(e.exception.status_code,409)
            self.assertEqual(len(writes),1)
        finally:
            release.set()
            await first


if __name__=='__main__':
    unittest.main()
