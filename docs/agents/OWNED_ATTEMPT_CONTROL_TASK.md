# Owned attempt preparation and cancellation

**2026-10-13 · accepted root contract · base `7d3354a` · C6 / V1-05/07/12.**
User loop: dispatch one reviewed C0; inspect bounded preparation/progress through
reload; stop exactly that owned attempt; retain evidence and inspect the outcome.
The saved question/context remains pinned while local draft edits remain separate.
This is the existing investigation, not a second persistent session controller.

## Scope and exclusions

Keep production native admission closed. No real account/model/upstream calls,
credential import or new provider. Offline authored subprocesses exercise pending
preparation including a device-login-shaped exchange; no real sign-in UI/code or
secret-control endpoint is added in this slice. The preparation seam must support
later native managed login without copying the probe driver into production.
Cancellation itself is useful for every owned investigation and closes a current
product gap; additional fixture token variants are not the objective.

## Shared contract

- Existing claim/claim_followup pins attempt/context before any work. No saved
  context revision after dispatch is introduced. Add optional attempt.lifecycle
  with version=1, phase in preparing/awaiting-sign-in/checking/running/closed,
  updatedAtMs (host observation), and optional stopReason drawn from fixed codes
  cancelled/deadline/failed/completed/owner-unavailable. These are descriptions,
  not execution grants. Keep native result status separately; cancellation does
  not fabricate a native terminal or prevent a valid completed-prefix recovery.
- PrivateInvestigationWorker gains reserve(attempt_id), inspect_owned(attempt_id)
  and cancel(attempt_id). reserve is a trusted-host in-memory operation performed
  synchronously before the API starts its worker thread. It must not relaunch an
  existing durable attempt. cancel latches only an existing live reservation,
  including before child registration, and closes only that attempt's worker.
  An unknown/stale identifier creates no reservation and controls nothing.
  run may reserve itself for legacy direct host callers. close still stops all
  owned work; close_evidence and writer exclusion retain their current guarantees.
- inspect_owned returns {owned:bool, canCancel:bool}; no client, PID, login code,
  raw event or auth detail. Latching cancellation makes canCancel false. A closed
  reservation cannot be reused for another process. Persistence/reopen never
  reconstructs live ownership. A second adapter over the same DB owns nothing.
- API GET /api/investigations/:id/attempts/:attemptId/control validates exact
  current attempt within its investigation and returns {attemptId,owned,canCancel}.
  POST on the same path with exactly {action:"cancel"} performs that same check,
  cancels only an existing owned reservation. GET returns {attemptId,owned,canCancel};
  POST returns {investigation,control:{attemptId,owned,canCancel}}. No body can supply context, process, path or command.
  Existing loopback/origin/JSON guards apply. A foreign/stale attempt is 409/404;
  an already stopped or unavailable local owner is a stable read, never relaunch.
- Optional NativeInvestigationWorker preparation is trusted-host-only. It runs
  after initialize and before thread/start, consumes events through the existing
  recorder/pump ownership, reports only fixed lifecycle phases and has a finite
  preparation deadline distinct from the existing turn timeout. Accepted interface:
  optional preparation(NativePreparation), preparation_timeout default 120 seconds
  on both workers. The facade offers bounded request, recv_event from the existing
  pump, phase and remaining. Preparation RPCs allow only account/login/start,
  account/login/cancel, account/read and config/read. Return values are ignored.
  The hook cooperates with these bounded waits; this is not arbitrary-code thread
  cancellation. Default no-preparation flow
  retains current behavior and native profile gate. Closing the worker must wake
  preparation and latch cancellation before thread/start/turn/start. A late
  successful preparation cannot revive a closed client. No second model loop.
- Private adapter forwards only validated lifecycle descriptions, never raw hook
  return values. Root accepts lifecycle in update_attempt, including closure after
  a completed artifact without erasing its result, and publishes fixed public
  errors. Host observations remain private raw evidence plus public descriptions.

## Ownership and integration

- history_ui: isolated worktree at base, owns investigation_worker.py and
  private_investigation.py plus new tests/test_owned_attempt_worker.py and new
  authored fixture. Propose preparation callable before implementing that seam.
- Root: investigation.py, api.py, root API acceptance/demo and documentation.
- native_frontier: separate worktree, owns UI InvestigationPane/types and a narrow
  controller helper if needed; wait for fixed GET/POST envelope. Actual browser
  acceptance must use the integrated API with a held authored preparation.
- Independent reviewer: tests/review in separate worktree, no production edits;
  challenges cancellation/registration/late completion/recovery races.

## Acceptance and limits

1. Cancel a held preparation, release a late completion: zero thread/start and
   turn/start; only the exact child stops; repeated/stale cancellation cannot
   affect another attempt. Private canaries stay out of ordinary views/export.
2. Cancellation before worker-thread registration prevents any child launch.
   Cancellation after a turn request leaves unknown unless retained closed-source
   evidence supports a valid result. Existing publication race guarantees hold.
3. Reload same host preserves C0/attempt and owned control; local draft/pending-save
   identity survives. Restart controller reports no live owner and cannot start,
   login, refresh or resend merely by reading or cancelling persisted history.
4. Lost cancel reply is safe to retry. Concurrent recovery cannot publish before
   capture closes. Actual API+browser proof, private raw source checks and separate
   native/resource classification are required. Full default Python/UI checks.
5. Record limitations: advisory ownership is trusted host scope, not authenticated
   arbitrary process control; no exactly-once effects; host crash child cleanup
   beyond existing process containment requires separate evidence.

Next native joining experiment may reuse the accepted positive managed-text
controls, but needs its own explicit root packet before native execution. This
contract authorizes authored subprocesses, reversible repository work and tests.
