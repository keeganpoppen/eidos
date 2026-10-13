# Return to a saved question

**2026-10-13 · integrated from `555a317` · C5, V1-01/03/08/10.**

## User loop and concrete gap

SavedComparisons already fetches the exact owners for a snapshot preview, but
largely displays IDs. The browser is a collapsed disclosure below comparison-save
controls. A returning person cannot assess a saved question's purpose and support
without first replacing the working arrangement. Improve that recovery loop using
existing immutable snapshots and source APIs, without another persistence model.

Provide a discoverable return-to-saved-work entry from the investigation surface
and useful content in the read-only snapshot preview: the saved question, exact
baseline result, context-only alternative, experiment rationale where present,
and saved evidence focus. The preview must allow exact original support inspection
before the explicit Open action. Current review must remain separately labelled
and must never replace historical pins. Keep identifiers in provenance details.
Retain the existing search/paging and error/retry paths. Do not duplicate the
comparison editor or auto-open a result merely because its preview finished.

## Existing interfaces and constraints

Reuse compositionSnapshots.list/get, savedWork.view/experiment/source,
resolveTarget, ArtifactContent/ArtifactLineage and openSnapshot. No backend route,
schema, controller, new summary generation, native dispatch or recipe activation.
An experiment's two fixed context IDs are not a reusable context recipe; byte and
retention measurements do not justify adopting a policy for future work.

Exact C0/A1/attempt versus context-only C1 must remain exact after C2/A2 appears.
Missing references and unknown renderer versions stay explicit and repairable.
Old async reads cannot replace a newly selected snapshot; failed reads can retry.
Keep investigation drafts, pending request identities, applied comparison and
unsaved arrangement edits intact during preview/support navigation. Opening is an
explicit existing action and must preserve those established recovery semantics.
Avoid current-context fallback or unmarked current artifact/adoption information.

## Ownership and integration

- history_ui: `/tmp/nema-saved-question-recovery`, branch
  `codex/saved-question-recovery`; owns ui/src/lib/SavedComparisons.svelte,
  ComparisonSurface.svelte, InvestigationPane.svelte, ui/src/routes/+page.svelte,
  a small new preview component/helper if needed, and focused UI tests. No shared
  saved-work/composition protocol changes without coordination. Prefer component
  styles; app.css changes require a concrete rendering reason.
- Independent acceptance: `/tmp/nema-saved-recovery-acceptance`, branch
  `codex/saved-recovery-acceptance`; owns a unique fixture/browser script, tests and
  docs/evidence report. Reuse labelled recorded-experiment fixture where possible.
- Root: cross-lane contract, review, integrated verification, docs and final commit.
  Native catalog work is independent and owns only its new probe/test/report files.

## Discriminating acceptance

Start in a fresh browser with several similarly named snapshots. The target pins
C0/A1 versus context-only C1; later C2/A2 and a changed review exist. From the preview,
recover the reason retry was rejected, locate the exact supporting raw record,
and distinguish the unresolved historical question from current review. Inspect
support before Open; verify the applied arrangement has not changed. Open retains
C0/A1/C1 with no alternative result and preserves a dirty investigation draft and
pending ID. Exercise delayed old preview, failed retry, unavailable support,
unknown focus renderer, desktop and 390px mobile with actual browser inspection.

Report objective availability/navigation and reference preservation. Do not claim
human reorientation speed from automation or invent participant responses. Human
benefit remains unmeasured until a returning person actually performs the task.
Run Bun tests/check/build and focused backend fixture checks; root integrates and
runs appropriate full checks. No credentials, private traces or model calls.
