# Counterfactual experiment and evaluation contract

**Implemented additive trusted-host contract, 2026-10-13.** Base
`50d1bc91870b9118a84706606d6a06008dffcdf7`, branch
`codex/counterfactual-laboratory`; serves [V1-08 and V1-11](../roadmap/V1.md).
The source of context meaning remains the canonical investigation packet.
Experiments relate existing investigations, exact artifacts, frozen context
revisions, and evidence; they do not introduce a second current investigation.
See [the task packet](COUNTERFACTUAL_TASK.md) for ownership and validation.

## What the experiment means

| Mode | Interpretation | Execution boundary |
| --- | --- | --- |
| `reinterpretation` | Apply another selection or interpretation to fixed recorded evidence. | Pure local derivation; no historical world transition. |
| `simulation` | Describe a historical continuation with explicitly mocked effects. | Mock effects and outcomes are immutable descriptions; this ledger does not execute or verify a mock interpreter transcript. |
| `native_branch` | Describe a proposed new native attempt. | Representable, but this module rejects attempt preparation. A future adapter must separately admit authority, isolate the workspace, and handle uncertain external outcomes. |

An experiment preserves the baseline investigation/context/exact artifact,
evidence horizon, named candidate change, old and new component versions,
alternative context, fixed evaluation case, mode, and explicit workspace and
external-effect assumptions. Context, instructions, model settings, and lenses
are versioned descriptions. Recording one does not establish that native Codex
loaded it or that a provider received it.

The first implementation supports selection and interpretation experiments.
It neither replays filesystem effects nor dispatches native workers. A native
conversation fork, workspace fork, simulation, and reinterpretation remain
different operations even if they share baseline content.

## Identity, freezing, and persistence

`ExperimentStore(InvestigationStore)` uses the existing TraceStore database and
ContextManifestStore immutable content graph. Additive `exp_records` indexes
bind unique record names to content references and lineage. Content identity
may be shared across experiments; experiment, attempt, outcome, review, and
adoption occurrences have independently reserved identities. Identical retry
of a name is idempotent; altered reuse conflicts.

Operations use the existing database lock and composable SQLite transactions.
An experiment operation must not commit its caller's open transaction.
No operation rewrites source investigation state, trace bytes, context
revisions, baseline artifacts, or prior experiment records. Returned JSON is
a description, not a mutable alias into stored state. Unknown source fields
survive snapshots.

The horizon is an immutable allowlist of `cm.trace` references, their original
raw bytes/digests and local sequence identities, plus a local sequence ceiling.
The allowlist is authoritative for this experiment; the ceiling is an index,
not a global causal clock or a claim of complete history. Later trace appends
and index hydration cannot enlarge the allowlist. Sequence identities are local
to the owning TraceStore; cross-database copying needs a separate namespace and
import contract.

Context snapshots retain the exact canonical packet and manifest reference.
Baseline snapshots require explicit investigation, context, and artifact IDs.
Artifact lookup checks both `artifact` and `nativeArtifact`, because the
[Cycle B review](INVESTIGATION_CYCLE_B_CONTRACT.md) can move the original result
before producing its receipt. Never resolve a saved baseline through today's
visible artifact or `currentContextId`. Preserve the original attempt mapping
and its pinned manifest separately from the context preview manifest.

Snapshot and horizon validation checks record membership and frozen content.
It cannot prove that arbitrary instruction, rationale, or answer text contains
no knowledge acquired later. A historical prospective claim therefore needs
an explicit capture boundary and evaluation limitations. Later interpretations
retain their later origin; no snapshot inherits the authority it describes.

## Python integration seam

The public seam is implemented in
`src/eidos/investigation_alternatives.py`; deterministic scoring lives in
`src/eidos/investigation_evaluation.py`.

| Operation | Result and obligation |
| --- | --- |
| `freeze_horizon(seqs, evidence_class, rationale)` | Content reference to a fixed allowlist. `evidence_class` is `synthetic` or `recorded`; neither label proves source truth. |
| `snapshot_context(investigation_id, context_id)` | Immutable exact context snapshot with canonical references. |
| `snapshot_baseline(investigation_id, context_id, artifact_id)` | Immutable baseline snapshot; all supplied identities must agree. |
| `version(component, version, definition)` | Immutable versioned component description. A label alone is not executable code or activation evidence. |
| `propose(name, before_version, after_version, criteria, rationale)` | Named proposal referring to old/new component versions and fixed criteria. Criteria contain a version and case-ID mapping. |
| `experiment(name, proposal, baseline, alternative_context, horizon, case_id, mode, assumptions, mock_effects=..., versions=...)` | Named immutable experiment specification. The case must come from the proposal's pinned suite. Optional `versions` maps `model`, `lens`, or `instructions` to explicit `before`/`after` version references. |
| `prepare_attempt(name, experiment, variant)` | Return the attempt record and whether newly created. Variant is `baseline` or `alternative`; native preparation is rejected. No executor callback runs. |
| `finish_attempt(name, attempt, answer, claims, assumptions=..., failures=...)` | One immutable outcome per attempt. A competing terminal outcome conflicts. |
| `evaluate(name, experiment, baseline_outcome, alternative_outcome)` | Deterministic evaluation bound to this experiment, its exact outcomes, selected contexts, and fixed criteria. |
| `review(name, proposal, evaluations, decision, actor, rationale, review_kind=...)` | Attributed `adopt` or `reject` decision; review kind is `human` or `synthetic`. Review must identify the evaluated proposal. |
| `adopt(name, review)` | Derive the accepted version and rollback version from the reviewed proposal. Record a decision; do not activate configuration. |
| `rollback(name, adoption, actor, rationale)` | Append an explicit return-to-version record, retaining the adoption and every rejected alternative. |

