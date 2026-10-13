# Saved-work discovery and exact source recovery at 1,000 owners

**2026-10-13 · integration base `1ee2821` · C1/C5, V1-01/02/03/04/09.**
This acceptance lane exercises discovery, result composition and original-support
recovery over 1,000 persisted investigations. Every completion is explicitly
authored synthetic data through the trusted host interface. No native process,
model, credential, or real provider request is involved.

The backend adds metadata catalogs, conditional selected-owner views and one exact
artifact/context/attempt source response. The UI searches and pages those catalogs,
loads selected owners explicitly, and follows source links without loading each
source owner's complete history. Legacy reads and mutation contracts remain
available; the measured UI does not use the legacy full catalog or owner routes.

## Fixture and measured scope

[`saved_work_scale_demo.py`](../../scripts/saved_work_scale_demo.py) creates an old
A→B→C chain followed by 997 unrelated completed owners. A has 32 contexts created
through ordinary revision requests before its authored completion. B and C contain
exact attributed result inputs; their prompts do not recursively copy earlier
transcripts. A's controlling source and rejected alternative retain their raw
records and unknown fields. Synthetic creation dates make catalog order stable
across host clock corrections.

The [persisted fixture measurements](SAVED_WORK_SCALE_SYNTHETIC_2026_10_13.json)
come from actual loopback HTTP responses through `serve.py`, including its real
JSON serialization and `Content-Length`. Instrumentation counts parsing of exact
stored canonical strings and traces source-reading SQL on the server connection.
It excludes API construction/recovery and does not infer source access from the
shape of a copied response.

| Read | HTTP body bytes | Canonical owners parsed |
| --- | ---: | ---: |
| First 20-owner catalog, initial projection | 8,189 | 1,000 |
| Hot 20-owner catalog | 8,189 | 0 |
| Case-folded `STRASSE` result search | 555 | 0 |
| Unchanged catalog | 99 | 0 |
| Unchanged selected-owner view | 99 | 0 |
| Reopened API, unchanged catalog after recovery | 99 | 0 |
| Exact source C | 7,278 | 1 |
| Exact source B | 7,372 | 1 |
| Exact source A | 6,501 | 1 |
| A's full selected-owner view | 417,697 | 1 |

Hot catalog/search/unchanged reads also issued zero canonical source-reading SQL
statements. The reopened result relies on an update trigger that marks an owner
dirty only when canonical bytes change; recovery's unchanged saves must not dirty
every owner again.

These are measurements of specific read paths, not constant-time or aggregate
resource claims. Initial API recovery still scans canonical owners. Cold or dirty
projection refresh can parse every changed owner. A changed selected-owner view
returns its full history. An exact source response transfers one packet but still
parses the full owning canonical row. Individual contexts and result bodies have
their existing limits; no new aggregate SQL, memory, disk or latency bound follows.

## Rendered recovery and retained state

[`check_saved_work_ui.mjs`](../../scripts/check_saved_work_ui.mjs) uses real Chromium
and the persisted fixture. The [browser report](saved_work_ui_2026_10_13.json)
records response body bytes and exact request paths. The run verifies:

- Initial selectors contain 20 metadata rows; next/back pages do not duplicate
  owners. Title search finds A outside the initial page, including Unicode case
  folding. Changing the search/page retains an explicitly selected result.
- A new investigation freezes A's exact canonical result and original attempt
  manifest. The server commits its save, then CDP deliberately drops the response.
  Reload and retry send the same request ID/body and produce one saved owner.
- A later revision retains the first packet. A dirty question and rationale, plus
  the historical preview selection, survive C→B→A navigation, back/close,
  comparison, and reload. The recovered original raw record matches byte for byte.
- Explicit comparison pins retain both context and artifact IDs through catalog
  paging and reload. Missing remembered owners leave editable catalog controls;
  explicit new selections repair that arrangement without automatic substitution.
- A failed selected-owner request cannot leave the previous owner actionable
  under the newly selected ID. Retry resolves the requested owner.
- At 390×844, the picker and source dialog fit the actual 390px viewport with no
  document/picker/dialog horizontal overflow. Controls remain reachable. There
  are zero uncaught JavaScript exceptions and no dispatch mutation.

The UI makes zero legacy full-catalog or full-owner GETs. Source-hop requests carry
the exact `contextId` and return one context, artifact and matching attempt. The
browser report separately records changed selected-owner responses, unchanged
polls, metadata catalogs and source detail bytes.

Inspected screenshots: [desktop original support](saved_work_ui_2026_10_13_desktop_lineage.png),
[desktop comparison](saved_work_ui_2026_10_13_desktop_comparison.png),
[390px result picker](saved_work_ui_2026_10_13_mobile_picker.png), and
[390px source dialog](saved_work_ui_2026_10_13_mobile_lineage.png).
The acceptance author, UI owner and parent integrator inspected the rendered
presentation. The parent independently reran the complete browser check against
integrated main: all checks passed, with eight exact source replies and eight
unchanged owner replies. Combined verification passed 732 Python tests (31 explicit
native opt-ins skipped), 58 Bun tests / 287 assertions, Svelte check and build.
This scripted synthetic task establishes neither human reorientation speed nor
native answer quality.

## Counterexamples and verification

The independent acceptance suite has **11 passing tests**. It covers actual HTTP
scale/bytes, all-owner/result keyset traversal, exact out-of-page composition and
idempotent save, historical source/attempt selection, wrong-owner/context rejection,
independent-writer invalidation, frozen-input preservation, and rebuild/reopen
stability. A labelled trusted canonical-import test makes current fields differ
from a retained historical artifact; the source endpoint must return that original
artifact's context and attempt, never the latest substitutes.

Actual HTTP tests exposed blank parameters being discarded by URL parsing before
validation: `limit=&limit=1`, `unexpected=`, and an empty `knownVersion` all bypassed
the intended rejection. Preserving blank values closes that gap. Cursor version
validation also rejects a JSON boolean in place of integer version 1. The parent
independently found and fixed needless projection invalidation during unchanged
recovery; the fixture now measures a second API opening explicitly.

```sh
uv run pytest tests/test_saved_work_acceptance.py
uv run python scripts/saved_work_scale_demo.py \
  --db /tmp/new-saved-work.db --output /tmp/saved-work-scale.json
uv run python scripts/saved_work_scale_demo.py \
  --db /tmp/new-saved-work.db --resume --serve
NEMA_SAVED_WORK_FIXTURE=/tmp/saved-work-scale.json \
  NEMA_SAVED_WORK_UI_PREFIX=/tmp/saved-work-ui \
  bun scripts/check_saved_work_ui.mjs
```

The browser command additionally requires Vite on port 5173 and a dedicated
Chromium profile with debugging on port 9222. The server uses only the explicitly
synthetic subprocess fixture if dispatch is invoked; this acceptance never invokes
dispatch. The integrator owns combined verification and canonical state/handoff.
