# Immutable named comparison acceptance

2026-10-13. Synthetic persisted sources, real local HTTP and Chromium. No native
or model invocation. Acceptance branch base: `b9f75ea`; tests/demo commit:
`0abeed7`. Root's pending backend was imported explicitly from the main workspace.
Final rendered UI: `849729b` (including `c4fa791` renderer retry and `06893af` mobile wrapping fixes).

The observed loop saves exact A/C result and source-focus references, recovers a
committed save after its response is lost, then finds, previews and opens that
snapshot in a separate isolated browser context. Altering placement creates a new
snapshot with copy ancestry; the original envelope stays identical. The saved
pending B inquiry retains its original context-only requested result after B has
received an offered packet and produced a terminal local review receipt.

## Independent checks

`tests/test_composition_acceptance.py`: **33 passed** against the final root
source. These tests use persisted authored A/B/C results and actual local Eidos
inquiry/experiment state. `AppServerClient.start` is forbidden in these tests.

- Exact retry survives controller reopen and actual source-row disappearance;
  a new request with unresolved references fails. Changed-body replay is 409.
  Two independent SQLite connections concurrently admit one snapshot.
- Wrong owner, context, artifact, record, thread, offered response, inquiry and
  experiment relationships fail. An inherited citation does not supply raw
  evidence. Valid context-only experiment alternatives and generic comparisons
  focused on an actual offered packet remain legal.
- Imported malformed receipt fixtures cannot substitute `inquiryId`, `responseId`,
  `decisionOccurrenceId` or `attemptId`. These four counterexamples exposed a
  missing relation check, now fixed by the integrator. This validates consistency
  of stored references; it does not authenticate a native result.
- Copied authority, action, raw-source and browser-draft fields are rejected.
  Mutation/execution routes do not exist. Unknown renderer versions remain exact
  inspectable descriptions; numeric and selector syntax boundaries are checked.
- 43 snapshots exercise literal casefold title matching and query-bound paging.
  Catalog/detail reads cause zero canonical-owner JSON parses and zero canonical
  source SELECTs. Actual HTTP checks cover the 16KiB raw body limit, identical
  retry, changed-body 409 and blank query rejection.

The [seed artifact](COMPOSITION_SNAPSHOT_SYNTHETIC_2026_10_13.json) records the
initial four immutable envelopes, later local inquiry decision, original raw
record with its unknown field, and zero canonical source access for catalog/detail reads
after controller reopen. Snapshot envelopes were 936–1165 bytes. The fixture JSON
contains synthetic source evidence to make the demonstration reproducible; the
snapshot envelopes contain references only.

## Rendered result

[scripts/check_composition_snapshot_ui.mjs](../../scripts/check_composition_snapshot_ui.mjs)
passed in real Chromium with three isolated browser contexts. Its
[network and assertion record](composition_snapshot_ui_2026_10_13.json) records:

- Server 201 response deliberately dropped after commit, page reloaded, exact
  captured request retried; one original snapshot, no duplicate.
- Fresh browser discovery and preview do not alter the applied comparison.
  Explicit Open restores exact owner/context/artifact/block/record references
  and the original raw bytes. Each browser's dirty question, rationale, selected
  sources and real pending investigation-save request remain deeply equal.
- Save-copy changes placement with ancestry, preserving the original envelope.
  Changing focus after preview disables Open until a new preview; selecting a
  different saved snapshot clears the previous preview. This is not a test of
  every possible delayed-response interleaving.
- Opening the old pending inquiry does not acquire a later response or result.
  An unknown renderer keeps the exact record/artifact references, visibly marks
  the passage unresolved, and highlights no block, including after reload.
- A legal artifact-plus-record focus without a block selector displays the exact
  cited record and labels the absent passage; it creates no block highlight. This
  independent rendered case accompanied the UI fix in `849729b`.
