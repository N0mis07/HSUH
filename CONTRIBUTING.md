# Contributing to HSUH

Community issues and pull requests are welcome. Keep HSUH a clear, chat-first Hermes client with honest measured stats and native task controls.

1. Fork, branch, and make one focused change. Keep Python and browser assets dependency-light; rebuild the locally bundled OpenUI assets when changing their source.
2. Add a failing behavior/regression test first, implement the fix, and run the checks in the README. Live-provider tests must be opt-in and bounded; never spend another user's quota during ordinary CI.
3. Keep model text untrusted. Use text nodes, not `innerHTML`; never render arbitrary tool/provider exception bodies. Do not expose private reasoning.
4. Preserve conversation/job ownership, stop semantics, limits, and error states. A successful network request is not proof of completed agent work.
5. Do not relax loopback binding, public Access JWT verification, owner authorization, origin checks, request bounds or HttpOnly cookies. Security-sensitive PRs require a separate review.
6. Never add credentials, personal session dumps, telemetry captures, real emails, provider bodies, private hostnames or `.env` files to commits. Inspect both your diff and history before publishing. Use `example.com` / `example.test` fixtures and ephemeral keys.
7. Credential collection remains **disabled** until a native vault route is integrated and audited end-to-end. A UI form alone is not secure functionality.
8. Document actual acceptance evidence and remaining limitations. Do not replace a blocked integration with plausible responses or guessed balances.

Screenshots should show fictional test data only. If proposing upstream UI/code reuse, identify the exact repository, file/ref and compatible license; permission from an author does not automatically license code they copied from someone else.

Run `python scripts/audit.py` before pushing. Its lightweight checks are not a substitute for independent security review. Do not file public issues containing exploitable secret material; see SECURITY.md.
