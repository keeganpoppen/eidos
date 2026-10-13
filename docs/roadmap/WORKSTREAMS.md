# Workstreams: a coordinated route to the reflective workbench

**Status:** proposed work allocation, not currently running agents. Use [ORCHESTRATION](../agents/ORCHESTRATION.md). Available tools, budgets, and current user authorization determine how many tasks can run at once.

## Integration before parallelism

An integrator owns the V1 use case, shared contracts, and final merge. Delegate independent implementation and independent criticism; do not let many agents each design a slightly different Nema. Read [STATE](STATE.md) first: discovery and a general ProcessRuntime already exist.

Before coding, agree a small versioned boundary proposal covering:

- **Evidence reference:** source kind, native/local identity, content/range identity, provenance and coverage. Noncontiguous selections must be representable.
- **Context revision:** source selections, instruction/model/lens versions, selection rationale, known/unknown native realization, content identity and adoption occurrence.
- **Investigation/attempt:** goal, baseline, context revision, executor/place, native thread mapping, allowed operations, budget, pending continuation, result/adoption identity.
- **Artifact/action:** typed result/reference, source support, proposed operation, preconditions, authority scope, and eventual receipt or uncertain outcome.

These are proposed interface obligations, not mandatory new kernel classes. A lane must not silently conflate an artifact's Name with permission to execute it. Freeze enough field meaning for a vertical slice; keep extensions versionable.

## Dependency map

```text
W0 contract + scenario selection
    |---- W1 evidence bridge -----------|
    |---- W2 context lineage ----------|---- W3 workbench ----|
    |---- W4 outer runtime/recovery ---|---------------------|--> V1 loop
    |---- W5 admission review ---------|---------------------|
    |---- W6 evaluation ---------------|---------------------|
    `---- W7 reflection proposal ------|---- after baseline -|

