# Supplied text and a saved engineering review

**2026-10-14 · implementation base `d2b5fdb06a88c5c1ac8f6d1b53ea71274ff3d290`.**
[Contract](../agents/SUPPLIED_TEXT_TASK.md), [D37](../roadmap/DECISIONS.md#d37--supplied-files-are-source-evidence-not-native-messages).
Integrated backend da018c8, UI a9adb2e +239e100, independent acceptance783d7ac.
Root owns episode/browser scripts, actual acceptance, final integration and docs.
All source/check files are public or explicitly authored. No workbench native,
account, auth, private-history, model or upstream operation was performed.

## Discriminator

Root independently reran the initial scout at
`/tmp/nema-local-reflection-parent-20261014`: ordinary JSON check output imports
through the actual CLI and retains exact bytes, but has no selectable thread or
discovery hit. Plain output refuses JSONL preview. A native-shaped authored wrapper
permits findings/comparison but renders as a message with misleading coverage.
Existing knowledge Values suffice for the later review; the missing part is intake.

The committed `scripts/supplied_text_episode.py` captures a subprocess executing
the public2386b29 import method and the publicd2b5fdb atomic adapter on the current
TraceStore. Malformed-tail retries retain1then2 records under the historical method,
zero then zero under the repaired adapter; intentional duplicate valid lines remain2.
This is a method/adapter comparison, not a full historical-release run. The actual
stdout SHA256 is `90eedb09dd716ddb6407b338d15c804d82dba4f862dd5de7a3c02933fe0e9623`.
It is distinct from the scout's earlier generated observation report.

Actual baseline browser: seven requests, one refused preview POST, no admission.
The independent unfinished question remained exact. Desktop and390px screenshots
were inspected. Root then used actual UI file selection, preview, commit, search,
source inspection, context save, authored findings and saved comparison.

## Implementation and counterexamples

`SuppliedText` admits one explicit UTF-8 file through preview/commit/receipt/original
GET routes. BLOB, host record and receipt commit atomically. Original bytes/hash
remain distinct from the generated envelope/hash. Exact replay compares submitted
bytes/name/format and the stored preview token before current parsing. A different
token under that request refuses409; old exact replay survives parser changes.

Live projection requires the admission ledger's exact record, coordinates, source,
bytes and hashes. Imported host shapes are refused; unknown native fields remain
opaque. Local source groups cannot reach native messaging. Frozen `localEvidence`
describes the supplied file after source loss, without resolving upstream authority.
Only document-containing new contexts change coverage; native-only hashes and the
historical managed-policy literal remain unchanged. Supplied text renders in escaped
plain text in history, discovery, context inspection and result provenance.

Root independently found a projection collision in the first implementation:
foreign typeless `item/completed` at an admitted document's coordinates inherited
its suppliedText type, indexed forged text and crashed history with missing
localEvidence. Preserved `/tmp/nema-supplied-text-projection-counterexample.py/json`.
The repair requires per-record admission throughout a local group, including
native-shaped completions/deltas/turn inputs. Review also caught an unknown dict/list
item.type compatibility regression in reserved-shape checking; tuple comparison
preserves old opaque-field behavior. Whitespace/BOM-only display names are refused
without normalizing accepted names. Original BOM/content/newline bytes survive.

Bounds:64KiB original bytes,64KiB generated envelope,96KiB serialized ContextRecord,
128KiB entire JSON response,480-character preview,4KiB browser recovery metadata.
Actual JSON escaping is counted. Existing128KiB aggregate prompt bounds still apply.
These are per-operation/wire bounds, not total database, CPU, memory or latency quotas.

## Verification

Parent `uv run pytest -o addopts='' -q`: **1,798passed /55explicit native skips,
65.80s**, `/tmp/nema-supplied-text-parent-full.log`. Backend32 new cases;
independent24 composed cases,93 combined compatibility tests. Independent review
includes six concurrent connections, exact replay after restart/raw loss, parser
failure, changed token, transaction rollback, copied/ordinary collision schedules,
warm ledger invalidation, private-store refusal and preserved historical inputs.

Parent UI: **265tests /1,213assertions**, check0errors/0warnings, buildclean.
Logs `/tmp/nema-supplied-text-parent-ui-{tests,check,build}.log`; presentation-only
rail correction received final parent check/build again. No new tests for that label.
The rail now identifies supplied text instead of displaying synthesized turn counts.

Actual browser reports share prefix `/tmp/nema-supplied-text-browser-20261014`:

| Mode | Requests / POSTs | Observed outcome | Report SHA256 |
| --- | --- | --- | --- |
| baseline |7/1| Plain stdout refuses JSONL preview |35a1715e8b548b74502b8414d09ec2d5fefe8e0f8a39b5a009127eab86bae798|
| flow |24/4| Two previews/admissions; second201reply lost; reload preserves pending metadata and independent slots |aa1dfc82c957d5b08586d5c1296a40735afe55305301548294cd4d719626e201|
| recovery |56/7| Actual API restart, receipt GET, wrong-file refusal, exact retry200; remaining three files admitted |34c07671ce2a5201b1abe90f830594c4e6dadd9273a52af3844986c7cbec2cfd|
| episode |34/5| Four exact sources selected; observation and review findings; one saved comparison |d19b5461d6f4a8b89e2ab64ce8d5e66453767f1adcd505faa1df06e0ec34aa0d|
| reopened |20/0| Actual restart, fresh browser, exact comparison and full frozen text |61836c6b2e83ad4ddbd990b86432ec03d5b4a1577a141f4c0a783e89d0f406ca|
| boundary |19/2| Exact fixture creation replay200 and held preview; visible frozen adversary after source loss |1cd2e0c3eae74de353d1d6fede2949b7c3d81f545fbd730483293b7915c07082|
| source-deleted |25/0| Original files404 after marked deletion/restart; canonical questions and frozen support unchanged |e5168564f8538efd60917885ed52b2f65138e39577fcce9664f66393bb319f55|

Desktop and390px acceptance had no horizontal overflow/runtime exceptions.
Network monitoring covers interactions after initial page load: the explicitly
opened literal Markdown/HTML image examples and frozen view created no external
requests or fetchable elements. The held preview was **browser-aborted-before-release**;
this proves cancellation, not delivery of stale bytes. Helper tests separately
cover fetchers ignoring abort. Independent editor/finding/history-import pending
canaries and source focus remain byte-exact during admission/recovery/close.

One harness correction is preserved as `...-boundary-first-hidden-frozen.json`
and `...-boundary-frozen-literal-contents-first-hidden-frozen.png`: DOM assertions
passed while an outer frozen-source disclosure stayed closed, so the screenshot
showed live history. Root rejected that visual evidence, opened all ancestor
disclosures, and reran after source deletion. The final screenshot visibly shows
frozen literal contents with no live thread. No application fix was needed.

## Saved episode and fresh reconstruction

Fixture `/tmp/nema-supplied-text-episode-20261014/workbench.db` is now source-deleted;
marker.json records this. Before deletion all five original files matched exact
bytes and SHA256. Afterward all three owner JSON hashes remain identical, zero raw
records/files remain, and all attempts/native artifacts remain null. Two owners
carry the review; a third is the isolated literal-rendering acceptance question.
`canonical-before-deletion.json`, `canonical-before-source-loss.json`, and
`canonical-after-source-loss.json` retain the byte checks. Fixture-only deletion
requires this script's marker and verifies every raw record belongs to its file ledger.

Saved observation `investigation_0e9b8b0d3dce4712b2ee14051e4fb5d4`, finding
`artifact_979bd40431311efd5ca1f6852f7e57bb11b2553b1de2c31573390157ee4eedb3`;
review `investigation_981a9a5aa8e948f0937efe9edf1da310`, finding
`artifact_f05e0217ed559ce167b4aef9af8f1e42165adaf2e33ff5f99bdfa203203f3602`.
The review includes scope, retain/reject-rollback judgment, costs left unmeasured,
and remaining obligations. It does not install code or turn draft status into adoption.

A fresh high-effort reviewer received only `saved-work-bundle.json`, read after API
restart (SHA256 `fb2bc9b7a695c6ca86e879cfa666f83c0cefdf565e66cea27792d73cd24d6318`).
It reconstructed pinned behavior, exact support, the review decision and rollback
constraints, and independently identified the limits: supplied-file integrity is
not authenticated execution; the bundle omits the exact harness/input and pinned
runtime/dependencies needed for an exact rerun;2aae982's original integration and
“reviewed parent” appear only in prose. No contradiction prevented analytical
continuation. This is recoverable coherence, not measured human benefit, exact
reproducibility, native model quality or completed V1 adoption.

All owned API/Vite/Chromium descendants and crash helpers stopped;8767/5173/9233
closed, temporary Vite config removed. `/tmp/nema-supplied-text-cleanup.json`.
Next discriminator: supply the missing reproducibility evidence through existing
documents/findings, test a fresh participant's exact reconstruction, and determine
whether any execution representation is actually missing before adding one.
