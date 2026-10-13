# Recorded experiment composition acceptance

2026-10-13 · acceptance base `579af9d`; fixture/tests first published in `b623ff8`.
This tests actual saved experiment, source and composition APIs over an explicitly
synthetic canonical history. No native subprocess or model is used.

The fixture freezes C0, C1 and C2 through the normal draft API. A labelled
trusted-host fixture helper then installs synthetic historical attempts/results
with canonical manifest pins, output records and completion validation. This
construction supplies C0/A1, a later C1 result and current C2/A2; it is not a
production feature for dispatching arbitrary historical contexts. The public
experiment API freezes E1 as C0/A1 versus context-only C1 before those later
results exist. E2 instead compares C0/A1 versus C2.

Both initial contexts include the same source artifact ID and exact artifact
content. C0 freezes its unreviewed state; C1 freezes its later rejection. The v2
evaluation marks that ID as changed, reports no added/removed artifact IDs, and
fails the frozen-result retention check. A source-level difference is visible;
this measurement makes no claim of better reasoning or user benefit.

## Independent backend verification

`tests/test_recorded_experiment_acceptance.py`: **14 passed** against the
integrator's current source. `AppServerClient.start` fails the test if invoked.

- Controller reopen preserves original experiment fields, context packets,
  baseline attempt/manifest and source raw bytes, including unknown fields.
- Current review changes independently; historical experiment targets and an
  existing saved snapshot remain identical. Read/preview/save operations do not
  change canonical owner rows, trace, request pins or authority occurrences.
- A new snapshot cannot bind E1 to current C2/A2, fill C1 with its later artifact,
  or substitute E2 while keeping E1 targets. Explicit result/context lens choices
  preserve the context-only target.
- Missing owner/experiment, wrong-owner experiment and missing baseline artifact
  fail without substituting current work. Old snapshot descriptions remain readable.
- Malformed trusted-import counterexamples change A1's attempt reference while
  retaining its descriptive artifact ID. Wrong-context attempts fail; a different
  valid attempt at the same context can resolve a generic reference but cannot
  satisfy E1's separately pinned baseline attempt. These cases exposed a backend
  admission-consistency gap, fixed by the integrator. They establish reference
  validation, not authenticity of arbitrary imported history.
- Real local HTTP returns exact experiment and source packets without dispatch or
  source mutation. Experiment responses describe the named evaluation and pins;
  the separate source response returns its exact original context and attempt.

The [persisted fixture record](RECORDED_EXPERIMENT_SYNTHETIC_2026_10_13.json)
contains frozen packets, initial E1/E2, an original named snapshot and exact
source IDs. All records and authored completions are synthetic.

## Browser evidence

The browser entrypoint is
[scripts/check_recorded_experiment_ui.mjs](../../scripts/check_recorded_experiment_ui.mjs).
It creates fresh E1/E2 occurrences through the actual API for each run, so review
advancement is repeatable on the same fixture database. That setup and the one
explicit synthetic review decision are reported separately from UI requests.
The final run passed against UI revision `fcf333f`; its
[rendered evidence](recorded_experiment_ui_2026_10_13.json) records each assertion
and actual HTTP response body sizes.

The script checks the investigation's Compare action and explicit Review/Apply;
unchanged dirty owner fields; exact baseline support and frozen source review;
context-only alternatives after lens changes; manual current-review refresh;
stale E1 after newer E2 and a delayed free-owner lookup; read failure/retry;
wrong-owner/missing experiment refusal; fresh-browser named snapshot recovery;
real pending investigation-save identities through navigation/reload; and the
separately labelled authored fixture. Mobile inspection includes the recorded
review, source-input diff and long artifact citation controls.

The run observed 17 successful exact experiment reads of 2,328–2,572 bytes,
one injected 503 and two expected 404 responses. Six exact source reads returned
6,534 or 8,525 bytes. The owner-wide experiment list was fetched once in the
investigation panel and never by comparison opening, refresh or recovery. These
are captured response sizes for this fixture, not general bounds on owner history.
The browser issued three intentional writes: two investigation saves whose replies
were dropped to establish real pending identities, and one named snapshot save.
Separate fixture setup issued two experiment creates and one explicit review.
No browser dispatch, adoption or review mutation occurred; no native/model call ran.

The delayed owner-read counterexample required invalidating obsolete free-comparison
binding work when a newer exact experiment preview takes ownership. The first mobile
pass also exposed an unwrapped artifact citation control. Both fixes are included in
`fcf333f`; the final run has zero JavaScript exceptions and zero document/comparison/
diff horizontal overflow at an actual 390px viewport.

The acceptance agent inspected the final [desktop experiment](recorded_experiment_ui_2026_10_13_desktop_experiment.png),
[exact source and raw record](recorded_experiment_ui_2026_10_13_desktop_exact_source.png),
[390px current review](recorded_experiment_ui_2026_10_13_mobile_review.png), and
[390px context diff](recorded_experiment_ui_2026_10_13_mobile_context_diff.png).
Source bytes and unknown fields remain readable; source review is visibly distinct
from the current experiment review. The mobile screenshots show normal scale and
wrapped identifiers.

## Reproduce and scope

```sh
uv run pytest tests/test_recorded_experiment_acceptance.py
uv run python scripts/recorded_experiment_demo.py --db /tmp/recorded-experiment-demo.db --output /tmp/recorded-experiment-demo.json --serve
```

Use a new database path. For the marked fixture only, `--resume` verifies retained
pins after reopen. Start Vite on 5173 and dedicated Chromium debugging on 9222, then:

```sh
NEMA_RECORDED_EXPERIMENT_FIXTURE=/tmp/recorded-experiment-demo.json NEMA_RECORDED_EXPERIMENT_UI_PREFIX=/tmp/recorded-experiment-ui bun scripts/check_recorded_experiment_ui.mjs
```

Isolated acceptance tests import the root source explicitly with
`PYTHONPATH=/home/elkeegano.guest/eidos/src uv run --project /home/elkeegano.guest/eidos pytest -q -o pythonpath=/home/elkeegano.guest/eidos/src tests/test_recorded_experiment_acceptance.py`.

This is scripted same-database composition and recovery. Source truth, arbitrary
caller authentication, native admission, actual model benefit and human task speed
remain outside its scope. Referenced owner views can still load complete selected
histories. Root owns independent integrated reproduction, canonical handoff and
adoption; this acceptance lane owns only its fixture, tests, browser script and
unique evidence.

## Parent integration verification

The integrator reviewed `aa0d847` + `fcf333f` and acceptance `b623ff8` + `6e8ae53`,
then reproduced the complete browser script against integrated main. All four
new desktop/mobile screenshots were inspected; document/review/diff overflow at
390px was zero, with no JavaScript exceptions. Three browser writes (two explicit
pending investigation saves and one comparison save) are separate from setup's
two new experiments and one review. No native dispatch occurred. Parent artifacts
are `/tmp/recorded_experiment_main_reproduction.json` and matching PNGs. Owned
fixture services were stopped after reproduction.

An independently generated/reopened new database produced byte-identical inspection
reports. Combined main Python including the separate catalog probe: **891 passed,
41 skipped**. Final main UI: **73 tests / 385 assertions**, check **0 errors /
0 warnings**, build passed. These results establish the stated synthetic workflow
and integrity cases, not human task speed or answer quality.
