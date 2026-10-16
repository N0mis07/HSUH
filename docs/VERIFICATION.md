# Verification record

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

## Not established by these checks

Independent human/agent source-review approval is **not** implied by the implementation owner's tests, generated-key fixtures or Bandit. A separate reviewer must inspect the final artifact before production use.

Hosted Cloudflare OAuth/Access setup, exact-domain owner login, non-owner denial, authenticated phone/computer use, persistence across application restarts, full Hermes tool/job bridging, token streaming and a native vault credential bridge are **not verified/implemented here**. Actual-device PWA installation remains distinct from responsive-browser and service-worker checks. No production deployment or unrelated DNS/profile/gateway modification is claimed by this record.
