# Reflective attention — UI contract, evidence, and handoff

NEMA-SEED-1 · 2026-10-13 · implementation base
`50d1bc91870b9118a84706606d6a06008dffcdf7` · branch
`codex/reflective-experiment-workbench`.

This UI lane advances V1-03/06/08/10/11 through one interaction: keep an active
question, its original evidence, a separately supplied packet, a result, and a
named alternative addressable while reviewing how they should be presented.
The existing comparison compositor, exact artifact pins, focus, source navigation,
native renderers, review/apply/undo, and real local-review API remain in use.
No Python/backend file or main revision was changed. This is the lane handoff;
the integrator retains ownership of the repository-wide handoff and roadmap.

## Use the workbench

In **Compare**, choose **Original evidence → request → result**, or use **Follow
evidence & response** from an investigation with a local review. Review the
resolved identities and apply the arrangement. Three linked apertures retain
the original answer/input, the exact inquiry and offered packet, and the resulting
Eidos receipt. Existing API offer/refuse/defer/retry/resume actions remain in the
real inquiry aperture. They use the existing admission and retry mechanism.

Pending is distinct from refusal. If a response arrives after an arrangement was
applied, the pending arrangement keeps its unbound result; **Review completed
evidence chain** stages the exact new response/result bindings. The receipt is
explicitly a local decision, not a new native model conclusion. The offered
packet was never sent to the original native turn.

**Open synthetic inquiry & experiment** explicitly loads a deterministic authored
fixture; it initially stages, rather than applies, the arrangement. The fictional
specialist requests acknowledgement and terminal-result evidence for request 41.
**Preview supplied-evidence outcome** loads the supplied stage and requires
another arrangement review. These stage switches perform no API mutation or
model call. No production agent proposal is invented.

**Compare the named alternative** retains the original artifact/input alongside
*Acknowledgement included*. Native line diffs show the added record 72, while
the evaluation distinguishes what its structural checks establish from unknown
reasoning quality and unmeasured user benefit. The alternative intentionally uses
later evidence and is labelled retrospective and counterfactual.

**Review improvement** exposes motivating bindings, a concrete presentation diff,
a falsifiable expected benefit, evaluation cases/limitations, resource uncertainty,
old/new presentation versions, and rollback. Applying the reviewed browser preview
visibly inserts the exact evidence chain before the comparison. Undo removes that
additional arrangement after reload while preserving comparison and focus.
**Adopt durable improvement** is disabled because this base has no such endpoint.
Neither local presentation application nor a future ledger adoption activates
native configuration by implication.

## Typed arrangement and adoption boundary

The executable contracts are [comparison.ts](../../ui/src/lib/comparison.ts),
[reflection.ts](../../ui/src/lib/reflection.ts), and
[improvement-preview.ts](../../ui/src/lib/improvement-preview.ts).

People or programs can supply the following data in **Structured attention request**:

```json
{"version":1,"intent":"evidence-chain","investigationId":"an-exact-saved-id"}
```

```json
{"version":1,"intent":"alternative-review","experimentId":"fixture:recovery-experiment-v1"}
```

`compileAttentionRequest` lowers these two supported intents to a proposal using
ordinary compositor bindings. It never evaluates code, resolves arbitrary Names,
or calls an execution endpoint. The named experiment must already be available;
this is not a free-form language model or remote agent submission API.

| Object | Reviewable meaning and invariants |
| --- | --- |
| `ApertureTarget` | Exact investigation/context/artifact IDs. A context-only target cannot follow a current result. |
| `Arrangement` | Existing left/right/lens/layout plus optional intent, inquiry binding, and experiment ID. Stack placement is realized for inquiry and comparison. |
| `InquiryBinding` | Exact continuation and inquiry; a supplied packet requires its response ID and evidence context ID. Original, response, packet, and receipt must agree. |
| Named experiment | Exact baseline and alternative. Changing a target cannot retain the old evaluation: apply rejects it, and restored mismatches withhold evaluation/preview. |
| Arrangement review | Before/after targets, intent rationale, offered packet/response, placement, retained focus, and browser scope. A changed base arrangement requires fresh review. |
| `Improvement` | Explicit fixture origin, proposal/version, evidence refs, experiment, expected benefit, patch, old/new presentation versions, rollback. |
| `ImprovementPreview` | `browser-presentation-preview` scope; exact proposal/experiment/version refs, prior and active version, undo. Never an Eidos or backend adoption receipt. |

