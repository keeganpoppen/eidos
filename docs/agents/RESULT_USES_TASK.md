# Direct saved uses of an exact result

**Accepted implementation contract · 2026-10-13 · base `25d6350b104c2543060fe76a9447502c81f56caa`.**
C1/C5, V1-03/04/09. Root owns integration and this interface; no native/account calls.

## User loop and evidence

“I am reconsidering F0. Which saved questions included that exact result, and what
did each receive?” Open result provenance, inspect its direct saved uses, inspect
historical B0 without replacing a dirty editor, and recover the same view after
restart. A newer F1 is a separate value, not an inferred supersession.

Root independently reproduced the scout counterexample using public D34/import-code
excerpts: `/tmp/nema-result-uses-baseline.py` and `.json`. Six owners/seven contexts
required104,509 serialized response bytes for full-owner scanning. Exact membership
is historical B0 plus current copied-input D. Current B1 dropped F0; C supplies B's
derived finding; E shares only raw records; F merely mentions F0. Text search misses
D and includes F. The proposed uses route returned404. No model/native calls.

## Relation and read contract

Scope is `direct-frozen-artifact-inputs/v1`: a saved context has a frozen
`artifactInputs` entry whose investigationId/artifactId equals the exact source pair.
Include historical/current/unattempted contexts and copied inputs. One list row per
consumer/context. Exclude prose mentions, shared raw records, browser drafts and
transitive paths. This reports supplied membership, not claim reliance or validity.

Original source existence is not a precondition. Resolve from surviving consumer
snapshots; never re-resolve upstream, rewrite them or cascade source deletion into
consumer relations. A missing original source may separately make lineage unavailable.
Retained authored findings must pass their schema and owner-bound content hash;
this does not recompute citation membership against the consumer's different context.

`GET /api/investigations/:source/artifacts/:artifact/uses`
accepts only `limit`(1..40,default20), `cursor`, `knownVersion` (one each).
Full envelope:
```
{scope, source:{investigationId,artifactId}, version, unchanged:false,
 uses:[{investigationId,investigationTitle,contextId,ownerVersion,isCurrent,
        questionExcerpt,rationaleExcerpt,matchingInputCount}], nextCursor}
```
Title/question/rationale previews are bounded to240 Unicode characters, including
omission markers. Exact strings live in detail. At most40rows and128KiB UTF-8 for the
whole JSON envelope; reduce returned rows and produce a correct cursor as needed.
No frozen snapshots, raw text or projected prompt in list metadata. Conditional
response includes scope/source/version/unchanged:true, without uses/nextCursor.
Versions must bind source, page, limit and ordered returned metadata.

Cursor binds scope, exact source pair, limit, relation version and stable order key.
Relation version hashes ordered matching (consumer,context,ownerVersion) metadata
after refreshing dirty projections in one SQLite snapshot. Canonical matching-consumer
changes invalidate cursors with409; unrelated owner changes need not. Malformed or
wrong-query cursors400. No current-page substitution. Sorting may use consumer
createdAt descending, consumerId/contextId ascending; make ordering deterministic.

`GET /api/investigations/:source/artifacts/:artifact/uses/:consumer/contexts/:context`
requires only `expectedVersion` (the row's ownerVersion), exactly once. Returns:
```
{scope,source:{investigationId,artifactId},investigationId,investigationTitle,
 contextId,ownerVersion,isCurrent,context,matchingInputIndexes:[integer,...]}
```
Within one snapshot resolve exact consumer/context, verify canonical ownerVersion
and exact matching frozen input membership, then return that exact context. Missing
consumer/context404; stale ownerVersion or mismatched membership409. Never substitute
current context, source artifact, current adoption, or a similarly named owner.
Context detail retains its existing canonical size limits; the128KiB list cap is not
a new global detail/owner/database/CPU quota. Conflicting duplicate context identities
or malformed matching snapshots must refuse rather than silently select one.

Reuse InvestigationReads replaceable indexes, dirty triggers and snapshot locking.
Migration/rebuild must backfill old canonical rows; no canonical mutation. Source
deletion only removes rows where it is the consumer. Warm reads need no whole-owner
parsing. Matching-metadata version work is O(matching contexts); cold/dirty refresh
still parses owners. Keep existing catalog/cursor/legacy serialization unchanged.
Malformed use projections retain a fixed derived error marker and discard partial
rows. New uses reads refuse completeness until repaired; unrelated legacy catalog
semantics remain intact. The shared refresh must not acquire a new legacy failure.

## Browser behavior

Entry inside ArtifactLineage: **Questions supplied this result**. Available for an
exact active target even when original source resolution fails. Explain saved input
membership and omitted transitive uses. Show title/question/rationale, exact IDs and
**Current saved context**/**Historical saved context**; place long exact references
in expandable details so narrow screens lead with the question/result.
**Inspect saved context**
opens inline exact preview with question, matching frozen result, other supplied
inputs/raw records, inclusion rationale, inputOrigin and collapsible projected input.
Reuse ArtifactContent/EvidenceRecord. Missing/stale read is an error, not zero uses.

No choose/useInvestigation call, browser persistence or mutation route. Independent
editor selection/question/rationales, pending saves, finding recovery and source focus
remain unchanged. Cancel late list/detail replies on target/page/consumer change or
dialog close. A follow action must not accidentally create a recursive preview stack.
Any explicit refresh resets cursors/selection before displaying new membership.
Explicit inspection focuses its preview; late original-source resolution must not
reset that focus or scroll after saved-use navigation has begun.

## Ownership and verification

- Backend/history_ui: new worktree from base, src/eidos/investigation_reads.py,
  src/eidos/api.py, new tests/test_result_uses.py. API/index/detail/negative tests.
- UI/native_frontier: separate worktree, new ResultUses.svelte and focused helper/tests,
  ArtifactLineage.svelte, saved-work.ts types if useful. No InvestigationPane changes
  without integrator agreement. Run bun tests/check/build.
- Independent/gateway_review: separate worktree, tests/test_result_uses_acceptance.py;
  challenge contract and actual patch, native startup prohibited. No production edits.
- Root: scripts/result_uses_demo.py, scripts/result_uses_browser.mjs, docs, integration,
  full suites and actual browser baseline/changed/restart/desktop/narrow acceptance.

Counterexamples: B0/B1 and D versus C/E/F; F1 never replaces F0; copied snapshot
survives source/raw deletion; consumer deletion clears its relations; independent
SQLite writer invalidates historical/current labels and detail/cursors; index rebuild
preserves canonical bytes; malformed/wrong-pair cursor; owner/context ambiguity;
maximum UTF-8 envelope; held browser reply after close/target change; zero POSTs and
byte-identical independent pending storage throughout inspection. Test no-current-
substitution directly. Use canonical APIs for normal fixtures and label trusted SQL
corruption/deletion injections. Root reconciles lane commits into one tested commit.

Known limits: scripted task completion is not measured human benefit. This exposes
saved selection only, not native consumption, a dependency graph, automatic
invalidation, replacement, propagation or transitive claim analysis.
