# Supplied text evidence — accepted contract

**2026-10-14 · base `d2b5fdb06a88c5c1ac8f6d1b53ea71274ff3d290` · C1/C5,
V1-01/03/11/12.** Root owns integration. Implementation and actual acceptance are
recorded in [the evidence report](../evidence/SUPPLIED_TEXT_INTEGRATION.md).
No account, auth, model or upstream calls.

## Discriminator and intended loop

The root reran `/tmp/nema-local-reflection-scout-20261014.py` into the fresh
`/tmp/nema-local-reflection-parent-20261014` directory. It executes the public
`2386b29` import method against the current TraceStore, not an entire old release.
A malformed tail leaves one then two prefix records under that old method, zero
then zero under the current method; intentional valid duplicate lines remain two.
Its observation.txt is a generated report of these observed checks, not captured
pytest stdout. Ordinary JSON report intake through the actual CLI retains exact
bytes but produces no selectable thread or discovery hit. Plain text refuses
history preview. An explicit authored native-shaped wrapper can carry findings
and a review, but incorrectly projects as an assistant message/app-server evidence.

Admit an explicitly selected local UTF-8 file, inspect/search its literal text,
select it alongside public code, freeze the exact inputs, save a finding and a
review using existing authored findings/compositions, then recover after restart.
The first episode reviews the real import regression and its limits. No new
experiment ontology and no relaxation of native-only experiment gates.

## Wire and persistence contract

New adapter `SuppliedText` in `src/eidos/supplied_text.py`, separate from the
app-server JSONL parser. Endpoints under `/api/evidence/files`:

- `POST /preview`: exactly `{format:'supplied-text/v1',fileName,contentBase64}`.
- `POST /`: same plus `{requestId,previewFingerprint}`. Return 201 for new
  admission or 200 for exact replay, wrapped as `{receipt}`.
- `GET /requests/:requestId`: exact stored `{receipt}` or 404.
- `GET /:id`: explicit original-byte inspection, `{receipt,contentBase64}`.

No query parameters; no caller-selected source, direction, path, URL or native
coordinates. fileName is a bounded display basename (255 UTF-8 bytes); requestId
is printable ASCII up to128 bytes. Strict canonical base64 and strict UTF-8;
preserve BOM, CRLF, no final newline and all admitted text bytes. Up to64KiB of
original bytes; additionally reject a generated envelope over64KiB or serialized
ContextRecord over96KiB. These bounds include escaping and metadata. Preview must
report refusal before any write. Whole JSON replies remain at most128KiB. Existing
context prompt bounds still apply to combined selections/questions.

Preview returns `{preview}` with format, fileName, fileSha256, byteLength,
parserVersion (`supplied-text-admission/v1`), previewFingerprint,
classification (`local-owner-supplied`), textExcerpt (at most480 characters),
truncated, discoverableFieldCount (0 or1). The fingerprint binds exact bytes,
display basename, format and parser version. No arbitrary content is interpreted
as a message or source assertion. Empty/whitespace-only files may have no search
hits; source selection remains available.

Receipt adds id, requestId, admittedAtMs, source, threadId, turnId, itemId, seq,
hostRecordSha256. The receipt may retain the bounded preview excerpt; original
file bytes are stored separately. Exact request replay is checked before current
parser/preview validation, including after restart; conflicting reuse409. Compare
the submitted previewFingerprint with the stored receipt's token without
recomputing it: an exact old-token replay survives parser changes, a changed token
under the same request identity refuses409.
Atomic receipt + original BLOB + one generated record. Failed validation or
transaction writes none; exact retry writes no duplicate. Same bytes under a new
request intentionally create a distinct admission. Pending browser storage keeps
compact request metadata/fingerprint, never file bytes; reload never auto-POSTs.
Well-formed POST400/409/413/422 refusal offers explicit dismissal of local recovery
with notice that an earlier save may still exist. GET404, network/5xx or malformed
responses retain pending recovery; none causes an automatic new request.

Host allocates an isolated source, a `local-document_` group and turn/item IDs.
Reserved method `$local/document`, item type `suppliedText`, internal direction.
The file is one opaque UTF-8 string inside that generated envelope. Original file
SHA and generated-envelope SHA are distinct. A receipt proves local file intake,
not authorship, repository origin, command execution or test success.

## Projection and boundary contract

Native JSONL imports reject the reserved new method namespace/type, as they already
reject private host publications. Strings mentioning those names remain inert.
Name checks alone are insufficient: live document projection/search requires a
matching admission ledger with exact seq, source, coordinates, envelope hash and
original bytes/hash. Forged/copied/preexisting records without proof remain raw
and are not indexed as supplied text. Private control stores stay refused.

