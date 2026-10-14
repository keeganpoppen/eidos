# Reliable explicit-file history ingestion — accepted contract

**2026-10-13 · base `2386b294cfe700622d672ff7e1a35dd9229eba30` · C3/C5 · V1-01/02/04/07/12.**
Root integrates; agents own separate worktrees. No native, account, private-history
or upstream calls. Only explicitly authored public fixture files for acceptance.

## Observed gap and complete loop

Root reproduced old `TraceStore.import_jsonl`: valid delta then malformed JSON
raises but leaves one committed record; retrying the valid line displays `needle
needle `. `/tmp/nema-ingest-baseline-20261013.json`, SHA256
`3f9e61bdee0794202d04e33a5fb57a3b3f938b9231e239f7e38b4856e0370e29`.
Actual fresh empty Chromium workbench: five GETs, zero POSTs; native creation disabled,
empty state mentions import, no file input/import action. Desktop/390px inspected.

Deliver explicitly chosen file → read-only review → explicit atomic import → exact
receipt/retry/restart → existing remembered-text discovery → raw inspection →
disjoint two-thread question → canonical save/reopen. Preserve independent dirty
and pending investigation state. This establishes authored recovery, not human
usefulness or arbitrary Codex export compatibility.

## Format, retention, isolation

`appserver-jsonl/v1`: UTF-8 JSON object per physical line; one explicit source label
and direction for the entire file. No direction guessing or export conversion.
Preserve exact original bytes in SQLite BLOB, including CRLF/LF/bare CR, blank lines,
repeated identical records and unterminated final line. Per-record raw_text retains
original content without line terminators. Record physical line and byte offsets.
Unknown ordinary fields/methods/objects remain data; source text never becomes policy.

8MiB file,512KiB physical line including terminator,20,000 physical lines including
blank,64 nesting depth. Refuse invalid UTF-8/BOM, nonobjects, nonfinite numbers,
unpaired surrogates, unrepresentable extracted scalars and empty/blank-only files.
Errors name bounded line/offset without echoing file contents. Reject parsed method
`$capsule/*` and actual `params.item.type=privateResultPublication` reserved host
publication shapes; ordinary strings containing these words stay valid data.

New byte imports use a fresh host-derived `captureSource` per operation. Requested
`source` remains an origin label in preview/receipt; it cannot choose a live recorder's
correlation scope. Never rewrite native coordinates or raw bytes. Under the same
transaction, refuse any NEW import whose thread IDs overlap existing trace rows,
thread annotations or semantic revisions. Recheck after preview; concurrent imports
cannot silently merge. Also refuse a preexisting capture-source collision. Exact
request replay precedes these checks. V1 does not merge additional same-thread
batches; a later merge must be explicit and separately reviewed.

## Shared core and durable operation

Backend owns `src/eidos/history_imports.py`: HistoryImports.preview(bytes,...),
commit(bytes,...), get_request(request_id), records(import_id,limit,cursor). All
constructor/read/write paths require workbench role. Preflight is file-local and
has no target history mutation. Shared eligible history projection supplies counts;
preview does not promise the whole current database display.

Commit under trace lock + BEGIN IMMEDIATE: request lookup/replay first, then checked
preview, collision checks, all append rows, original BLOB, immutable line mappings,
receipt and ledger; commit once. Any failure rolls back the entire operation and
index triggers. Refuse an existing outer transaction for durable byte commits.
Same request/operation returns original receipt, even after source deletion or later
parser changes; changed body409. Never recreate deleted rows on replay. Distinct
request IDs are distinct operations, still subject to collision refusal.

Operation fingerprint is SHA256 canonical {format,source,direction,fileSha256,
byteLength}; excludes filename/parser/current database/timestamps. Preview fingerprint
also binds parserVersion and file-local summary. Replay compares exact operation
identity before new parser/admission policy. No global identical-line deduplication.

Legacy TraceStore.import_jsonl(Iterable[str])->int preserves source/correlation/count
semantics, each call distinct; use shared bounded validation plus atomic batch/
savepoint. It cannot promise original-file bytes after caller newline normalization,
or durable receipt/idempotency. Only the byte path provides those guarantees.

## Frozen HTTP envelopes

Dedicated bounded JSON uploads only; generic256KiB body cap stays unchanged.
Upload cap `4*ceil(8MiB/3)+4096`; strict base64 + decoded bound; handle incomplete
body, unknown/duplicate fields and bad metadata. Source label <=256UTF8bytes,
filename <=255UTF8bytes (display basename only), requestId <=128 printableASCII.
Every full response envelope <=128KiB; mapping pages refuse oversized envelopes
rather than truncate identity. No CPU/RSS/total-database/wall-clock upload quota claim.

- POST `/api/history/imports/preview`, body
  `{format,source,direction,fileName,contentBase64}` → `{preview}`.
- POST `/api/history/imports`, same body plus `{requestId,previewFingerprint}`
  → `{receipt}`;201 first,200 replay.