W8 continuity/integration runs throughout; it is not another competing runtime.
```

Initially use read-only scouts for these lanes and then a bounded set of implementers. A useful first cohort is evidence/context, workbench, runtime/recovery, and independent boundary/evaluation review. Increase parallelism only when contracts and file ownership permit it.

## W0 — Integrator and contract steward

**Question:** what must cross subsystem boundaries for one two-thread investigation to survive and remain inspectable?

**Read:** destination, V1, state; `trace.py`, `semantic_tree.py`, `api.py`, `process_runtime.py`; relevant tests.

**Deliver:** a short contract ADR, fixture names, dependency/ownership plan, and a runnable end-to-end scenario. Keep a live integration branch/worktree and resolve interface conflicts before other agents compensate locally.

**Acceptance:** one agreed reference can be resolved through source evidence, context preview, worker input, and returned artifact. Both UI and runtime use it. No agent needs the founding chat.

**Owns:** shared contract changes, root docs, API coordination, final merge. Other agents propose shared changes rather than editing them simultaneously.

## W1 — Evidence, import, and semantic projection

**Question:** can native history and live events become stable addressable evidence for a real investigation?

**Starting points:** `codex.py`, `codex_proxy.py`, `trace.py`, `semantic.py`, `semantic_tree.py`, `view.py`, summary-tree docs and trace tests.

**Deliver:** stable evidence/range references, import/live provenance labels, bounded retrieval of disjoint ranges, cross-thread selections, and fixture-backed unknown-field/ordering tests. Keep normalized projections rebuildable. Preserve existing weighted hindsight behavior where useful; do not replace it with record-count chunking.

**Contract:** exports evidence references and selection results; does not grant access or spawn workers merely because a Name resolves.

**Tests:** V1-01/02/04; repeated import, absent native fields, mixed live/import sources, long tool detours, reverse links, raw support reconstruction.

**Boundary:** coordinate public API changes with W0; do not also rewrite `trusted.py`.

## W2 — Context manifests and selection

**Question:** what did we intend to supply, what was available, and what can we demonstrate was used?

**Starting points:** `epistemics.py`, `cuts.py`, semantic Values, Codex adapter and instruction/config discovery. Read MEMBRANE.

**Deliver:** a reviewable immutable context packet for the target task; ingredient versions and inclusion rationale; content/delta representation; explicit desired/projected/observed states; activation probes for selected native ingredients; private snapshot storage policy.

**Contract:** consumes W1 evidence references and emits a Context revision used by W3 and W4. Model context and runtime configuration are related but not interchangeable.

**Tests:** V1-04/09; structural sharing of unchanged inputs, immutable historical resolution, two attempts in one turn with different observed context, stale file-watch assumptions, missing provider capture labelled unknown.

**Boundary:** no global AGENTS/config mutation; no complete-provider-context claim from filesystem evidence alone.

## W3 — Reflective interaction and compositor

**Question:** can the owner manipulate this work without thinking about framework administration?

**Starting points:** `ui/`, `api.py`, `serve.py`, `view.py`; INTERACTION and existing UI scripts.

**Deliver:** linked navigation/evidence/work/comparison apertures for the chosen investigation; context preview/diff; native result/diff/question rendering; saved selection/layout; one reviewable arrangement or aperture command.

**Contract:** uses shared object/evidence identities and action preconditions, not UI-local substitutes. Reads results and status from persisted state.

**Tests:** V1-03/04/06/10; real rendered screenshots, long text/diff handling, keyboard navigation, noncontiguous evidence, no focus theft, reload continuity, undo. Use sanitized fixtures.

**Boundary:** UI build passing is necessary but not sufficient. Coordinate one API seam with W0 rather than expanding endpoints ad hoc.

## W4 — Durable outer investigation and native execution

**Question:** can a pending multi-process investigation resume as the same work, not just as a restarted inner model?

**Starting points:** `process_runtime.py`, `model_process.py`, `observer_process.py`, `meta_protocol.py`, discovery/exchange, `codex.py`, API task control.

**Deliver:** persisted outer attempt identity; native worker/session mapping; bounded scheduling; pending inquiry propagation to the UI; continuation correlation after restart; cancellation/unknown-outcome handling; selected result reintegration. Reuse the generic ProcessRuntime instead of reviving requester/responder engine species.

**Contract:** consumes a versioned context and admitted task; exposes status/events/artifacts with causal references. Never silently reruns a process merely because the outer request was retried.

**Tests:** V1-05/06/07/08; fail before/after each native/provider/prepare/commit/resume boundary; repeated delivery; request ID with altered payload; completed inner process while outer task is pending; native crash/coexistence.

**Boundary:** no claims of native stack serialization or cross-domain atomicity. Treat existing synchronous callbacks as adapters, not a finished scheduler.

## W5 — Authority/admission and failure review

**Question:** which actors can actually cause each transition, and why are its outputs legitimate?

**Starting points:** `trusted.py`, `authority.py`, `genesis.py`, process runtime, model/executor registration, source disclosure, exposed API endpoints.

**Deliver:** explicit trusted-computing boundary, admitted-call paths, attacker/caller model, counterexample tests, protected transition admission, bounded execution/resource policy, and crash-window disposition rules. Preserve narrow TM mechanics; do not demand a universal proof checker when a constrained trusted adapter suffices.

**Tests:** V1-12 plus cross-cut concerns: guessed identifiers, substituted holder strings, arbitrary output grants, one low-privilege input to high-privilege output, unauthorized registration, historic replay, stale handoff, concurrent acceptance, terminal mismatch, subprocess/resource failure, prompt injection into persistent instructions.

**Contract:** reviewer may report blockers without independently redesigning all subsystems. One owner controls `trusted.py`; shared findings become a coordinated patch plan.

**Boundary:** observing a security problem is not permission to exercise it against the owner's live accounts or external systems. Use local synthetic domains.

## W6 — Evidence and evaluation harness

**Question:** does the integrated tool change the owner's work, and are improvement claims reproducible?

**Starting points:** existing tests, summary-tree fixtures, sanitized long histories, UI workflow.

**Deliver:** a representative task/fixture set, expected evidence/rationale, recovery scenarios, baseline measurements, native probe procedure, and an acceptance report keyed to V1 IDs. Provide independent adversarial scenarios rather than solely testing implementation-shaped happy paths.

**Tests:** all V1 scenarios, especially evidence sufficiency, hindsight leakage, duplicate effects, budget/cancellation, and source citation validity. Separate mock, local integration, real-native, UI-observed, and human-evaluated results.

**Boundary:** no private trace publication and no fabricated benchmark wins. A missing environment is reported as unverified, not passed.

## W7 — Reflection and controlled improvement

**Question:** can the workbench improve one part of its own workflow using its own records?

**Starting points:** REFLECTION, semantic context/model pipeline, W1–W6 artifacts.

**Deliver:** one grounded improvement proposal to a context builder, lens, wrapper, or arrangement; baseline/alternative experiment; reviewable patch; adoption/rejection and rollback. Record the auditor's own inputs and operations.

**Tests:** V1-08/11; source support, prospective vs hindsight distinction, held-out regression checks, bounded native calls, unchanged live world during simulations, explicit instruction adoption.

**Dependency:** needs a usable baseline. It must not become a separate autonomous “improvement platform” before the owner can perform the underlying task.

## W8 — Context stewardship and integration evidence

**Question:** can a new session and a new agent cohort continue without hidden conversation state?

**Deliver:** a compact current handoff, decision updates with stable IDs, task ownership, validated file links, actual test commands/results, blockers, and one runnable next action. Follow CONTINUITY; keep source and interpretation separate.

**Boundary:** root policy/vision edits are not an automatic reward for finishing a task. Preserve high-level intent and label changes as proposed, accepted, superseded, or verified.

## Coordinated future axes

After a working V1 loop, choose experiments based on observed bottlenecks: richer derivation graphs and uncertainty; browser/terminal sidecars; multi-window compositor hosts; authenticated remote placement; continuation code migration; more complete provider capture; role/protocol typing; reusable context/skill synthesis; explicit resource scheduling. These are branches, not mandatory prerequisites.

The next thousand sessions need direction and an integration discipline, not a thousand simultaneously open tracks.