Except for occurrence names and snapshot identity arguments, parameters after
`name` are supplied by keyword. `get(name)` and
`list(kind=..., parent=..., experiment=...)` resolve and enumerate
`ExperimentRecord` values. Records expose `.name`, `.kind`, `.parent`,
`.experiment`, `.cid`, `.data`, and `.content`, whose `.ref(label)` resolves
immutable content edges. These are trusted-host APIs: a supplied actor name
does not authenticate a human, and synthetic review is never owner approval.

An attempt's presence is a durable reservation, not permission to execute.
Repeated preparation of pending work returns the existing record and never
reruns an effect. This initial implementation crosses no external execution
boundary. Future native support must commit admission before launch, preserve
unknown outcomes after interruption, correlate receipts, and forbid automatic
retry when external effects may already have occurred. No exactly-once
external-effects guarantee follows from local idempotency.

## Evaluation and review

The fixed suite records relevant evidence, expected supported claims, answer
requirements, held-out cases where applicable, and budget constraints. Evaluate
both variants against the same frozen case. Record selected and omitted
relevant evidence, grounded versus unsupported claims, answer coverage/usefulness
proxies, out-of-horizon evidence, context size and available resource accounting,
changed assumptions, and failures. Missing model token/cost observations remain
unknown; byte counts or deterministic estimates are not observed usage.

Synthetic checks establish fixture behavior and protocol correctness only.
They cannot establish measured improvement in real model reasoning. Matching
a citation establishes availability, not entailment. Deterministic fixture
entailment labels must not be applied to arbitrary recorded evidence. A future
model judge needs its own versioned input/output and limitations; it cannot
promote itself to an oracle or human reviewer.

The evaluated surface is structured fixture claims. Free answer prose and the
retained original baseline artifact are not graded. Both evaluated outcomes
are new fixture reinterpretations. Declared component versions do not prove
that those code/model/lens/instruction versions produced a context or outcome;
the demonstration identifies its deterministic runner separately. Reviews
reference exact evaluation occurrences. Adoption requires every fixed case ID;
rejection may retain incomplete evaluation with explicit missing case IDs.
The review also freezes omitted evaluations and pending attempts, making known
omissions inspectable without preventing selective reporting. It is not a
preregistered trial.

An improvement claim states its tested scope. A better result on the motivating
case alone does not establish generalization. Keep held-out outcomes and
regressions addressable, including rejected candidates. Review binds the exact
proposal and evaluations; adoption derives its component version and rollback
target from that binding. A demonstration may record synthetic review and
adoption, clearly labelled as such. Neither a synthetic nor a human decision
here edits AGENTS.md, skills, native configuration, or live context selection.

## Minimal future HTTP requirements

No API/UI routes are added in this delivery. The integrator can expose creation,
inspection, and lineage listing for experiments; explicit attempt preparation
and outcome recording; evaluation; review; adoption; and rollback. Mutations
need caller-qualified idempotency names and conflict responses for altered
reuse or mismatched baseline/context/outcome relationships. Reads must return
the pinned identities, evidence class, execution mode, assumptions, exact
artifact, criteria, evaluator version, review kind, and activation limitations.
Use existing authentication/admission boundaries; stored names grant neither
inspection authority nor native execution permission.

## Required regression evidence

Protect immutable histories, exact artifact pinning through Cycle B changes,
distinct occurrence identities for equal content, replay conflicts, one outcome
per attempt, transaction rollback and restart, horizon exclusion after append,
cross-experiment outcome rejection, native preparation rejection, no historical
authority transfer, synthetic-versus-real claim boundaries, explicit versioned
adoption/rollback, and addressable rejection. The runnable demonstration must
complete proposal → experiment → evaluation → review → adoption with fixed
synthetic cases and no live native/provider calls. Passing these checks does
not establish native isolation, arbitrary semantic entailment, or a rendered
workbench workflow.
