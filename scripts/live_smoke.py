"""Opt-in real integration: uses the configured Hermes provider. No mock answers."""
import asyncio
import json
import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hsuh.chat import ChatManager


async def until(manager, cid, states, timeout=100):
    end = time.monotonic()+timeout
    while time.monotonic() < end:
        c = manager.get(cid)
        if c['task']['state'] in states:
            return c
        await asyncio.sleep(.25)
    raise TimeoutError('Integration probe timed out')


async def main():
    m = ChatManager()
    try:
        a,b = m.create(),m.create()
        m.submit(a['id'], 'Use clarify now to ask which fictional name I prefer: Cedar or Birch. After the answer reply exactly with the chosen name. No other tools.')
        question = await until(m,a['id'],{'pending_input','failed'})
        assert question['task']['state']=='pending_input', question['task']['summary']
        m.submit(b['id'], 'Reply exactly HSUH_INDEPENDENT_OK. No tools.')
        second = await until(m,b['id'],{'completed','failed'})
        assert second['task']['state']=='completed', second['task']['summary']
        assert second['messages'][-1]['content'].strip()=='HSUH_INDEPENDENT_OK'
        assert m.get(a['id'])['task']['state']=='pending_input'
        q=question['question']
        assert len(q['questions'])==1
        await m.answer(a['id'],q['id'],{q['questions'][0]['qid']:'Birch'})
        first = await until(m,a['id'],{'completed','failed'})
        assert first['task']['state']=='completed', first['task']['summary']
        assert first['messages'][-1]['content'].strip()=='Birch'
        m.submit(a['id'], 'What fictional name did I choose? Reply with only that name. No tools.')
        recalled = await until(m,a['id'],{'completed','failed'})
        assert recalled['task']['state']=='completed', recalled['task']['summary']
        assert recalled['messages'][-1]['content'].strip()=='Birch'
        assert [i['role'] for i in m.chats[a['id']]['history']]==['user','assistant','user','assistant']
        print(json.dumps({'passed':True,'independent_concurrent_turn':True,'native_question_card':True,
                          'clarification_answer':'Birch','multi_turn_recall':'Birch','model':m.model,
                          'scope':'Documented AIAgent library; native clarify only'},indent=2))
    finally:
        await m.shutdown()


if __name__=='__main__':
    asyncio.run(main())
