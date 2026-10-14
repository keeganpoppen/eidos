# Historical input reuse — integrated acceptance

**2026-10-13 · working base `2a62d68` · C1/C4/C5 / V1-04/08/09.**
[Contract](../agents/CONTEXT_INPUT_REUSE_TASK.md),
[D32](../roadmap/DECISIONS.md#d32--reuse-frozen-historical-inputs-through-a-new-canonical-question).
All source history/results and browser recovery entries are explicitly authored.
No native process, account, model, external action or automatic adoption occurs.

## Behavior and evidence

A historical context preview can now stage a blank new question using its exact
frozen records, selections and result snapshots. Existing create handles an exact
inputSource reference instead of fresh selectors. One canonical projector builds
new prompt/coverage and hash-covered inputOrigin; within-owner revision lineage
stays separate. Server resolves request replay before source lookup and never
refreshes inherited source reviews or revives old prompt/inquiry/native state.

The separate browser staging entry persists exact body/request identity before
sending. Save success remains inspectable without replacing the current editor.
Read-only saved-input inspection pins the initial context even when its owner later
has newer revisions. Open requires resolving an original pending save and an
explicit replacement choice for dirty fields. Changed draft/preview/navigation
or leaving the investigation surface cancels a delayed Open response. Missing-source
400/404/409 refusals retain exact requests until deliberate dismissal; unknown
network outcomes retain exact retry. Reload sends nothing automatically.

Thin selectors were rejected because ordinary artifact resolution recaptures
current adoption metadata. A complete frozen source context remains reusable when
its original raw rows/result owner are absent; a missing or wrong-owner context
refuses. This makes the snapshot useful without claiming its source is still
reachable or true. Unknown raw/envelope fields survive. Later edited contexts
point to their parent without claiming they still equal the initial reused inputs.

## Independent counterexamples

Backend tests preserve raw/inquiry/runtime field separation, legacy identities,
source snapshot hashes, current prompt bounds and exact request conflict behavior.
Independent review deletes original raw rows and the artifact owner and forbids
raw SELECTs: frozen reuse still succeeds. Six separate SQLite connections create
exactly one target and one revision event for the same request. A committed reply
lost before a later target revision/source deletion reopens with the initial
context intact, even though normal request replay returns the current owner.

UI review caught wrong-title receipts, unsaved-new-editor detection, a changed
historical preview during delayed Open, and Compare hiding the still-mounted pane.
The final guard binds editor, preview, staged receipt, navigation and visibility
generation. Component/helper tests cover storage failure before send, lost response,
refused/uncertain recovery, stale replies and initial-versus-current context pins.

## Actual browser outcome

The same fixture was inspected before and after implementation. Baseline:
18 API requests, zero POSTs, C0 preview beside a different C1 editable selection;
no historical-input reuse action. After implementation: 67 requests and exactly two
identical creation POSTs, the first 201 response deliberately lost, the second
recovering it. SQLite inspection confirms one request mapping and one new reused
investigation. The two existing authored historical attempts remain the only
attempts. No dispatch/adoption/cancel endpoint was invoked.

C0 contains two disjoint records and an old adopted result snapshot; a newer result
and review exist at its source, and C1 selects different evidence. The new draft
retains C0's exact inputs/rationales/old review, uses the new question, and carries
its original context/manifest reference. Source owners and frozen history remain
byte-equivalent. Existing dirty editor/pending-save storage stays byte-for-byte
unchanged through stage/create/retry/reload/read-only exact-prompt inspection.
Open is blocked by the pending editor save. A second isolated browser context
checks Keep editing versus explicit replacement, and a held Open response across
Compare→return cannot change that editor. Confirmed Open selects the exact created
context. Desktop 1600/390px checks report no document/component horizontal overflow.

After actual API restart on the same database, a new isolated browser context
restores the previously captured authored local-storage entries. Eighteen GETs,
zero POSTs resolve the same result and retain both recovery identities. This is
explicit fixture restoration, not a claim that disposed browser contexts persist.
Root inspected desktop/mobile captures and corrected default browser buttons to
use existing workbench styles. A separate appearance run made 28 GETs and zero
POSTs, restoring authored snapshots only in an isolated browser context. Root
inspected its saved result, exact packet and form controls at 1600/390px; no
document or new-component horizontal overflow was measured.

Raw reports/screenshots stay outside the repository under
`/tmp/nema-context-reuse-browser-20261013-*`. Report SHA-256 values:

| Report | SHA-256 |
| --- | --- |
| baseline | `32a372cdd44608b5805e7f9096a2ad631c245044a9854b11fefdf7dd1a515d29` |
| flow | `9df227dae33fc570f1f889c97771d068793684f9d315962a3ab049c457388ed1` |
| reopened | `bab2749b6e9f0b132278ee13a12bb79c4a65dc2542daa692c6749905d8a88328` |
| appearance | `3265481c167a4abdbcca72bdc3a3de1e716753901495777867da5b206d1c08d2` |

All owned API/Vite/Chromium processes, including recorded crash handlers, stopped;
ports 8767/5173/9233 closed and temporary Vite config removed. Scripted availability
and identity preservation do not measure returning-person speed or model answer quality.

## Verification

Backend `62fcb32` and independent acceptance `8a451ba`; UI `0915378`, visibility
fix `96ee184` and style-only `c66796f`. Parent 42 focused backend/independent/legacy
checks pass in 0.55s. Full parent Python:
**1,559 passed / 55 explicit native skips in 57.51s**,
`/tmp/nema-context-reuse-parent-full.log`. UI: **126 tests/610 assertions**, zero
Svelte errors/warnings and clean build. Final visibility and styling changes also pass check/build and are exercised by
the browser. Seed navigation 5 passes.
No native invocation was run for this slice.