Storage retains references and presentation preferences, not copies of artifacts,
raw evidence, context prompts, or adopted policy. `nema.composition.v1` preserves
focus and twelve undo entries. The fixture-stage preference stores only `pending`
or `supplied`; the fixture is regenerated from versioned source. The improvement
preview validates its exact proposal/experiment versions and strips extra fields.
Unavailable objects stay unavailable. These browser records do not provide
cross-device durability, multi-tab concurrency control, authenticated authorship,
or server-authoritative provenance.

The renderers retain native evidence and patches. Offered evidence can now resolve
through its exact response rather than being mistaken for an ordinary context
revision. Each inquiry record index has a 20-record page and range controls.
Keyboard Enter activates source selections; Alt+E focuses their shared evidence
aperture. Selection, immutable bindings, and browser undo survive reload.

## Coordination with B, C, and the integrator

The sibling working-tree contracts were inspected read-only during this session:
`specialist-initiated-inquiry/docs/agents/SPECIALIST_INQUIRY_API.ts` and
`SPECIALIST_INQUIRY_CONTRACT.md`; and
`counterfactual-laboratory/docs/agents/EXPERIMENT_CONTRACT.md`.
They were uncommitted, evolving work at inspection, not capabilities of this base.
This is a concrete integration handoff, not a claim of cross-lane merged acceptance.

**B — specialist inquiry.** Its `origin: native-specialist` and
`mode: terminal-needs-evidence` must remain distinct from this base's owner-started
`synthetic-eidos` review. After A2 dispatch, B retains A1 in `attemptHistory` and
the Eidos receipt in `artifactHistory`. Integration must extend exact resolvers
to those arrays, rather than require the current attempt to own every historical
inquiry. Render `native-needs-evidence`, the disclosure receipt, and A2's
`native-specialist-result`/`continuedFrom` as distinct artifacts. Preserve source
offer/refuse versus recipient answered/refused, cancellation, realization failure,
and admission error. `nativeNext.contextId` is a preview, not execution.
`/continue` separately admits a new native attempt; `/resume` and `/recover` only
repair locally. This UI does not enable the unmerged `/continue` or cancellation
routes or claim a hidden interactive model stack exists.

**C — experiment ledger.** Its `ExperimentRecord.name` is occurrence identity;
`.cid` is shareable content identity. The production adapter must retain both,
plus exact baseline/context snapshots, horizon, criteria, evaluator, outcome,
review, adoption, and rollback references. C grades two new structured fixture
reinterpretation outcomes, not arbitrary prose or the retained original artifact.
Do not relabel our authored comparison as C's measured outcome. C's trusted-host
`adopt` records a reviewed version and rollback target without activating config.
Its inspected delivery has no HTTP routes. The UI's durable adoption therefore
remains unavailable; a browser preview cannot substitute for the ledger.

**Integrator.** Replace fixture loading with an admitted read projection only
after those seams agree. Preserve this lane's request compiler and renderers;
add read adapters rather than another mutable investigation store. Durable
arrangement submissions need author/origin, proposal ID, exact semantic targets,
base version, idempotent request identity, realized arrangement receipt, conflicts,
and explicit rollback. Server-reported capability/precondition information must
govern newly enabled authority-changing controls. No sibling backend content was
copied into this branch.

## Retrieval audit and bounded server proposal

Observed current behavior: the thread view retrieves the full selected thread
every 1.5 seconds outside Compare; the investigation pane retrieves its full
selected investigation every 1.5 seconds; Compare retrieves all investigations
and embedded context/record payloads every 5 seconds while open. Hidden panes
also retain their data. These are material network, parse, and memory costs.

The [retrieval observation](attention-retrieval.json) records three complete
452,996-byte decoded synthetic history responses: 1,358,988 bytes total. The
40-turn projection is 26,714 bytes. The DOM remains at most 40 turns, but the
complete 1,200-turn payload is repeatedly delivered. Heap observations include
application and browser activity and neither prove a bound nor diagnose a leak.
These are decoded intercepted JSON bytes, not measured compressed wire traffic.

Proposed server work, **not implemented**:

