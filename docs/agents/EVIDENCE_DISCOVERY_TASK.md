# Evidence discovery in unmapped history

**Accepted integration contract · 2026-10-13 · base `1698f6abb74523a3d04b54e840bd38057f55c2a9`.**
C3/C5 / V1-01/04/08. Root integrates on main. No native, model, account, private
trace, browser owner-profile or external service use is authorized by this slice.

## User-visible loop and discriminator

Remember words → find recorded source text across imported history → inspect exact
raw contributors → explicitly select disjoint evidence → existing canonical context
save/preview/reopen. Search changes neither working draft nor pending save identity.

Observed baseline on this base: root removed only derived semantic maps from the
existing authored 1,200-turn history, preserving raw bytes, then used actual Chromium
and local API. Initial page lacks the remembered decision; no source-text search
exists. Sequential next-page actions find it after 27 advances, 36 API reads and
zero POSTs. Screenshots inspected; dirty editor stays unchanged. Report:
`/tmp/nema-evidence-discovery-browser-20261013-baseline.json`. This is capability
and request evidence, not a human-speed measurement. Exact result search starts
later in the workflow and deliberately excludes underlying source history.

## Source projection and boundaries

Search known text fields used by the history projection, with explicit scope
`displayed-history-text/v1`. This means source text fields, including Markdown
markup, not a DOM-text normalization or semantic understanding claim.
Allow userMessage content[type=text].text; turn/start input[type=text].text only
when no userMessage suppresses that fallback; agentMessage.text; exposed reasoning
summary/content string parts; commandExecution.command and output; fileChange
path strings. Separate fields/parts cannot create a cross-field phrase. Match
literal Unicode-casefold substrings; percent/underscore and punctuation are literal.

Share final-versus-delta projection rules with the API rather than fork precedence.
Nonempty final text replaces prior deltas; empty final follows existing fallback.
Later completed/history items replace older final items. Text can span deltas.
A hit owns an excerpt and exact contributing records, never start..end expansion.
For delta excerpts retain segment-to-record membership, including every excerpt
character's source. Preserve original raw bytes/unknown fields in exact inspection.

Exclude provider directions, non-item control methods, generic raw/detail/tool
JSON, unknown fields, nontext input attachments and internally annotated threads.
Private capsule publications already have result discovery and remain outside
this first source-history search. Workbench store role is required at construction
and reads; never attach or open private-control evidence. This scope is not a
universal sanitizer for public imported text, and copied text grants no authority.
Filter excluded records before projection: a provider/control row that reuses an
eligible item's coordinates neither supplies nor replaces eligible text. Scope
names shared display-field rules applied to eligible history, not equality with
the whole current thread DOM. Exact matched raw inspection remains distinct from
Show in history's surrounding projection.

## Frozen API contract

Backend owns API routes, new derived module(s), shared item projector extraction
if needed, and backend tests. Existing API payloads/projection stay compatible.

`GET /api/evidence/search?q=...&threadId=...&limit=20&cursor=...&knownVersion=...`

- q: trimmed, nonempty, at most 200 characters. Optional threadId restricts exact
  visible thread; omitted searches all eligible recorded threads. Default limit20,
  max40. Reject duplicate/unknown/invalid parameters.
- Return `{scope,version,unchanged:false,hits,nextCursor}`. No raw bodies in list.
  knownVersion matches this exact normalized query/page/limit/source generation;
  unchanged response cannot suppress a different query or page.
- Hit `{id,version,threadId,turnId,itemId,field,anchorSeq,recordSeqs,excerpt}`.
  itemId may be null for turn input. field names are stable keys (labels in UI).
  excerpt at most 240 Unicode characters including visible omission markers.
  Exact contributor refs are bounded (max256); no min/max membership substitution.
  One first-occurrence hit per matching text field; deterministic keyset ordering.
  id identifies field; version binds text, coordinates and raw source identity.
- Bound the complete serialized search page to 128KiB as well: unusually long
  imported thread/turn/item identifiers can exceed excerpt limits by themselves.
  Overbound pages return413 explicitly, without truncating identifiers or silently
  hiding matching fields. Root reproduced a 200,000-character thread identifier.
- Cursor binds normalized query/filter/limit and index generation. Changed source
  generation returns409 requiring explicit refresh, not silently omitted matches.
- `GET /api/evidence/hits/:id?q=...&version=...` returns `{scope,hit,records}` using
  the same normalized query to resolve excerpt contributors. Records use the
  existing frozen-record envelope `{seq,threadId,source,direction,method,rawText,sha256}`.
  Require exact hit version and visible source; changed409/missing404, no fallback
  to current latest item. Bound source detail by existing max256 records/128KiB;
  oversized source returns explicit413 and never silently truncates evidence.

