# Architecture / integration contract

## Composition

An Operate surface: conversation selector → focused transcript/composer → VPS inspector. Plain HTML/CSS/ES modules, with no copied product source and no frontend bundle/build. Tablet/phone panels are explicit navigation targets. Mote is an original SVG/PNG mascot.

FastAPI owns a memory-only map of chats. Each submitted turn creates a conversation-owned task with a UUID, state, timestamps and result anchor. One turn per conversation, two subprocess workers across all conversations. The browser polls; a changed selected chat never owns or cancels the backend worker. Server restart is an explicit loss boundary, not silent durable persistence.

## Hermes seam

Authoritative docs:

- [Python library](https://hermes-agent.nousresearch.com/docs/guides/python-library): `AIAgent`, a fresh instance per task, `run_conversation`, `conversation_history`, constrained toolsets.
- [API server](https://hermes-agent.nousresearch.com/docs/user-guide/features/api-server): supported OpenAI-compatible and `/v1/runs` surfaces, progress/cancellation/capability discovery. HSUH did **not** enable this gateway surface or restart the user's gateway. A future gateway adapter should discover `/v1/capabilities`, not assume every installed version exposes every event/job feature.
- [Credential vault](https://hermes-agent.nousresearch.com/docs/user-guide/features/credential-vault): future secure website sign-in must preserve the native vault's secret separation.

`worker.py` imports the existing Hermes source bootstrap and native config/provider resolver. It preserves the configured model/provider/reasoning effort, rejects external tool-capable app-server execution, passes `enabled_toolsets=['clarify']`, then asserts the actual tool snapshot is exactly `{'clarify'}`. No terminal, browsing, code execution, tool search or delegation is exposed. Config/state ownership remains the default Hermes profile; no config writes or gateway restarts.

Workers communicate by bounded NDJSON over private stdin/stdout pipes:

- `ready`: non-secret model/provider/reasoning identity.
- `question`: actual normalized native `clarify` callback fields; parent assigns a one-use question UUID and marks pending input. Answers flow back through stdin. No credential request type is accepted.
- `final`: provisional final text after Hermes reports `completed` and no failed/interrupted/partial status. The parent requires exactly one final, no following events, EOF and exit code zero before committing assistant text/history. A failed protocol/exit commits neither.
- `error`: generic failure; arbitrary provider exceptions and stdout/stderr are not browser/log content.

A turn's immutable task identity is captured at submission. A chat and worker slot remain busy until process teardown and diagnostic disposal complete, even after final/error/cancel. Process/work removals compare their exact owner; terminal state, question cleanup and successful transcript commit occur together without an await. Stop captures its original turn and cannot cancel a newer turn after a late await. One 240-second deadline starts after slot acquisition and encloses startup, initial write/drain, all response/input waits and process exit; termination has a separate 3-second grace before SIGKILL.

Native Hermes currently writes provider-error request dumps through `agent.logs_dir` regardless of `save_trajectories`. HSUH assigns this source-verified attribute to a fresh parent-owned private temporary directory before `run_conversation`, preserves the native secret redactor and removes the directory after process teardown. It does not change `HERMES_HOME` or profile settings for diagnostics. Ordinary conversation text can temporarily remain in these dumps, and abrupt parent/VPS death can leave temporary files: see SECURITY.md. There is no verified native no-content-retention switch in this integration.

HSUH retains only user/final text for the next turn, combining clarified input into the originating user turn to preserve role alternation. It drops model reasoning and tool traces. This reduced transcript is appropriate only for this limited toolset; a future full-agent API adapter should preserve native server-side session/tool history instead.

## Resource and quota observations

`telemetry.py` samples VPS host `/proc` via psutil in a worker thread. Used memory is total minus available. Process RSS cannot be summed or attributed to individual chats; process command lines/environment are never returned.

`quota.py` caches source reads for 60 seconds and projects only numeric provider limits and non-secret provenance. Native `hermes usage --json` already resolves account usage without running inference. Aperture's existing read-only `/api/quotas` returns configured budget buckets; an empty list means no buckets configured, not unlimited funds. HSUH currently does not parse populated bucket balances because that schema was not verified. All native background/delegated job visibility is explicitly unavailable until a gateway event/job bridge is connected.

## Hosting handoff

Required upstream: `http://127.0.0.1:8110`, preserving Host. The launcher has no non-loopback bind flag.

The default Cloudflare Access public mode uses these operator settings:

- `HSUH_PUBLIC_ORIGIN`: exact HTTPS origin, e.g. `https://hsuh.example.com`.
- `HSUH_ACCESS_TEAM`: Cloudflare Access team slug only.
- `HSUH_ACCESS_AUDIENCE`: audience of the self-hosted Access application protecting the entire origin.
- `HSUH_OWNER_EMAIL`: exact owner identity also allowlisted by the edge policy.
- `HSUH_APERTURE_URL`: optional private HTTPS origin for the existing quota integration (not an auth setting).

The first four are fail-closed. A signed Access JWT must validate issuer/audience/algorithm/expiry and owner email on every request; merely being logged into an OAuth provider is insufficient. Public proxying of default loopback mode is prohibited. No trust of proxy-supplied email headers or arbitrary `X-Forwarded-*` headers.

Keep Cloudflare DNS/routes/tunnel configuration separate and never overwrite unrelated records. Hosted owner authentication and non-owner denial require actual edge testing, not just local cryptographic fixtures. No installer or execution is required on Windows. PWA is online-only and intentionally retains no private response caches.

An existing ZeroFrame issuer can replace Access with `HSUH_AUTH_MODE=zeroframe`,
`HSUH_PUBLIC_ORIGIN`, `HSUH_SSO_ISSUER` and `HSUH_SSO_OWNER_ID`. `sso.py` verifies
ES256 passes using the issuer's public keys, exact audience/issuer, owner subject,
role, issued-at and expiry. The issuer owns passkeys, QR/device invitations and
site permissions. HSUH adds owner authorization and a bounded, ten-minute,
single-use challenge stored server-side and in a Secure/HttpOnly host-only cookie.
The signed nonce must match that cookie; the final path comes from server state.
The callback has a separate bounded cross-origin form POST entry; ordinary API
requests retain their existing same-origin/header/body checks. A public pass is
required for assets and APIs too, and the loopback Host is refused in this mode.
