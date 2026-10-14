# Managed attempt integration — offline evidence

**2026-10-13 · working integration base `8ed2f0a` · C6 / V1-05/07/12.**
[Contract](../agents/MANAGED_ATTEMPT_TASK.md),
[decision](../roadmap/DECISIONS.md#d31--separate-contained-startup-fresh-readiness-and-recorded-closure).
This checkpoint records authored protocol/browser acceptance and independent
review. Frozen runtime integration, the full suite and the separately reviewed
actual-native configuration/preparation probe passed on authored local transport. No real account, DNS, provider, model or
subscription call was made by these checks.

The separately reviewed first native compatibility run stopped before login,
thread or turn: native reported its resolved canonical provider URL while the
validator required absence. Cleanup joined, no endpoint was contacted and no
result published. The [compatibility packet](../agents/NATIVE_PRODUCT_MANAGED_TASK.md)
preserves that outcome and the source-supported exact-value correction. The
[second native run](NATIVE_PRODUCT_MANAGED_EXPERIMENT.md) passed: nine allowed
RPCs, six local CONNECT/HTTP exchanges,44 private records and one synthetic
publication among three public records. Reopen preserves that exact result without
restoring ownership. Earlier browser reports remain historical; the stricter
interpreter was exercised using a fresh disposable fixture, never edited receipts.

## Implemented loop

An explicit server flag enables fresh managed attempts from existing pinned work.
The private worker owns a disposable runtime and a full-context/source identity.
Fresh device login and ordered account/config readiness precede one private
receipt and the existing thread/turn loop. No alternate event pump or model loop.
The generic requested-policy manifest is a retained legacy projection; current
managed startup and admission are separately described by their private receipts.
Only the exact currently owned control response includes the transient challenge.
Stop targets that attempt; result publication and reopen reuse existing proof
resolution. The legacy native profile remains closed by default.

## Counterexamples that changed the implementation

| Counterexample | Resulting rule and evidence |
| --- | --- |
| Completed response, failed cleanup, failure marker cannot be stored | Managed publication/recovery requires one successful exact final close record. Missing record leaves raw completion private/unknown. Independent reproduction includes actual DB close/reopen and zero public rows/resend. |
| Copied, duplicate, failed or premature close, or native bytes after close | Historical recovery refuses inconsistent closure; no inferred resource state from absent evidence. Parent parameterized regression covers each case. |
| Stop arrives while startup guard owns registration lock | Signal cancellation before acquiring that lock and check after guard return. Held authored guard reproduces zero Popen and joined run/cancel threads. |
| Low-level startup unwind enters high-level close while concurrent cleanup needs the startup lock | Startup failure invalidates managed state and requests nonwaiting close; final close still requires joined resources. Independent composed reproduction drops from7.07s to0.058s with zero Popen and successful final cleanup. |
| Cancel admitted A, then start B | Fresh B remains awaiting its own login with no thread/turn. A's challenge and readiness cannot reappear. |
| Expired/foreign URL/code or delayed stale control | Server emits only fixed URL/bounded code/future deadline; UI retires challenges on expiry, completion, cancel, navigation and ownership loss. |

This closure rule deliberately loses automatic managed terminal recovery across a
host crash between native completion and close commit. Raw evidence is preserved;
legacy completed-prefix behavior remains unchanged. The trusted Python host and
local database access are not security boundaries against arbitrary owner code.

## Rendered browser acceptance

`scripts/managed_attempt_browser.mjs` runs against
`scripts/managed_attempt_demo.py`, the actual loopback API and Vite UI, with an
authored stdio runtime. The sign-in link is inspected, never followed. Authoring
an account reply does not establish native or subscription behavior.

The fresh strict-URL flow at1600px and390px captured62 API requests and exactly4 POSTs: A dispatch,
a committed cancel with its response deliberately lost, an explicit retry of that
same cancellation, and independent B dispatch. A remains unknown after release
with zero thread/start or turn/start. B completes one exact pinned prompt with a
synthetic result from private evidence. Two authored children total. Navigation,
reload, dirty fields and an authored pending-save identity survive; no challenge
is written to browser storage or ordinary API payloads. No external requests or
JavaScript exceptions. Parent and reviewer inspected code/link/deadline/Stop and
result rendering, with no horizontal overflow at390px.

After an actual API-only restart,24 GETs and zero POSTs recover the same attempt,
context and result. Both attempts are unowned/noncancellable, challenge absent,
with unchanged authored request logs and no new child. Parent-owned API/Vite and
agent-owned Chromium plus observed descendants were stopped; the temporary Vite
configuration was removed.

The initial dev-port5181 run returned403 on dispatch under the existing Origin
check, before any attempt/child. That failure remains separate. The successful
run used supported port5173; no production Origin guard was relaxed.

Current raw reports/screenshots remain under
`/tmp/nema-managed-attempt-strict-browser-20261013-*`; they are not repository
fixtures. Flow SHA256 is
`4f59d7e60c825d6aeca5dfaa8bbf0354f217d5d7b54925e7565e926263cb4e1e`;
reopened SHA256 is
`0883b10c7f1720bee76fa2775d752ccea6fb57ce2e99605d57022a39d97d8d78`.
Root inspected desktop/390px sign-in and result screenshots; the browser owner
inspected all eight captures. Chromium381838 and nine observed owned processes
exited, CDP9232 closed, API/Vite exited and temporary Vite config was removed.

Earlier reports under `/tmp/nema-managed-attempt-browser-20261013-*` remain
historical because their authored replies omitted the canonical resolved URL. Reproducible script SHA256:
`796cc1df72fbc2dca4bf25a8b7fe3c02d268259c6b252a071c56e22833ebb23d`.
Flow JSON SHA256:
`54a613c00e15476e3dd074e142a376f8bbaa6e1a2b759b54b8fbdced749fa622`.
Reopened JSON SHA256:
`2f4c37d46972564ce65ff3f38759b61e586cb343a4a337070de9526e83189893`.
Setup failure SHA256:
`fe69cc68aac25d6e3816afb1b44131a2bdf58158fba81b9460445f0c21f6bff6`.

## Checks and limits

Parent focused worker/control/private/legacy/owned checks:165 passed in4.36s;
subsequent managed cancellation/closure and seed checks:18 passed in0.67s.
Parent Svelte check:zero errors/warnings; Bun:108 tests/539 assertions; build passes.
Final parent Python suite: **1,528 passed /55 explicit native skips in56.80s**,
`/tmp/nema-managed-final-full.log`. Earlier containment integration passed
1,482/54 in55.28s; the final suite includes the strict URL and product-probe defaults. This includes packaged
wheel imports outside checkout, authored namespace/guard execution, startup/
resolver cancellation and local opaque WebSocket/settings traffic beyond20s.
Containment commit `802b68d`; high-level startup unwind fix `cb801b4`. No actual
native Codex or real DNS call is part of these default checks.
Independent reviewer:36 private/managed checks plus exact failed-marker/reopen and
held-startup schedules. These are offline checks, not live account usability,
model quality, complete provider-context capture or exactly-once effects.


Final focused follow-ups after the full suite:19 context-manifest/managed-worker
checks passed in0.77s for requested-policy wording; two retained native-report
replay checks passed in0.14s, including the newly added positive replay; seed
navigation5 passed. These checks launch no real native/model request. Independent
review accepted the second native report and rejected mutated closure, issuer-cut
and public/private source coordinates.


## CI compatibility correction

Commit `fa7eabf` pushed successfully, but [CI38489881645](https://github.com/keeganpoppen/eidos/actions/runs/38489881645)
failed two legacy request-manifest identity checks; UI check/build passed. A final
wording-only change after the full suite altered content-addressed requested-policy
bytes. The19 focused follow-ups did not include that compatibility fixture. Restore
the legacy string, keeping historical/new legacy request identities stable; actual
managed startup/admission evidence remains in the separate private receipts. No
runtime, native configuration, routes, bounds or probe bytes changed. This failure
is preserved rather than relabelled as a passing final checkout.

Correction verification:25 focused legacy/context/managed-worker checks passed;
full parent **1,529 passed /55 native skips in56.63s**,
`/tmp/nema-managed-ci-correction-full.log`. The extra test versus1,528 is retained
positive-report replay. All native/runtime bytes still match the second report.
