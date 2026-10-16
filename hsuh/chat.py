"""Conversation-owned jobs. UI polling is independent of worker lifetime."""
import asyncio
import copy
import json
import os
from pathlib import Path
import signal
import sys
import time
import uuid

from fastapi import HTTPException

BUSY = {'queued', 'running', 'pending_input'}


class ChatManager:
    def __init__(self):
        self.chats = {}
        self.work = {}
        self.processes = {}
        self.slots = asyncio.Semaphore(2)
        self.model = None

    @property
    def active_count(self):
        return sum(c['task'] is not None and c['task']['state'] in BUSY for c in self.chats.values())

    def create(self):
        if len(self.chats) >= 40:
            raise HTTPException(409, '40-chat memory limit; delete a conversation first')
        c = {'id':uuid.uuid4().hex, 'title':'New conversation', 'created_at':time.time(),
             'messages':[], 'history':[], 'pending_clarifications':[], 'tasks':[], 'task':None, 'question':None, 'revision':0}
        self.chats[c['id']] = c
        return self.get(c['id'])

    def _find(self, chat_id):
        if chat_id not in self.chats:
            raise HTTPException(404, 'Conversation not found')
        return self.chats[chat_id]

    def get(self, chat_id):
        return copy.deepcopy({k:v for k,v in self._find(chat_id).items() if k not in {'history','pending_clarifications'}})

    def list(self):
        return [{'id':c['id'], 'title':c['title'], 'task':copy.deepcopy(c['task']), 'revision':c['revision']}
                for c in self.chats.values()]

    def submit(self, chat_id, message):
        c = self._find(chat_id)
        text = message.strip()
        if not text:
            raise HTTPException(422, 'Message is empty')
        if c['task'] and c['task']['state'] in BUSY:
            raise HTTPException(409, 'This conversation already has an active turn')
        if len(c['tasks']) >= 30:
            raise HTTPException(409, '30-turn limit; start a new conversation')
        task = {'id':uuid.uuid4().hex, 'label':' '.join(text.split())[:72], 'state':'queued',
                'created_at':time.time(), 'started_at':None, 'ended_at':None, 'summary':'Waiting for a worker', 'result_message_id':None}
        c['task'] = task
        c['pending_clarifications'] = []
        c['tasks'].append(task)
        c['messages'].append({'id':uuid.uuid4().hex, 'role':'user', 'content':text, 'at':time.time()})
        if len(c['tasks']) == 1:
            c['title'] = ' '.join(text.split())[:52]
        c['revision'] += 1
        self.work[chat_id] = asyncio.create_task(self._run(c, text))
        return self.get(chat_id)

    async def _run(self, c, message):
        p = None
        task = c['task']
        try:
            async with self.slots:
                task.update(state='running', started_at=time.time(), summary='Starting Hermes')
                c['revision'] += 1
                # Never inherit a parent's subagent/session identity or model overrides.
                env = {k:v for k,v in os.environ.items() if not k.startswith('HERMES_')}
                env['HERMES_HOME'] = str(Path.home() / '.hermes')
                root = Path(os.environ.get('HSUH_HERMES_ROOT', str(Path.home()/'.hermes/hermes-agent'))).resolve()
                env['HSUH_HERMES_ROOT'] = str(root)
                p = await asyncio.create_subprocess_exec(sys.executable, str(Path(__file__).with_name('worker.py')),
                    stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
                    env=env, cwd=str(Path(__file__).parent.parent), start_new_session=True, limit=1048576)
                self.processes[c['id']] = p
                if p.stdin is None or p.stdout is None:
                    raise RuntimeError('Worker pipes are unavailable')
                p.stdin.write((json.dumps({'message':message, 'history':c['history']})+'\n').encode())
                await p.stdin.drain()
                async with asyncio.timeout(240):
                    while line := await p.stdout.readline():
                        event = json.loads(line)
                        kind = event.get('type')
                        if kind == 'ready':
                            self.model = {'model':event['model'], 'provider':event['provider'], 'reasoning_effort':event['reasoning_effort']}
                            task.update(summary='Hermes is responding')
                        elif kind == 'question':
                            c['question'] = {'id':uuid.uuid4().hex, 'questions':event['questions']}
                            task.update(state='pending_input', summary='Waiting for your answer')
                        elif kind == 'final':
                            content = event.get('content')
                            if not isinstance(content, str) or not content.strip() or len(content) > 100000:
                                raise ValueError('Invalid final response')
                            msg = {'id':uuid.uuid4().hex, 'role':'assistant', 'content':content, 'at':time.time()}
                            c['messages'].append(msg)
                            # No reasoning/tool results in HSUH history. Clarification text is included as user input.
                            context = message
                            if c['pending_clarifications']:
                                context += '\n\nClarifications supplied during this turn:\n' + '\n'.join(c['pending_clarifications'])
                            c['history'].extend([{'role':'user','content':context}, {'role':'assistant','content':content}])
                            task.update(state='completed', summary='Response received', result_message_id=msg['id'], ended_at=time.time())
                        elif kind == 'error':
                            raise RuntimeError('Hermes worker failed')
                        else:
                            raise ValueError('Unknown worker event')
                        c['revision'] += 1
                    await p.wait()
                    if task['state'] != 'completed' or p.returncode != 0:
                        raise RuntimeError('Worker ended without a successful response')
        except asyncio.CancelledError:
            task.update(state='cancelled', summary='Stopped by you', ended_at=time.time())
            raise
        except TimeoutError:
            task.update(state='failed', summary='Turn exceeded the 240-second limit. No response was fabricated.', ended_at=time.time())
        except Exception:
            # Never return arbitrary SDK exception bodies, paths or credentials to a browser/log.
            task.update(state='failed', summary='Hermes did not complete this turn. Check native provider sign-in and compatibility; no response was fabricated.', ended_at=time.time())
        finally:
            c['question'] = None
            c['revision'] += 1
            if p is not None:
                if p.returncode is None:
                    try:
                        os.killpg(p.pid, signal.SIGTERM)
                        await asyncio.wait_for(p.wait(), 3)
                    except (ProcessLookupError, TimeoutError):
                        if p.returncode is None:
                            os.killpg(p.pid, signal.SIGKILL)
                            await p.wait()
                if p.stdin:
                    p.stdin.close()
            self.processes.pop(c['id'], None)

    async def answer(self, chat_id, question_id, answers):
        c = self._find(chat_id)
        question = c['question']
        if not question or question['id'] != question_id or c['task']['state'] != 'pending_input':
            raise HTTPException(409, 'Question is no longer pending')
        expected = {q['qid'] for q in question['questions']}
        if set(answers) != expected or len(json.dumps(answers)) > 12000:
            raise HTTPException(422, 'Answer every displayed question; max 12,000 characters')
        p = self.processes.get(chat_id)
        if p is None or p.returncode is not None or p.stdin is None:
            raise HTTPException(409, 'Worker is no longer available')
        # Claim the one-use question before the first await; simultaneous requests cannot answer twice.
        c['question'] = None
        c['task'].update(state='running', summary='Sending your answer to Hermes')
        c['revision'] += 1
        # Preserve input before yielding: a very fast worker can finish while drain is pending.
        text = '\n'.join(f"{q['question']} {answers[q['qid']]}" for q in question['questions'])
        c['messages'].append({'id':uuid.uuid4().hex, 'role':'user', 'content':'Clarification: '+text, 'at':time.time()})
        c['pending_clarifications'].append(text)
        p.stdin.write((json.dumps({'answers':answers,'outcome':'submitted'})+'\n').encode())
        await p.stdin.drain()
        # Do not overwrite a completed/failed or newly pending-input state after the await.
        return self.get(chat_id)

    async def stop(self, chat_id):
        c = self._find(chat_id)
        task = self.work.get(chat_id)
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        if c['task'] and c['task']['state'] in BUSY:
            c['task'].update(state='cancelled', summary='Stopped by you', ended_at=time.time())
            c['question'] = None
            c['revision'] += 1

    async def delete(self, chat_id):
        await self.stop(chat_id)
        self.chats.pop(chat_id, None)
        self.work.pop(chat_id, None)

    async def shutdown(self):
        await asyncio.gather(*(self.stop(cid) for cid in tuple(self.chats)))
