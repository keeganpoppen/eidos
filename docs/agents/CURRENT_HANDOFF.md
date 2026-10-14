# Current handoff — discover evidence before knowing its coordinates

**2026-10-13 · integration base `1698f6abb74523a3d04b54e840bd38057f55c2a9`.**
This snapshot accompanies the completed evidence-discovery integration. Historical
input reuse at that base is pushed and [CI38491870455](https://github.com/keeganpoppen/eidos/actions/runs/38491870455)
passed. The continuing autonomous mission remains active; a completed slice is not
its completion. No real account, private history, model or upstream call authorized.

## Completed C3/C5 slice — V1-01/04/08

[Contract](EVIDENCE_DISCOVERY_TASK.md), [acceptance](../evidence/EVIDENCE_DISCOVERY_INTEGRATION.md),
[D33](../roadmap/DECISIONS.md#d33--discover-recorded-text-through-exact-source-contributors).
Remembered text now finds eligible history before semantic maps or known record
coordinates. Shared projection precedence excludes replaced text; exact inspection
shows contributing raw records. Provider/control rows are filtered before projection,
even when reusing public item IDs. Excerpts and full response envelopes are bounded;
stale cursors/hits refuse. Disposable SQL index tracks cross-connection mutations.
Cold rebuild, dirty-thread projection and literal scans remain corpus-scaled.

Explicit Add stages exact disjoint membership, correcting the prior [1,3]→1–3
selection error. Current busy/pending-save gates cover discovery and legacy item
Add. Read-only search/inspection preserves dirty and pending drafts; late responses
cannot revive after query, navigation or aperture changes. Canonical Save remains
the source freeze boundary: inspected hashes are not a new Save precondition.

Integrated lanes: backend `a65be27` + `398bdd7`, UI `720355e`, independent acceptance
`06867e4` + `65b98d1`. Root owns public authored fixture/browser scripts, count
pluralization, docs and final integration. Prior [historical input reuse](../evidence/CONTEXT_INPUT_REUSE_INTEGRATION.md)
and [managed attempt](../evidence/MANAGED_ATTEMPT_INTEGRATION.md) evidence remains linked.
Preserve the legacy policy literal identified in `2a62d68`; it hashes into manifests.

## Verification and cleanup

Full Python **1,602 passed / 55 explicit native skips in 59.13s**; UI **146 tests /
689 assertions**, zero Svelte errors/warnings, clean build. Final text-only correction
also passed check/build and restart browser inspection. Independent review accepted
source and scripts; Unicode metadata demonstrated and closed a response-size gap.

Same authored 1,200-turn corpus, with maps removed: baseline 27 page advances,
36 GETs/zero POSTs, 1,201,333 long-thread response bytes. Changed remembered-decision
phase: 3 GETs/45,393 bytes, no supplied source coordinates. Whole flow: 57 requests,
one canonical draft POST, exactly four inspected records across two threads and
no interleaved neighbor. Dirty/pending draft bytes unchanged. Actual API restart,
pagination and filtering: 38 GETs/zero POSTs; saved context and separate pending
editor restored exactly. Desktop/390px screenshots inspected, no horizontal overflow.
First restart harness race is preserved separately; settling initial reads before
restoration/reload corrected the harness, with no product logic change.

Scripts: `scripts/evidence_discovery_demo.py`, `scripts/evidence_discovery_browser.mjs`.
Reports/hashes: [acceptance](../evidence/EVIDENCE_DISCOVERY_INTEGRATION.md), raw captures
`/tmp/nema-evidence-discovery-browser-20261013-*`. Fixture2,605 records, one owner,
one request mapping, zero attempts. Source raw hash unchanged. All owned API/Vite/
Chromium roots, descendants and recorded crash handlers stopped; 8767/5173/9233
closed, temporary Vite config removed. No native call. Scripted retrieval does not
measure human speed or answer quality.

## Next discriminator and ownership

Independent scouts converge on reliable explicit-file history ingestion. Existing
`import-jsonl` already accepts one direction/source for a file; it is an append loop,
not a missing feature. A malformed tail leaves a committed prefix, and retrying it
duplicates a delta. Unsupported objects can report success without visible threads.
Start with a root reproduction and fresh-empty-browser baseline. Freeze a bounded
preflight → atomic commit → durable exact-operation receipt contract before exposing
upload. Retain original bytes, unknown fields and line-to-sequence mapping; preserve
intentional repeated lines. Retry after lost reply/restart must return original
membership. Do not scan directories, infer mixed traffic directions, call codex-sync
or claim arbitrary exports are supported. Use only authored/supplied public fixtures.

Root next: inspect `src/eidos/trace.py:import_jsonl`, `src/eidos/cli.py` and empty
`ui/src/routes/+page.svelte`, then establish contract and disjoint fresh worktrees.
Completed discovery worktrees remain clean under `/tmp/nema-evidence-discovery-`
`backend`, `ui`, `review`. Backend/UI agents are now assigned read-only ingestion
contract refinement; no new implementation assigned yet. Older managed worktrees
may contain historical unintegrated changes and must not be swept into main.

Independent alternative worth testing after entry integrity: complete and reopen
an owner-authored evidence-backed finding without fabricating a native attempt.
Existing rationale/review notes may or may not cover that need; establish an actual
workflow gap before adding another artifact type. Aperture-to-new-question input
reuse is another narrow composition candidate. Real owner usability and authorized
subscription-backed useful work remain unobserved.
