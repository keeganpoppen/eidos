# Authored findings without native dispatch — accepted implementation contract

**2026-10-13 · base `2aae982806de5386d0e42dc22f499bdb6d5e77f4` · C1/C5/C6 · V1-02/04/07/08.**
Root integrates. Three lanes own separate worktrees. No native, account, private
history, model or upstream calls. Public repository excerpts are explicitly authored
fixture records, never represented as actual native conversation.

## Observed gap and useful loop

Root asked why D34 refuses same-thread imports and what would justify merging,
using D34 and the exact `HistoryImports.commit` implementation at the base. A
conclusion/open question retained as selection rationale survives database reopen
and historical-input reuse, but result discovery returns no match. `complete`
correctly returns409 “investigation has no attempt”. Evidence:
`/tmp/nema-authored-finding-baseline.py` and matching `.json`. A first harness call
used an unsupported catalog `scope` parameter and refused400; the corrected public
catalog query reproduced the gap. No product mutation concealed that harness error.

Deliver saved exact context → Write finding → conclusion/open questions → Save →
lost reply/restart recovery → result-text discovery → original support inspection →
reuse as a frozen result input in another question and plain saved comparison.
Keep independent dirty/pending investigation drafts intact. No native lifecycle
transition is part of saving a finding.

## Canonical value and admission

Optional `findings[]` on the existing investigation, added only on first finding.
Do not add empty arrays to legacy owners or alter old context/prompt/manifest hashes.
Each immutable value is:

```
{id, kind:"owner-authored-finding", contextId, text,
 citations:number[], unsupportedCitations:number[],
 artifactCitations:string[], unsupportedArtifactCitations:string[],
 authorship:{kind:"local-owner",createdAtMs:number}}
```

No attemptId, outputSeqs, outputEvidence, executionEvidence, continuedFrom or fake
raw output record. Authorship means submission through the local owner workbench,
not authenticated human identity. UI says “Authored finding”; the host fixes kind
and attribution. Text is nonempty valid UTF8, at most128KiB; whitespace/BOM-only
prose refuses without normalizing accepted bytes. Unknown write fields
refuse. Context must be an exact saved context belonging to this owner; it need
not be current. Store native status/attempt/artifact/history/adoption/continuation,
current context and inquiry state unchanged.

Derive citation membership only from this frozen context's direct records and
direct artifact inputs. Preserve unsupported references; never inherit raw support
through another result. Uncited hypotheses are valid: show “No cited support”. With
supported references show “Cited sources supplied; claims not verified”. Finding
prose resembling terminal inquiry syntax is ordinary attributed text. Oversized
numeric citation tokens must produce a controlled400 refusal, not int-conversion500.
The new authored path accepts numeric citation tokens only through2**53-1 so Python,
JSON and browser identity agree; zero remains unsupported. This narrows only new
authored admission, without changing legacy native citation/domain behavior.

ID is a domain-separated versioned hash of owner ID, exact context ID, exact text
and derived citation sets, excluding timestamp. Same content in the same owner and
context can reuse the original immutable finding; a different request still obtains
its own receipt mapping. Include owner ID because context IDs may coincide across
owners. No edit/delete route; a revision is a further finding.

## Exact save and recovery

- POST `/api/investigations/:id/findings` with exactly
  `{requestId,contextId,text}` → `{finding}`,201 newly admitted request/200 replay.
- GET `/api/investigations/:id/findings/requests/:requestId` → `{finding}` or404.

Request ID is1..128 printableASCII and not all whitespace. Durable request fingerprint binds route owner,
context and exact text. One dedicated SQLite receipt index may store request ID,
fingerprint, owner ID, finding ID and immutable receipt JSON. Under lock and
BEGIN IMMEDIATE, resolve exact replay before current source validation, then admit
context/finding and write owner+receipt atomically. Same request changed body409;
wrong-owner receipt GET404. Concurrent exact requests produce one value. A response
is the original finding, never the latest mutable investigation. Receipt JSON is
bounded256KiB before commit (ordinary request body cap remains256KiB). No database,
CPU or whole-owner size quota is claimed.

Browser finding draft/pending body lives in a separate bounded slot, proposed
`nema.authored-finding.v1`; exact context and question are visible. Changing the
main selection/current context never silently repins the finding. Persist the
exact request before POST; unknown replies stay pending, with explicit receipt GET
or exact retry. Reload performs no POST. Do not discard another tab's slot. Save
success exposes the exact finding/source; it cannot clear or rewrite the independent
investigation draft. No automatic send, completion, adoption or inquiry action.

## Existing read/composition integration

Use a small shared artifact enumeration/source resolver at the three current
duplication sites: investigation inputs, read catalog/source, plain compositions.
Authored admission requires canonical `findings[]` membership plus valid host
kind/schema and exact context. Claiming authored kind in a native artifact must
not bypass missing attempt provenance. Conflicting same IDs across collections
refuse. Native artifacts retain existing exact attempt/context validation.

Existing artifactId references/catalog search/source routes apply. Source envelope
has `attempt:null,adoption:null` for authored findings; catalog attemptId is null.
Frozen artifactInputs retain exact finding and source context/manifest IDs, with
`sourceAttemptManifestId:null,sourceAdoption:null`. Exact historical support remains
available from frozen context even if current raw rows are absent. Do not globally
rewrite old projected prompt instructions. Explicit authored UI branches replace
native-only field dereferences. Plain comparison and saved snapshots work; native
adoption, specialist inquiries and recorded-experiment baselines remain attempt-bound.
Any UI admission based on “has artifacts” must preserve these native gates.

## Ownership and verification

- **history_ui/backend:** `/tmp/nema-authored-finding-backend`, branch
  `codex/authored-finding-backend`; `src/eidos/{investigation,investigation_reads,
  compositions,api}.py`, one small shared resolver module if warranted, backend
  tests `tests/test_authored_findings.py`. Own shared Python interfaces.
- **native_frontier/UI:** `/tmp/nema-authored-finding-ui`, branch
  `codex/authored-finding-ui`; `ui/**` only. Narrow staged editor, types, authored
  rendering, discovery/reuse/comparison integration, meaningful UI state tests.
- **gateway_review/independent:** `/tmp/nema-authored-finding-review`, branch
  `codex/authored-finding-review`; `tests/test_authored_finding_acceptance.py` only.
  Read both implementation lanes; report other fixes to owners. Tests may be
  written before backend exists and run after applying its commit locally.
- **root:** main, contract/docs, public-repository fixture/demo/browser acceptance,
  all integration/conflict resolution and final commit/nonforce push.

Discriminators: F0/C0 save reply lost → C1 revision/native progress → reopen/retry
returns F0/C0; zero attempt creation from finding save; direct/inherited citation
distinction; ungrounded hypothesis labelled; original support survives raw deletion;
result text finds F0; B freezes exact F0/context/attribution without attempt authority;
plain comparison saves/reopens while native-only actions stay unavailable. Six
concurrent exact requests, transaction failure before receipt, wrong owner/context,
forged kind/output/authorship, huge citation digits and old byte hashes are adversarial
cases. Root inspects actual desktop/narrow UI and restart/lostreply behavior, then
runs full Python, Bun tests/check/build and seed checks. Scripted authored evidence
does not establish human benefit, native quality or real subscription availability.
