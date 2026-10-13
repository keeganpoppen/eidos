# Recorded experiments in durable comparison — next integration contract

**2026-10-13 · integrated from `579af9d` · V1-08/10/11, C1/C5.**
Parent integrated the reviewed UI, backend consistency fix and independent acceptance.
See [current handoff](CURRENT_HANDOFF.md) and
[acceptance](../evidence/RECORDED_EXPERIMENT_COMPOSITION_INTEGRATION.md) for evidence.
This is an existing product seam, not a new evaluator or recipe activation.

## User loop and observed gap

A real stored context experiment currently appears only in RecordedExperiment.
ComparisonSurface resolves alternative-review through the authored reflection
fixture, and its compiler requires results on both sides. The actual API freezes
baseline context/result/attempt plus a context-only alternative. Connect those
existing references: Compare these saved inputs → review exact context composition
→ Apply → inspect source/input differences and retained baseline result → save a
named snapshot → recover it in a fresh browser. Never invent an alternative result.

## Shared contract

Reuse WorkbenchExperiment and existing owner-scoped
`GET /api/investigations/:owner/experiments/:id`. Validate owner+experiment identity,
exact baseline context/artifact/attempt membership and alternative context. Use
`savedWork.view` for selected owner reads and deduplicate concurrent consumers.
Fetch only the named experiment; no owner-wide experiment polling or catalog.

RecordedExperiment supplies onCompare(experimentId). InvestigationPane extends
its existing callback to `(ownerId, 'alternative-review', experimentId)`; +page
passes the optional experiment ID and existing request nonce to ComparisonSurface.
Other navigation clears that ID. Real structured alternative-review requests name
both owner and experiment; fixture origin remains explicit and separately labelled.

Compile the exact API targets into an Arrangement with lens=context, layout=beside,
intent=alternative-review and experimentId. Baseline retains its artifact. The
alternative remains artifact-free even if one now exists for that context. Reopen
an applied/saved arrangement resolves its existing pins; it does not compile a new
arrangement from current owner state. An explicit lens change must not auto-fill
an experiment target with a later result. Editing bindings drops the experiment
association through existing free-comparison behavior.

Reuse contextText/LineDiff, EvidenceRecord and ArtifactLineage for source-level
comparison and support recovery. Keep the exact retained baseline result accessible
from context comparison. Extract a shared read-only evaluation view if it avoids
competing presentations; review/rollback mutations and retry remain owned by the
existing RecordedExperiment. Show current review separately from immutable pins.
Refresh that view on explicit reopen/manual Refresh; guard stale asynchronous
responses by owner+experiment+request identity. No automatic adoption or activation.

## Integration ownership

- Root: shared backend/API only if needed, independent invariants and final docs/
  integration. Avoid new backend routes unless existing projection cannot support
  the exact reference contract. Own task packet and acceptance reconciliation.
- history_ui: `/tmp/nema-recorded-experiment-ui`, branch `codex/recorded-experiment-ui`; UI/event/
  type/helper changes and unit tests, check/build, coordinate browser selectors.
- independent acceptance: `/tmp/nema-recorded-experiment-acceptance`, branch
  `codex/recorded-experiment-acceptance`; new fixture/check/evidence files,
  exact HTTP/browser/reopen challenges; no production UI ownership.
- native_frontier: independent tool-control research, not a dependency of this loop.

## Discriminating acceptance

Evaluate E over baseline C0/A1 and context-only C1. Include a selected artifact
whose ID is unchanged but frozen rejection/adoption content differs between C0/C1.
Then advance to C2/A2 and add a result for C1. Opening E must show C0/A1 versus C1
without a result, correct changed-input diff and exact original raw support. The
current review may advance and be explicitly refreshed; E pins, original packets
and saved snapshot content remain identical. No dispatch, context revision, review
or adoption occurs from preview/open/save alone. Dirty investigation draft and its
pending request identity survive navigation and reload.

Challenge missing owner/experiment/result, wrong-owner IDs, delayed E1 response
after choosing E2, failed load with retry, unknown/mismatched experiment bindings,
legacy authored fixture behavior and saved snapshot recovery. Actual desktop/mobile
inspection and clean diff/unit/check/build/full integration verification precede
commit/push. Report synthetic vs recorded evidence accurately; deterministic
retention/size metrics establish neither reasoning improvement nor human benefit.
