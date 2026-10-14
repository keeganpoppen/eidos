# Reuse exact historical inputs for a new question

**Accepted implementation contract · 2026-10-13 · base `fa7eabf`.**
C1/C4/C5, V1-04/08/09. The managed-attempt wave is committed and pushed; its
[offline evidence](../evidence/MANAGED_ATTEMPT_INTEGRATION.md) does not establish
real account availability. This slice advances returning to useful work without
another native experiment. All acceptance uses synthetic local history.

## Observed gap and chosen loop

InvestigationPane's historical preview uses previewId; New alternative from
selection calls newDraft(true), which carries the current editable inputs and old
question. These differ when a historical revision is inspected. Further, the
ordinary artifact resolver captures current source review metadata, so copying
only historical selectors refreshes part of the frozen input.

From a named historical context, explicitly stage a new title and blank question
using its exact frozen inputs. Save a distinct investigation through the existing
canonical projector, inspect the result, then deliberately open it. Inspection,
creation, response loss, retry and reload preserve the existing editable draft
and its separate pending-save identity. No dispatch, adoption or authority transfer
occurs. First save uses the frozen source inputs; ordinary revisions afterward
remain the existing path for editing them.

## Shared API and data contract

Existing POST /api/investigations gains one mutually exclusive creation mode:

```json
{
  "requestId": "fresh durable creation identity",
  "title": "New title",
  "question": "Newly entered bounded question",
  "inputSource": {"investigationId": "exact owner", "contextId": "exact context"}
}
```

Reject selections or artifactInputs alongside inputSource, including empty arrays.
No client frozen content, projectedPrompt, inputOrigin, configuration or arbitrary
provenance field is accepted. Existing create/revise requests remain compatible.
No new route, recipe registry, default activation or execution profile is needed.

Under the existing transaction, check request replay before source resolution,
then resolve the exact context within the named owner's contexts. Missing owner,
missing context or a wrong-owner context fails without latest-context substitution.
Deep-copy only selections, records and artifactInputs from that frozen context.
Preserve rationales and entire frozen record/artifact envelopes, including unknown
raw payload fields and captured source adoption/manifests. Do not re-resolve their
current source reviews. The historical context itself is the input snapshot;
missing historical context cannot be replaced by a newer result or record set.

Generate the current canonical prompt with the new question and recomputed
coverage. Do not copy source question, projectedPrompt, coverage prose,
inquiryLineage/continuation text, native state, attempt, adoption, authority or
unknown top-level context fields. These remain intact in the original. This does
not strip instruction-like historical raw evidence: it remains quoted untrusted
data under the existing projector. New parentContextId is null; within-owner
parent revisions and cross-owner origin remain distinct.

New context has server-authored, hash-covered optional provenance:

```json
{
  "inputOrigin": {
    "version": 1,
    "kind": "historical-context-inputs",
    "investigationId": "source owner",
    "contextId": "source context",
    "manifestId": "source manifest, or null for legacy absence"
  }
}
```

Expose this as a selected/local optional manifest entry (not an observation of
native delivery). Legacy contexts/manifests retain their existing identities.
Ordinary later revisions use parentContextId to reach the initial reuse; do not
claim edited inputs still equal the original. A create retry returns the owner’s current state under existing request-ledger
semantics. The UI must identify the exact initial reused context by parent=null,
matching origin and requested new question; it must not substitute a newer
currentContextId. Keep that exact context in saved-result inspection/Open, and
label any newer current revision separately. Apply existing selection, record and
projected-byte bounds; no alternate prompt-building implementation. Neither a
source Name nor copied native output creates a continuation or live capability.

## Staged UI and request recovery

Add “Start a draft with these inputs” beside the exact saved context preview.
Stage that explicit target, source title/label and record/result counts; title is
editable and question starts blank. Persist this staged creation separately from
nema.investigation-draft.v1. Target and new fields do not alter editor selections,
question, pendingRequest, preview or live controls. Historical preview changes do
not retarget an already staged/pending request. One bounded staged creation is
enough; do not introduce a general draft registry.

Persist the exact request body and requestId successfully before sending. Storage
failure refuses send. A lost reply retains exact retry; disable changes that would
change a pending request. No automatic POST on reload/navigation. A pending request
cannot be silently dismissed or replaced. An explicit server400/404/409 refusal
may retain a refused status and offer deliberate Dismiss refused creation; keep
the exact request until that choice and never claim this proves no earlier effect.
Network/5xx/malformed-success outcomes remain pending and locked. Cancellation before sending is local.
On success show the saved investigation/context and a read-only Inspect saved
input action (exact initial question/origin/coverage and expandable projected input),
then a distinct Open saved draft action; do not automatically call useInvestigation or overwrite the working draft.
Reopen must retain saved-result discovery and the original editor recovery identity.
If the editor has an unresolved save, Open stays disabled with an explanation.
Otherwise replacing unsaved edits requires an explicit UI replacement choice.
After opening, ordinary saved-context preview/edit/dispatch rules apply; no action
is automatically performed because inputs were reused. Show origin as inspectable
provenance, never as proof of source claims or execution authority.

## Ownership and integration

Root owns this packet, docs, authored fixture/browser acceptance scripts, API seams
if needed and final integration/commit. Base main is clean `fa7eabf`.

- history_ui: `/tmp/nema-context-inputs-backend`, branch codex/context-inputs-backend.
  Own src/eidos/investigation.py, src/eidos/investigation_context.py and new focused
  Python tests. Refactor existing projection without changing legacy packet bytes.
  No API/UI/native changes without root coordination.
- native_frontier: `/tmp/nema-context-inputs-ui`, branch codex/context-inputs-ui.
  Own InvestigationPane.svelte, types.ts, a small staged-creation helper/component
  and focused UI tests. Other shared UI files only by coordination. No backend or
  browser fixture edits; give root stable labels/selectors for acceptance.
- gateway_review: `/tmp/nema-context-inputs-review`, branch codex/context-inputs-review.
  Independent authority/evidence/recovery review; counterexamples against both
  contributions. Do not rewrite owned production files; report runnable failures.

Read this packet, nearer AGENTS, relevant implementation and linked evidence;
immutable shared context need not be reconstructed from the whole repository.
Contributions should be scoped tested commits for root to inspect/integrate.
No native, account, DNS or upstream service work is part of this contract.

## Decisive acceptance and refusal cases

A historical C0 includes disjoint records and an exact frozen artifact review.
Later the source artifact review changes, and current C1/editor inputs differ.
Preview C0 while an unrelated dirty/pending draft exists. Stage a new question,
create with a deliberately lost committed response, reload and retry exactly.
New context keeps C0's exact snapshots/rationales and source origin, uses only the
new canonical question, and omits old inquiry/runtime/control fields. Exactly one
new draft appears; no thread/turn/dispatch. Original history, context hashes and
editor/pending recovery bytes stay unchanged. Open obeys the explicit guard above.

Backend counterexamples: missing/wrong-owner source, ambiguous mixed input modes,
injected provenance/prompt fields, replay after source availability changes,
requestId body conflict, source payload immutability/unknown field conservation,
newer artifact/review substitution, prompt bounds and legacy identity compatibility.
UI counterexamples: stale asynchronous response/target change, pending body edit,
storage failure, exact retry after reply loss/reload, no auto-send, editor pending
save and explicit replacement. Root runs focused/full Python, UI check/tests/build,
actual desktop/390px browser flow and independent review before commit/push.
