# Verification record

## Native Hermes control, 2026-10-16

- **48 Linux Python tests pass**, including eleven native adapter regressions for
  restart recovery, lost-admission idempotency, exact-run stop ownership, pending
  approval IDs, private event projection and owner/origin/body guards. Three
  production-controller scenarios cover deferred drafts, pending conversation
  creation and navigation during initial hydration (five cases). OpenUI parser
  cases pass.
- A real native terminal task returned the requested harmless marker; recreating
  the adapter recovered its exact task and persisted transcript. The runtime
  remained the configured model/provider.
- Hosted owner login reached Work & tools. A real terminal sleep task was stopped
  from that panel, native cancellation settled and its completion marker was not
  produced. Anonymous `/api/control` is denied. The ledger and local service key
  file have mode 0600.
- Desktop and 390px phone layouts were visually inspected; no document horizontal
  overflow and all five phone navigation buttons are at least 44px high.
- The installed native API's unattended-code approval mismatch was reproduced
  with a harmless print request and a failing native regression. The included
  compatibility patch passes **254 native approval tests** in an isolated source
  checkout, preserving unattended, webhook, cron and single-query behavior. The
  first run from inside the live profile was blocked in three existing tests by
  the native real-home I/O guard; the isolated run passes all 254.
- Hosted guidance reached the exact native run and its final response included
  the added marker. That same run was observed active immediately before an HSUH
  service restart, recovered active afterward, and then completed normally.
- The user explicitly chose to interrupt the other active native run for the
  compatibility reload. Native stop settled before gateway restart. Both Telegram
  and API returned connected. A real native approval card displayed the exact
  pending operation; Deny was submitted and Hermes confirmed no execution or
  workaround. The stricter manual test mode was restored to the original smart
  mode, and saved permanent approvals were verified unchanged.
- Independent security review remains pending; tests do not imply that review.

## Operations control centre and OpenUI, 2026-10-16

- The final operations candidate passed **37 Python tests on Linux**, including
  read-only native metadata projection, unavailable-source handling and gateway
  freshness. Generated OpenUI programs are checked against the actual SDK parser;
  valid components pass and unknown/tool-bearing/oversized programs are rejected.
  The three existing send/draft race scenarios, syntax checks, publication scan,
  dependency audit and both GitHub CI runs passed.
- Desktop and 390px phone layouts were visually inspected with fictional data.
  Navigation and the phone chat composer remained usable, with no horizontal page
  overflow. Local fixtures never called a model or provider.
- The real owner passkey session opened the hosted control centre. CPU/RAM
  history, process rows, native sessions, gateway state, token/call counters and
  Codex quota/reset data loaded from the actual VPS sources. Sample times and
  unavailable states are visible. Existing native jobs were not restarted.
- Through the hosted UI, a real Hermes turn produced an OpenUI checklist using
  Stack, Heading and Checklist. It completed in five seconds. The first checkbox
  was checked through the browser and stayed checked across polling. The actual
  OpenUI renderer was visible, with no browser error logs. Model-generated UI is
  labelled separately from authoritative host telemetry.
- Anonymous access to the added activity endpoint is denied at the deployed
  origin. Existing passkey/issuer/state/owner gates remain in place. Native job
  execution control, durable chat persistence and physical-device PWA installation
  remain outside this change. Independent source review is not implied by tests.

## ZeroFrame sign-in follow-up, 2026-10-16

- Added optional owner-pinned ZeroFrame ES256 SSO, reusing the issuer's existing
  passkeys and phone/QR/device invitation flow instead of requiring GitHub OAuth.
- The final candidate passed **34 Python tests on Linux**, including nine new SSO
  tests covering a complete signed round trip, wrong owner/key/issuer/audience,
  expiry, state/cookie binding, single-use and simultaneous callbacks, oversized
  requests, denied APIs/assets and unavailable-key-server throttling.
- Browser syntax checks, the three existing frontend race scenarios, diff checks
  and the working-tree/history publication guard passed. The SSO tests also pass
  on Windows; existing Linux process-group tests require Linux (`os.killpg`).
- On the operator-hosted HTTPS site, an existing real passkey session returned
  through the issuer and opened HSUH. The UI reported `ZeroFrame passkey`; a real
  Hermes turn completed with `HSUH_PASSKEY_OK`. Anonymous root navigation redirects
  to the configured issuer; protected API/assets return 401; a forged callback
  returns 403. Legacy edge authentication was replaced only after confirming the
  origin gate, with private rollback copies retained.
- This verifies reuse of an existing passkey session. A new physical phone QR
  scan and a second live issuer account were not exercised; wrong-owner rejection
  is covered with generated signing keys. Tests are not independent review.

The records below describe earlier artifacts and their acceptance boundaries.

Initial local checks were run on Linux with Python 3.14.7 and the existing Hermes source checkout at `297552a9d646119871391d202509822cd86330df`. The web dependency versions are pinned in `requirements.txt`; no frontend build/install was required.

## Executed acceptance

