"""Owner-only adapter to the existing Hermes gateway. No agent/tool execution here.

Native sessions hold transcripts. A private, bounded SQLite ledger holds workspace
membership, admission idempotency and run receipts so a web restart cannot orphan
work. Closing the site disconnects observers, never cancels native work.
"""
import asyncio
from contextlib import suppress
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import time
import uuid

from fastapi import HTTPException
import httpx

BUSY = {'queued', 'running', 'pending_input', 'waiting_for_approval', 'stopping', 'reconnecting'}
TERMINAL = {'completed', 'cancelled', 'failed', 'interrupted'}
IDENTIFIER = re.compile(r'[A-Za-z0-9_-]{1,160}\Z')


def identifier(value):
    if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
        raise HTTPException(422, 'Invalid native identifier')
    return value


def text(value, limit=1000):
    return value[:limit] if isinstance(value, str) else ''


def approval_view(value):
    if not isinstance(value, dict) or not value.get('request_id'):
        return None
    # The native API redacts commands before putting them on the approval wire.
    return {'request_id': text(value['request_id'], 160),
            'command': text(value.get('command'), 6000),
            'description': text(value.get('description') or value.get('reason'), 1500),
            'choices': [c for c in value.get('choices', []) if c in {'once', 'deny', 'session'}]}


class GatewayClient:
    def __init__(self):
        key = os.environ.get('HSUH_GATEWAY_KEY', '')
        if len(key) < 16:
            raise ValueError('Native control requires the private gateway service key')
        port = int(os.environ.get('HSUH_GATEWAY_PORT', '8642'))
        if not 1 <= port <= 65535:
            raise ValueError('Invalid gateway port')
        self.client = httpx.AsyncClient(base_url=f'http://127.0.0.1:{port}',
            headers={'Authorization': 'Bearer '+key}, trust_env=False,
            follow_redirects=False, timeout=httpx.Timeout(12, connect=2), limits=httpx.Limits(max_connections=16))

    async def request(self, method, path, body=None, key=None):
        try:
            headers = {'Idempotency-Key': key} if key else {}
            async with self.client.stream(method, path, json=body, headers=headers) as r:
                if r.status_code >= 300:
                    # Do not proxy arbitrary native/provider errors or authentication headers.
                    detail = {409:'Hermes reports a conflict or a stale control request. Refresh and retry.',
                              429:'Hermes is at its concurrent task limit. Try again shortly.',
                              404:'The native resource is unavailable or has expired.',
                              401:'Native gateway authentication needs operator attention.'}.get(r.status_code,
                                'The native gateway could not complete this request.')
                    raise HTTPException(r.status_code if r.status_code in {404,409,429} else 503, detail)
                data = bytearray()
                async for chunk in r.aiter_bytes():
                    data.extend(chunk)
                    if len(data) > 2*1024*1024:
                        raise HTTPException(502, 'Native response exceeds the supported size')
                value = json.loads(data)
                if not isinstance(value, dict):
                    raise ValueError('Invalid gateway response')
                return value
        except (httpx.HTTPError, ValueError):
            raise HTTPException(503, 'Native gateway unavailable. Accepted tasks keep running; reconnect to check them.') from None

    async def events(self, run_id, after):
        async with self.client.stream('GET', f'/v1/runs/{identifier(run_id)}/events',
                                     headers={'Last-Event-ID': str(after)}, timeout=httpx.Timeout(45, connect=2)) as r:
            r.raise_for_status()
            size, parts = 0, []
            async for line in r.aiter_lines():
                size += len(line)
                if size > 256000:
                    raise ValueError('Event exceeds supported size')
                if line.startswith('data:'):
                    parts.append(line[5:].lstrip())
                elif not line:
                    if parts:
                        event = json.loads('\n'.join(parts))
                        if isinstance(event, dict):
                            yield event
                    parts, size = [], 0

    async def close(self):
        await self.client.aclose()


