"""Real, bounded OS-worker fixtures; never import Hermes or call a provider."""
import asyncio
from contextlib import asynccontextmanager
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from hsuh.chat import BUSY, ChatManager


async def until(predicate):
    async with asyncio.timeout(3):
        while not predicate():
            await asyncio.sleep(.005)


class TurnLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.manager = ChatManager()
        self.cid = self.manager.create()['id']
        self.scratch = tempfile.TemporaryDirectory(prefix='hsuh-turn-')
        self.root = Path(self.scratch.name)
        self.spawned = []

    async def asyncTearDown(self):
        await self.manager.shutdown()
        for p in self.spawned:
            self.assertIsNotNone(p.returncode, 'Fixture process must be reaped')
        self.scratch.cleanup()

    @asynccontextmanager
    async def workers(self, *sources):
        original = asyncio.create_subprocess_exec
        sources = iter(sources)
        async def spawn(*args, **kwargs):
            p = await original(sys.executable, '-u', '-c', next(sources), **kwargs)
            self.spawned.append(p)
            return p
        with patch('hsuh.chat.asyncio.create_subprocess_exec', spawn):
            yield

    def emit(self, *events):
        return '\n'.join(f'print({json.dumps(json.dumps(e))}, flush=True)' for e in events)

    def waiting_worker(self, event, marker, release):
        return ('import os,sys,time\nfrom pathlib import Path\nsys.stdin.readline()\n' + self.emit(event)
                # Close the protocol pipe without exiting: exercise p.wait(), not just readline().
                + '\nfd=os.open(os.devnull,os.O_WRONLY); os.dup2(fd,1); os.close(fd)\n'
                + f'Path({str(marker)!r}).touch()\nwhile not Path({str(release)!r}).exists(): time.sleep(.005)\n')

    async def test_final_keeps_turn_busy_until_exit_then_next_question_survives(self):
        marker, release = self.root/'emitted', self.root/'exit'
        first = self.waiting_worker({'type':'final','content':'First answer'}, marker, release)
        question = {'type':'question','questions':[{'qid':'q0','question':'Fictional name?'}]}
        second = ('import sys\nsys.stdin.readline()\n' + self.emit(question)
                  + '\nsys.stdin.readline()\n' + self.emit({'type':'final','content':'Second answer'}))
        async with self.workers(first, second):
            self.manager.submit(self.cid, 'First turn')
            old = self.manager.work[self.cid]
            await until(marker.exists)
            await asyncio.sleep(.03)  # Give the parent time to consume the emitted final.
            state = self.manager.get(self.cid)
            self.assertIn(state['task']['state'], BUSY)
            self.assertEqual([m['role'] for m in state['messages']], ['user'])
            with self.assertRaises(HTTPException) as error:
                self.manager.submit(self.cid, 'Too early')
            self.assertEqual(error.exception.status_code, 409)
            release.touch()
            await asyncio.wait_for(old, 3)
            self.assertEqual(self.manager.get(self.cid)['task']['state'], 'completed')
            self.manager.submit(self.cid, 'Second turn')
            await until(lambda: self.manager.get(self.cid)['question'] is not None)
            second_process = self.manager.processes[self.cid]
            q = self.manager.get(self.cid)['question']
            await self.manager.answer(self.cid, q['id'], {'q0':'Birch'})
            await asyncio.wait_for(self.manager.work[self.cid], 3)
            self.assertEqual(self.manager.get(self.cid)['task']['state'], 'completed')
            self.assertIsNot(second_process, self.spawned[0])
            self.assertEqual(len(self.manager.chats[self.cid]['history']), 4)

    async def test_late_stop_completion_cannot_cancel_a_new_turn(self):
        ready = self.root/'ready'
        first = f"import time\nfrom pathlib import Path\nPath({str(ready)!r}).touch()\ntime.sleep(20)"
        second = ('import sys\nsys.stdin.readline()\n' + self.emit({'type':'question','questions':[{'qid':'q0','question':'Name?'}]})
                  + '\nsys.stdin.readline()\n' + self.emit({'type':'final','content':'Done'}))
        async with self.workers(first, second):
            self.manager.submit(self.cid, 'Old turn')
            old = self.manager.work[self.cid]
            await until(ready.exists)
            # Registered before stop's await: enqueue a new turn as soon as old cleanup finishes,
            # but before the old stop request's continuation resumes.
            old.add_done_callback(lambda _: self.manager.submit(self.cid, 'New turn'))
            await asyncio.wait_for(self.manager.stop(self.cid), 3)
            self.assertEqual(self.manager.get(self.cid)['task']['label'], 'New turn')
            self.assertIn(self.manager.get(self.cid)['task']['state'], BUSY)
            await until(lambda: self.manager.get(self.cid)['question'] is not None)
            q = self.manager.get(self.cid)['question']
            await self.manager.answer(self.cid, q['id'], {'q0':'Birch'})
            await asyncio.wait_for(self.manager.work[self.cid], 3)
            self.assertEqual(self.manager.get(self.cid)['task']['state'], 'completed')

    async def test_deadline_includes_initial_stdin_backpressure(self):
        self.manager.chats[self.cid]['history'] = [
            {'role':'user','content':'x'*12000}, {'role':'assistant','content':'y'*100000}
        ] * 5
        original_timeout = asyncio.timeout
        deadlines = []
        def short_deadline(seconds):
            deadlines.append(seconds)
            return original_timeout(.08)
        async with self.workers('import time; time.sleep(20)'):
            with patch('hsuh.chat.asyncio.timeout', short_deadline):
                self.manager.submit(self.cid, 'Bounded non-reading worker')
                work = self.manager.work[self.cid]
                await asyncio.sleep(.35)
                self.assertTrue(work.done(), 'Initial stdin drain must be inside the deadline')
                self.assertEqual(deadlines, [240])
                self.assertEqual(self.manager.get(self.cid)['task']['state'], 'failed')
                self.assertIn('240-second limit', self.manager.get(self.cid)['task']['summary'])
                self.assertIsNotNone(self.spawned[0].returncode)
                self.assertEqual(self.manager.chats[self.cid]['history'][0]['content'], 'x'*12000)
                self.assertEqual(len(self.manager.get(self.cid)['messages']), 1)

    async def test_deadline_includes_process_startup(self):
        original_timeout = asyncio.timeout
        attempted = asyncio.Event()
        async def slow_start(*args, **kwargs):
            attempted.set()
            await asyncio.sleep(20)
        with patch('hsuh.chat.asyncio.create_subprocess_exec', slow_start), patch(
                'hsuh.chat.asyncio.timeout', lambda _: original_timeout(.08)):
            self.manager.submit(self.cid, 'Slow startup')
            work = self.manager.work[self.cid]
            await asyncio.wait_for(attempted.wait(), 1)
            await asyncio.sleep(.25)
            self.assertTrue(work.done(), 'Spawn must be inside the deadline')
            self.assertEqual(self.manager.get(self.cid)['task']['state'], 'failed')
            self.assertNotIn(self.cid, self.manager.processes)

    async def test_deadline_includes_wait_after_final_and_never_commits(self):
        marker, release = self.root/'emitted', self.root/'never-release'
        source = self.waiting_worker({'type':'final','content':'Uncommitted answer'}, marker, release)
        original_timeout = asyncio.timeout
        async with self.workers(source):
            with patch('hsuh.chat.asyncio.timeout', lambda _: original_timeout(.08)):
                self.manager.submit(self.cid, 'Deadline also covers exit')
                work = self.manager.work[self.cid]
                await asyncio.wait_for(work, 2)
        self.assertTrue(marker.exists())
        self.assertEqual(self.manager.get(self.cid)['task']['state'], 'failed')
        self.assertEqual(self.manager.chats[self.cid]['history'], [])
        self.assertEqual(len(self.manager.get(self.cid)['messages']), 1)

    async def test_unsuccessful_protocol_never_commits_final_or_history(self):
        final = {'type':'final','content':'Must not be committed'}
        cases = {
            'nonzero': (self.emit(final), 1),
            'error_after_final': (self.emit(final, {'type':'error'}), 0),
            'duplicate_final': (self.emit(final, final), 0),
            'question_after_final': (self.emit(final, {'type':'question','questions':[]}), 0),
            'missing_final': ('', 0),
        }
        for name, (events, code) in cases.items():
            with self.subTest(name=name):
                cid = self.manager.create()['id']
                source = 'import sys\nsys.stdin.readline()\n' + events + f'\nraise SystemExit({code})'
                async with self.workers(source):
                    self.manager.submit(cid, 'Fictional failed turn')
                    await asyncio.wait_for(self.manager.work[cid], 3)
                state = self.manager.get(cid)
                self.assertEqual(state['task']['state'], 'failed')
                self.assertEqual([m['role'] for m in state['messages']], ['user'])
                self.assertEqual(self.manager.chats[cid]['history'], [])
                self.assertIsNone(state['task']['result_message_id'])
                self.assertNotIn(cid, self.manager.processes)

    async def test_stop_during_error_or_timeout_teardown_finishes_cleanup(self):
        import os
        import shutil
        import signal
        original_timeout = asyncio.timeout
        for mode in ('error', 'timeout'):
            with self.subTest(mode=mode):
                self.manager = ChatManager()
                self.cid = self.manager.create()['id']
                marker = self.root / (mode + '-terminating')
                diagnostic_marker = self.root / (mode + '-diagnostic')
                source = (
                    'import os,signal,time\nfrom pathlib import Path\n'
                    f'def stop(*args): Path({str(marker)!r}).touch()\n'
                    'signal.signal(signal.SIGTERM,stop)\n'
                    'd=Path(os.environ["HSUH_DIAGNOSTICS_DIR"])\n'
                    '(d/"canary").write_text("Fictional diagnostic")\n'
                    f'Path({str(diagnostic_marker)!r}).write_text(str(d))\n'
                    + (self.emit({'type':'error'}) + '\n' if mode == 'error' else '')
                    + 'while True: time.sleep(.01)\n'
                )
                diagnostic = None
                p = None
                with patch('hsuh.chat.asyncio.timeout', lambda seconds: original_timeout(.4 if seconds == 240 else seconds)):
                    async with self.workers(source):
                        self.manager.submit(self.cid, mode)
                        work = self.manager.work[self.cid]
                        try:
                            await until(marker.exists)
                            p = self.spawned[-1]
                            diagnostic = Path(diagnostic_marker.read_text())
                            self.assertTrue((diagnostic/'canary').exists())
                            # Both requests arrive while failed/timeout teardown is already awaiting exit.
                            await asyncio.wait_for(asyncio.gather(
                                self.manager.stop(self.cid), self.manager.stop(self.cid)), 5)
                            self.assertTrue(work.done())
                            self.assertIsNotNone(p.returncode, 'Stop must reap a SIGTERM-ignoring worker')
                            self.assertFalse(diagnostic.exists(), 'Stop must dispose native diagnostics')
                            self.assertNotIn(self.cid, self.manager.processes)
                            self.assertNotIn(self.cid, self.manager.work)
                            self.assertEqual(self.manager.slots._value, 2)
                        finally:
                            if p is not None and p.returncode is None:
                                os.killpg(p.pid, signal.SIGKILL)
                                await p.wait()
                            if diagnostic is not None and diagnostic.exists():
                                shutil.rmtree(diagnostic)
                async with self.workers(self.emit({'type':'final','content':'Following turn'})):
                    self.manager.submit(self.cid, 'Following turn')
                    await asyncio.wait_for(self.manager.work[self.cid], 3)
                    self.assertEqual(self.manager.get(self.cid)['task']['state'], 'completed')

    async def test_cancellation_does_not_release_chat_during_slow_teardown(self):
        marker, release, ready = self.root/'terminating', self.root/'exit', self.root/'ready'
        first = ("import signal,time\nfrom pathlib import Path\n"
                 f"def stop(*args):\n Path({str(marker)!r}).touch()\n while not Path({str(release)!r}).exists(): time.sleep(.005)\n raise SystemExit(0)\n"
                 f"signal.signal(signal.SIGTERM,stop)\nPath({str(ready)!r}).touch()\nwhile True: time.sleep(.01)\n")
        second = ('import sys\nsys.stdin.readline()\n' + self.emit({'type':'question','questions':[{'qid':'q0','question':'Name?'}]})
                  + '\nsys.stdin.readline()\n' + self.emit({'type':'final','content':'Done'}))
        async with self.workers(first, second):
            self.manager.submit(self.cid, 'Cancel this turn')
            await until(ready.exists)
            stopping = asyncio.create_task(self.manager.stop(self.cid))
            try:
                await until(marker.exists)
                self.assertIn(self.manager.get(self.cid)['task']['state'], BUSY)
                with self.assertRaises(HTTPException):
                    self.manager.submit(self.cid, 'Not until cleanup finishes')
            finally:
                release.touch()
                await asyncio.wait_for(stopping, 3)
            self.manager.submit(self.cid, 'Next turn')
            await until(lambda: self.manager.get(self.cid)['question'] is not None)
            q = self.manager.get(self.cid)['question']
            self.assertIs(self.manager.processes[self.cid], self.spawned[1])
            await self.manager.answer(self.cid, q['id'], {'q0':'Birch'})
            await asyncio.wait_for(self.manager.work[self.cid], 3)
            self.assertEqual(self.manager.get(self.cid)['task']['state'], 'completed')
