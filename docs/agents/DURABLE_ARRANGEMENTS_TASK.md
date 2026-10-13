# Durable arrangement snapshots — active task contract

**2026-10-13 · base `b9f75ea` · V1-01/10, C5.** Parent owns integration.
The previous scale loop is committed/pushed and verified in CURRENT_HANDOFF.

## User loop and decision

Review/apply an exact comparison and source focus, save it under a name, open a
fresh browser on the same authority-local database, find and preview the saved
arrangement, explicitly open it, then save an altered copy. A later result/inquiry
response must never replace a saved historical pin. Save the compiled reference
arrangement, not a request to recompile semantic intent against current work.

Use create-only immutable snapshots; do not add a mutable workspace head or
synchronize browser state. A future mutable bookmark can refer to these IDs.
Snapshots are ordinary versioned descriptions, not controllers or authorization.
Reuse ContextManifestStore immutable objects with a thin metadata/idempotency index.
Do not copy source histories, draft context, native handles/authority, browser scroll,
open state or undo into the snapshot. Browser drafts and local undo remain local.
Existing browser state is uploaded only by an explicit Save action.

## Frozen HTTP contract

`GET /api/compositions?limit=20&q=<title>&cursor=<opaque>` returns
`{compositions:[{id,title,createdAtMs,rendererVersion,copiedFrom}],nextCursor}`.
Maximum40/minimum1; literal casefolded title substring; keyset order creation DESC,
ID ASC; cursor bound to the normalized query. No full owner loads for listing.
`GET /api/compositions/:id` returns `{composition:<exact saved envelope>}`.

`POST /api/compositions` takes exactly
`{requestId,title,rendererVersion,arrangement,focus,copiedFrom?}`. Returns201 with
`{composition:<exact saved envelope>}` both for first commit and an exact retry.
Envelope is `{schemaVersion:1,id,contentId,title,createdAtMs,rendererVersion,
arrangement,focus,copiedFrom}`; copiedFrom is null when omitted. Same requestId with
different content is409; successful replay returns the original immutable envelope
before consulting now-changed source availability. Copy ancestry must name a saved
composition. Repeated titles are legal labels; IDs identify immutable occurrences.
No update/delete/apply/native endpoint is introduced.

Arrangement uses existing strict reference shape:
`{left:{investigationId,contextId,artifactId?},right:<same>,lens:'result'|'context',
layout:'beside'|'stacked',intent?:'evidence-chain'|'alternative-review',
inquiry?:{continuationId,inquiryId,responseId?,evidenceContextId?},experimentId?}`.
Focus is null or `{investigationId,contextId,artifactId?,blockId?,seq?,threadId?}`.
`seq` and `threadId` occur together; blockId requires artifactId. Unknown input
fields are rejected, never promoted into executable policy or source content.
IDs max200 characters, title max160, rendererVersion max120, request body max16KiB.

Backend validates owner/context/artifact membership, exact source record/thread
membership, and inquiry/experiment relationships where supplied. Offered inquiry
packets are legal contexts only through their owning response. A focus record with
an artifact must be cited by that artifact. Block selectors are derived UI values;
backend checks syntax, not Markdown parser equivalence or claim entailment.
New saves need resolvable references. Existing snapshots stay byte-identical and
readable if sources later disappear; source resolution is a separate derived view.
A repaired arrangement creates a new copy. Reads never rebind to current IDs.

UI supplies an explicit rendererVersion covering content-block selector semantics
and the installed Markdown parser version. Unknown versions remain inspectable;
opening them must not silently resolve the same block offset under a new parser.
Prefer explicit unresolved block focus/fallback with visible explanation, keeping
exact artifact/record references. Do not pretend a version label authenticates
source or caller. Do not invent claim proof from citation checks.

## Ownership

- Root: `src/eidos/compositions.py`, `src/eidos/api.py`, focused backend tests,
  shared contract/docs/main commit. Use existing CM objects, strict finite JSON,
  transactions and local HTTP write admission. No kernel/worker changes.
- `/root/history_ui`: `/tmp/nema-durable-arrangements-ui`, branch
  `codex/durable-arrangements-ui`, UI-only. Explicit save/retry/list/preview/open/
  save-copy controls within comparison, retained browser draft/pins, source-missing
  repair, selector-version handling. Own tests, check/build, coordinate browser.
- `/root/native_frontier/gateway_review`: `/tmp/nema-durable-arrangements-acceptance`,
  branch `codex/durable-arrangements-acceptance`. Own new
  `tests/test_composition_acceptance.py`, `scripts/composition_snapshot_demo.py`,
  `scripts/check_composition_snapshot_ui.mjs`, unique evidence only. Independently
  challenge backend/source/persistence and actual fresh-browser behavior.
- `/root/native_frontier`: finish synthetic-provider probe in its existing
  worktree; afterward review root backend read-only. Probe integration is separate
  from granting production admission. Existing user authorization covers only
  disconnected fake provider work, no real model/credentials/upstream.

## Acceptance and integration

Save a real persisted synthetic A1/A2 (or A/C) comparison with exact source focus;
advance source lifecycle afterward; reopen controller and use a fresh browser
profile. Review/open restores original IDs and source bytes, leaves investigation
question/rationale/pending-save identity untouched, and performs no native action.
Save a changed copy with ancestry while original content is byte-identical.

Challenge a committed-but-lost save reply/reload, simultaneous same-request saves,
changed-body replay409, wrong-owner/context/artifact/record/inquiry, forged action
fields, unknown renderer version, and missing source after save. List/search/pages
are bounded metadata. No automatic open on selection/poll or browser migration.
Run focused and full Python/UI/seed checks, inspect actual desktop/mobile UI and
preserve synthetic evidence. Report exact scope; no cross-database sharing,
authentication, collaboration synchronization or human-speed claim.
