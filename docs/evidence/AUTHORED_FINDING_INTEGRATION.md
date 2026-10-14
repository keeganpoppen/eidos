# Authored findings: exact support without native dispatch

**2026-10-13 · integration base `2aae982806de5386d0e42dc22f499bdb6d5e77f4`.**
[Contract](../agents/AUTHORED_FINDING_TASK.md),
[D35](../roadmap/DECISIONS.md#d35--authored-findings-are-reusable-knowledge-independent-of-native-completion).
All source material is explicitly authored from public repository excerpts. No
account, private history, native startup, model or upstream request was used.

## Decision and implementation

Root asked why same-thread imports are refused and what would justify a merge,
using D34 and the exact `HistoryImports.commit` implementation at the base. A
conclusion stored in selection rationale survived reopen and historical-input
reuse, but result search could not find it. Completion correctly refused409 without
an attempt. Actual baseline browser inspection found the saved context and closed
native action, with no authored-finding action:19GETs, zeroPOSTs, desktop/390px.

The investigation now retains optional immutable `findings[]`, pinned to an exact
saved context and attributed as a local owner submission. Canonical membership,
schema, citation sets and owner-bound content identity are checked through a small
shared resolver. Native artifacts still require their own attempt provenance.
Result search, original-support inspection, frozen result inputs and plain saved
comparisons reuse existing references. No native status, output record, attempt,
adoption, inquiry or current-context transition accompanies a finding save.

The write accepts128KiB UTF8 prose and derives direct supplied citation membership.
Unsupported references remain visible; uncited hypotheses are permitted. Numeric
tokens are ASCII, at most16digits and2**53-1; unsupported zero is retained. This
new-path bound preserves exact browser/server identity without rewriting legacy
native values. Whitespace/BOM-only prose refuses; valid BOM-bearing prose keeps
its original bytes. A256KiB receipt limit is checked before commit.

Dedicated request receipts return the original finding after later context/native
progress and source damage. Identical content in one owner/context reuses that
immutable value; independent request receipts remain distinct. Browser draft/pending
state uses a separate512KiB slot with the exact body retained before POST. Reload
does not submit. Receipt reads and exact retries preserve the independent editor.
No total database, CPU or whole-owner read/write bound is claimed.

Integrated lanes: backend `5d9fa8` plus whitespace correction `49f6b0b`, UI
`ffa246e`, independent tests `c60df2c`. Root reviewed actual changes and owned the
public-repository fixture, browser acceptance, documentation and integration.

## Verification and defects that changed the result

Root `uv run pytest`: **1,706 passed /55 explicit native probes skipped in59.38s**.
Root UI: **220 Bun tests /940 assertions**, Svelte **0errors/0warnings**, clean build.
Logs `/tmp/nema-authored-finding-parent-{full,ui-tests,ui-check,ui-build}.log`.
Seed-context5passes and diff checks passed. Native probes were not enabled.

Independent acceptance covers six-connection exact replay, content deduplication,
late receipt-write rollback, F0/C0 after C1 and an explicitly synthetic native
completion, source deletion, copied-owner/forged-kind/ambiguous-ID refusal,
direct versus inherited citations, saved comparisons and unchanged legacy hashes.
Synthetic completion fixtures do not represent native execution.

Review found two actual implementation defects before integration: a FEFF-only
finding was accepted by Python but rejected by browser whitespace validation;
and a disposed UI client could process a late201 and rewrite the slot after a new
client had restored it. Narrow admission and disposal guards repaired both;
regressions demonstrate the original failures and exact subsequent recovery.

The first browser recovery run also exposed harness mistakes. It assumed a newly
created question was already in a mounted catalog page, and its generic dialog
selector clicked a hidden dialog's close button. Screenshot inspection revealed
later scripted actions behind the still-open inspector. Those results were not
accepted as a complete UI demonstration. Root preserved the report/screenshots and
database, changed the harness to explicit catalog searches and visible-dialog
selectors with closed-state assertions, then repeated the entire changed workflow
on a fresh fixture. No product patch was needed for these harness errors.

## Final actual browser sequence

Fixture database `/tmp/nema-authored-finding-final-20261013.db`; marker
`/tmp/nema-authored-finding-final-marker.json`. Public source excerpts and their
file hashes are pinned to2aae982. Authored owner
`investigation_672a93e6a6b044cba307222099fd462c` retains C0
`context_9908c4859879a2b87e88db2204adb3495cea7c9a1fa4e846dc6831dbe548676b`.

1. **Flow:29requests/onePOST.** Write F0 while an independent investigation has
   dirty inputs and an authored pending-save identity. Deliberately lose the201
   reply. Exact pending finding body and independent editor survive reload;
   no automatic POST and only one canonical finding.
2. Advance the marked fixture explicitly to C1 and stop/restart the actual API.
   **Recovery:72requests/fivePOSTs.** Explicit receipt GET returns F0/C0 with no
   write. A separately restored pending snapshot performs exact retry200. In a
   fresh browser context, remembered result text finds F0; inspect original support
   before adding it to B. Save B, then its finding citing F0 while `[evidence:1]`
   is correctly unsupported because B contains no directly selected raw records.
   Save an uncited C1 hypothesis with “No cited support”. Search both exact owners,
   apply and save a plain comparison. The five writes are retry, B creation,
   B finding, hypothesis, comparison. No native action occurs.
3. Stop/restart the API again. **Reopened:20GETs/zeroPOSTs.** A fresh browser finds,
   previews and opens the same saved comparison. Both owners are exactly equal to
   their prior values. Open the visible source inspector and both original raw
   records; displayed raw text and SHA256 match the original C0 values exactly.

Root inspected desktop1600px and narrow390px screenshots, including pending,
source inspector, unsupported citation, uncited hypothesis and reopened comparison.
No document/component horizontal overflow was observed. Explicitly restored local
snapshots are labelled in the scripts; disposed contexts are not claimed to persist.
All browser POST paths were checked against question/finding/comparison writes.

Final independent SQL check: **2original raw records,2investigations,3findings,
3finding request receipts,1composition,zero attempts/artifacts/adoptions**. Both
owners remain native-status `draft`. The original raw text/hashes are unchanged.
Cleanup `/tmp/nema-authored-finding-cleanup.json`: all owned API/Vite/Chromium
descendants and observed crash handlers stopped;8767/5173/9233closed; temporary
Vite config removed. No service is represented as still running.

## Reproduction and retained artifacts

Use `scripts/authored_finding_demo.py --db <fresh.db> --output <marker.json> --serve`
with the normal local UI pointed at8767. Launch an isolated loopback CDP browser.
Run `scripts/authored_finding_browser.mjs` with `NEMA_AUTHORED_FINDING_MARKER`,
`NEMA_UI_ORIGIN`, `NEMA_UI_DEBUG`, `NEMA_UI_EVIDENCE_PREFIX` and mode `flow`.
Explicitly advance only that marked fixture with `--resume --advance`, restart
its API, run mode `recovery`, restart again, then mode `reopened`. New fixture
creation refuses an existing database/sidecars; resume requires its unique marker.
Mode `baseline` is for prechange2aae982 and does not pass against the new UI.

Reports below are local authored evidence, not committed personal traces:

| Report under `/tmp/` | SHA256 |
| --- | --- |
| `nema-authored-finding-baseline.json` | `2dff767675bc31d9cef6b9115048f3ce183a14b0f7641ad49dda914901924c22` |
| `nema-authored-finding-browser-20261013-baseline.json` | `0b85d872f0922ef7ce4fc83a5f67b52f46d7ca08499a610c3d3a234140e24e2a` |
| `nema-authored-finding-browser-20261013-recovery-first-failure.json` | `9cb80356e27a752e2b33f2e2f8d24a41018fd6e86b170649ba21898204324cad` |
| `nema-authored-finding-final-browser-20261013-flow.json` | `d90fb33d19d63789ac83f412e33cc62d2326393f24024b4c89c10b580a479047` |
| `nema-authored-finding-final-browser-20261013-recovery.json` | `864ce424d48b66e2adca6508fb18f3b0cd548cf99b494053882a9089e256fe1e` |
| `nema-authored-finding-final-browser-20261013-reopened.json` | `28116689d3938e62dd383ceaf5c2f970f7dc7fa0ffb82abc015a7220c0f5542b` |
| `nema-authored-finding-parent-verification.json` | `e8bdab42900c0cfe9bfb1f814db3e3038da2e8a9fe872e82186122618a75e491` |

This establishes a useful scripted public-repository finding/reuse loop. It does
not measure returning-person speed, logical correctness of authored claims, native
answer quality, actual subscription availability or complete V1 acceptance.
