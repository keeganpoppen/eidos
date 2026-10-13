# Returning to a saved question — rendered acceptance

2026-10-13. **Observed with synthetic saved histories, no native or model calls.**
The baseline UI is `555a317`; the changed UI is frozen commit `9feac92`.
Fixture/test contribution: `b1cb281`. The API source is root main at `555a317`
with the independently reviewed product integration in progress; this lane changes
no backend route or schema. This report measures content availability and exact
reference preservation. Human reorientation speed and usefulness remain unmeasured.

## Objective before/after result

The same persisted target was previewed in isolated Chromium contexts against the
old and new UI. Five similarly named saved comparisons distinguish the original
question from broader inputs, a newer result, an older renderer, and an unavailable
source. Selection and preview do not open a comparison.

| Available in the preview before Open | `555a317` | `9feac92` |
|---|---|---|
| Exact saved question | No | Yes |
| Recorded experiment rationale | No | Yes |
| Exact retained baseline result | No | Yes |
| Explicit context-only alternative | No | Yes |
| Original raw saved-focus record | No | Yes |
| Separately labelled current review | No | Yes |
| Action to inspect original result/support | No | Yes |
| Investigation entry to return to saved work | No | Yes |

The baseline already showed IDs and “No result pinned”; the context-only row here
measures the new content preview's explicit aperture label. These observations do
not claim that historical support was inaccessible elsewhere in the old product.

[Baseline capture](saved_question_recovery_baseline_2026_10_13.json) and
[baseline screenshot](saved_question_recovery_baseline_2026_10_13_desktop_baseline.png)
record the old preview. [Changed capture](saved_question_recovery_ui_2026_10_13.json)
records actual browser requests, checks, and screenshot paths. The scripted result
is visible in the [desktop preview](saved_question_recovery_ui_2026_10_13_desktop_preview.png)
and [390px preview](saved_question_recovery_ui_2026_10_13_mobile_preview.png).

## Discriminating history and recovery checks

The [persisted fixture marker](SAVED_QUESTION_RECOVERY_SYNTHETIC_2026_10_13.json)
reuses the recorded-experiment demo. Its target fixes C0/A1 against context-only C1,
although current C2/A2 and a later result for C1 exist. The same supplied artifact ID
has different frozen adoption state in C0 and C1. Synthetic completions and one
post-save owner removal are explicitly trusted fixture construction; they are not
native execution or a new production deletion operation.

The preview displays the immutable proposal rationale, the saved question, and
the exact rejection record: an automatic retry can duplicate an operation whose
first reply was lost. Current experiment rejection is separately labelled as read
at preview time. Neither it nor current C2/A2 replaces historical pins. Exact raw
record strings, including unknown fields, match the persisted fixture bytes.
The [reason/support screenshot](saved_question_recovery_ui_2026_10_13_desktop_reason_support.png)
shows original evidence separately from current review.

Acceptance exercised:

- A context-only comparison with **no saved focus** exposes selected raw record 3
  lazily before Open. Its raw evidence component is absent until disclosure opens.
  The applied arrangement remains empty and the pending draft stays exact.
  [Rendered evidence](saved_question_recovery_ui_2026_10_13_desktop_unfocused_support.png).
- Baseline support opens exact C0/A1, then its supplied result, then Back/Close.
  The supplied result retains C0's frozen null adoption despite a later rejection.
  [Original support](saved_question_recovery_ui_2026_10_13_desktop_original_support.png).
- A real successful investigation-create reply is deliberately lost at the browser
  transport. Its persisted pending request ID and dirty fields remain byte-for-byte
  equal across Return to saved work, preview, support navigation, explicit Open,
  and reload. No run/start occurs. Unapplied arrangement layout/lens/context edits
  survive an Investigation → Return entry roundtrip and all read-only inspection.
- Both a delayed old snapshot response and a delayed old experiment response lose
  to a newer selection. Injected one-shot 503 responses have working retry paths;
  failed experiment reads do not borrow another review.
- An actually absent source owner remains explicitly unavailable through retry;
  no current result is substituted. An unknown renderer retains exact raw support
  without inventing a passage highlight.
- Explicit Open and a second fresh-browser recovery preserve C0/A1/C1 and the
  exact saved focus. The C1 aperture has no artifact despite a later C1 result.

