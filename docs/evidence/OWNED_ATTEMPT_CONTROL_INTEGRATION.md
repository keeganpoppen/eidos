# Owned preparation, cancellation and recovery

**2026-10-13 · integration base `7d3354a` · C6 / V1-05/07/12.**
The existing pinned investigation now exposes its last recorded preparation phase
and lets its current host stop exactly the work it owns. Reload retains context,
attempt, local draft and stop retry identity. Saved evidence remains inspectable
after cancellation and restart. [Contract](../agents/OWNED_ATTEMPT_CONTROL_TASK.md).
All subprocess/API/browser evidence here is authored; zero native/model/auth calls.
Production native admission remains closed and no real sign-in endpoint is added.

## Implemented behavior and challenged boundaries

The API reserves an attempt before starting its worker thread. Cancellation latches
that reservation before child registration, closes only its worker and never
allocates a handle from a copied name. A second controller cannot control the first
controller's child. The existing durable capsule binding prevents relaunch after
restart, including cancellation before any child or private database existed.

`NativePreparation` uses the existing bounded event pump and offers only fixed
account/login/config request methods. Its finite deadline is separate from the
turn deadline. It is a cooperative trusted-host callback, not a mechanism for
forcibly interrupting arbitrary Python code. Native profile admission precedes it.
Late completion after cancellation cannot start a thread or turn. After a sent
turn, cancellation does not invent a terminal: existing closed-reader validation
may still publish a supported completed result, otherwise the outcome is unknown.

Lifecycle observations have fixed phases/reasons and host timestamps; unknown
details cannot enter their public projection. Closure cannot regress or erase a
completed artifact. Live ownership is read separately and is not inferred from
historical progress. This preserves the difference between observed history and
current authority without adding another persisted session state machine.

Independent review reproduced a prelaunch cancellation that had no durable claim:
direct host retry after reopening could start it. Persisting the stopped claim
before returning fixes that schedule. Other adversarial schedules cover stopping
between claim and child registration, stale stop while another child prepares and
another adapter trying to recover/control active work.

A close failure retains its exact diagnostic privately and returns fixed HTTP503:
“Attempt stop was not confirmed; retry this same attempt.” Cancellation remains
latched, and explicit retry can re-close that same owned handle even when
canCancel is false. The browser stores stop retry identity separately from draft/
save state; GET, selection and reload never send a stop automatically. A delayed
read cannot restore stale control, and an acknowledgement cannot replace newer
result state or local draft edits.

## Verification

Parent full Python: **1,276 passed / 53 explicit native skips in 26.23s**, log
`/tmp/nema-owned-parent-final-suite.log`. Subsequent cancellation-error wording
change: all **12 API checks passed**. Five seed-context checks and diff whitespace
check passed. Independent worker/private/codex run: **148 passed**; four separate
authored subprocess boundary regressions are integrated. No native binary ran.

The actual API regression dispatches the held preparation, cancels it, releases
late fixture events and verifies zero thread/turn; starts a separate attempt;
retries the stale stop without affecting it; completes its exact frozen C0 once;
and reopens without extra launch/RPC. Main SQL export contains no private canary.

Parent Svelte check/build passed with zero errors/warnings. Final parent frontend:
**96 Bun tests / 486 assertions**. The new HTTP503 case
checks explicit same-attempt retry after 503 while an intervening GET reports
owned=true/canCancel=false. The 18 focused helper cases contain 70 assertions.

The real API/Vite/Chromium flow passed at 1600px and 390px. It captured **57 API
responses / four POSTs**: two dispatch 202, one committed cancel 200 whose reply was
deliberately lost, and an exact cancel 200 retry. Held preparation, dirty fields,
authored pending-save identity and pending stop intent survived reload without a
POST. Releasing the cancelled fixture created zero thread/turn. The separate
success created exactly one thread/turn and one derived publication, with exact
context/attempt/artifact retained across reload. Two authored child launches total.
No JavaScript errors, private canary/sign-in URL exposure or horizontal overflow.
Root inspected the held desktop and completed mobile screenshots directly.

An earlier harness falsely expected 200 from dispatch; its failure report remains
at `/tmp/nema-owned-attempt-final-real-flow-failure.json`. The corrected harness
reran the whole flow on a fresh database; no product fix was needed for that
failure. Successful report: `/tmp/nema-owned-attempt-accepted-real-flow.json`.
Screenshots share that prefix and suffixes held/lost-reply/cancelled/completed/
mobile-completed. Report SHA256:
`f4292ba0402ee9cfa1a480b4635d107c20ffd02ced055bfd9b34f235c3c9aa0a`.

Root stopped only its exact API process 348952 and restarted the same database as
process 349457. The subsequent browser run captured **24 GETs / zero POSTs**;
same contexts, attempts and artifact, owned=false/canCancel=false, no extra child
launch or fixture RPC. Report `/tmp/nema-owned-attempt-accepted-real-reopened.json`,
SHA256 `0b2411e858816ea9b2d9afdf1769eaeabef296674b7c07c86182bc6af7bfb94d`.
Its screenshot ends in reopened-unowned-history.png. The exact successful portable
harness is [owned_attempt_browser.mjs](../../scripts/owned_attempt_browser.mjs).
Fixture API/Vite/Chromium were stopped after acceptance; only synthetic artifacts
remain under `/tmp`.

Reproduce the authored API fixture with a fresh path:

```sh
uv run python scripts/owned_attempt_demo.py --db /tmp/owned-demo.db --output /tmp/owned-demo.json
uv run python scripts/owned_attempt_demo.py --db /tmp/owned-demo.db --resume --serve --port 8767
uv run pytest tests/test_owned_attempt_api.py tests/test_owned_attempt_worker.py tests/test_owned_attempt_boundaries.py
```

## Limits and next experiment

Ownership and private recording remain trusted-host boundaries, not authenticated
control for arbitrary callers. Graceful cancellation/restart evidence does not
prove host-crash child cleanup or exactly-once external effects. A recorded
awaiting-sign-in phase is not a real sign-in UI or account admission.

The [next accepted offline experiment](../agents/NATIVE_OWNED_WORKER_TASK.md)
joins the independently verified managed native transport to this actual worker,
preparation hook and private publication. It specifically challenges namespace
cwd, native policy acknowledgement, MCP inventory, deadlines and recorder closure
at their shared boundary. Real-account usability and production admission remain
separate unresolved work.
