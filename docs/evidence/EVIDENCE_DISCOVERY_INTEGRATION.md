# Evidence discovery — integrated acceptance

**2026-10-13 · baseline `1698f6abb74523a3d04b54e840bd38057f55c2a9`.**
[Accepted contract](../agents/EVIDENCE_DISCOVERY_TASK.md),
[D33](../roadmap/DECISIONS.md#d33--discover-recorded-text-through-exact-source-contributors).
The implementation and integrated verification below are complete.
All data is authored public fixture evidence. No native process/model/account call.

## Observed gap

The existing 1,200-turn fixture is useful after a semantic map supplies support
coordinates. Removing only derived maps preserves its exact raw evidence but
leaves paging and numeric source navigation. Result search cannot find source text
before a result exists; native semantic indexing remains gated.

Root seeded `scripts/evidence_discovery_demo.py`: 2,605 raw records, including the
existing large history and additional split-delta, overwritten completion,
interleaved same-thread source and excluded-field cases. The map removal preserved
the original raw hash; all added cases are explicitly authored. No saved work or
preselected source coordinates were installed for the browser task.

Actual Chromium/local API on the same fixture: the initial 40-turn page did not
contain the remembered decision. Sequential rendered-page phrase detection used
27 Later turns actions, with no supplied record number, to reach it. Thirty reads
of that thread (including background polls) transferred 1,201,333 response bytes;
the whole baseline captured 36 reads / 1,204,443 response bytes / zero POSTs. Dirty
editor bytes remained unchanged. Root inspected first-page and reached-decision
screenshots. This is not a measurement of human search speed or answer quality.

Raw report `/tmp/nema-evidence-discovery-browser-20261013-baseline.json`, SHA-256
`1fdb5f79d26100e077c9be9a57b8c696f9e30de013dca526b99e5dc39011fdb0`.
Large raw captures stay outside this public repository.

## Implemented behavior

Search typed recorded text fields using shared display-projection precedence,
with explicit eligible-source scope. A replaced draft cannot supply a current
match; a phrase split across deltas can. Provider/control records are excluded
before projection, even if they reuse an eligible item's coordinates. Exact raw
inspection remains distinct from the current surrounding thread view.

Search and inspection are read-only. Explicit Add stages exact contributing record
references; canonical Save freezes source bytes under the existing builder.
Independent scouting reproduced an old selection error: item records [1,3] became
range1–3, including unrelated same-thread2. The UI lane corrects this path and
routes source additions through current editor busy/pending-save guards.

A derived index and its versions are replaceable projections, not source authority.
Cold rebuild and literal scan cost remain explicit. Limits bound returned excerpts
and raw detail; they do not prove constant-time corpus search. Private-control
storage stays outside this read path. Copied text grants no execution capability.

## Actual changed UI and recovery

On the same corpus, the remembered-decision phase made three successful reads:
search 767 bytes, exact raw source 1,455 bytes and surrounding source page 43,171
bytes, totaling 45,393. It used no supplied record number and required no sequential
page advance. These are scripted retrieval costs; the first baseline also found
the distant decision eventually. This does not establish human-speed improvement.

The whole flow captured 57 requests and one deliberate canonical draft POST. Search,
inspection and history reveal left an original dirty question/pending-save entry
byte-identical; source Add stayed disabled. A held source response could not revive
after query/aperture change. Unknown, replaced, hidden, control and provider phrases
returned no hits. In a separate isolated browser context, explicit Add collected
decision 2397, counterexample 138 and split-delta records 2597/2599; unrelated same-thread
2598 stayed out. Canonical records equal the exact inspected envelopes. One owner,
one request mapping, zero attempts/artifacts/adoptions. The entire 2,605-record raw
source hash remains unchanged.

After an actual API restart on the same database, explicit restoration of authored
browser snapshots recovered the same canonical context and independent pending
draft. Final restart/pagination/filter run: 38 GETs, zero POSTs. Actual 20-hit next/
previous pages and exact-thread filtering passed. Root inspected 1600/390px search,
exact raw sources, disjoint selection and canonical context; no document/component
horizontal overflow was measured. A final text-only correction pluralizes counts.

First restart run is preserved separately: 53 GETs, zero POSTs, no application JS
exceptions. The harness reloaded its second fresh browser context before initial
reads settled; a canceled intercepted thread read left its request tracker pending
and Chromium reported Invalid InterceptionId. Waiting for those initial reads
before restoration/reload fixed the harness; no product logic changed for this.
The first raw report is not relabelled as successful.

| Report under `/tmp/nema-evidence-discovery-browser-20261013-` | SHA-256 |
| --- | --- |
| `baseline.json` | `1fdb5f79d26100e077c9be9a57b8c696f9e30de013dca526b99e5dc39011fdb0` |
| `flow.json` | `25966604312a8c8799f2bae0e0343c6d16b454f775fbb3e3b9c02491bcd5f65d` |
| `first-reopened-failure.json` | `ea71e5964eaa750f6277eb9619604c3bf9411d2c51c3bae62c9292474482eccb` |
| `reopened.json` | `aa7d3b8de0a293d585de5705503f5f19f12802ecc191058d525337942de4f4ef` |

## Independent counterexamples, costs and verification

Backend `a65be27` plus response-bound correction `398bdd7`; UI `720355e`;
independent tests `06867e4`/`65b98d1`. Review accepted final source. Exact-source
cases cover exclusion before same-ID projection, late RPC hydration, user-input
suppression, concurrent annotation/update/delete/rollback, stale cursors/hits,
rebuild epochs, exact canonical save/reopen and private-role refusal.

Root reproduced an unusually long imported coordinate yielding a 200,467-byte
single-hit response. The full search envelope now has the same 128KiB ceiling as
inspection, with 413 rather than truncated identifiers or hidden matches. Independent
Unicode metadata reproduction failed before the fix and passed after. Page limits
and short excerpts alone were insufficient.

On a copied 2,605-record root fixture, cold search took 47.124ms; subsequent ordinary
queries took 0.275–0.358ms. Owner instrumentation found warm unchanged reads parse
zero raw JSON; a changed long thread reprojects that whole thread. The index is a
replaceable performance adapter; cold rebuilds, changed-thread projection and
literal scans scale with corpus text, and are not CPU/RSS quotas. The read snapshot
reserves SQLite write access during refresh/query for consistent generation/results.

Parent full Python: **1,602 passed / 55 explicit native skips in 59.13s**,
`/tmp/nema-evidence-discovery-parent-full.log`. UI: **146 tests / 689 assertions**,
zero Svelte errors/warnings and clean build; final text-only correction also passes
check/build and restart browser inspection. Seed-context 5 passes. Root reviewed
actual diffs, and independent review checked root fixture/browser evidence scripts.
All owned API/Vite/Chromium processes and recorded crash handlers stopped;
ports 8767/5173/9233 closed and temporary Vite config removed. No native call was run.
