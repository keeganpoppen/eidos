# Orchestration protocol for future sessions

This is a working method for building Nema with agents. It is not a runtime permission policy and does not assume that a particular host exposes subagents, worktrees, or a named effort level. Consult [SOURCES](SOURCES.md) for the host documentation checked when this seed was created.

## O1. The coordinator owns the whole

Begin by reconstructing the destination and current state, not by distributing the whole repository to a swarm. Read AGENTS, START_HERE, destination, V1, and state. Inspect HEAD/status. Select one integrated user-visible outcome and state why it is the best next move.

Use high reasoning effort for uncertainty, architectural judgment, and integration when the host supports it. Do not hardcode a model ID, fictional `ultra` API parameter, or unlimited work budget. Availability, subscription limits, tool permissions, and cost remain explicit constraints.

The coordinator must exercise judgment. The user should not have to manually choose among every possible branch, fix each agent's context, or arbitrate conflicting schemas. Surface consequential ambiguities and proceed with justified, reversible choices where possible.

## O2. Scouts before writers

A useful first wave consists of short read-only investigations: evidence/context integration, UI experience, runtime/recovery, authority/admission, and evaluation. Each scout returns existing implementation, a concrete gap, likely change surface, counterexamples, and one recommendation. It must not write code or silently alter shared plans.

The coordinator then freezes a minimal shared contract and assigns implementers with disjoint ownership. Four well-scoped lanes with review are often more effective than a dozen uncoordinated writers. Add agents for genuinely independent work; cap total concurrency based on tools and observed resource pressure.

Use [WORKSTREAMS](../roadmap/WORKSTREAMS.md) as a menu of responsibilities, not a mandate to launch all lanes simultaneously. The active slice should remain one coherent loop.

## O3. Every task is a contract

A task packet needs:

```text
Task ID / goal / parent integration target
Base revision and relevant decision/V1 IDs
Read set: exact files or source ranges, not the entire chat
Write set: owned files; shared files requiring coordinator approval
Inputs and expected output contract
Invariants and failure cases to protect
Acceptance commands and evidence artifacts
Budget, stop conditions, and unresolved questions
Result format and reintegration point
```

Request a usable patch, tests, and a compact explanation. Reports should distinguish observed code, inferred behavior, proposed changes, and unverified claims. The worker does not get permission to inspect unrelated data or execute external actions simply because the task is ambitious.

## O4. Coordinate files and interfaces

Use separate worktrees/branches when available. A shared workspace requires an explicit file ledger. One agent owns `trusted.py` and other hot shared surfaces for a given cycle. Workers who need shared API changes propose them to the contract owner rather than racing replacements.

The integrator reviews diffs and semantic compatibility, runs the combined tests, resolves conflicts, and creates the final commit. Never force-push or overwrite intervening user/agent changes. Check branch state immediately before integration. Native threads, provider sessions, and file worktrees are different isolation boundaries.

Direct integration on main was authorized in the founding conversation; it is not a requirement to expose every intermediate broken state. Prefer a coherent tested integration commit. If the current host/user chooses PRs, follow that workflow.

## O5. Integrate early and evaluate at three levels

**Local correctness:** unit/contract tests, negative cases, serialization, deterministic fixtures.

**System correctness:** native adapter probes, replay/restart/race tests, context lineage, protected admission, and resource/cancellation behavior.

**User usefulness:** actual recovery/delegation/comparison in the rendered workbench. Preserve a screenshot or recording and a task outcome using sanitized data.

Do not let separate green suites substitute for a working boundary between them. An independent reviewer should try to falsify the accepted assumptions, particularly around liveness, duplicate effects, source truth, and unexpected authority.

## O6. Communicate partial results without flooding the human

Provide short substantive progress updates at meaningful stages: a discovered gap, a settled contract, an integrated test, or a tradeoff that changes scope. Avoid narrating every tool call or repeating the entire architecture. Keep one active recommendation; mention adjacent possibilities only when they materially change the decision.

Do not report that subagents worked unless the tools actually ran them. Without subagent tools, follow the same decomposition sequentially. Do not imply background work persists beyond the session unless the host genuinely supports and has scheduled it.

## O7. Preserve decisions, not conversational bulk

Before compaction or ending a session, use [CONTINUITY](CONTINUITY.md). Save task IDs, completed changes, verified commands, new evidence, unresolved assumptions, and a runnable next step. A fresh agent should not need to reread all worker messages.

Update canonical specs when a design commitment changes; otherwise leave them stable. Store large reports or transcripts separately and link to exact evidence. Do not promote an agent's interpretation into policy without review. A skill should teach a reusable procedure and reference the canon, not duplicate an ever-growing constitution.

## O8. Counteract our recurring failure modes

- **Endless elegant reductions:** after a conceptual result, connect it to a concrete workbench behavior. Deletion is valuable only when it preserves capability and lowers future cost.
- **Demo-shaped certainty:** ask which failure a test could not have found. “The test passes” is not “authority is secure” or “the UI is useful.”
- **Expanding every aside:** preserve promising ideas in the decision register; do not open all of them as tasks.
- **Unbounded more-is-better effort:** use budgets, selective context, staged synthesis, and independent review. Stop workers whose output cannot change the integrated result.
- **Context drift:** keep source revision, intended status, and supersession explicit. New code is not automatically the new vision; old prose is not automatically the current implementation.

The desired symphony has shared timing and a conductor. It is not every instrument playing every note.
