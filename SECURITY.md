# Security

## Scope and threat boundary

HSUH is a **single-owner VPS client**, not a multi-tenant service. It runs with the VPS user's permissions; never expose it with arbitrary agent tools enabled. The initial integration permits only Hermes `clarify`. Existing native Hermes sessions, delegated jobs and credential vaults are not bridged.

- Default bind: `127.0.0.1`, exact loopback Host allowlist, same-origin mutations, custom request header, process-local HttpOnly/SameSite session cookie.
- Public mode: exact HTTPS origin; Cloudflare Access RS256 JWT validation with pinned team issuer, application audience, expiry/issued-at and signed owner email. Every path is protected. Edge Access must also restrict the owner. Never trust an email header alone or publish loopback mode behind an anonymous proxy.
- No query-string authentication, access logs, browser token storage, client chat persistence, offline caching or public telemetry. No conversation text is sent to telemetry/quota adapters. Provider stdout/stderr and arbitrary exceptions are not browser output.
- Application state is memory-only and bounded. Worker processes are isolated per turn, limited to two concurrent workers, time-bounded and stopped as a process group. This is **not an OS sandbox**.
- Website credential entry is disabled. Chat and clarification answers are model-visible; do not enter secrets. A user who pastes a secret in ordinary chat would be sending it to the configured model. HSUH does not claim to identify every possible secret.
- Native Hermes may maintain its own operational/authentication files. HSUH disables trajectories, memory, context-file injection and background review for its workers, passes no session database, and does not modify saved provider/profile settings. Standard library/OS process memory is not a secret vault.

## Reporting

Do not publish credentials, personal histories, raw authentication headers or exploit details in a public issue/PR. Use GitHub's private vulnerability reporting if enabled on the repository; otherwise open a minimal issue requesting a private contact channel without sensitive details. Maintainers should enable private vulnerability reporting before inviting reports.

The project is an early version, not an audited production platform. Separate code tests, independent source review, edge-configuration checks, authenticated hosted acceptance and actual-device PWA installation. An empty quota response is not an unlimited budget; a failed worker is not a successful assistant response.
