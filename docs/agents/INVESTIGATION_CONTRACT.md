# Two-thread investigation — Cycle A contract

For the integrated additive context/review/comparison contract, follow
[Cycle B integration](INVESTIGATION_INTEGRATION_CONTRACT.md). This document retains
the original Cycle A seam and its historical limits.

**Provisional realization, 2026-10-12; base `b40d9ac`.** Serves V1-02/03/04/05/07/08. This is a bounded delivery contract, not a new kernel ontology or a claim that all V1 gates pass.

The additive [Cycle B API/runtime contract](INVESTIGATION_CYCLE_B_CONTRACT.md) defines the optional Eidos inquiry/review continuation, native-artifact compatibility, and exact UI integration fields. The original native-dispatch contract below remains in force.

Input: exact disjoint evidence ranges from two recorded native threads and one bounded question. Visible result: a saved immutable context preview, one native specialist attempt, an attributable artifact, source return, and explicit adopt/reject decision. Reopening retains identity; uncertain dispatch never automatically runs again.

## Shared wire contract (schemaVersion 1)

All objects use camelCase. Evidence selection: `{threadId, startSeq, endSeq, rationale}`. Resolve the inclusive range **within that thread**, require both endpoints to exist there, and freeze selected records. Each record contains `{seq, threadId, source, direction, method, rawText, sha256}`. Sequence numbers are local to this trace database. Raw bytes and unknown fields survive; names and hashes grant no authority.

Context: `{id, parentContextId, question, selections, records, projectedPrompt, coverage, createdAtMs}`. `coverage` explicitly identifies selected app-server evidence and unknown provider context. Prompt is exact reviewed native user input; other native instructions/tools/configuration are not claimed captured. Context revisions are immutable; an investigation may revise before dispatch. Dispatch freezes that revision. A later alternative is a separate investigation.

Investigation: `{schemaVersion, id, title, createdAtMs, contexts, currentContextId, status, attempt, artifact, adoption}`. Status is `draft`, `dispatching`, `running`, `completed`, `failed`, or `unknown`. Attempt initially null, then `{id, contextId, status, source, threadId, turnId, startedAtMs, timeoutSeconds, error}`. The host fixes the worker implementation, one native turn, read-only sandbox, isolated temporary working directory, 120-second turn deadline. This is not a token/cost guarantee or a remote security boundary.

Artifact: `{id, text, outputSeqs, contextId, attemptId, citations, unsupportedCitations}`. Citations use `[evidence:N]`; membership in the selected packet proves availability, not truth or entailment. Adoption: `{artifactId, decision, note, createdAtMs}`, where decision is `adopt` or `reject`; it records a conclusion choice and changes no source history or files.

## HTTP seam

- `GET /api/investigations` → `{investigations: Investigation[]}`.
- `POST /api/investigations` with `{requestId,title,question,selections}` → Investigation.
- `GET /api/investigations/:id` → Investigation.
- `POST /api/investigations/:id/contexts` with `{requestId,parentContextId,question,selections}` → Investigation.
- `POST /api/investigations/:id/dispatch` with `{contextId}` → Investigation; atomic one-attempt claim, repeats return existing state, altered context conflicts.
- `POST /api/investigations/:id/recover` with `{}` → Investigation; inspect recorded evidence only, never resend.
- `POST /api/investigations/:id/adoption` with `{artifactId,decision,note}` → Investigation; identical repeats are harmless, changed decisions conflict.

Creation/revision request IDs bind an immutable body; reuse with changed content conflicts. Invalid selection is 400, unknown object 404, stale/conflicting state 409. Reads cause no native calls. Context preview and dispatch are separate actions. Mutation requests are admitted only through the local JSON API; no generic TM authority interface is exposed.

## Implementation ledger

Integrator owns `api.py`, `serve.py`, integrated API tests, this contract, fixture/demo, and continuity docs. Context lane owns new `investigation.py` and `test_investigation.py`. Worker lane owns new `investigation_worker.py` and `test_investigation_worker.py`. UI lane owns `ui/src/`. Each lane starts at the base in its own `/tmp/nema-*-b40d9ac` worktree; integrator imports reviewed patches and makes the final commit.

Store interface: `InvestigationStore(trace)` with `create(body)`, `revise(id,body)`, `get(id)`, `list()`, `claim(id,contextId)` returning `(Investigation, claimed_bool)`, `update_attempt(id, **fields)`, `complete(id, artifact)`, `adopt(id,body)`. All transitions use SQLite transactions across connections, not only Python locks. Expose `InvestigationError(status,message)` for API translation. Store fixes attempt IDs/deadlines; worker cannot supply arbitrary authority.

Worker interface: `NativeInvestigationWorker(trace, command=None).run(attempt, context, update)` returns artifact fields `{text,outputSeqs,citations,unsupportedCitations}`. `update(**fields)` durably records source before native launch, then native thread/turn mappings. `recover(attempt,context)` returns those fields or None, using only matching recorded evidence. Failures retain raw evidence and propagate to coordinator, which marks uncertain outcome. Worker rejects unsupported native interaction explicitly. It owns and closes its app-server and temporary directory. No caller-controlled command, cwd, or provider is exposed over HTTP.

## Required counterexamples and limits

Interleaved threads; unknown raw fields; stale/reimported evidence after preview; duplicate/concurrent launch; altered request ID; crash before send and after native completion but before artifact commit; native failure with text must not count as success; citation outside selected context; repeated adoption; reload/source focus; no automatic native replay. Independent boundary and product reviews follow integration.

Pending native completion is exposed. A resumable specialist disclosure inquiry, ProcessRuntime-to-outer-Elaborate correlation, complete context lineage, arbitrary workspace forks, cancellation UI, and measured human task benefit remain later obligations. A fake app-server validates local adapter behavior only; real-native evidence must be reported separately.
