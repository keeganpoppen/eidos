# Explicit history import — baseline and integration evidence

**2026-10-13 · implementation base `2386b294cfe700622d672ff7e1a35dd9229eba30`.**
[Accepted contract](../agents/HISTORY_IMPORT_TASK.md). Implementation and combined verification below are complete.
All files and browser recovery snapshots are explicitly authored public fixtures.

## Observed baseline

Root used authored JSONL in an isolated temporary database. The current iterable
importer appended a valid agent-message delta, then raised JSONDecodeError on a
malformed second line. One record remained committed. Retrying the valid line
produced two records and displayed `needle needle `. This is a data integrity
failure, not simply a missing file chooser.

Report `/tmp/nema-ingest-baseline-20261013.json`, SHA256
`3f9e61bdee0794202d04e33a5fb57a3b3f938b9231e239f7e38b4856e0370e29`.

Actual Chromium against a fresh empty workbench made five GETs and zero POSTs.
Native thread creation was disabled, and the empty state suggested importing Codex
history without offering an import action or file input. An unfinished question
remained editable. Desktop1600px and390px screenshots were inspected; the latter
also makes the rail entry necessary because the empty source view is below the
initial viewport. No human speed claim follows from this scripted observation.

Script `scripts/history_import_browser.mjs`, mode baseline. Report
`/tmp/nema-history-import-browser-20261013-baseline.json`, SHA256
`f00890cae8a9d51ed69afadaf9c8bc7689ee53ce5e3b0c413216a5dbc628b3f5`.
No native process, model, account, private history or upstream call.

## Integrated behavior and boundary review

Backend `f597460`, UI `87135bd`, independent acceptance `e3261b3`. Root owns
fixture/browser scripts, integration/docs, count pluralization and a source-label
correction described below. Original file bytes, exact record lines, mappings and
receipt commit in one SQLite transaction. Replay resolves the same operation before
new parser/collision policy; it never recreates deleted source rows. Metadata-only
browser recovery requires explicit receipt checking or exact-file retry.

Review found source labels alone could correlate imported responses with unrelated
native requests, and native ID collisions could replace existing displayed history.
New imports therefore get a host-derived capture source and refuse existing thread
IDs, including retained annotations/maps. Reserved host-publication shapes refuse;
ordinary unknown fields and strings remain data. A receipt identifies supplied bytes
and local writes, not authentic native origin or execution authority. Legacy iterable
imports retain correlation semantics but now roll back as one batch/savepoint.

The fixture generator produces8records across two threads: an unknown object, future
fields, intentional identical repeated deltas, and a split phrase separated by an
unrelated same-thread record. Original file is1,491bytes,10physical lines including
2blanks, mixed CRLF/LF and an unterminated final line. SHA256
`83ae06a321743eaaa549c6a50ae45396f8ddc10a8cbc667dfd3996823bea03db`.
Malformed/unsupported companions exercise refusal. Its reusable --serve option now
requires exclusive creation of a fresh database; a reviewer caught that the first
helper draft could open unrelated existing work. An authored refusal check confirmed
existing bytes remain untouched before serve is called.

## Actual browser, failure injection and restart

Flow:22requests,5POSTs (four read-only file previews and one deliberate import).
Malformed final JSON and unsupported-only files publish no records. A held preview
cannot attach after selecting a different file. The accepted preview reports eight
records, two threads, four turns and five searchable fields; original bytes sent
match the supplied file. The first import reply is deliberately lost after201 at
the response interception stage. Reload sends no import; exact metadata and an
independent pending investigation editor remain byte-identical.

After an actual API restart, a fresh browser context with explicitly restored
pending metadata resolves the original receipt by GET with zero POSTs. Another
restored pending context refuses a different file, then deliberate exact retry
returns200 and the identical receipt; both POST bodies match. Recovery run totals
59requests,2POSTs: that replay and one canonical investigation creation. A separate
fresh question finds decision, counterexample and split phrase through recorded-text
search, inspects exact raw records and explicitly selects four records across two
threads. The interleaved neighbor stays out. Repeated identical deltas remain two
records, displaying `echo echo`. Canonical context equals inspected records; native
attempt/artifact/adoption remain absent. Reload retains the same saved question.

Second actual API restart:17GETs,zeroPOSTs; same receipt and complete canonical owner
resolve exactly. Root inspected desktop1600px and390px receipt presentation, file
preview, pending recovery and saved context. No document/component horizontal
overflow was measured. Imported unfinished records exposed a misleading existing
LIVE badge: it now says PARTIAL with a missing-completion explanation. Missing
command completion defaults also describe missing evidence rather than
claim running work. Final check/build and restart screenshots include this correction.

| Report under `/tmp/nema-history-import-browser-20261013-` | SHA256 |
| --- | --- |
| baseline.json | f00890cae8a9d51ed69afadaf9c8bc7689ee53ce5e3b0c413216a5dbc628b3f5 |
| flow.json | 80d48dc41621ceeb575780a21984dbc1a174018e5304a8ce311bb829b5a80a7a |
| recovery.json | 80941cf6ba719a9ff19a61a141e49c2d41cdc8b1e0118cac665d8318c2e72db3 |
| reopened.json | 85a4e10c8a8247b62e558fa2792e2ce0d8bffdd49b3457080c6fbd9b89a33e59 |

Final read-only SQL inspection confirms one import receipt, eight raw records,
eight exact line mappings, original BLOB equality, one investigation and one
creation request. Raw text matches every original content-byte span and hash.
`/tmp/nema-history-import-parent-verification.json` records these checks. Browser
contexts were disposed after each run; explicitly restored snapshots are not a
claim that disposed contexts survived restart.

## Independent tests, costs, checks and cleanup

Independent tests exercise six-connection same-request admission, distinct-operation
collision races, annotations/maps-only collisions, failure at receipt insertion
after all eight appends, unchanged discovery generation on rollback, exact mixed
line-ending mapping, RPC source isolation, reserved shape versus inert text,
deleted-source replay with parsing forcibly unavailable, private-role refusal and
legacy nested-savepoint rollback. Composed discovery→canonical save→reopen passes.

Root full Python: **1,663passed /55explicit native skips in58.57s**,
`/tmp/nema-history-import-parent-full.log`. UI: **192tests /838assertions**,
zero Svelte errors/warnings, clean build. Final presentation-only corrections pass
check/build and actual restart inspection. Seed-context5passes; diff checks clean.
Owner authored20,000-record/2,466,699-byte probe measured preview679.84ms,
commit797.17ms, exact replay0.86ms; receipt937bytes,100-record map page16,794bytes.
These observations are not CPU/RSS or total database quotas. Original BLOB plus
raw rows, derived indices and WAL incur additional storage.

All owned API/Vite/Chromium roots, descendants and recorded crash handlers stopped;
8767/5173/9233closed, temporary Vite config removed. Cleanup record
`/tmp/nema-history-import-cleanup.json`. No native/account/model/upstream call.
V1 supports one-direction app-server JSON objects only, refuses same-thread merging,
and retains the original BLOB without a download route. Real owner archives,
human usefulness and real native availability remain unobserved.
