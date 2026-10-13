# Specialist-originated inquiry — integration contract

Implementation based on `50d1bc91870b9118a84706606d6a06008dffcdf7`, branch
`codex/specialist-initiated-inquiry`. Additive to the
[Cycle B contract](INVESTIGATION_CYCLE_B_CONTRACT.md). Scope: Python/API V1-06/07/12.
[Typed UI contract](SPECIALIST_INQUIRY_API.ts) is supplied for the integrator and
Codecy D; no `ui/`, `codex.py`, or `investigation_worker.py` changes are included.

## Native seam for Codecy A

The base worker rejects all native server requests, including
`item/tool/requestUserInput`. Under that admitted policy this delivery uses
**terminal needs additional evidence → separately admitted new native attempt**.
It does not resume a hidden model stack or reply to a native interactive request.
The sibling native-specialist-v2 worktree had no new event contract available when
inspected. The integrator must reconcile this envelope with Codecy A before
claiming interactive support; no live interactive handle is fabricated here.

New context packets include a versioned final-output instruction. A specialist
can end its attempt with one explicit `final` / `final_answer` agent message:

```json
{"schemaVersion":1,"kind":"nema-needs-evidence","question":"Which source supports this?","cause":"The supplied ranges omit the acknowledgement."}
```

Only the complete JSON object with exactly these fields is accepted. Question and
cause are bounded, nonempty UTF-8 strings. Quoted examples, commentary, duplicate
keys, unknown protocol versions, and model-supplied identity/authority fields do
not become admitted specialist questions. Unknown native event fields remain in
raw evidence; the full original native artifact is preserved.

`investigation_inquiries.terminal_inquiry(store, id, worker)` is an evidence-only
adapter. It reuses `NativeInvestigationWorker.recover`, checks the frozen input,
exact final output, unique native incarnation request, event coordinates, and the
immutable dispatch pin's investigation/attempt/manifest association. It emits the
Python `NativeInquiryAdmission` / TypeScript `NativeInquiryCause` envelope. IDs,
question, cause, event sequence/hash and request sequence are frozen in the host
link, Eidos origin, continuation and inquiry. Copied result JSON cannot create a
live inquiry under another investigation. This function does not grant authority.
The trusted controller admits it through `open_specialist`; no HTTP route accepts
caller-invented native observations, native handles, holders, programs or checkpoints.

An interactive integration needs Codecy A's live request admission, exact typed
RPC identity, cancellation/disconnect policy and reply-delivery uncertainty
contract. `mode: "terminal-needs-evidence"` must not be relabelled interactive.

## Lifecycle and HTTP

Native result commit classifies an evidence request as `native-needs-evidence`
with outer status `needs-evidence` while `attempt.status` remains `completed`.
This blocks adoption or owner-review races before durable inquiry admission.
Malformed recognized protocol results are `native-inquiry-invalid`; admission
errors are visible as `inquiryAdmissionError`. Ordinary answers remain unchanged.

The controller automatically admits a valid specialist result into the existing
`Discover → AwaitDiscovery` program and shared `ProcessRuntime`. It preserves the
original result in `nativeArtifact`. An owner-started Cycle B review retains
`origin: "synthetic-eidos"`; this path uses `origin: "native-specialist"`.
There is no new requester/responder engine.

Existing inquiry GET and response POST routes retain offer/refuse/defer bodies.
They act through the existing trusted loopback owner service and source observer,
not authenticated remote-agent identities. Offer snapshots the exact selected
ranges. A source decision and recipient incorporation have different occurrences.
An offer adds evidence availability and a receipt with no factual claims.
Deferral spends source responder authority and leaves the waiting requester intact.

- `POST /api/investigations/:id/resume {}` and `recover {}` perform local repair
  only; they never launch native work. GET remains a pure read.
- `POST /api/investigations/:id/inquiries/:qid/cancel {requestId,note?}` records
  local cancellation and revokes host advancement. Cancellation is neither a
  Discovery refusal nor proof the historical generic TM socket was consumed.
  A terminal source response already admitted prevents cancellation. Cancelled
  inquiries remain readable; explicit resume/respond conflict, recovery returns
  their cancelled state. Restoring pre-cancel public JSON does not restore authority.
- `POST /api/investigations/:id/continue {requestId,continuationId,contextId}`
  returns 202 and explicitly admits **one new native attempt**. Use the prepared
  `continuation.nativeNext.contextId`, inspect its packet first, and persist
  requestId before sending. Exact retries return the existing state; altered reuse,
  competitors, wrong investigation/context, spent admission and stale IDs conflict.

After source incorporation, `nativeNext` holds a preview built solely from the
original frozen context, source response and outcome lineage. The preview is
immutable and has a separate manifest. Its creation does not change
`currentContextId` or send native work. Combined input remains limited to 256
records / 128 KiB; an oversized preview reports an error and cannot dispatch.
The prompt explicitly treats offers, prior output and notes as evidence to assess.

A new attempt/pin, advancement of its private admission record, previous attempt
and receipt history, and `currentContextId` change commit together before launch.
`attemptHistory` preserves A1; `nativeArtifact` preserves its result;
`artifactHistory` preserves the Eidos receipt. A2's new artifact includes
`continuedFrom` with inquiry/response/source occurrence/outcome/context lineage.
Review/adoption selects that new native result. The inquiry or local incorporation
receipt cannot be adopted as a new native conclusion. Context-lineage GET includes
historical attempt pins and their observations separately from A2's pin.

This slice admits one specialist inquiry and one follow-up per investigation.
If A2 again needs evidence, its result remains `needs-evidence`, is not adoptable
as a conclusion, and exposes the bounded-cycle limitation in `inquiryAdmissionError`.
No third turn is automatically or manually admitted through this continuation.

## State and recovery distinctions

Inquiry statuses `pending`, `deferred`, `offer`, `refuse`, `answered`, `refused`,
`cancelled` distinguish source admission/commit from incorporation. Cycle B keeps
its previous offer/refuse final statuses. `continuation.realizationStatus: failed`
plus `error` records a retryable local runtime failure without inventing a source
decision. Native `failed` and `unknown` stay on their own attempt; an unanswered
inquiry, cancellation and an uncertain native send are never folded into refusal.
`completed` on a continuation means local incorporation, not A2 execution.

Native callbacks carry an expected attempt ID. Late A1 callbacks and unscoped
callbacks after rollover cannot update A2. Recovery reads only recorded evidence;
a committed admission without delivery proof stays `unknown`, including failures
before worker launch. No checkpoint, pin, recovered question or HTTP retry resends
uncertain work. This is single admission per operation, not exactly-once external
execution.

Persistence adds `investigation_native_continuations` beside the existing private
runtime links and TM tables in the trace database. Its row is created only after
host-validated native inquiry incorporation; copying public labels or JSON cannot
upgrade a Cycle B review into native execution. Back up the whole database; public
JSON exports carry descriptions, not live authority. Existing contexts, prompts,
artifacts and adopted Cycle B work are not migrated or overwritten.

All validation is synthetic/local. No provider turn, subscription use, real native
interactive behavior, UI usability, distributed authentication, complete provider
context capture, or universal native containment is established by these tests.
