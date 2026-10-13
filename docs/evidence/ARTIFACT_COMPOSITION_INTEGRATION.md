# Exact results as context — integration evidence

**2026-10-13 · implementation base `29a164a` · synthetic work only.** The commit
containing this report owns the combined implementation. [D28](../roadmap/DECISIONS.md)
records the composition and compatibility decision.

## Observed contract

`POST /api/investigations` and context revision accept optional `artifactInputs`
entries containing `investigationId`, `artifactId` and `rationale`. Selections may
be empty when an artifact is supplied. Both input kinds share the 32-entry and
128 KiB projected-prompt bounds; raw evidence retains its 256-record bound.

The server resolves exact canonical artifacts, including retained history,
and validates their source context and attempt. Client snapshots and provenance
overrides are rejected. Frozen inputs preserve complete artifact content and
unknown fields, source context and attempt manifest references, and a separately
recorded matching adoption snapshot. Historical inquiry and receipt descriptions
remain data; source continuation or execution authority is not imported.

Context manifests contain explicit frozen-artifact slots. Output citations identify
only directly supplied artifacts/records. Inherited citations do not silently
become direct evidence. Original support is recovered through the separately saved
source context. Follow-up context reconstruction retains frozen artifact inputs
and their coverage. Later source adoption does not rewrite old packets.

## Counterexamples and compatibility

- Independent A→B→C acceptance recovers the controlling raw evidence from C after
  reopening SQLite, without including A's result or omitted transcript in C's
  prompt. All three authored host completions are explicitly synthetic.
- Source selection, revision, manifest and lineage reads create no attempt/pin
  or native call. An instrumented app-server refuses any accidental startup.
- Wrong-investigation artifact IDs, forged client snapshots, duplicate inputs,
  and combined source/prompt bounds are rejected.
- Direct versus inherited raw and artifact citations remain distinguishable.
- A synthetic inquiry/offer/A2 preserves original artifact slots and adoption
  snapshots. Unknown canonical artifact fields survive selection.
- Exact golden context, prompt and manifest hashes from clean base `29a164a`
  remain unchanged for legacy packets, including explicit empty `artifactInputs`.
- Independent review found that comparing artifact IDs alone allowed a smaller
  alternative to drop a recorded rejection while passing retention. Fixed metrics
  compare the full frozen input except inclusion rationale and report
  `changedArtifactIds`. The regression fails retention despite equal IDs/counts.

The comparison horizon records explicit frozen artifacts as well as raw records.
Artifact inputs outside that horizon fail validation, and the fixture entailment
evaluator refuses to grade them. Version 2 comparisons measure retained inputs and
prompt bytes, not reasoning improvement, truth or model cost.

## Reproduction

```sh
uv run pytest tests/test_artifact_context_acceptance.py tests/test_artifact_context_compatibility.py
uv run python scripts/artifact_composition_demo.py --db /tmp/nema-artifact-next.db
uv run python scripts/artifact_composition_demo.py --db /tmp/nema-artifact-next.db --resume
```

Use a fresh path for the first invocation. The demo rejects unmarked databases on
resume. Its optional `--serve` uses the existing synthetic worker; no native model
or account is used. The parent independently generated/reopened a second database;
the two reports were byte-identical.

For the browser check, start that demo server, Vite on 5173 and a disposable
Chromium profile with remote debugging on 9222, then run:

```sh
NEMA_ARTIFACT_FIXTURE=/tmp/artifact-demo-report.json NEMA_ARTIFACT_UI_PREFIX=/tmp/artifact-browser node scripts/check_artifact_composition_ui.mjs
```

Write the demo's initial report with `--output /tmp/artifact-demo-report.json`.
The browser script creates one synthetic draft and revision; it sends no dispatch.

## Combined and rendered verification

- `uv run pytest`: **697 passed, 6 skipped** (explicit native opt-ins).
- `cd ui && bun test tests && bun run check && bun run build`: **52 tests / 259
  assertions**, **0 errors / 0 warnings**, production build passed.
- `uv run pytest tests/test_seed_context.py` and `git diff --check`: passed.
- Independent Chromium at 1600×1100 and actual 390×844 mobile width followed
  C→B→A, recovered the exact raw source including unknown fields, displayed frozen
  adoption separately, and created/reloaded/revised an artifact-only context.
- Unsaved question, inclusion rationale and a third selected result survived
  provenance navigation, Back, close and reload without changing server packets.
  Only two POSTs occurred: create and revision. Zero dispatch requests or JavaScript
  exceptions were observed. Picker/add/close controls were hit-tested within the
  narrow viewport; dialog/workbench/document horizontal overflow was zero.
- Browser review exposed two actual layout defects: an unbroken artifact-ID diff
  and long source-thread title expanded their panes/viewport. Both were fixed and
  the final screenshots inspected by the UI owner, independent acceptance and parent.
- The parent independently reran the complete browser script against the integrated
  main UI and current backend: all desktop/mobile checks passed with the same exact
  context IDs. The existing write-origin guard rejected an initial attempt from
  development port 5174; the rerun used the admitted 5173 port without changing policy.

Saved evidence: [synthetic chain](ARTIFACT_COMPOSITION_SYNTHETIC_2026_10_13.json),
[browser observations](artifact_composition_ui_2026_10_13.json),
[desktop provenance](artifact_composition_ui_2026_10_13_lineage.png),
[frozen preview](artifact_composition_ui_2026_10_13_preview.png),
[mobile picker](artifact_composition_ui_2026_10_13_mobile_picker.png), and
[mobile provenance](artifact_composition_ui_2026_10_13_mobile_lineage.png).

Accepted source commits: UI `4bc4de4`/`6befeb2`, independent acceptance
`61a0740`/`0de5146`. Parent owns backend, compatibility tests, review fix and
combined integration. The separate rejected native gateway experiment is preserved
in [its report](NATIVE_GATEWAY_ADMISSION_EXPERIMENT.md); it changes no production gate.

## Limits

This establishes a local, synthetic composition workflow, not source truth,
automatic contradiction resolution, answer quality, authenticated multiuser
disclosure or complete provider context. The generic Python host interface remains
trusted. Results may contain unsupported claims; adoption stays a separately
attributed decision. The production native gate remains closed.
