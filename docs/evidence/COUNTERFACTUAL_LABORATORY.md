# A bounded context rule, evaluated and retained

**2026-10-13 · NEMA-SEED-1 · implementation base
`50d1bc91870b9118a84706606d6a06008dffcdf7` · branch
`codex/counterfactual-laboratory`.** This report describes the commit containing
it. This is synthetic local evidence for V1-08/11, not a native model benchmark.

## Delivered loop

The motivating frozen question asks what a design decision and a separate crash
experiment jointly imply about retrying an interrupted dispatch. P0 selects the
design note. P1 additionally selects the explicitly linked crash evidence. The
result distinguishes durable admission from the uncertainty of an external effect.

The complete persisted loop is proposal → seven experiments (six fixed P1 cases
and a rejected relabel-only alternative) → independent P0/P1 attempts and outcomes
→ evaluations → attributed synthetic review → versioned adoption → rollback.
The adoption is a demonstration record, not the owner's approval or live activation.
The candidate implementation is `select_context` in
[investigation_evaluation.py](../../src/eidos/investigation_evaluation.py): preserve
mandatory seeds, add only their direct `relatedEvidence` references already inside
the horizon, and respect record/byte limits. P0 remains available as the rollback.

[ExperimentStore](../../src/eidos/investigation_alternatives.py) references canonical
investigations, exact artifacts, context packets, preview manifests and request pins.
Frozen snapshots preserve unknown fields. Immutable `cm_objects` share content;
additive `exp_records` reserve distinct occurrence/attempt identities. There is no
second current investigation. Every outcome and rejected alternative remains readable.

The [contract](../agents/EXPERIMENT_CONTRACT.md) documents the persistence and minimal
integrator API. No HTTP or UI surface was changed. Reinterpretation, described mocked
simulation, and proposed native branch have separate labels. Native attempt preparation
fails closed; this subsystem contains no executor or live effect replay.

## Observed fixed-set results

The [machine-readable artifact](COUNTERFACTUAL_DEMONSTRATION.json) retains exact
canonical/content/occurrence references, criteria denominators, selectors' omissions,
code digests, costs and comparison checks from one actual local fixture run.
Fixture claim annotations and a fixed extractor supply the answers; no model judges
them. The suite was pinned before experiment attempts. The structural held-out case
is predeclared, but is not a blinded benchmark.

| Fixed case | Evidence recall P0 → P1 | Grounded answer-facet coverage P0 → P1 | Additional canonical prompt bytes |
| --- | --- | --- | --- |
| Missing crash prerequisite | 1/2 → 2/2 | 1/2 → 2/2 | 773 |
| Structural held-out: provider visibility | 1/2 → 2/2 | 1/2 → 2/2 | 767 |
| Cycle / transitive link | 1/2 → 2/2 | 1/2 → 2/2 | 745 |
| Unrelated nearby evidence | 1/1 → 1/1 | 1/1 → 1/1 | 0 |
| Post-horizon reference | 1/1 → 1/1 | 1/1 → 1/1 | 0 |
| Relevant source exceeds budget | 1/2 → 1/2 | 1/2 → 1/2 | 0 |

Selection precision is 1 in both variants for all six cases. No fixture claim has
unsupported citations or out-of-horizon evidence. The budget case remains an explicit
failure of evidence sufficiency: P1 does not make every answer complete. The relabel-only
proposal adds no evidence or answer facet and is rejected. Three unchanged guardrail
cases correctly do not claim an improvement; the aggregate review requires nonregression
on every case and improvement on both discovery and structural held-out cases.

Selection byte limits count the evidence projection; evaluation separately measures
the full canonical prompt, including question and wrapper overhead. The largest observed
addition is below the declared 4,000-byte additional-context allowance. Token estimates
use UTF-8 bytes divided by four, rounded up. Actual provider tokens and prices remain
unknown. Native/model calls and native `turn/start` records are zero.

Only structured synthetic claims are graded. The original retained artifact and free-text
answer prose are not evaluated; their consistency and usefulness require review. A cited
record alone is not proof of entailment. These results establish bounded fixture behavior,
not improved real-model reasoning, human speed, or real-world generalization. Later
information hidden in prose/instructions is outside the record-membership leakage check.

## Reproduce and inspect

Use a new database path for the first command:

```bash
uv run python scripts/counterfactual_demo.py --db /tmp/nema-counterfactual-example.db
uv run python scripts/counterfactual_demo.py --db /tmp/nema-counterfactual-example.db --resume
uv run pytest tests/test_investigation_alternatives.py tests/test_investigation_evaluation.py tests/test_counterfactual_demo.py tests/test_counterfactual_crash.py
```

The observed run used `/tmp/nema-counterfactual-20261013-final.db`. Fresh and reopened
reports were identical except for the inspection-mode label. A fresh run creates new
investigation identities; reproducible behavior does not imply identical occurrences.
Resume reads the completed run and creates no attempts or evidence. An interrupted demo
without its final descriptive marker is refused with its ledger retained for inspection.

## Verification and independent review

`uv sync`, `uv run eidos --help` and `git diff --check` passed. The integrated
`uv run pytest` run completed with **429 passed, 2 skipped** (existing opt-in native
probes). The 68 new regressions comprise 43 evaluator/selector, 18 ledger, four
complete-demo and three abrupt-process-exit tests. Seed-context tests and additional
new-document/archive link validation passed. No frontend files changed or UI acceptance
was claimed. Focused tests cover immutable baseline/alternative histories, unknown fields, original `nativeArtifact`
after visible replacement, shared content with distinct identities, changed-key conflicts,
cross-experiment outcome rejection, two-connection terminal races, constructor/write
rollback inside an outer transaction, horizon escape, copied authority descriptions,
recorded-data refusal by the fixture evaluator, full adoption-case coverage, partial
rejection, and version-derived rollback.

Three subprocess regressions call `os._exit(73)` after preparation, inside an uncommitted
outcome transaction, and after outcome commit. Reopen retains the same attempt, exposes
zero or one committed outcome as appropriate, and emits no new trace records. This is a
local ledger guarantee, not exactly-once external execution.

Independent evaluation review caught the ungraded-prose ambiguity; reports now explicitly
name the scored surface and retained-artifact limitation. Reported execution failures
block an improvement recommendation. Review records preserve missing case IDs, omitted
evaluations and pending attempts rather than hiding incomplete or selectively chosen work.
An identical review retry retains that original snapshot after later work completes.

## Remaining integration

Expose the contract through the existing owner API and bind comparison apertures to
exact experiment/outcome IDs. Native dispatch must remain in the separately owned native
admission/recovery path, with explicit workspace and external-effect isolation. A future
human/model evaluation needs versioned judge inputs and limitations. No model turn,
native configuration change, AGENTS/skill rewrite, or rendered UI acceptance is claimed.
