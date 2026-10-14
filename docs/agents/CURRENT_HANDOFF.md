# Current handoff — bring supplied history into recoverable work

**2026-10-13 · integration base `2386b294cfe700622d672ff7e1a35dd9229eba30`.**
Evidence discovery at that base is pushed; [CI38497695685](https://github.com/keeganpoppen/eidos/actions/runs/38497695685)
passed. This snapshot accompanies completed explicit-file import integration.
The autonomous mission remains active; completing this slice does not complete it.
No real account, private history, model or upstream call is authorized.

## Completed C3/C5 slice — V1-01/02/04/07/12

[Contract](HISTORY_IMPORT_TASK.md), [acceptance](../evidence/HISTORY_IMPORT_INTEGRATION.md),
[D34](../roadmap/DECISIONS.md#d34--import-supplied-bytes-as-one-isolated-recoverable-operation).
Root reproduced malformed-tail partial commit and retry duplication, plus the actual
empty-browser import affordance gap. The shared byte importer now supports bounded
stateless review, atomic original BLOB/records/line mappings/receipt, and exact
request replay before current parser/collision policy. Same-file CLI retries do not
append again. Legacy iterable API retains source/correlation semantics but gains
atomic batch/savepoint rollback; it claims neither original-file bytes nor receipts.

New byte imports use a host-derived capture source; supplied source is an origin
label. Native thread collisions (raw/annotations/maps) and reserved host publication
shapes refuse. Original coordinates/unknown fields/repeated lines remain evidence;
copied descriptions cannot create native ownership. API requires at least one known
searchable field; CLI can retain explicitly reported raw-only imports. V1 accepts
one-direction UTF8JSON objects,8MiBfile/512KiBline/20kphysical lines;128KiBresponse
ceilings include metadata. No same-thread merging, raw download, or total resource
quota. File-local preview does not attest authentic native origin or useful answers.

One import dialog is accessible from rail/empty state. A separate metadata-only
browser slot persists exact operation identity before POST. Reload never submits;
GET receipt or exact-file reselect/retry is deliberate. Wrong files/stale previews/
foreign slots refuse. Dirty/pending investigation editor stays byte-identical.
Read-only receipt does not establish current availability of every original record.
Import polling preserves existing focus. Partial source records now say PARTIAL;
missing command completion no longer defaults to running.

Integrated lanes: backend `f597460`, UI `87135bd`, independent tests `e3261b3`.
Root owns scripts/docs, pluralization and partial-record labels. Source review
accepted the frozen lanes; a fresh-only fixture serve guard fixes a reviewed helper
risk. Prior [discovery](../evidence/EVIDENCE_DISCOVERY_INTEGRATION.md),
[historical reuse](../evidence/CONTEXT_INPUT_REUSE_INTEGRATION.md) and
[managed attempt](../evidence/MANAGED_ATTEMPT_INTEGRATION.md) evidence remain linked.
Preserve the exact legacy policy literal from `2a62d68`; it hashes into manifests.

## Verification and cleanup

Root full Python **1,663 passed /55 explicit native skips in58.57s**,
`/tmp/nema-history-import-parent-full.log`. UI **192tests /838assertions**, Svelte
0errors/0warnings, clean build. Final text-only corrections also check/build clean
and actual restart screenshots show PARTIAL. Seed-context5passes, diff checks clean.
Independent11cases cover six-connection replay, distinct-operation collision race,
late-ledger rollback, exact mixed-ending mapping, old request isolation, source
removal/replay without parser, reserved shapes, private-role and nested rollback.

Actual browser baseline5GETs/zeroPOSTs. Flow22requests/5POSTs (four stateless previews,
one import whose successful201reply is lost). First API restart: explicit receipt
GET resolves same import with zeroPOSTs; separate restored pending snapshot rejects
wrong file then exact retry returns200/same receipt. Recovery59requests/2POSTs
(replay + canonical question), exactly4inspected records across2threads. Second API
restart17GETs/zeroPOSTs, same canonical owner/receipt. Desktop1600/390px inspected,
no document/component overflow. Explicitly restored authored browser snapshots are
not a claim that disposed browser contexts persisted.

Final SQL: one import,8rawrecords/8exactmappings, original1,491-byte BLOB identical,
one investigation/request; no attempt/artifact/adoption. Report hashes in acceptance.
Scripts: history_import_demo.py/history_import_browser.mjs; raw reports
`/tmp/nema-history-import-browser-20261013-*`; fixture directory
`/tmp/nema-history-import-fixture-20261013`; database
`/tmp/nema-history-import-20261013.db`. All owned API/Vite/Chromium descendants and
crashhandlers stopped;8767/5173/9233closed; temporary Vite config removed. Cleanup
`/tmp/nema-history-import-cleanup.json`. No native/account/model/upstream call.

## Next discriminator and ownership

Scouts converge on useful work without dispatch: write an owner-authored grounded
finding, reopen it and reuse it in another question. Existing rationale survives
restart/input reuse but remains commentary on a draft; its conclusion is absent
from result discovery. Artifact completion currently requires a native attempt,
adoption requires an artifact, and no authored-result route exists. A public authored
API probe produced one source/zero native calls and demonstrated those refusals.

Root next: independently inspect InvestigationStore.complete/result input resolution,
result catalog and UI around a saved context; reproduce the owner-finding gap using
public repository evidence. Prefer an immutable finding tied to an exact saved
context, with explicit authorship and support. Do not fabricate completed attempts,
weaken native result requirements, or introduce a general artifact framework before
the useful loop exists. Test lost reply/restart, advance C0→C1 while F0 stays pinned,
then exact reuse into a new question. Existing rationale may remain sufficient for
some notes; establish which action needs a finding.

history_ui is assigned a read-only backend schema/reuse design in the completed
`/tmp/nema-history-import-backend` worktree; no new implementation yet. native_frontier
completed a read-only API/UI scout with the gap above. gateway_review completed
import acceptance. All three import worktrees are clean (backend/UI/review), at
branches codex/history-import-*. Root owns main integration/next contract. Older
managed worktrees may retain historical unintegrated changes; do not sweep them in.
Real owner usability and authorized subscription-backed useful work remain unobserved.