- `python -m unittest discover -s tests -v`: **16 passing tests**, covering live RAM semantics, exact Host/origin/cookie gates, size/field bounds, disabled credential endpoint, conversation isolation, duplicate-turn rejection, native-runtime failure without assistant text, real OS process-group cancellation, question-answer races, PWA no-cache behavior, quota projection and generated-key Access signature/audience/expiry/owner checks.
- `python -m compileall -q hsuh tests scripts`: passed.
- `node --check hsuh/static/app.js` and `node --check hsuh/static/sw.js`: passed.
- `python scripts/audit.py`: checked working files and, after commit, all reachable git blobs/commit metadata for secret/personal-data patterns. This is a heuristic publication guard, not an independent reviewer.
- Bandit 1.9.4: the initial scan found one low-severity assert-in-production finding. The assertion was replaced with an explicit runtime error. Final Bandit scan: **0 findings, 0 scanner errors**, 543 lines of application Python inspected.
- `python scripts/live_smoke.py`: **passed real configured-provider integration**, not a mock: native clarify card → pending input; a second conversation completed `HSUH_INDEPENDENT_OK` while the first waited; answer `Birch` resumed the first turn; a follow-up recalled `Birch`. Runtime identity remained `gpt-6.1-sol`, `openai-codex`, high reasoning. Saved profile configuration and gateway were not changed/restarted.
- Real browser verification at 1280px desktop and 390×844 phone viewport: no horizontal overflow; phone panels switch; primary panel-navigation targets are 44px tall; live RAM/processes and quota-source results render; disabled username/password inputs remain disabled. Both browser storage maps were empty. Service worker was registered/controlling the online-only app.
- Browser-native flow separately exercised a real clarify card while another chat finished, then returned `Birch` after the selected answer. Conversation indicators showed pending input separately from completed state.
- Native quota and the existing Aperture `/api/quotas` were actually queried. Native quota returned an account window; Aperture returned no configured budget buckets. No personal quota balances or private hostnames are committed here.
- Actual preview listener was verified bound only to loopback, with unauthenticated API requests denied. A browser session cookie unlocks loopback mode; public hosting requires the stronger Access configuration described in the README.

## Local correctness follow-up (public base `d86be075648b505cf7654d4428937681379ee237`)

- Regression suites first reproduced the premature-final/cleanup race, cancelled-turn cleanup admission, incomplete startup/drain deadline, failed-final history commit and delayed frontend send draft loss. Re-running the new fixtures against an extracted immutable public-base tree still fails; the candidate passes. No live provider is used by these fixtures.
- `python -m unittest discover -s tests -v`: **24 passing tests**, including real OS subprocesses with final→EOF→delayed exit, a following clarification, stop/new-turn callback interleaving, slow termination, non-reading stdin backpressure, slow startup and scaled full deadlines. Invalid/nonzero/error-after-final/duplicate-final protocols never commit assistant text or model history.
- `node tests/frontend_races.cjs`: **3 deferred-send scenarios pass** against the complete production controller: switching to B, editing A and editing A away/back to identical text. The A→B delayed-send scenario also passes in actual Chromium with exact production HTML/JS and fictional network data; this is not hosted acceptance.
- Native diagnostic disposal fixtures exercise the real worker and manager with an explicitly fictional SDK boundary on success, error, timeout and SIGTERM-ignoring/SIGKILL cancellation. The mode-0700 temporary directory is removed after teardown; the fixture native sessions directory receives no dumps. Model/provider/reasoning, exactly-clarify tools, memory/session/trajectory disabling and no fallback are asserted at that boundary.
- Installed native source `d923a5eb487a17c0a68801bba9ef0f56c81040a8` confirms unconditional error dumps to `agent.logs_dir`. An offline direct invocation of its actual dump helper under an isolated temporary `HERMES_HOME` confirms the redirect works and native redaction retains ordinary fictional conversation text. No configured-provider inference, active-profile changes or gateway restart is needed for this probe. Isolation/disposal is mitigation, not a no-disk-retention guarantee; see SECURITY.md.
- Python compileall, both production JavaScript syntax checks, the working-file/reachable-history publication guard and `git diff --check` pass. Bandit 1.9.4 initially flagged a generic exception/pass branch; explicit failure classification resolves it, and the final application scan has **0 findings and 0 scanner errors**.
- No live provider, hosted Cloudflare OAuth or actual-device PWA check was run for this follow-up. Earlier integration observations above predate these adapter changes and do not validate the final artifact. Independent exact-patch review remains required before pushing.

## Not established by these checks

Independent human/agent source-review approval is **not** implied by the implementation owner's tests, generated-key fixtures or Bandit. A separate reviewer must inspect the final artifact before production use.

Hosted Cloudflare OAuth/Access setup, exact-domain owner login, non-owner denial, authenticated phone/computer use, persistence across application restarts, full Hermes tool/job bridging, token streaming and a native vault credential bridge are **not verified/implemented here**. Actual-device PWA installation remains distinct from responsive-browser and service-worker checks. No production deployment or unrelated DNS/profile/gateway modification is claimed by this record.
