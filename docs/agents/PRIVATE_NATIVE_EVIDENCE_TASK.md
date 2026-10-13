# Private native recording with attributable result publication

**2026-10-13 · base `6ea405a` · C6 / V1-02/05/06/07/12.** Root accepts
this implementation contract. The user-visible loop is the existing bounded
investigation, including its evidence inquiry, reload/recovery and grounded result
reuse. Raw control records must not enter ordinary source selection or exports.
No sign-in UI or live-account execution is introduced; production admission stays
closed. This is a prerequisite for the owned managed lifecycle, not a second loop.

## Observed gap and decision

A source/annotation labelled private in the main TraceStore remains readable by
`get(seq)` and direct context-selection SQL. Unknown account fields can therefore
be copied into a projected prompt. A separate private database per attempt is the
accepted boundary. Record the entire owned incarnation privately, including late
account events, unknown fields, errors, stderr and capture-gap payloads. Keep raw
JSON/unknown fields under the existing recorder semantics; do not switch sinks
when login finishes or pretend derived output is an original native record.

NativeInvestigationWorker remains the execution/recovery implementation. A narrow
PrivateInvestigationWorker adapter delegates to it, then publishes the recovered
result as a versioned, host-authored main-store `$capsule/result`. Default app
investigations use the adapter after acceptance; legacy public recordings and
artifacts remain recoverable without migration. Existing native launch admission
is unchanged. Default tests and browser acceptance use authored subprocesses only.

## Shared interfaces frozen for parallel work

- Root adds `TraceStore(path, *, role="workbench")`, retaining default/legacy
  behavior. Explicit `role="private-control"` marks a newly created private store.
  Ordinary open refuses a marked private store before schema/WAL mutation. Explicit
  role access is a trusted-host interface, not authentication against arbitrary
  Python/OS callers. Root exposes the store's normalized `path` for derived local
  storage placement; no browser request supplies a private path.
- history_ui owns new `src/eidos/private_investigation.py`, focused tests and a
  synthetic canary subprocess fixture. `PrivateInvestigationWorker` preserves
  `run(attempt, context, update, *, on_event=None)`, `recover(attempt, context)`,
  `close()`, command/profile/evidence properties needed by the existing controller.
  Own private creation, binding, exact raw persistence, private recovery,
  publication ledger and error mapping within this module. Root owns all existing
  production files, envelopes and API/inquiry/context integration.
- The adapter creates a private host-only directory outside native mounts, mode
  0700, and private files 0600. Default disk-backed location is a deterministic
  sibling of the main database; an in-memory host store may own a temporary root
  reused by adapters over that same object. Native cannot choose the path. Durable
  binding fixes capsuleId, attemptId, contextId, canonical context digest and
  source incarnation before it can be used for recovery. Names locate; they do not
  reconstruct a process or execution grant. Reopening evidence never starts native.
- Publication is `direction=internal`, `method=$capsule/result`, params containing
  version=1, attemptId/contextId/threadId/turnId, text, executionEvidence and typed
  provenance. It is explicitly derived. Preserve the existing public attempt
  coordinates; native IDs are identification metadata, not sign-in details. Do not
  publish unknown fields, control replies, raw errors or private filesystem paths.
  Result text itself is the deliberately published output, not guaranteed secret-free
  content. Existing context citations are recomputed by InvestigationStore.
- A main database ledger unique by attempt binds publication seq and canonical
  content digest to the private capsule. Append and ledger commit share one
  transaction. Lost replies/recovery reuse that exact publication; differing
  recovery conflicts. Child-authored publication-shaped records never establish
  the ledger. Public `outputSeqs` contain only main publication seqs, never private
  seqs. Return optional `outputEvidence={kind:"private-capsule-publication",
  version:1,capsuleId:<opaque>}` with the ordinary artifact fields. Root validates
  this envelope against the host publication and retains it in immutable artifacts.
- `resolve_result_evidence(attempt, context, artifact)` on the adapter returns a
  trusted-host dictionary with `kind="private-capsule"`, `capsuleId`, `trace`
  (the private TraceStore), `artifact` (original private recovery result) and
  `attempt` (bound private incarnation coordinates). It verifies binding and
  publication before resolving. Legacy public artifacts use the original main
  evidence path. Fixed public failures contain no raw native exception strings;
  exact diagnostics remain private. `on_event` must not leak raw private details
  through existing public progress projection.

## Preserve the existing protocols

Root adapts terminal_inquiry to use the resolver for private results while keeping
all request-pin, exact prompt, final-phase, native event/turn/source and preceding
request checks. Do not synthesize an appserver_to_client event from publication.
Main evidence retains the existing schema v1 observation. Private observations
use a versioned variant with typed capsule-scoped request/event references;
bare private seqs must never imply main-store coordinates. A missing private
proof cannot create a new inquiry admission. Already admitted continuations keep
their host ledger and causal description after controller restart.

Context lineage must not infer native outbound/acknowledgement from publication.
Record an explicit derived publication/private-validation receipt or honest
coverage gap; never place raw private traffic in the main ContextStore. Fixed
public errors apply at API callbacks and recovery too. Controller restart closes
live authority; only evidence recovery is available. This change adds no login,
refresh, export, cancellation endpoint, profile exemption or new model provider.

Root owns artifact/UI type integration and safe default activation. A later UI
lane may own the small renderer change: “Inspect published result” plus “Derived
publication; original native evidence retained privately.” Keep resource evidence
(synthetic/native-observed/unverified) separate. Ordinary and private result
comparison/reuse/snapshots retain the same exact artifact and context identity.

## Acceptance and stop conditions

Demonstrate ordinary conclusion and terminal inquiry through the existing API/UI
using synthetic subprocesses. Put canaries in unknown login/account/config/error,
late notifications, stderr and malformed-frame diagnostics. Preserve raw evidence
privately and exclude those canaries from public responses, source selections,
main database, HTML, drafts and errors, except deliberately published result text.
Check private/main seq collisions, lost publication/completion replies, database
reopen, one stable artifact/no process resend, inquiry offer/refusal/restart,
wrong capsule/context, spoofed publication and capture gap. Preserve legacy cases.

Bound newly retained raw records using the existing AppServer limits and explicit
private ledger limits; bound outgoing control records as well. Report logical
capture/record bounds separately from physical SQLite/aggregate retention costs.
Do not claim a whole-disk quota or silently discard evidence to meet one. Stop
before admitting a new attempt when its configured retention budget is exhausted.
No cleanup of existing user data and no secret-erasure claim. Ordinary open of a
private store must refuse; direct trusted OS access is outside that guard.

Owner worktree: history_ui creates `/tmp/nema-private-native-evidence` from 6ea405a,
branch `codex/private-native-evidence`. Root implements shared seams on main and
communicates exact diffs for local use; exclude those shared copies from agent
commit. Return a reviewed patch/commit and actual acceptance results. Integrator
owns combined Python/UI checks, actual browser inspection, final commit and push.
