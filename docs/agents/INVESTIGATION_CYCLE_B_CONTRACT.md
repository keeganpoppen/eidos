# Cycle B — investigation continuation API/runtime contract

**Implementation contract, 2026-10-13; base `ac2c093`; branch `codex/investigation-continuations`.** Scope: V1-06/07/12 through the existing store and API. Root integrator owns investigation/store/API, this contract and reintegration; bounded runtime and integration-test lanes own separate new files. No changes to worker, Codex transport, UI, or generic kernel.

## Operational mapping and limit

`Investigation.id → attempt.id → continuation.id → ModelProcess / ProcessProtocol → checkpoint → DiscoveryInquiry → source decision → resumed ModelProcessOutcome → Artifact → adoption`.

The native worker currently rejects all interactive server requests. This slice therefore provides an explicit **synthetic Eidos evidence review of a successful native artifact**, initiated by the owner; it is not a question emitted by Codex and does not resume a hidden native stack. The fixed Eidos Closure uses existing Discover/AwaitDiscovery and ProcessRuntime, with no external callbacks. The final artifact retains the native answer and adds an attributable disclosure/refusal receipt; it does not claim a fresh model synthesis.

Native dispatch still durably claims its single Attempt before any worker launch. No continuation on failed/unknown/running native attempts, no automatic redispatch, no second native turn. `attempt.status` always describes native execution, separately from the outer work status. An adopted Cycle A result cannot be reopened by this slice.

## Additive HTTP contract

Existing Cycle A endpoints remain unchanged. New JSON mutation bodies reject unknown fields:

- `POST /api/investigations/:id/continuation` — `{requestId, attemptId, question}`. Requires a completed, unadopted native artifact. Admits one continuation per investigation, then advances to a pending Inquiry. Exact retry repairs unfinished work; altered request reuse or a second continuation conflicts.
- `GET /api/investigations/:id/inquiries/:inquiryId` — the investigation's addressed inquiry, including its responses. Pure read.
- `POST /api/investigations/:id/inquiries/:inquiryId/responses` — `{requestId, decision, note?, selections?}`. Decision is `offer`, `refuse`, or `defer`. Offer requires reviewed evidence ranges in the Cycle A selection shape; other decisions reject selections. Offer snapshots exact records before source admission. Exact retry returns/repairs the same response, including an old defer retried after a terminal response. A new terminal competitor conflicts.
- `POST /api/investigations/:id/resume` — `{}`. Advances only this investigation's host-admitted Eidos continuation and reintegrates its result; never executes native work. Existing `recover` also repairs Eidos continuation state after native reconciliation.

Errors retain Cycle A 400/404/409 semantics. Runtime failure leaves durable intent/checkpoint/response and a visible continuation error; retry uses the same identity. HTTP supplies no holder, executor, program, protocol, projection, checkpoint, Cut, or authority grants. There is no generic TM endpoint.

## View model for the UI

Cycle A JSON remains schemaVersion 1; `continuation` is absent/null on legacy objects and is an additive versioned object on new ones. Outer statuses add `pending` and `resuming`. A continuation carries `schemaVersion:1`, `id`, `attemptId`, `origin:"synthetic-eidos"`, `question`, `status` (`preparing`, `pending`, `resuming`, `completed`), `error`, `processId`, `protocolId`, `modelId`, `checkpointId`, `initialCheckpointId`, `outcomeId`, `contextName`, and `inquiry`.

Inquiry: `{id, question, status, openedOccurrenceId, responses}`. Status is `pending`, `deferred`, `offer`, or `refuse`. Response: `{id, requestId, decision, note, status, evidenceContext, occurrenceId, disclosureCutId, responseValueId}`; response status is `admitted` or `committed`. `evidenceContext` is null except on offers, where it is the exact frozen Cycle A context packet. Source response and requester incorporation are separate causal records.

On continuation admission, the existing artifact moves to `nativeArtifact` unchanged, and `artifact` becomes null until reintegration. Adoption is unavailable while pending. Final `artifact` preserves the Cycle A text/output/citation fields and adds `kind:"eidos-evidence-review"`, `nativeArtifactId`, `continuationId`, `processId`, `outcomeId`, `inquiryId`, `responseId`, `decisionOccurrenceId`, `contextName`, and `evidenceContextId`. It includes an explicitly labeled Eidos receipt after the unchanged native answer. Citation availability is not entailment. Adoption selects this final artifact and never applies a patch or grants authority.

