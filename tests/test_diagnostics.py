"""Exercise the real worker/manager against a fictional native-library boundary."""
import asyncio
from contextlib import nullcontext
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from hsuh.chat import ChatManager


class DiagnosticIsolationTests(unittest.IsolatedAsyncioTestCase):
    async def test_diagnostic_directory_is_isolated_and_removed_on_every_exit(self):
        with tempfile.TemporaryDirectory(prefix='hsuh-native-fixture-') as directory:
            root = Path(directory)
            (root/'hermes_bootstrap.py').write_text('')
            (root/'hermes_cli').mkdir()
            (root/'hermes_cli/__init__.py').write_text('')
            (root/'hermes_cli/config.py').write_text(
                "def load_config_readonly(): return {'model':{'default':'fixture-model','provider':'fixture-provider'},'agent':{'reasoning_effort':'high'}}\n")
            (root/'hermes_cli/runtime_provider.py').write_text(
                "def resolve_runtime_provider(**kwargs): return {'provider':'fixture-provider','api_mode':'chat_completions'}\n")
            # This is not a model response fake: it is an explicit offline SDK-boundary fixture.
            source = '''import json, signal, time
from pathlib import Path
class AIAgent:
    def __init__(self, **kwargs):
        assert kwargs['enabled_toolsets'] == ['clarify']
        assert kwargs['reasoning_config'] == {'enabled':True,'effort':'high'}
        assert kwargs['session_db'] is None and not kwargs['save_trajectories']
        assert kwargs['skip_memory'] and kwargs['skip_background_review']
        assert kwargs['fallback_model'] == {}
        self.model, self.provider = kwargs['model'], kwargs['provider']
        self.tools = [{'function':{'name':'clarify'}}]
        self.logs_dir = Path(__file__).parent/'native-sessions'
        self.logs_dir.mkdir()
    def run_conversation(self, message, **kwargs):
        if message == 'cancel': signal.signal(signal.SIGTERM, signal.SIG_IGN)
        self.logs_dir.joinpath('request_dump_fixture.json').write_text('Ordinary fictional conversation canary')
        Path(__file__).with_name('diagnostic-path.json').write_text(json.dumps(str(self.logs_dir)))
        if message == 'error': raise RuntimeError('Fictional provider failure')
        if message in ('cancel', 'timeout'): time.sleep(20)
        return {'completed':True,'final_response':'Fictional SDK boundary output'}
'''
            (root/'run_agent.py').write_text(source)
            original_timeout = asyncio.timeout
            for mode in ('success', 'error', 'timeout', 'cancel'):
                with self.subTest(mode=mode):
                    manager = ChatManager()
                    cid = manager.create()['id']
                    marker = root/'diagnostic-path.json'
                    marker.unlink(missing_ok=True)
                    try:
                        deadline = patch('hsuh.chat.asyncio.timeout', lambda _: original_timeout(.2)) if mode == 'timeout' else nullcontext()
                        with patch.dict('os.environ', {'HSUH_HERMES_ROOT':str(root)}), deadline:
                            manager.submit(cid, mode)
                            work = manager.work[cid]
                            if mode == 'cancel':
                                async with asyncio.timeout(3):
                                    while not marker.exists():
                                        await asyncio.sleep(.005)
                                diagnostic = Path(json.loads(marker.read_text()))
                                self.assertEqual(diagnostic.stat().st_mode & 0o777, 0o700)
                                process = manager.processes[cid]
                                await asyncio.wait_for(manager.stop(cid), 5)
                                self.assertEqual(process.returncode, -9, 'Ignored SIGTERM requires process-group SIGKILL')
                            else:
                                await asyncio.wait_for(work, 3)
                        self.assertTrue(marker.exists(), 'Native fixture must actually run')
                        diagnostic = Path(json.loads(marker.read_text()))
                        self.assertNotEqual(diagnostic, root/'native-sessions', 'Never retain chat dumps in native sessions')
                        self.assertFalse(diagnostic.exists(), 'Parent must remove diagnostic content after reaping worker')
                        self.assertEqual(list((root/'native-sessions').iterdir()), [])
                        self.assertEqual(manager.get(cid)['task']['state'], {'success':'completed','error':'failed','timeout':'failed','cancel':'cancelled'}[mode])
                    finally:
                        await manager.shutdown()
                        # Fixture SDK initialization deliberately uses the same test-only path each turn.
                        for dump in (root/'native-sessions').glob('*'):
                            dump.unlink()
                        (root/'native-sessions').rmdir()
