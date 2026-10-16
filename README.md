# HSUH

An original, compact browser workspace for [Hermes Agent](https://github.com/NousResearch/hermes-agent). Execution and conversation state live on a Linux VPS; computer and phone clients need only a browser. HSUH is an independent project, not an official Nous Research client.

## Initial working scope

- Independent multi-turn conversations, with two concurrent Hermes workers and a bounded queue.
- Conversation-owned task cards and list indicators: queued, running, needs input, completed, failed, stopped; real start/elapsed time and response anchors. Switching chats or refreshing the browser does not stop a turn.
- Native Hermes `clarify` question cards, including single-select, multi-select and typed non-sensitive answers.
- Live VPS RAM total/used/available, swap and top process RSS. Values come from `psutil`/Linux `/proc`, not generated content. RSS includes shared pages and is **not additive**, nor per-chat attribution.
- Read-only native provider quota windows via `hermes usage --json`; optional existing Aperture quota-bucket discovery. Sources, fetch times, caching and unavailable states are visible. Aperture budgets are not ChatGPT subscription quota or invoices.
- Responsive desktop/phone UI and an online-only installable PWA, with an original small mascot, Mote. No client-side conversation storage, offline cache or push notifications.
- Optional public HTTPS entry through **Cloudflare Access**, with server-side RS256 JWT/issuer/audience/expiry validation **and an explicit owner email allowlist**. Other authenticated OAuth users cannot access the VPS.

## Deliberate limitations

This release is **conversation + clarify only**, not a remote terminal. Native terminal, browser, file, delegation and existing gateway/background-job integrations are not connected. HSUH does not pretend to track jobs started elsewhere. Full agent tools remain disabled until their approvals and authorization can be safely bridged.

Website credential inputs are visibly disabled. `/api/credentials` fails closed with 501 and does not parse or forward the payload. No native vault bridge is wired; never enter a password, token, payment detail or login code in chat/question cards. There are no working website-login forms yet.

Responses appear when a turn finishes; token streaming and raw reasoning are not exposed. Task summaries are deterministic public execution state, **not private chain-of-thought**. Text/fenced-code rendering deliberately does not execute model HTML.

All HSUH chat/task state is in **VPS process memory**: survives switching and browser refresh, not a server restart. It is not imported into existing Hermes sessions. Each conversation is capped at 30 turns, with up to 40 conversations; each turn has a 240-second wall-clock limit, including human-input waits. No automatic weaker-model fallback. Provider failure becomes a failed task, never a fabricated answer.

## Run on the VPS

Requires Python 3.11+ for the web app and an existing configured Hermes source installation in its supported/pinned environment. This implementation was exercised against the installed Hermes source version recorded in `docs/VERIFICATION.md`; Hermes changes rapidly and its Python interfaces may require adapter updates.

```sh
cd /path/to/HSUH
python -m venv .venv
.venv/bin/pip install -r requirements.txt
# Use Hermes' Python runtime/environment for live workers. See note below.
HSUH_HERMES_ROOT="$HOME/.hermes/hermes-agent" .venv/bin/python -m hsuh --port 8110
```

**Runtime note:** the subprocess worker uses the same interpreter as the app, imports `hermes_bootstrap` from `HSUH_HERMES_ROOT`, then the documented `AIAgent` library. On an existing Hermes server, using its already-prepared Python interpreter avoids reinstalling Hermes dependencies. Hermes is **not** available as a supported pip package. If the interpreter cannot load Hermes, turns fail closed; diagnose against [Hermes' Python library guide](https://hermes-agent.nousresearch.com/docs/guides/python-library) rather than installing a guessed package. Default profile credentials are resolved privately through Hermes' native provider resolver. No profile or gateway settings are changed.

The launcher **always binds `127.0.0.1`**. Open `http://127.0.0.1:8110` locally. For a temporary desktop session, use an encrypted SSH local-forward from your existing SSH client; do not expose the port to the LAN or internet.

For Aperture, set `HSUH_APERTURE_URL=https://your-private-aperture-host` to reuse an existing authorized connection. This is optional; HSUH only reads `/api/quotas`, never changes routing, quotas, grants or retention. No bucket schema is guessed: the current implementation reports count/absence and links to authoritative balances if buckets exist.

## Authenticated phone/computer hosting

Use a Cloudflare Tunnel whose only upstream is `http://127.0.0.1:8110`. Keep the original public Host header. Create a **self-hosted Cloudflare Access application** covering the entire hostname, including `/api/*` and assets, with your OAuth identity provider and an allow policy restricted to the owner. Do not deploy an Allow Everyone or bypass policy.

Set these on the VPS before launch (substitute real operator-controlled values; none belong in git):

```sh
export HSUH_PUBLIC_ORIGIN=https://hsuh.example.com
export HSUH_ACCESS_TEAM=your-access-team-slug
export HSUH_ACCESS_AUDIENCE=your-self-hosted-application-audience
export HSUH_OWNER_EMAIL=owner@example.com
python -m hsuh --port 8110
```

Public mode refuses to start without complete authentication configuration. Every request is validated against Access's public signing keys; a forwarded email header alone is never trusted. The owner email must match the signed JWT email. The app does not use OAuth provider access/refresh tokens in the browser. Session cookies are HttpOnly/SameSite=Strict and Secure in public mode. The default loopback mode is **not** safe to publish through an anonymous reverse proxy.

Cloudflare configuration/DNS/identity setup is intentionally outside this repository. The application must not be called deployed or phone-accessible until exact-host anonymous-denial, owner-login and non-owner-denial have been exercised. After HTTPS login, use your browser's Install action or iPhone Safari's Share → Add to Home Screen. PWA installation and OAuth redirects depend on the browser; an actual-device install is a separate acceptance check.

## Check / contribute

```sh
python -m unittest discover -s tests -v
python -m compileall -q hsuh tests
node --check hsuh/static/app.js
node --check hsuh/static/sw.js
```

No frontend bundler is required; static assets are served directly. Tests use generated fictional identities/signing keys and no live provider calls. Optional real integration check: `python scripts/live_smoke.py` (uses your configured provider/subscription for a few bounded turns). Read [CONTRIBUTING.md](CONTRIBUTING.md), [SECURITY.md](SECURITY.md) and [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## License / provenance

New HSUH code and Mote artwork are MIT licensed. No ChatGPT source, decompiled bundle, Hush source or proprietary assets are included. Familiar interaction patterns are not a claim of affiliation. Third-party dependencies retain their own licenses. Any future upstream reuse requires exact-source and license review first.
