# Current handoff — historical input reuse integrated; unmapped recovery next

**2026-10-13 · integration base `2a62d681e38f34b1172640d89489f75ea3980335`.**
The commit containing this handoff integrates the following verified slice.
Prior managed attempts `fa7eabf` and legacy manifest correction `2a62d68` are
pushed; [CI38490354738](https://github.com/keeganpoppen/eidos/actions/runs/38490354738)
passed both jobs. The continuing autonomous mission remains active.

## Completed C1/C4/C5 slice — V1-04/08/09

[Contract](CONTEXT_INPUT_REUSE_TASK.md), [acceptance](../evidence/CONTEXT_INPUT_REUSE_INTEGRATION.md),
[D32](../roadmap/DECISIONS.md#d32--reuse-frozen-historical-inputs-through-a-new-canonical-question).
A historical context preview can stage a blank new question with exact frozen
records, selections, result snapshots and their old review metadata. Existing
POST /api/investigations accepts inputSource={investigationId,contextId} instead
of fresh selectors. The request ledger resolves replay before source lookup.
One canonical projector recomputes prompt/coverage and records hash-covered local
inputOrigin; parent=null keeps new-owner origin distinct from ordinary revisions.
Old prompt, inquiry, native state and unknown top-level fields are not inherited.
Unknown frozen raw/envelope fields remain intact. Frozen context suffices even if
original raw rows/result owner are gone; missing exact context refuses.

Separate browser staging persists the exact request before send. Lost replies
retain exact retry; reload never sends. Saved input inspection pins the initial
context even if the replayed owner has progressed. Open is deliberate: pending
editor save blocks it, dirty content requires a replacement choice, and changed
editor/preview/navigation/visibility cancels a delayed response. No dispatch,
adoption, activation, native fork or inherited authority.

Integrated lanes: backend `62fcb32`, independent acceptance `8a451ba`, UI `0915378`,
visibility fix `96ee184`, style-only `c66796f`. Root owns scripts, docs and integration.

## Verification and cleanup

Parent 42 focused checks passed; full Python **1,559 passed / 55 explicit native
skips in 57.51s**, `/tmp/nema-context-reuse-parent-full.log`. UI **126 tests / 610
assertions**, zero Svelte errors/warnings, clean build; final CSS also check/build
clean. Independent review accepted database concurrency, deleted underlying data,
progressed-owner retry and UI response guards.

Actual authored browser baseline: 18 reads, no reuse affordance. Flow: 67 requests,
exactly two identical creation POSTs (first committed reply deliberately lost),
one new owner. Historical snapshots and old review remain exact; dirty editor and
pending-save bytes unchanged. Keep/replacement, exact-prompt inspection and delayed
Open across Compare were exercised. Actual API restart: 18 GETs, zero POSTs,
explicit restoration of prior authored storage snapshots resolves same saved work.
Final appearance capture: 28 GETs, zero POSTs; desktop/390px inspected, no document
or new-component horizontal overflow. Report hashes are in the acceptance document.
Scripts: `scripts/context_input_reuse_demo.py`, `scripts/context_input_reuse_browser.mjs`.
Raw evidence remains `/tmp/nema-context-reuse-browser-20261013-*`.

All owned API/Vite/Chromium processes and recorded crash handlers stopped;
8767/5173/9233 closed. Temporary Vite config removed. No native/model/account call
was made for this slice. Scripted identity preservation does not measure human
speed, useful answers or real subscription service availability.

## Next runnable discriminator — C3 / V1-01/04

[PROGRAM](PROGRAM.md) records strategic ordering. Find remembered support in
unmapped imported history before knowing record numbers. Existing substantial
history proof supplies semantic-map coordinates; current history UI otherwise
requires paging or numeric Go to record. Exact result search deliberately excludes
raw history and cannot help before a first result exists.

Root: seed an isolated authored 1,200-turn history from
`scripts/investigation_demo.py`, remove only derived maps, demonstrate current UI
recovery limitations, preserve baseline. Then freeze a bounded contract for public
displayed-text discovery → exact source inspection → explicit disjoint selection
→ canonical save/reopen. Never inspect personal traces silently. Search raw JSON
is not equivalent: final items can replace earlier deltas, while split deltas can
assemble a match. Exact contributing membership and private/control-store exclusion
must remain explicit. No semantic ranking/model/indexing call is needed.

Read-only scouts active at this checkpoint: history_ui inspects backend projection,
index and store boundaries; native_frontier challenges product priority and UI
navigation/selection seams; native_frontier/gateway_review reviews root acceptance
scripts and proposes independent search counterexamples. No next implementation
ownership or native-resource contract has been assigned yet. Prior worktrees
`/tmp/nema-context-inputs-{backend,ui,review}` preserve completed lane commits.
Older managed worktrees contain historical uncommitted seams: do not integrate them.
