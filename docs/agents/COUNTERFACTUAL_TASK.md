# Counterfactual laboratory task packet

**Active implementation slice, 2026-10-13.** Seed `NEMA-SEED-1`; base
`50d1bc91870b9118a84706606d6a06008dffcdf7`; branch
`codex/counterfactual-laboratory`. Integrate one tested commit on this branch.
Do not modify `main`.

## Outcome and contract

Serve [V1-08 and V1-11](../roadmap/V1.md): retain an exact baseline, compare a
named context-selection alternative under a frozen evidence horizon, evaluate
a fixed suite, and record attributable review, adoption, and rollback. Deliver
one complete synthetic demonstration and the persistence/provenance contract;
do not claim measured gains in real model reasoning.

The shared interface is [EXPERIMENT_CONTRACT](EXPERIMENT_CONTRACT.md). Reuse
canonical InvestigationStore, TraceStore, and ContextManifestStore identities.
The accepted scope is additive reference-based experiment persistence and pure
deterministic evaluation. Native execution may be described but fails closed
at preparation until separately integrated. No live Codex/provider calls are
authorized or required by this task packet.

## File ownership and integration

| Lane | Owned changes | Integration point |
| --- | --- | --- |
| Parent integrator | `src/eidos/investigation_alternatives.py`, evidence report, compact handoff, final commit | Own experiment lifecycle and shared interface; review combined suite. |
| Evaluation lane | `src/eidos/investigation_evaluation.py` and corresponding pure evaluation tests | Fixed-case evaluator consumes pinned contexts/outcomes; no persistence or execution effects. |
| Boundary/documentation lane | `tests/test_investigation_alternatives.py`, `docs/agents/EXPERIMENT_CONTRACT.md`, this task packet | Independently test references, authority, hindsight, retry, and adoption boundaries against implementation. |
| Demonstration lane | `scripts/counterfactual_demo.py`, `tests/test_counterfactual_demo.py` | Synthetic multi-thread P0/P1 fixture and complete lifecycle. |

Protected surfaces: `investigation.py`, `investigation_continuations.py`,
`api.py`, `investigation_worker.py`, and `ui/`. Propose integration requirements
in the contract; do not edit these files independently. One integrator owns
shared interfaces and the commit. Existing unrelated work must be preserved.
The lanes use disjoint files in the shared workspace on the already isolated
branch; additional worktrees are unnecessary for this allocation. Parent
coordination handles every shared interface change.

## Inputs and limits

Read the seed entry documents and relevant subtree instructions, then
[REFLECTION](../vision/REFLECTION.md), [SEMANTICS](../vision/SEMANTICS.md),
[Cycle B evidence](../evidence/INTEGRATION_CYCLE_B.md),
[context contract](CONTEXT_MANIFEST_CONTRACT.md), and
[Cycle B contract](INVESTIGATION_CYCLE_B_CONTRACT.md). Read source modules by
bounded assignment; share findings and immutable references instead of asking
every lane to reconstruct every subsystem.

Use synthetic public-safe traces. Preserve raw fields and provenance. Context
and artifact snapshots describe historical data; they never revive capability
authority. Review actor labels are attribution in a trusted-host store, not
authentication. A synthetic adoption demonstrates lifecycle persistence, not
the owner's approval or live activation.

## Acceptance and handoff

The demonstration compares P0 with P1 adding a specific relevant source or
changing a bounded projection. Pin the suite before evaluation and retain
held-out or regression cases. Report evidence selected/omitted, claim support,
usefulness proxies, hindsight leakage, additional context/resource budget,
assumptions, failures, and limits on generalization. Retain rejected outcomes.

Run focused new-module tests, `uv run pytest tests/test_seed_context.py`, and
the combined Python suite. No presentation changes are owned here, so UI
inspection is not an acceptance substitute or an additional delivery claim.
Record actual commands and results in the integration evidence, with revision
and limitations. Review the final diff for protected-file changes and public
data hygiene, then commit only on the assigned branch.

Stop or narrow a lane if it needs a protected module, native dispatch, arbitrary
effect replay, or a competing investigation controller. Bring the smallest
required change to the integrator. Before finishing, preserve the exact
implementation status, tests, open obligations, and next runnable integration
step under [CONTINUITY](CONTINUITY.md).