Add optional descriptive `localEvidence` to verified ContextRecord values:
`{kind:'supplied-text',version:1,id,fileName,fileSha256,byteLength,
classification:'local-owner-supplied',parserVersion,hostRecordSha256}`.
The generated raw envelope contains the exact decoded text. Frozen contexts retain
their descriptor and render after original ledger/source loss; it is a description,
never a live authorization. Selected reserved local records with invalid/missing
proof refuse new canonical selection. Existing native-only hashes, prompts,
manifests and legacy policy literals stay byte-compatible. Only newly built
packets containing verified/frozen documents receive source-aware coverage that
does not label those documents observed app-server evidence.

Thread summaries/payloads add `sourceKind:'supplied-text',sourceOnly:true` for verified local groups;
their preview is the display basename. Projected suppliedText item exposes text
and localEvidence; search field is `suppliedText.text`. Discovery retains its
existing scope/bounds and exact contributor sequences, uses a new derived index
version, and responds to admission/record deletion or change. Existing generic
JSON/unknown/private fields do not become searchable.

Local groups are source-only. `/api/threads/:id/messages` and LiveCodex.send must
refuse them before any native call. Prefix checks may deny, never establish
verified provenance. UI hides native messaging for them. Investigation dispatch
from explicitly selected documents remains governed by existing independent gates.

History, exact search inspection, frozen context and result lineage render supplied
documents as escaped plain text. Never Markdown/HTML/image/URL loading. Label
“Supplied text” and “Local file; contents supplied by the owner.” Preserve literal
code and instruction-like content as evidence. Display refs/hashes in disclosures.

## Ownership and integration

- Backend: `/tmp/nema-supplied-text-backend`, branch
  `codex/supplied-text-backend`. Own supplied_text.py, api.py, trace.py if needed,
  history_imports.py (reserved-shape refusal only), history.py, view.py,
  history_projection.py, evidence_discovery.py, investigation.py and focused new
  `tests/test_supplied_text.py`. Coordinate any additional shared file first.
- UI: `/tmp/nema-supplied-text-ui`, branch `codex/supplied-text-ui`. Own ui/src
  changes, focused helper tests. Add independent “Add text evidence” dialog/client
  and metadata-only `nema.supplied-text.v1` pending slot capped at4KiB; preserve existing history-import receipt behavior,
  investigation/finding drafts, source focus and pending storage. Do not replace
  the active arrangement/draft automatically. On explicit “Open supplied text”,
  refresh source list and navigate; explicit search uses existing discovery.
- Independent review: `/tmp/nema-supplied-text-review`, branch
  `codex/supplied-text-review`. Own only new
  `tests/test_supplied_text_acceptance.py`; critique implementations/interfaces,
  send defects to owners. No shared implementation edits or copied commits in final.
- Root: this contract, public reproducible episode/scripts, baseline and final
  browser inspection, composed recovery/counterexamples, docs and final commit.

All worktrees start at d2b5fdb. Each lane returns a clean commit and actual test
evidence. Root cherry-picks without committing, reviews actual diffs, runs full
Python/UI checks and actual browser loop, then one coherent integration commit.

## Acceptance and strongest counterexamples

1. Exact BOM/CRLF/Unicode/control text roundtrips, original versus envelope hashes,
   bounded escaped payloads, bad UTF-8/base64/metadata/extra fields/oversize refuse.
2. Lost reply, restart, exact request replay before changed parser validation,
   conflict and concurrent duplicate delivery; failed atomic admission leaves none.
3. Forged host shape via ordinary import, direct trusted trace insertion and copied
   coordinates/hash cannot gain document projection; no generic JSON indexing.
   Imported document containing RPC, private-like fields, Markdown remote images,
   HTML or instructions stays literal and causes zero extra network/native calls.
4. Search→exact inspection→selection→finding→review→saved comparison, source-local
   coverage and zero native attempts. Legacy native packet hashes unchanged.
5. Delete original admission/raw in an explicitly marked disposable fixture:
   frozen context, finding and copied historical inputs remain exact/descriptive;
   stale discovery is invalidated, no substituted current/live source.
6. Actual desktop and390px UI review; pending upload recovery with file reselect,
   late replies after close/change cannot alter focus or overwrite drafts. Existing
   independent pending editor/finding/history-import values survive byte-exact.
7. Fresh participant reconstructs pinned before/after source, observed result,
   inference limits, review decision and rollback basis from saved work alone.
   This measures recoverable coherence, not human speed or model quality.
