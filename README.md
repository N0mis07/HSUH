# HSUH

An original, compact browser workspace for [Hermes Agent](https://github.com/NousResearch/hermes-agent). Execution and conversation state live on a Linux VPS; computer and phone clients need only a browser. HSUH is an independent project, not an official Nous Research client.

## Chat, a buddy and the essentials

Chat opens first, with rounded conversation bubbles and Mote, the original HSUH
buddy. Mote's status follows the selected task: ready, working, waiting for your
input or permission, or interrupted/failed. Suggested messages fill the composer
without sending. The quiet summary shows only RAM, the first Codex quota window
and the active Hermes agent count. Tool logs sit in an expandable activity section;
approval requests and question cards stay directly visible in the conversation.

Work & tools retains the native controls. Stats opens the detailed readings:
measured CPU/RAM history,
swap, disk space, network/disk rates, Linux resource pressure, searchable process
RSS/CPU/thread counts, native gateway state, open Hermes sessions, turn leases,
delegation state counts, recorded API/tool/token totals, and native Codex/provider
quota windows with reset times. Open sessions include idle conversations; they
are not a running-agent count. Session metadata is read through SQLite read-only
connections; prompts, message bodies, process arguments and environments are not
part of these statistics. Missing/incompatible sources show unavailable states.

Conversations use the real [OpenUI](https://www.openui.com/docs) Lang React
renderer (`@openuidev/react-lang` 1.0.1). Hermes can emit a fenced `openui` program
using six permitted components: Stack, Heading, Paragraph, Metric, DataTable and
Checklist. Checklists are interactive in the current view. Unknown, malformed,
oversized or tool-bearing programs fall back to text. No raw HTML, arbitrary
JavaScript, remote URLs, Query/Mutation handlers or model-driven API actions are
registered. Generated measurements are model content, separate from the measured
dashboard. Existing provider/model settings are preserved; no OpenUI Gateway key
or hosted observability service is needed.

Browser assets are bundled locally with exact dependency versions and a lockfile:

```sh
npm ci
npm run build:ui
node tests/openui.mjs
```

The committed bundle lets the VPS run without a frontend build service. Rebuild
after editing `frontend/openui.tsx`; CI checks the source too. Dependency licenses
are retained in `hsuh/static/licenses.txt` and legal bundle comments. OpenUI is
MIT-licensed software from Thesys, not OpenAI's private application source.

## Native Hermes control

With `HSUH_NATIVE_CONTROL=1`, HSUH connects to the existing authenticated,
loopback Hermes API server. It uses `/v1/runs`, native persisted sessions and
the native scheduler. Tools follow the **api_server** platform configuration;
configure it to match Telegram for toolset parity. HSUH does not change native
tool/approval settings automatically.

- Start tasks in chat, watch tool/subagent activity, send guidance to a running
  task and stop its exact run. Stopping stays pending until native settlement.
  Closing the browser or restarting HSUH does not cancel native work.
- Approve once, deny, or approve for the native session when offered. Every
  decision includes the current run and exact approval request ID. Permanent
  approvals and blanket approval responses are not exposed.
- Work & tools shows tasks, tool availability, native/Telegram sessions and
  schedules. Pause, resume or run existing schedules; ask Hermes in chat to create
  or edit them. Pausing a schedule does not interrupt an execution already running.
- Open existing transcripts and continue them. Controls target website-started
  runs; turns already owned by Telegram remain under that transport's control.
- Native transcripts persist in Hermes. A private SQLite ledger records workspace
  membership, admission IDs and bounded receipts. Ambiguous admission retries reuse
  the same native idempotency key, including after restart. Removing a workspace
  chat retains the native transcript. The UI displays the latest 100 messages and
  30 task cards, rather than an unlimited transcript export.

Set `HSUH_GATEWAY_KEY` to the existing local service key through a private
environment file, never a browser value or committed file. Only the backend uses
it, at `127.0.0.1:8642`. `HSUH_GATEWAY_PORT` can change that local port;
`HSUH_CONTROL_DB` optionally selects the ledger path (default
`~/.local/state/hsuh/control.sqlite3`). No arbitrary upstream URL is accepted.
Keep native interactive/smart approvals enabled. Hermes resolves its provider
credentials and applies its own memory, context, retention and diagnostic policy.
Website credential collection remains disabled. Clarifications use ordinary
chat replies in native mode; the native API has no clarify-card callback.

## Library-only working scope

The sections below describe the limited fallback when native control is disabled.

- Independent multi-turn conversations, with two concurrent Hermes workers and a bounded queue.
- Conversation-owned task cards and list indicators: queued, running, needs input, completed, failed, stopped; real start/elapsed time and response anchors. Switching chats or refreshing the browser does not stop a turn.
- Native Hermes `clarify` question cards, including single-select, multi-select and typed non-sensitive answers.
- Live VPS RAM total/used/available, swap and top process RSS. Values come from `psutil`/Linux `/proc`, not generated content. RSS includes shared pages and is **not additive**, nor per-chat attribution.
- Read-only native provider quota windows via `hermes usage --json`; optional existing Aperture quota-bucket discovery. Sources, fetch times, caching and unavailable states are visible. Aperture budgets are not ChatGPT subscription quota or invoices.
- Responsive desktop/phone UI and an online-only installable PWA, with an original small mascot, Mote. No client-side conversation storage, offline cache or push notifications.
- Optional public HTTPS entry through **Cloudflare Access**, with server-side RS256 JWT/issuer/audience/expiry validation **and an explicit owner email allowlist**. Other authenticated OAuth users cannot access the VPS.
- Alternatively, reuse an existing **ZeroFrame passkey login**, including its phone/QR and device invitation flow. Signed ES256 passes must match this site and the configured owner's immutable ID. Other people on the same issuer cannot open HSUH.

## Deliberate limitations

The library-only fallback permits **conversation + clarify only**. Full tools and
task controls require native mode above. Host statistics always use a separate
read-only metadata adapter.

Website credential inputs are visibly disabled. `/api/credentials` fails closed with 501 and does not parse or forward the payload. No native vault bridge is wired; never enter a password, token, payment detail or login code in chat/question cards. There are no working website-login forms yet.

Responses appear when a turn finishes; token streaming and raw reasoning are not exposed. Task summaries are deterministic public execution state, **not private chain-of-thought**. Text/fenced-code rendering deliberately does not execute model HTML.

All HSUH chat/task state is in **VPS process memory**: survives switching and browser refresh, not a server restart. It is not imported into existing Hermes sessions. Each conversation is capped at 30 turns, with up to 40 conversations; each turn has a 240-second execution deadline after acquiring a worker slot, including subprocess startup, stdin backpressure, human-input waits and exit. Queue waiting is excluded; failed/cancelled workers retain their slot and chat ownership through bounded teardown (up to 3 seconds before forced termination). No automatic weaker-model fallback. Provider failure becomes a failed task, never a fabricated answer.

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

### Existing ZeroFrame passkeys

For a hostname served by your existing ZeroFrame issuer, reuse its sign-in instead
of creating a GitHub OAuth application. The issuer must support `/sso` and publish
its public ES256 keys at `/.well-known/zf-sso`:

```sh
export HSUH_PUBLIC_ORIGIN=https://hsuh.example.com
export HSUH_AUTH_MODE=zeroframe
export HSUH_SSO_ISSUER=https://login.example.com
export HSUH_SSO_OWNER_ID=your-owner-id
python -m hsuh --port 8110
```

Open HSUH normally. It redirects to the existing passkey page and returns after
sign-in; an existing issuer session returns without another prompt. Phone/QR
availability comes from the existing passkey authenticator and issuer invitations.
No passkeys or GitHub credentials are collected by HSUH.

The issuer must grant this owner access to HSUH. The app additionally pins the
owner ID, verifies the issuer, exact audience, signature, role and one-hour maximum
lifetime on every request, and binds the callback to a ten-minute, single-use
browser challenge. Passes are kept in Secure/HttpOnly host-only cookies. APIs and
assets remain unavailable anonymously. Mutations still require the exact HSUH
origin and custom request header.

Keep the tunnel pointed at loopback with the original public Host. When migrating
from Cloudflare Access, **first deploy and verify the ZeroFrame gate at the origin**,
then replace the exact hostname's Access/tunnel checks. Keep private rollback
copies of the prior configuration; never disable authentication on other hosts.
ZeroFrame mode refuses missing configuration and does not inherit loopback access.
Restarting the app clears library-only chats; check for active work before a mode
migration. Native tasks and their ledger survive HSUH restarts.

### Cloudflare Access alternative

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
node tests/frontend_races.cjs
node tests/openui.mjs
python scripts/audit.py
```

No frontend bundler is required; static assets are served directly. Tests use generated fictional identities/signing keys and no live provider calls. Optional real integration check: `python scripts/live_smoke.py` (uses your configured provider/subscription for a few bounded turns). Read [CONTRIBUTING.md](CONTRIBUTING.md), [SECURITY.md](SECURITY.md) and [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## License / provenance

New HSUH code and Mote artwork are MIT licensed. No ChatGPT source, decompiled bundle, Hush source or proprietary assets are included. Familiar interaction patterns are not a claim of affiliation. Third-party dependencies retain their own licenses. Any future upstream reuse requires exact-source and license review first.