- A separately labelled source-view 404 browser transport fixture leaves the saved
  references visible. Explicitly selecting C, releasing unavailable focus and
  saving a copy repairs the view while the original stays unchanged. Actual
  canonical-row deletion/replay is covered separately by Python acceptance.
- Six intentional mutation requests: two investigation context saves used to
  establish pending draft recovery, and four snapshot POSTs including the identical
  retry. No dispatch, adoption, inquiry decision or native request occurred.
  No JavaScript exceptions were observed.

Snapshot catalog HTTP response bodies were 272–1687 bytes as this small fixture
accumulated named snapshots; exact detail bodies were 952–1360 bytes. These are
observed body sizes, not latency or large-dataset benchmarks. Source preview uses
selected owner views; this slice does not make full selected histories bounded.

A 160-character unbroken legal name reproduced a mobile overflow: document 1547px,
preview 2735px beyond their widths. UI commit `06893af` added inherited wrapping.
The final 390px run measured zero overflow for the document, saved-comparison
section, preview title and evidence focus. Inspected screenshots:

- [Exact result and original raw evidence](composition_snapshot_ui_2026_10_13_desktop_source.png)
- [Fresh-browser preview before opening](composition_snapshot_ui_2026_10_13_desktop_preview.png)
- [Long legal name at 390px](composition_snapshot_ui_2026_10_13_mobile_long_title.png)
- [Artifact citation without a passage at 390px](composition_snapshot_ui_2026_10_13_mobile_artifact_record.png)
- [Unknown-renderer preview at 390px](composition_snapshot_ui_2026_10_13_mobile_preview.png)
- [Unresolved passage with retained source record](composition_snapshot_ui_2026_10_13_mobile_unknown_renderer.png)

## Reproduce and handoff

From the integrated repository, choose a new database path:

```sh
uv run pytest tests/test_composition_acceptance.py
uv run python scripts/composition_snapshot_demo.py --db /tmp/composition-demo.db --output /tmp/composition-demo.json --serve
```

Start Vite on 5173 and dedicated Chromium with remote debugging on 9222. Then:

```sh
NEMA_COMPOSITION_FIXTURE=/tmp/composition-demo.json NEMA_COMPOSITION_UI_PREFIX=/tmp/composition-ui bun scripts/check_composition_snapshot_ui.mjs
```

Use `--resume` only with the script's marked synthetic database. The browser script
creates new names on every run. Tests in an isolated acceptance worktree used
`PYTHONPATH=/home/elkeegano.guest/eidos/src uv run --project /home/elkeegano.guest/eidos pytest -q -o pythonpath=/home/elkeegano.guest/eidos/src tests/test_composition_acceptance.py`.

Checked backend SHA-256:
`compositions.py=28b33cbfdafa477b8738853079c7edc611ca3f6bb1fdb6b5b4dd93adeda732bf`,
`api.py=e32f7e981be2b85b1ae5d94cff6a59546ce2e4be047e13bf60989281ba629e4e`.

Parent integration reproduced the complete Chromium check against main Vite and
inspected its desktop/raw-source, mobile long-title, artifact-record and unknown-
renderer screenshots. All assertions passed with zero JavaScript exceptions,
zero mobile overflow, six intended POSTs and no native/dispatch action. Local
reproduction artifacts are `/tmp/composition_snapshot_main_reproduction.json`
and matching PNGs; committed lane artifacts above remain the public evidence.
The parent then stopped the owned fixture API, Vite and dedicated Chromium.

Combined final verification: **821 Python passed, 34 intentional native opt-ins
skipped**; **67 Bun tests / 344 assertions**, Svelte **0 errors / 0 warnings**,
production build and seed-context tests passed. The separate synthetic-provider
native opt-in passed **39 tests**, with scope in its own report.

Root owns canonical STATE/HANDOFF and integration. This acceptance
establishes scripted same-database recovery and read-only source binding. It does
not establish source truth, caller authentication, cross-database import,
collaborative synchronization, native admission, or measured human task speed.
