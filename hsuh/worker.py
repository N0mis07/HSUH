"""Fresh process per turn using the documented Hermes Python library.

Protocol contains only final text, native clarify cards and non-secret runtime
identity. Provider diagnostics/stdout are discarded, never streamed to browsers.
"""
import contextlib
import json
import logging
import os
from pathlib import Path
import sys


def main():
    wire = sys.stdout
    def emit(event):
        wire.write(json.dumps(event, ensure_ascii=False)+'\n')
        wire.flush()

    # Keep SDK/plugin diagnostics out of HSUH output, logs and conversation history.
    logging.disable(logging.CRITICAL)
    with open(os.devnull, 'w') as discard, contextlib.redirect_stdout(discard), contextlib.redirect_stderr(discard):
        try:
            root = Path(os.environ.get('HSUH_HERMES_ROOT', str(Path.home()/'.hermes/hermes-agent'))).resolve()
            if not (root/'run_agent.py').is_file():
                raise RuntimeError('Hermes source checkout unavailable')
            sys.path.insert(0, str(root))
            import hermes_bootstrap  # Hermes' pinned dependency/bootstrap environment
            from hermes_cli.config import load_config_readonly
            from hermes_cli.runtime_provider import resolve_runtime_provider
            from run_agent import AIAgent
            cfg = load_config_readonly()
            model = cfg['model']['default']
            provider = cfg['model']['provider']
            effort = cfg.get('agent', {}).get('reasoning_effort', 'high')
            runtime = resolve_runtime_provider(requested=provider, target_model=model)
            # Do not permit a runtime that delegates to an external tool-capable Codex process.
            if runtime.get('api_mode') == 'codex_app_server':
                raise RuntimeError('External tool runtime is not supported by HSUH')
            initial = json.loads(sys.stdin.readline())

            def clarify(questions):
                emit({'type':'question', 'questions':questions})
                answer = sys.stdin.readline()
                return json.loads(answer) if answer else {'answers':{},'outcome':'cancelled'}

            agent = AIAgent(
                model=model, provider=runtime['provider'], api_mode=runtime['api_mode'],
                api_key=runtime.get('api_key'), base_url=runtime.get('base_url'),
                enabled_toolsets=['clarify'], quiet_mode=True, max_iterations=6,
                skip_context_files=True, skip_memory=True, skip_background_review=True,
                session_db=None, save_trajectories=False, fallback_model={},
                reasoning_config={'enabled':True, 'effort':effort},
                clarify_callback=clarify, run_budget_seconds=220,
                ephemeral_system_prompt=(
                    'You are Hermes, accessed through HSUH. This initial client supports conversation and the clarify tool only. '
                    'You cannot execute commands, browse, start delegated tasks, access existing sessions or use credentials. '
                    'Do not claim to do those things. Use clarify for consequential missing information or when explicitly asked to show a question card. '
                    'Never ask for passwords, tokens, payment data or login codes in chat or clarify. A native vault bridge is not connected. '
                    'Give concise activity explanations, not private chain-of-thought. Be explicit about limitations.'),
            )
            actual = {t.get('function',{}).get('name') for t in (agent.tools or [])}
            if actual != {'clarify'}:
                raise RuntimeError('Tool allowlist invariant failed')
            emit({'type':'ready','model':agent.model,'provider':agent.provider,'reasoning_effort':effort})
            result = agent.run_conversation(initial['message'], conversation_history=initial['history'])
            # The documented result has completed/failure metadata in current Hermes.
            content = result.get('final_response')
            if not result.get('completed') or result.get('partial') or result.get('interrupted') or result.get('error') or result.get('failed'):
                raise RuntimeError('Hermes reported unsuccessful completion')
            if not content:
                raise RuntimeError('Hermes returned no final answer')
            emit({'type':'final','content':content})
        except Exception:
            emit({'type':'error'})
            return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