class NativeManager:
    native = True

    def __init__(self, gateway=None, path=None, watch=True):
        self.gateway = gateway or GatewayClient()
        path = Path(path or os.environ.get('HSUH_CONTROL_DB', Path.home()/'.local/state/hsuh/control.sqlite3'))
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if not path.exists():
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(fd)
        self.db = sqlite3.connect(path)
        self.db.execute('PRAGMA journal_mode=DELETE')
        self.db.execute('CREATE TABLE IF NOT EXISTS workspace (id TEXT PRIMARY KEY, data TEXT NOT NULL)')
        self.chats = {row[0]: json.loads(row[1]) for row in self.db.execute('SELECT id,data FROM workspace')}
        # JSON duplicates the current receipt embedded in the history. Restore one
        # canonical object so status, events and control ownership settle together.
        for c in self.chats.values():
            current = c.get('task')
            if current:
                for index, saved in enumerate(c['tasks']):
                    if saved['id'] == current['id']:
                        merged = {**saved, **current}
                        if 'outbox' not in current:
                            merged.pop('outbox', None)
                        if (saved.get('last_seq', -1), len(saved.get('events', []))) > (current.get('last_seq', -1), len(current.get('events', []))):
                            merged.update(events=saved.get('events', []), last_seq=saved.get('last_seq', -1))
                        c['task'] = c['tasks'][index] = merged
                        break
        self.locks = {}
        self.refresh_slots = asyncio.Semaphore(6)
        self.observers = {}
        self.watch = watch
        self.processes = {}  # Execution belongs to Hermes, never a web worker process.
        self.model = None
        self.closed = False

    @property
    def active_count(self):
        return sum(c.get('task') is not None and c['task']['state'] in BUSY for c in self.chats.values())

    def _lock(self, chat_id):
        return self.locks.setdefault(chat_id, asyncio.Lock())

    def _find(self, chat_id):
        identifier(chat_id)
        if chat_id not in self.chats:
            raise HTTPException(404, 'Conversation is not in this workspace')
        return self.chats[chat_id]

    def _save(self, c):
        c['revision'] += 1
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO workspace VALUES (?,?)', (c['id'], json.dumps(c)))

    async def create(self, session_id=None):
        if len(self.chats) >= 100:
            raise HTTPException(409, '100-conversation workspace limit; remove a conversation first')
        if session_id:
            identifier(session_id)
            if session_id in self.chats:
                return await self.get(session_id)
            session = (await self.gateway.request('GET', '/api/sessions/'+session_id))['session']
        else:
            session_id = 'hsuh_'+uuid.uuid4().hex
            session = (await self.gateway.request('POST', '/api/sessions', {'id':session_id, 'source':'api_server'}))['session']
        c = {'id':session_id, 'native_session_id':session_id, 'title':text(session.get('title'), 120) or 'New conversation',
             'source':text(session.get('source'), 40) or 'api_server', 'created_at':time.time(),
             'tasks':[], 'task':None, 'revision':0, 'removed':False}
        self.chats[session_id] = c
        self._save(c)
        return await self.get(session_id)

    async def list(self):
        # Status polling is independent of the selected conversation, including after restart.
        pending = [(c, c['task']) for c in self.chats.values() if c.get('task') and c['task']['state'] in BUSY]
        pending += [(c, t) for c in self.chats.values() for t in reversed(c['tasks']) if t is not c.get('task') and t['state'] in BUSY]
        async def refresh(c, task):
            async with self.refresh_slots:
                await self._refresh(c, task)
        await asyncio.gather(*(refresh(c, task) for c, task in pending[:200]))
        return [{**copy.deepcopy({k:c[k] for k in ('id','title','revision','source')}),
                 'task':{k:v for k,v in self._public_task(c['task']).items() if k != 'events'} if c['task'] else None}
                for c in reversed(list(self.chats.values())) if not c.get('removed')]

    def _public_task(self, task, event_limit=100):
        result = {k:copy.deepcopy(v) for k,v in task.items() if k not in {'outbox','fingerprint','request_key','events'}}
        result['events'] = copy.deepcopy(task.get('events', [])[-event_limit:]) if event_limit else []
        # Use the execution host clock; a phone/desktop clock may differ from the VPS.
        result['elapsed_seconds'] = max(0, int((task.get('ended_at') or time.time())-(task.get('started_at') or task['created_at'])))
        return result

    async def get(self, chat_id):
        c = self._find(chat_id)
        await self._refresh(c)
        result = await self.gateway.request('GET', f"/api/sessions/{c['native_session_id']}/messages?limit=100&order=latest")
        resolved = result.get('session_id')
        if resolved and resolved != c['native_session_id']:
            c['native_session_id'] = identifier(resolved)
            self._save(c)
        messages = []
        for m in result.get('data', []):
            # No system messages, private reasoning, tool arguments or raw tool results.
            if m.get('role') not in {'user','assistant'} or not isinstance(m.get('content'), str) or not m['content']:
                continue
            content = m['content'][:100000]
            # Native delivery envelopes are model-routing instructions, not chat copy.
            guidance = re.fullmatch(r'\[OUT-OF-BAND USER MESSAGE[^\n]*\]\n(.*)\n\[/OUT-OF-BAND USER MESSAGE\]', content, re.DOTALL) if m['role'] == 'user' else None
            messages.append({'id':str(m.get('id', len(messages))), 'role':m['role'],
                             'content':guidance.group(1) if guidance else content,
                             'kind':'guidance' if guidance else 'message', 'at':m.get('timestamp')})
        task = c.get('task')
        # Admission can be visible before Hermes writes its first transcript row.
        if task and task.get('outbox') and task['state'] in BUSY:
            messages.append({'id':task['id']+'-pending', 'role':'user', 'content':task['outbox']['input'], 'at':task['created_at']})
        return {'id':c['id'], 'title':c['title'], 'source':c['source'], 'native':True,
                'native_session_id':c['native_session_id'], 'created_at':c['created_at'],
                'messages':messages, 'tasks':[self._public_task(t, 100 if t is task else 5) for t in c['tasks'][-30:]],
                'task':self._public_task(task) if task else None, 'question':None,
                # Native transcript can change independently (Telegram, compression, async delivery).
                'revision':str(c['revision'])+':'+hashlib.sha256(json.dumps(messages, sort_keys=True).encode()).hexdigest()[:16]}

    async def submit(self, chat_id, message, request_key=None):
        c = self._find(chat_id)
        message = message.strip()
        if not message:
            raise HTTPException(422, 'Message is empty')
        request_key = identifier(request_key or uuid.uuid4().hex)
        async with self._lock(chat_id):
            prior = next((t for t in c['tasks'] if t['request_key'] == request_key), None)
            fingerprint = hashlib.sha256(message.encode()).hexdigest()
            if prior:
                if prior['fingerprint'] != fingerprint:
                    raise HTTPException(409, 'This submission ID belongs to a different message')
            else:
                if c.get('task') and c['task']['state'] in BUSY:
                    raise HTTPException(409, 'Wait for this native task to settle or stop it first')
                if len(c['tasks']) >= 200:
                    raise HTTPException(409, '200-task workspace limit; open a fresh conversation')
                task = {'id':uuid.uuid4().hex, 'request_key':request_key, 'fingerprint':fingerprint,
                        'run_id':None, 'label':' '.join(message.split())[:72], 'state':'queued',
                        'created_at':time.time(), 'started_at':None, 'ended_at':None,
                        'summary':'Submitting to the native gateway', 'result_message_id':None,
                        'approval':None, 'events':[], 'last_seq':-1,
                        'outbox':{'input':message, 'session_id':c['native_session_id'],
                                  'instructions':self._instructions()}}
                c['task'] = task
                c['tasks'].append(task)
                c['removed'] = False
                if c['title'] == 'New conversation':
                    c['title'] = ' '.join(message.split())[:70]
                self._save(c)  # Durable intent precedes the native mutation.
                await self._admit(c, task)
        return await self.get(chat_id)

    @staticmethod
    def _instructions():
        ui = Path(__file__).with_name('openui-prompt.txt').read_text(encoding='utf-8')
        return ('You are Hermes in the owner-authenticated HSUH control centre. Use your native tools, skills and memory as on Telegram. '
                'Tasks execute on the VPS. Retain all native approval requirements. Never ask for secrets in ordinary chat; '
                'website credential collection is unavailable. Give brief public activity summaries, never private reasoning. '
                'If you need clarification, ask the owner in your response; they can reply in this conversation. '+ui[:24000])

    async def _admit(self, c, task):
        if task.get('run_id') or not task.get('outbox'):
            return
        if time.time()-task['created_at'] > 23*3600:
            task.update(state='interrupted', ended_at=time.time(), summary='Unconfirmed admission is older than the native replay window. Check the native transcript before retrying.')
            task.pop('outbox', None)
            self._save(c)
            return
        try:
            result = await self.gateway.request('POST', '/v1/runs', task['outbox'], key='hsuh-'+task['id'])
            task['run_id'] = identifier(result['run_id'])
            task.update(state='running', started_at=task['created_at'], summary='Running in the native Hermes gateway')
            task.pop('outbox', None)
        except HTTPException as exc:
            if exc.status_code in {404,409,429}:
                task.update(state='failed', ended_at=time.time(), summary=exc.detail)
                task.pop('outbox', None)
            else:
                task.update(state='reconnecting', summary='Admission not confirmed. Reconnecting with the same submission ID.')
        self._save(c)
        self._observe(task)

    async def _refresh(self, c, task=None):
        task = task or c.get('task')
        if not task or task['state'] not in BUSY:
            return
        async with self._lock(c['id']):
            if not any(t is task for t in c['tasks']):
                return
            if not task.get('run_id'):
                if task is c.get('task'):
                    await self._admit(c, task)
                else:
                    task.update(state='interrupted', ended_at=time.time(), summary='Older admission has no native receipt. Check the transcript before retrying.')
                    task.pop('outbox', None)
                    self._save(c)
            if task.get('run_id'):
                try:
                    status = await self.gateway.request('GET', '/v1/runs/'+task['run_id'])
                    self._apply_status(c, task, status)
                    self._observe(task)
                except HTTPException as exc:
                    if exc.status_code == 404:
                        task.update(state='interrupted', summary='Native run receipt expired or is unavailable. Check the transcript before retrying.', ended_at=time.time())
                    else:
                        task['summary'] = 'Gateway connection unavailable. Native work may still be running.'
                    self._save(c)

    def _apply_status(self, c, task, status):
        state = status.get('status')
        if state not in BUSY | TERMINAL:
            return
        before = json.dumps(task, sort_keys=True)
        task.update(state=state, approval=approval_view(status.get('approval')) if state == 'waiting_for_approval' else None)
        task['summary'] = {'completed':'Native task completed', 'cancelled':'Native task stopped',
            'failed':'Native task failed. Check Hermes and provider status.', 'interrupted':'Native task interrupted by gateway restart.',
            'waiting_for_approval':'Waiting for your decision', 'stopping':'Stop requested. Waiting for native execution to settle.'}.get(state, 'Running in the native Hermes gateway')
        if state in TERMINAL:
            task['ended_at'] = status.get('updated_at') or time.time()
            if status.get('pending_steer'):
                task['undelivered_guidance'] = True
                task['summary'] += ' Latest guidance was not delivered; send it as a new message.'
        usage = status.get('usage')
        if isinstance(usage, dict):
            task['usage'] = {k:v for k,v in usage.items() if k in {'input_tokens','output_tokens','total_tokens','cache_read_tokens','cache_write_tokens'} and isinstance(v, (int,float))}
        runtime = status.get('runtime')
        if isinstance(runtime, dict):
            self.model = {k:text(runtime.get(k), 100) for k in ('model','provider','reasoning_effort')}
        if before != json.dumps(task, sort_keys=True):
            self._save(c)

    def record_event(self, task_id, event):
        for c in self.chats.values():
            task = next((t for t in c['tasks'] if t['id'] == task_id), None)
            if task is None:
                continue
            seq = event.get('seq')
            if isinstance(seq, int):
                if seq <= task['last_seq']:
                    return
                task['last_seq'] = seq
            name = event.get('event')
            if name not in {'tool.started','tool.completed','subagent.start','subagent.complete','message.interim',
                            'approval.request','approval.responded','run.steered','replay.truncated'}:
                return
            if name in {'tool.started','tool.completed','subagent.start','subagent.complete','message.interim', 'approval.responded','run.steered','replay.truncated'}:
                item = {'event':name, 'at':event.get('timestamp') or time.time()}
                if name.startswith('tool.'):
                    item.update(tool=text(event.get('tool'), 100), error=bool(event.get('error')),
                                duration=event.get('duration') if isinstance(event.get('duration'), (int,float)) else None)
                elif name == 'message.interim':
                    item['text'] = text(event.get('text'), 3000)
                elif name.startswith('subagent.'):
                    item['text'] = text(event.get('status'), 100)
                task['events'] = (task['events']+[item])[-100:]
            if name == 'approval.request' and task['state'] not in TERMINAL:
                task.update(state='waiting_for_approval', approval=approval_view(event))
            if name == 'approval.responded':
                task['approval'] = None
            self._save(c)
            return

    def _observe(self, task):
        if not self.watch or task['state'] not in BUSY or not task.get('run_id') or task['id'] in self.observers:
            return
        async def observe():
            try:
                async for event in self.gateway.events(task['run_id'], task['last_seq']):
                    self.record_event(task['id'], event)
            except (httpx.HTTPError, ValueError, HTTPException):
                pass  # Polling reattaches with Last-Event-ID; disconnect never stops the task.
            finally:
                self.observers.pop(task['id'], None)
        self.observers[task['id']] = asyncio.create_task(observe())

    def _owned_task(self, chat_id, task_id):
        c = self._find(chat_id)
        task = c.get('task')
        if not task or task['id'] != task_id or not task.get('run_id'):
            raise HTTPException(409, 'This control belongs to an older or unconfirmed task. Refresh first.')
        return c, task

    async def stop(self, chat_id, task_id=None):
        async with self._lock(chat_id):
            c, task = self._owned_task(chat_id, task_id)
            if task['state'] in TERMINAL:
                return
            result = await self.gateway.request('POST', '/v1/runs/'+task['run_id']+'/stop', {})
            self._apply_status(c, task, result)

    async def approve(self, chat_id, task_id, request_id, choice):
        async with self._lock(chat_id):
            c, task = self._owned_task(chat_id, task_id)
            status = await self.gateway.request('GET', '/v1/runs/'+task['run_id'])
            self._apply_status(c, task, status)
            approval = task.get('approval')
            if task['state'] != 'waiting_for_approval' or not approval or approval['request_id'] != request_id or choice not in approval['choices']:
                raise HTTPException(409, 'This approval is no longer pending or this choice is unavailable')
            await self.gateway.request('POST', '/v1/runs/'+task['run_id']+'/approval', {'request_id':request_id, 'choice':choice})
            task.update(approval=None, state='running', summary='Decision sent to Hermes')
            self._save(c)
        return await self.get(chat_id)

    async def steer(self, chat_id, task_id, message):
        async with self._lock(chat_id):
            c, task = self._owned_task(chat_id, task_id)
            await self.gateway.request('POST', '/v1/runs/'+task['run_id']+'/steer', {'input':message})
            task['events'] = (task['events']+[{'event':'guidance.sent','text':message[:3000], 'at':time.time()}])[-100:]
            self._save(c)
        return await self.get(chat_id)

    async def answer(self, *args):
        raise HTTPException(409, 'Reply in the native conversation to answer Hermes')

    async def delete(self, chat_id):
        c = self._find(chat_id)
        if c.get('task') and c['task']['state'] in BUSY:
            raise HTTPException(409, 'Stop this task and wait for it to settle before removing the conversation')
        # Removal is workspace membership only; the native transcript stays in Hermes.
        with self.db:
            self.db.execute('DELETE FROM workspace WHERE id=?', (chat_id,))
        self.chats.pop(chat_id)

    async def control(self):
        tools, jobs, sessions = await asyncio.gather(
            self.gateway.request('GET','/v1/toolsets'), self.gateway.request('GET','/api/jobs?include_disabled=true'),
            self.gateway.request('GET','/api/sessions?limit=60'))
        return {'enabled':True, 'tools':[{k:t.get(k) for k in ('name','label','description','enabled','configured','tools')} for t in tools.get('data',[])],
                'jobs':[self._job(j) for j in jobs.get('jobs',[])][:100],
                'sessions':[{k:s.get(k) for k in ('id','title','source','started_at','ended_at','message_count','model','tool_call_count')} for s in sessions.get('data',[])],
                'tasks':sorted([{'chat_id':c['id'], 'title':c['title'], **self._public_task(t, 5)} for c in self.chats.values() for t in c['tasks'][-5:]], key=lambda t:(t['state'] in BUSY, t['created_at']), reverse=True)[:80],
                'note':'Tools run on the VPS with native Hermes permissions. Closing this site keeps tasks running. Telegram sessions can be opened here; stop and steering target tasks started here. Scheduled jobs use the native scheduler.'}

    @staticmethod
    def _job(j):
        return {k:j.get(k) for k in ('id','name','schedule_display','enabled','state','next_run_at','last_run_at','last_status','paused_reason')}

    async def job_action(self, job_id, action):
        identifier(job_id)
        if action not in {'pause','resume','run'}:
            raise HTTPException(422, 'Unsupported scheduler action')
        result = await self.gateway.request('POST', f'/api/jobs/{job_id}/{action}', {})
        return {'job':self._job(result.get('job', {}))}

    async def shutdown(self):
        if self.closed:
            return
        self.closed = True
        observers = list(self.observers.values())
        for task in observers:
            task.cancel()
        await asyncio.gather(*observers, return_exceptions=True)
        await self.gateway.close()
        self.db.close()