| Read seam | Necessary bound and identity |
| --- | --- |
| Investigation listing | Summary-only cursor pages, stable world/snapshot identity, revision/ETag; no embedded raw contexts. |
| Thread window | Snapshot-bound cursor or around-sequence request, explicit next/previous cursors and total if known. Preserve exact record coordinates. |
| Context/artifact | Immutable metadata/reference reads, separately bounded bodies; historical artifact-by-ID lookup, including B's history. |
| Evidence | World + context + thread + sequence + digest; reject mismatches. Count and byte limits, including one oversized record. |
| Polling/cache | Conditional requests, abort superseded requests, share immutable reads, bounded cache eviction, explicit oversized-content continuation. |

The current endpoints do not implement these contracts. Passing pagination
parameters or rendering fewer nodes would not establish server bounds. A single
expanded original record, prompt, or large Markdown block can still be expensive.

## Reproduction and verified evidence

Start the existing synthetic service in a fresh database (no native account/model):

```bash
uv sync
uv run python scripts/investigation_demo.py --db /tmp/nema-attention-fresh.db --serve
```

In separate terminals:

```bash
cd ui
bun install
bun run dev -- --host 127.0.0.1
```

```bash
chromium --headless --no-sandbox --disable-gpu --remote-debugging-port=9222 --user-data-dir=/tmp/nema-attention-fresh-browser about:blank
NEMA_UI_EVIDENCE_PREFIX=docs/evidence/attention node scripts/check_investigation_ui.mjs
```

Use an isolated temporary profile; the script clears its tab's presentation storage.
`--no-sandbox` accommodates this container, not ordinary browsing guidance.

Observed validation on this implementation:

- `uv sync`; `uv run pytest`: **361 passed, 2 skipped** (opt-in native probes).
- `cd ui && bun install && bun run check && bun test tests && bun run build`:
  **0 errors / 0 warnings**, **36 tests / 181 assertions passed**, production build passed.
- Extended Chromium workflow passed after responsive and binding repairs. It
  retains the existing two-thread save/revise/dispatch-fixture/reload/source-return/
  review/adoption/comparison path, then exercises real recorded evidence-chain
  bindings and the authored inquiry/alternative/improvement workflow.
- The browser asserts keyboard source selection/reload, native context diffs,
  staged/cancelled/applied/undone changes, stack geometry, mismatched experiment
  rejection, disabled durable adoption, actual evidence-first insertion, unchanged
  saved API objects, and **zero API mutations during the attention/fixture/preview
  operations**. Existing real local-review actions still mutate through the API.
- At 900px and 390px, the page and open improvement review wrap; the evaluation
  table has its own keyboard-accessible horizontal region. Long-history metering
  records repeated full responses alongside the existing 40-turn DOM check.
- `git diff --check` passed. No live Codex/model command or deployment was run.

Screenshots were rendered and inspected; they establish presentation and scripted
interaction, not a human performance study:

| Capture | What it shows |
| --- | --- |
| [Recorded API chain](attention-recorded-evidence-chain.png) | Real saved synthetic API objects: original native output fixture, separately offered packet, Eidos receipt. |
| [Pending inquiry](attention-pending-inquiry.png) | Explicit authored specialist question, original input, no fabricated returned result. |
| [Supplied evidence](attention-supplied-evidence-chain.png) | Distinct original/offered/result bindings with native evidence rendering. |
| [Named alternative](attention-named-alternative.png) | Original versus retrospective counterfactual; context change and inference limits. |
| [Improvement review](attention-improvement-review.png) | Evaluation, unknown benefit, browser preview, rollback, disabled durable adoption. |
| [Retrieval data](attention-retrieval.json) | Repeated complete payload delivery despite bounded DOM rendering. |

Additional `attention-*.png` captures retain the prior saved-comparison, native
patch, context-diff/provenance, pending-review, and original/receipt acceptance.
Prior evidence files remain unchanged.

Independent review found and repaired misattributed experiment evaluation after
target rebinding, inquiry/result/packet mismatches, unrealized stacked placement,
inaccessible evidence after record 20, synthetic artifacts labelled native in
review controls, and offered packets labelled revision zero. Chromium found and
repaired an open evaluation table expanding the whole mobile page.

Root integrated disjoint contract/fixture, improvement-renderer, and browser-test
lanes and owns the final commit. There is no ongoing or scheduled worker claim.
The next runnable step is the reproduction above, followed by integration of B's
historical artifact/attempt resolver and C's admitted read projection. Acceptance
must retain the original, receipt, and new native result as separate exact versions
and continue rejecting unrelated experiment outcomes. Actual native model quality,
durable improvement adoption, bounded retrieval, and measured user benefit remain
open; this synthetic UI experience does not close those gates.