- GET `/api/history/imports/requests/:requestId` → `{receipt}` or404.
- GET `/api/history/imports/:id/records?limit=100&cursor=...`
  → `{importId,records:[{line,byteStart,contentByteEnd,byteEnd,seq,rawSha256}],nextCursor}`.

Preview fields: `format,parserVersion,discoveryScope,fileSha256,byteLength,
operationFingerprint,previewFingerprint,recordCount,blankLineCount,physicalLineCount,
summary:{threadCount,turnCount,unscopedRecordCount,discoverableFieldCount},warnings,
committable,reason`. `reason` null or `no-discoverable-history`. Warnings fixed codes,
not source excerpts. API accepts only appserver_to_client/client_to_appserver; new
API commit requires at least one file-local discoverable field, otherwise422.
Preview exposes valid unsupported objects with zero readable fields and disabled
commit. Unknown objects beside readable history are retained.

Receipt fields: `id,requestId,operationFingerprint,previewFingerprint,format,
parserVersion,discoveryScope,fileSha256,byteLength,fileName,source,captureSource,
direction,createdAtMs,recordCount,blankLineCount,physicalLineCount,summary,warnings`.
Counts are frozen file-local interpretation; mapping/source availability later is
separate from historical receipt. No original-file download route in this slice.
Errors use `{error}` and appropriate400/404/409/413/422; no raw contents in errors.

CLI keeps `import-jsonl DB FILE --source --direction`, all five existing directions,
and `imported N records` output. Reads binary through shared byte importer; default
requestID deterministically derived from operation fingerprint, optional --request-id
sets explicit identity. Filename changes do not reimport. Explain capture-source
isolation/collision refusal and receipt identity; raw-only CLI imports remain allowed
with explicit zero-readable summary. --preview/--json may expose the same review/
receipt if useful. This is a deliberate, tested migration from repeated appending.

## Browser ownership and recovery

New HistoryImport.svelte/history-import.ts/helper tests, narrow +page wiring only.
Entry from thread rail and empty state, existing workbench styles. Import has separate
state and never edits InvestigationPane or its recovery keys. File size checked
before reading; exact bytes hashed and base64 transmitted without newline conversion.
Preview counts and supported format remain understandable, not a schema dashboard.

Before POST persist bounded metadata only in `nema.history-import.v1`:
requestId,format,source,direction,fileSha256,byteLength,previewFingerprint,
operationFingerprint,fileName. Storage failure prevents send; never persist file
bytes/base64. Pending reload offers explicit Check import receipt GET;404 retains
unknown outcome. No automatic POST or newID. Explicit same-request retry requires
reselection of exact file hash/length; renamed file acceptable. Validate every receipt
binding; malformed or foreign recovery metadata is preserved/refused. Detect another
tab changing the pending slot. Pending options locked; source/file/direction changes
invalidate stale hash/preview work before commitment. Late responses cannot open
history, steal focus or replace another operation. A well-formed commit error with
400/409/413/422 may offer explicit Dismiss refused import, preserving exact metadata
until the deliberate click and explaining that an earlier request may still have
committed. Receipt checking remains available first. Network/5xx/malformed responses
and GET404 never permit automatic clearing. A stale error cannot unlock dismissal.
Existing editor and source focus
survive import/inspection. Receipt navigation is explicit, mappings bounded.

## Ownership, verification and integration

- history_ui: fresh `/tmp/nema-history-import-backend`, branch codex/history-import-backend;
  owns history_imports.py, trace.py import helper, cli.py, api.py, backend/CLI tests.
- native_frontier: `/tmp/nema-history-import-ui`, branch codex/history-import-ui;
  owns new HistoryImport/client/tests and narrow +page wiring. Coordinate exact
  labels/selectors with root before browser script implementation.
- native_frontier/gateway_review: `/tmp/nema-history-import-review`, branch
  codex/history-import-review; owns independent tests/test_history_import_acceptance.py.
  Review final source and root scripts, especially race/rollback/import spoof cases.
- Root owns this packet, docs, scripts/history_import_demo.py and
  scripts/history_import_browser.mjs, integration and final commit/push.

Tests must cover malformed-tail zero publication, duplicate physical lines retained,
exact CRLF/unknown bytes+mapping, lost receipt/restart replay, wrong-file/source/
direction sameID conflict, six-connection same-request race, concurrent colliding
new operations, annotations/maps-only collisions, reserved host publication shapes,
private-role refusal, parser/response bounds and fault after final append before
receipt commit. Immutable receipt survives deleted raw source without recreating it.

Root authored fixture:8records/two threads, unknown object, repeated delta, split
phrase separated by unrelated same-thread record;2blank physical lines, mixed endings.
Actual browser starts empty, refuses malformed/unsupported review without mutation,
loses successful import response, preserves pending draft, checks/retries exact
receipt without duplication, finds/inspects sources and saves a two-thread context.
Restart API and recover same receipt/context with zero automatic POSTs; inspect
1600/390px. Preserve failures separately. Full uv pytest, Bun tests/check/build,
seed-context, independent review, owned-service cleanup and coherent main commit.