The UI should label this as an owner-started Eidos review, show the question and pending state, offer/defer/refuse controls, source decision history, and the native result separately. Use returned IDs for request retry and navigation. Persist a requestId before sending. GET/poll has no advancement side effects. Do not infer native success from outer status; inspect attempt.status. Never expose resume controls for arbitrary historical checkpoints.

## Persistence and recovery

Additive tables share TraceStore's SQLite database. Existing rows need no rewrite. A host-only runtime linkage table records admitted continuations; public/historical descriptions do not create that linkage. TM uses a private shared-connection adapter with locked transactions/savepoints, so its existing semantic algorithms and ProcessRuntime remain unchanged. No external work is allowed inside these local transactions.

Admission intents and response snapshots commit before semantic realization. Stable operation keys recover preparation, occurrence, checkpoint, and outcome writes. Source decision realization and its linkage commit locally together; requester advancement/reintegration happen afterward. Deferral may commit an actual source DiscoveryDefer but never completes or consumes the waiting requester. Repeated pending checks create no occurrences. Copying JSON or a historical Eidos Value cannot admit a new live continuation.

Required failures: before native claim commit, after claim/before launch, before external launch mapping, after native call/before artifact commit; before/after semantic admission/preparation/commit/checkpoint/response/outcome; before outer reintegration; lost HTTP responses; concurrent duplicate and competing requests. Evidence must distinguish synthetic/local protocol verification from real-native acceptance. No live native calls are planned for this slice.

## Final implementation / compatibility details

The contract is implemented in `investigation_continuations.py` (admission/reintegration), `investigation_runtime.py` (fixed program and existing-runtime adapter), and `api.py`. The shared ledger is `investigation_runtime_links`; its runtime state is host-only. SQLite initialization adds existing TM tables beside the existing trace/investigation tables. Back up the whole database as one unit; exporting only investigation JSON exports descriptions, not resumable authority. There is no continuation import/admission endpoint. Unlinked historical rows remain readable and cannot resume; startup records their admission error and continues recovering admitted work.

Success codes: continuation admission 202; response, resume, recovery, inquiry GET 200. A 2xx mutation acknowledges the durable outer state; inspect `continuation.error` and `status` to know whether local realization finished. Ordinary runtime errors leave the response or initial intent persisted, are returned as visible errors on the continuation, and can be repaired with the original request or `/resume`. No user action parameters belong in resume/recover bodies. Reads return the current state, so an old successful request retried after further work returns the current investigation plus the same historical response; it does not rewind the view.

There is one optional review and one inquiry per native attempt in this slice, with at most 31 deferrals followed by a terminal response. A second review or native attempt requires a separate investigation. Changing native context after dispatch remains prohibited. `currentContextId` and native artifact `contextId` continue to identify the exact native input; `contextName` identifies the inner semantic Context and `evidenceContextId` identifies the offered packet. The offered packet's inherited `projectedPrompt` is a data projection only: it was not sent to a second native turn.

`initialCheckpointId` is immutable. `checkpointId` remains the last suspended checkpoint after completion and may then describe spent authority; `outcomeId` is the completed process result. IDs support attribution, not authentication. There is no generic Name resolution or authority mutation route. The source response occurrence is exposed on the response and final artifact; the requester incorporation and finish are retained in the named ModelProcessOutcome's existing event lineage.

Legacy rows retain schemaVersion 1 and their exact original artifact/adoption. A native result can enter this review only before adoption. During review the original artifact is preserved in `nativeArtifact`; late native callbacks or repeated native `complete` calls cannot overwrite the pending review or final artifact. New final artifacts deliberately retain original native citations; the disclosure receipt introduces no new inferred claim. Older clients can read the additive fields but cannot render the new workflow without implementing it. An old binary does not resume Cycle B work; keep the new code to operate active reviews. No original trace bytes, native configuration, or UI files are migrated.

Reviewable failure evidence is in `test_investigation_continuation_failures.py`, `test_investigation_continuation_concurrency.py`, `test_investigation_continuations_api.py`, and `test_investigation_runtime.py`. Existing worker tests retain the external-send/deadline/failure coverage. Source selection/decision and their outer links use one local SQLite transaction; faults inside that segment roll it back to its durable response intent. Inner requester operations commit independently, exercising committed-occurrence/checkpoint/outcome repair before outer reintegration. This is a local placement choice, not a distributed atomicity or exactly-once external-effects claim.
