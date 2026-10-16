# Native gateway compatibility

HSUH uses native `/v1/runs`, run status/events/approval/steer/stop,
`/api/sessions` and `/api/jobs`. Transcripts and tool policy belong to Hermes;
the browser never receives the API service key. Opening a Telegram transcript
does not grant this adapter ownership of a Telegram turn already in flight.

The tested Hermes 0.22.2 source (`d923a5eb487a17c0a68801bba9ef0f56c81040a8`)
advertises run approvals but has an inconsistent unattended predicate:
`execute_code` is denied as unattended even when the run has registered its
human approval notifier. Shell/tool approval presence already recognizes that
notifier. A real hosted harmless-print test reproduced the discrepancy.

[The compatibility patch](../patches/hermes-api-approval-context.patch) makes
`api_server` unattended only when its exact current approval session lacks a
notifier. Webhooks, cron, single-query calls and plain API calls keep their
existing unattended policy. It does not change approval mode, auto-approve
tools, disable the guardian or introduce a global bypass. Three native guard
regressions include a failing-before/passing-after arbitrary-code case.

Inspect the installed native source before applying the patch; later releases
may already contain an equivalent fix. Apply from a clean native checkout with
`git apply --check` followed by `git apply`, run the Hermes canonical approval
tests in an isolated checkout, then reload the native gateway while idle. The
patch is included for review and is not automatically applied by HSUH. Retain
native smart/manual policy rather than enabling unattended auto-approval.

Website credential collection, raw reasoning, clarify-card callbacks, file/media
upload and control of already-running Telegram turns are not provided by this
adapter. Clarifications work as ordinary chat replies. Tools operate on the VPS,
using whatever native services and credentials are installed there.