Use a disposable SQLite-derived index, source-dirty triggers across connections,
and one snapshot for source generation/version/results. Include insert/delete,
old and new coordinates on update (RPC hydration), annotation changes, and index
rebuild/schema change. Warm unchanged reads must not reparse all history. Reuse
existing transaction/cursor/excerpt patterns where sound. Index granularity may
be per turn or thread if correctness and measured local costs justify it. Cold
rebuild and literal scans can scale with corpus text: state measured costs and
limitations. Do not silently index a prefix and claim no matches outside it.
No semantic/model ranking, background live observer, or source-history rewriting.

## UI and exact selection

UI owns a small discovery component/helper/tests, InvestigationPane, types and
narrow +page/history/ThreadItem integration. Root owns fixture/browser/docs.
Mount discovery beside investigation evidence inputs, visually using existing
workbench controls. Search/read-only inspection remain available during unresolved
editor saves. Display excerpt, field/source labels, and exact record references;
render raw inspection as inert text. Optional Show in history uses existing
aroundSeq/membership/navigation generation but is surrounding context, not a
substitute for exact matched raw inspection.

Add these source records is explicit, disabled during editor busy/pending save.
Only inspected exact records may be added; validate response identity and bound
stale responses to query/page/filter/navigation/active aperture. Search or source
inspection never automatically adds, saves, replaces or dispatches. Keep existing
canonical creation/revision and immutable context preview; no new draft registry.
The inspector binds the bytes it read. Add stages references; existing Save resolves
and freezes them. Do not claim that an unsaved selection enforces the inspected
hash against later trusted-host source edits. No new hash precondition is added to
the existing selector API in this slice.

Fix the demonstrated existing item-selection seam within this same lane: item
recordSeqs[1,3] must not select unrelated same-thread2. Merge only actually adjacent
selected sequences, respecting combined32-input and256-record bounds; refuse an
addition that cannot fit rather than widen. Route existing Add item/map through
an explicit busy/pending editor gate so it cannot silently replace a pending save
identity. Preserve existing intentional semantic support ranges as ranges. Avoid
new global selection machinery; use one small tested membership helper and Pane
callback/binding seam. Backend canonical bounds remain authoritative.

## Independent acceptance and ownership

- history_ui: `/tmp/nema-evidence-discovery-backend`, branch
  codex/evidence-discovery-backend. Write src/eidos/evidence_discovery.py (and a
  shared projection module if necessary), api.py, tests/test_evidence_discovery.py.
  Coordinated addition: view.py may append optional ItemView.final_event and set it
  exactly where final_item is chosen, so source attribution shares that decision.
  Do not change trace.py schema/append behavior without coordinating first.
- native_frontier: `/tmp/nema-evidence-discovery-ui`, branch
  codex/evidence-discovery-ui. Own UI files described above and tests. No backend.
- native_frontier/gateway_review: `/tmp/nema-evidence-discovery-review`, branch
  codex/evidence-discovery-review. Independently challenge contract and final
  implementation; own tests/test_evidence_discovery_acceptance.py only.
- Root: scripts/evidence_discovery_demo.py, evidence_discovery_browser.mjs,
  docs/evidence/EVIDENCE_DISCOVERY_INTEGRATION.md, decision/state/handoff; sole
  shared contract owner and final tested commit/push integrator.

Read relevant nearer AGENTS, api.py projection/thread handlers, history.py, view.py,
trace.py role/annotations/hydration, investigation_reads.py, +page.svelte,
ThreadItem.svelte, history.ts and InvestigationPane; no full-context reread needed.

Decisive tests: split phrase across deltas with interleaved unrelated same-thread
record; later final removes match; empty-final fallback; reordered reasoning parts;
late coordinate hydration; same IDs in other thread; hidden annotation via second
connection; update/delete/rebuild between search pages/inspection; private-store
refusal; Unicode expansion and literal wildcard symbols; bounded large-field
excerpts with explicit oversized inspection; hot-query raw parse count.

Root browser: same unmapped corpus, discover decision + counterexample + cross-thread
split text using queries (expected record IDs are assertions, not navigation inputs).
Inspect exact sources; pending/dirty editor unchanged; explicit Add blocked during
pending; after independent fresh draft add/save has exactly expected source bytes.
No unwanted neighbor, overwritten text or unknown/control/provider/hidden canary
matches. Held source reply and changed query/navigation cannot steal focus.
Actual API restart preserves canonical saved context and sends no POST. Inspect
1600/390px screenshots. Preserve baseline and any first failure distinctly.

Run focused backend/UI tests, independent regressions, then parent full pytest,
Svelte check/Bun tests/build and actual browser. Stop owned services before commit.
Return commit(s), changed behavior, commands/results, limitations and no fabricated
human/native usefulness claim. Do not push lane branches or overlap other owners.