At 390×844, document and preview horizontal overflow are both **0 CSS pixels**.
The [mobile evidence/review](saved_question_recovery_ui_2026_10_13_mobile_reason_support.png)
and [mobile provenance dialog](saved_question_recovery_ui_2026_10_13_mobile_original_support.png)
were visually inspected at normal scale. No JavaScript exceptions were recorded.

## Reads, writes, and limits

The final changed-UI run made exactly one browser POST: the deliberate pending
investigation save (server 201, reply then dropped). All recovery interactions used
GETs or local UI state. There were zero legacy full-investigation-catalog GETs and
zero native turn dispatches. Successful decoded HTTP response bodies were:

| Read | Observed body size |
|---|---:|
| Individual snapshot | 809–1,251 bytes |
| Exact experiment | 2,324–2,702 bytes |
| Exact artifact source | 6,534–8,525 bytes |
| Owner view, including unchanged replies | 99–29,810 bytes |

These are actual Network response-body measurements, not copies shaped like HTTP
responses. Preview still uses selected-owner full views and can therefore read a
large owner's history; this is not a new bounded-owner-payload claim. Histories,
missing-source construction, delayed responses, and failures are authored synthetic
cases. No human participants, natural-language task success, latency advantage,
production admission, or external exactly-once behavior is inferred.

## Verification and reproduction

Independent Python fixture/recorded-experiment acceptance: **19 passed** (5 new).
The saved fixture reopens byte-identically after the browser run, with zero recorded
`turn/start`. UI owner reports **78 Bun tests / 416 assertions**, check/build clean
for `9feac92`. The parent independently reproduced the full browser script on
integrated main with a fresh marked database: every recovery assertion passed,
all seven content checks passed, 390px document/preview overflow was zero and
there were no JavaScript exceptions. It also observed only the one intentional
investigation POST. Parent seed/reopen output remained byte-identical after the
browser run. Root and UI owner inspected all seven parent screenshots and the
baseline; no concrete presentation defect was found. Both lanes stopped their
verified owned services. Parent report: `/tmp/nema-saved-question-root-browser.json`.

Parent combined checks: **973 Python passed / 44 explicit native checks skipped;
78 Bun tests / 416 assertions; Svelte 0 errors / 0 warnings; build passed**.
Browser-script JavaScript syntax and context-link checks also passed. The separate
paired native catalog reproduction passed 24 opt-in checks; it made two contained
turns and six authored local provider requests, with zero real model/upstream/auth.

From the integrated repository, use a new local database and private Chromium
profile. The browser script starts/stops no services and closes only its own
isolated browser contexts. Re-running it creates one extra draft via a unique
pending request; saved comparison/experiment fixture identities remain unchanged.

```sh
uv run python scripts/saved_question_recovery_demo.py \
  --db /tmp/nema-saved-question-repro.db \
  --output /tmp/nema-saved-question-repro.json
uv run python scripts/saved_question_recovery_demo.py \
  --db /tmp/nema-saved-question-repro.db --resume --serve --port 8765
```

In separate shells, start the normal UI (`cd ui && bun run dev --host 127.0.0.1
--port 5173 --strictPort`) and isolated headless Chromium:

```sh
chromium --headless --no-sandbox --disable-gpu --remote-debugging-port=9222 \
  --user-data-dir=/tmp/nema-saved-question-repro-chromium --no-first-run about:blank
NEMA_SAVED_RECOVERY_FIXTURE=/tmp/nema-saved-question-repro.json \
NEMA_SAVED_RECOVERY_UI_PREFIX=/tmp/nema-saved-question-repro-browser \
NEMA_UI_ORIGIN=http://127.0.0.1:5173 \
NEMA_DEBUG_ORIGIN=http://127.0.0.1:9222 \
  bun scripts/check_saved_question_recovery_ui.mjs
uv run pytest -o addopts='' -q tests/test_saved_question_recovery_acceptance.py \
  tests/test_recorded_experiment_acceptance.py
```

For the before capture, serve `555a317`'s UI against the same fixture and run the
same script with `NEMA_SAVED_RECOVERY_BASELINE=1` and a separate output prefix.
This lane used isolated ports API 8766, Vite 5175, Chromium 9223. Vite's launch-time
proxy target was `http://127.0.0.1:8766` with `changeOrigin:false`; the existing
same-origin guard was preserved. No production Vite configuration was changed.
