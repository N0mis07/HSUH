"""Conversation-owned jobs. UI polling is independent of worker lifetime."""
import asyncio
import copy
import json
import os
from pathlib import Path
import signal
import sys
import tempfile
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
        if (c['task'] and c['task']['state'] in BUSY) or (chat_id in self.work and not self.work[chat_id].done()):
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
        self.work[chat_id] = asyncio.create_task(self._run(c, text, task))
        return self.get(chat_id)

    async def _run(self, c, message, task):
        # Capture ownership at submission, never from mutable c['task'] after an await.
        p = None
        diagnostics = None
        acquired = False
        content = None
        outcome = {'state':'failed', 'summary':'Hermes did not complete this turn. Check native provider sign-in and compatibility; no response was fabricated.'}
        try:
            await self.slots.acquire()
            acquired = True
            task.update(state='running', started_at=time.time(), summary='Starting Hermes')
            c['revision'] += 1
            # Queue time is excluded; one deadline covers startup, pipes, input waits and exit.
            async with asyncio.timeout(240):
                # Never inherit a parent's subagent/session identity or model overrides.
                env = {k:v for k,v in os.environ.items() if not k.startswith('HERMES_')}
                env['HERMES_HOME'] = str(Path.home() / '.hermes')
                root = Path(os.environ.get('HSUH_HERMES_ROOT', str(Path.home()/'.hermes/hermes-agent'))).resolve()
                env['HSUH_HERMES_ROOT'] = str(root)
                # Parent owns disposal even when the worker must be killed. No profile edits.
                diagnostics = tempfile.TemporaryDirectory(prefix='hsuh-diagnostics-')
                env['HSUH_DIAGNOSTICS_DIR'] = diagnostics.name
                p = await asyncio.create_subprocess_exec(sys.executable, str(Path(__file__).with_name('worker.py')),
                    stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
                    env=env, cwd=str(Path(__file__).parent.parent), start_new_session=True, limit=1048576)
                self.processes[c['id']] = p
                if p.stdin is None or p.stdout is None:
                    raise RuntimeError('Worker pipes are unavailable')
                p.stdin.write((json.dumps({'message':message, 'history':c['history']})+'\n').encode())
                await p.stdin.drain()
                while line := await p.stdout.readline():
                    event = json.loads(line)
                    if content is not None:
                        raise ValueError('Worker event after final response')
                    kind = event.get('type')
                    if kind == 'ready':
                        self.model = {'model':event['model'], 'provider':event['provider'], 'reasoning_effort':event['reasoning_effort']}
                        task.update(summary='Hermes is responding')
                    elif kind == 'question':
                        if c['question'] is not None:
                            raise ValueError('Worker already has a pending question')
                        c['question'] = {'id':uuid.uuid4().hex, 'questions':event['questions']}
                        task.update(state='pending_input', summary='Waiting for your answer')
                    elif kind == 'final':
                        content = event.get('content')
                        if c['question'] is not None or not isinstance(content, str) or not content.strip() or len(content) > 100000:
                            raise ValueError('Invalid final response')
                        # A final is provisional until EOF, clean exit and teardown.
                        task.update(summary='Finishing Hermes worker')
                    elif kind == 'error':
                        raise RuntimeError('Hermes worker failed')
                    else:
                        raise ValueError('Unknown worker event')
                    c['revision'] += 1
                await p.wait()
                if content is None or p.returncode != 0:
                    raise RuntimeError('Worker ended without a successful response')
                outcome = {'state':'completed', 'summary':'Response received'}
        except asyncio.CancelledError:
            outcome = {'state':'cancelled', 'summary':'Stopped by you'}
            raise
        except TimeoutError:
            outcome = {'state':'failed', 'summary':'Turn exceeded the 240-second limit. No response was fabricated.'}
        except Exception:
            # Never return arbitrary SDK exception bodies, paths or credentials to a browser/log.
            outcome.update(state='failed')
        finally:
            # Reaping has its own task: Stop may arrive after an error/timeout has
            # already entered finally. Repeated cancellation must not abandon it.
            async def reap():
                if p is not None:
                    if p.returncode is None:
                        try:
                            os.killpg(p.pid, signal.SIGTERM)
                            await asyncio.wait_for(p.wait(), 3)
                        except (ProcessLookupError, TimeoutError):
                            if p.returncode is None:
                                try:
                                    os.killpg(p.pid, signal.SIGKILL)
                                except ProcessLookupError:
                                    pass
                                await p.wait()
                    if p.stdin:
                        p.stdin.close()

            cleanup = asyncio.create_task(reap())
            cleanup_cancelled = False
            while not cleanup.done():
                try:
                    await asyncio.shield(cleanup)
                except asyncio.CancelledError:
                    cleanup_cancelled = True
                    outcome = {'state':'cancelled', 'summary':'Stopped by you'}
            cleanup.result()
            # Keep the turn busy and its slot owned until reaping actually ends.
            if self.processes.get(c['id']) is p:
                self.processes.pop(c['id'], None)
            if self.work.get(c['id']) is asyncio.current_task():
                self.work.pop(c['id'], None)
            if diagnostics is not None:
                diagnostics.cleanup()
            if acquired:
                self.slots.release()
            # No awaits between ownership check, transcript commit and releasing busy state.
            if self.chats.get(c['id']) is c and c['task'] is task:
                c['question'] = None
                if outcome['state'] == 'completed':
                    msg = {'id':uuid.uuid4().hex, 'role':'assistant', 'content':content, 'at':time.time()}
                    c['messages'].append(msg)
                    context = message
                    if c['pending_clarifications']:
                        context += '\n\nClarifications supplied during this turn:\n' + '\n'.join(c['pending_clarifications'])
                    c['history'].extend([{'role':'user','content':context}, {'role':'assistant','content':content}])
                    outcome['result_message_id'] = msg['id']
                c['pending_clarifications'] = []
                task.update(**outcome, ended_at=time.time())
                c['revision'] += 1
            if cleanup_cancelled:
                raise asyncio.CancelledError

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
        turn = c['task']
        task = self.work.get(chat_id)
        if task and not task.done():
            if not task.cancelling():
                task.cancel()
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                if not task.done():
                    raise
        if c['task'] is turn and turn and turn['state'] in BUSY:
            turn.update(state='cancelled', summary='Stopped by you', ended_at=time.time())
            c['question'] = None
            c['revision'] += 1

    async def delete(self, chat_id):
        await self.stop(chat_id)
        self.chats.pop(chat_id, None)
        self.work.pop(chat_id, None)

    async def shutdown(self):
        await asyncio.gather(*(self.stop(cid) for cid in tuple(self.chats)))
