# Reflective comparison — UI contract and continuation

**NEMA-SEED-1 · 2026-10-13 · implementation base `ac2c093b675c5765abccaeff33a721f48f4318ce` · branch `codex/reflective-workbench`.** This document describes the commit containing it. It advances V1-03/04/10 and the comparison part of V1-08; it does not claim all of those scenarios or V1 are complete. Python source and backend implementations are unchanged.

## The interaction

An ongoing investigation can hold two saved readings beside one another. Open **Compare saved work** from an investigation, or **Compare** in the workbench. Bind A and B to saved investigations and exact context revisions. Choose returned work or context/evidence, review the proposed arrangement, and apply it. The two targets can also be different revisions of the same investigation.

**Inspect support** beside a passage keeps both readings in place and reveals its frozen input below. Selecting another cited record does not change the original transcript selection, either aperture binding, or the current investigation draft. The focus survives changing a lens, applying/undoing an arrangement, and reload. A passage without citations is explicitly unsupported; a citation outside the supplied packet has no source action.

**Inspect what changed** displays a line diff of returned text or of the question, evidence ranges, inclusion rationale, and frozen-record hashes. A changed hash at the same address remains visible. The raw evidence is available separately. Textual differences do not decide which interpretation is correct.

The existing evidence map, context builder, native dispatch, result adoption, and transcript remain available. Comparison introduces only read/presentation actions. Its arrangement controls never dispatch, recover, adopt, change context, or apply returned code.

## Four concepts, one presentation model

| Concept | Concrete meaning here |
| --- | --- |
| Surface | The comparison region in the existing browser workbench. There is no new surface registry. |
| Lens | Version 1 of `returned work` or `context & evidence`, with a native text-diff projection. |
| Aperture | A position (`left` or `right`) bound to `{investigationId, contextId}`. Position does not identify the investigation. |
| Focus | A separate relation to `{investigationId, contextId, artifactId?, blockId?, threadId?, seq?}`. Rearranging positions does not rebind it. |

[`comparison.ts`](../../ui/src/lib/comparison.ts) owns one versioned `Composition`: arrangement, retained focus, open/closed preference, and up to twelve undo snapshots. [`ComparisonSurface.svelte`](../../ui/src/lib/ComparisonSurface.svelte) interprets it. A draft arrangement is separate from the applied one. Review shows before/after target, lens and placement; cancel has no applied effect. Apply records the new arrangement locally; undo restores a prior arrangement while preserving the *current* focus. Undo works after reload. This is local presentation history, not a server-side provenance log or an agent-authored arrangement proposal.

The `beside` placement becomes vertically stacked on narrow screens without changing its semantic bindings. A deliberate `stacked` placement is also reviewable. These are two useful placements, not a general layout engine.

## Existing API and evidence boundary

Comparison uses **GET `/api/investigations`**, whose current response contains all investigations and frozen context records. Objects displayed in comparison are server-derived, including status, adoption, exact question, artifact text and evidence bytes. The baseline [investigation contract](../agents/INVESTIGATION_CONTRACT.md) remains authoritative for the existing API.

Browser storage under `nema.composition.v1` contains only presentation references and settings, never artifact text, copied investigations, raw records, hashes, or projected prompts. Restore validates the version and strips unrecognized fields. Missing investigation/context IDs remain visibly unavailable; they are never silently replaced by another target. A failed refresh identifies displayed snapshots as potentially stale. Unavailable browser storage is reported and does not disable the workflow.

Artifact focus validates the whole chain: artifact ID → artifact's exact `contextId` → the selected immutable Markdown block → a citation admitted by the server → the frozen record's thread and sequence. Changing `currentContextId`, tampering with a stored context ID, or remembering a different record in the same packet cannot silently change a passage's support. Membership is attribution, **not entailment**. Context-record selection can inspect any record in that selected context and is labelled separately from cited passage support.

Markdown block anchors are offsets derived by the versioned renderer inside an immutable artifact; they are not cross-version claim identities. Original bytes and unknown fields remain in `rawText`, with the server-provided SHA-256 shown alongside them. The evidence renderer recognizes observed message, command-output and file-change shapes; unknown shapes expose original bytes without inventing content. The original record disclosure is rendered on demand.

Returned fenced `diff`/`patch` content is displayed with native added/removed lines and explicitly labelled **not applied**. Waiting/unknown/failed results show the saved question and server status. There is no invented progress feed, resumable question, or answer control: this API has no structured inquiry contract.

## Large content and navigation

- The transcript renders a window of at most 40 turns, with earlier/later controls and sequence navigation. Semantic selection and source return choose the relevant window before scrolling. The remembered window survives reload. Sequence search locates a containing turn range; it does not establish exact membership for interleaved thread records.
- Context record indexes show 20 records per page. Undo resets their pagination so a shorter restored packet cannot appear empty.
- Returned prose renders 32 Markdown blocks per page. Moving focus to another aperture does not reset the previous aperture's page. Diff views render 120 rows per page and collapse long unchanged runs. Explicit expansion remains available.
- Diff computation caps the LCS matrix at 200,000 cells. Larger unmatched regions are represented as exact removed/added replacements, not a claim of minimum edit distance.
- Buttons/selects support ordinary keyboard navigation; Enter activates support and record controls, Escape cancels an arrangement edit, and Alt+E moves keyboard focus to the evidence heading. Polling does not move keyboard focus or explicitly scroll an aperture.

These bounds limit default DOM work. Both the investigation and thread APIs still fetch complete payloads; network, memory and server-side history scalability are **not solved**. A single very large Markdown block or explicitly expanded patch may still be expensive.

## Reproduction and visual evidence

Use a fresh path for the existing **synthetic** service, then run Vite and an isolated Chromium. No account/model call is required or performed:

```bash
uv sync
uv run python scripts/investigation_demo.py --db /tmp/nema-reflective-demo.db --serve
```

In separate terminals:

```bash
cd ui
bun install
bun run dev -- --host 127.0.0.1
```

```bash
chromium --headless --no-sandbox --disable-gpu --remote-debugging-port=9222 --user-data-dir=/tmp/nema-reflective-browser about:blank
node scripts/check_investigation_ui.mjs
```

Use a fresh, private temporary Chromium profile. The script clears presentation storage in its test tab. The `--no-sandbox` flag accommodates the container used for acceptance; it is not a recommendation for ordinary browsing.

The script retains the original selection → save → revise → synthetic dispatch → reload → source return → adoption check, then creates a second saved investigation through the existing API. It checks comparison of investigations and revisions, real context diffs, staged/cancelled/applied/undone arrangements, keyboard support navigation, frozen source identity, reload, and unchanged authoritative objects.

The existing fake worker intentionally returns the same substantive conclusion for both tasks, while their questions and selected context differ. Additional browser-only fixtures exercise a *different* interpretation, native patch rendering, an unsupported citation, and a 1,200-turn history. They are explicitly labelled and do not alter the database. The competing-artifact projection has its native output sequences and adoption cleared; it is a rendering fixture, not another worker's observed conclusion.

| Artifact | What it demonstrates |
| --- | --- |
| [Server comparison](reflective-server-comparison.png) | Two actual saved investigations from the synthetic API, separate context bindings, returned work, and original frozen evidence. |
| [Context diff](reflective-context-diff.png) | Real question/range differences; the competing packet excludes record 38. |
| [Reflective workbench](reflective-workbench.png) | Clearly labelled browser-only competing interpretation, native patch and exact supplied source. |

Observed verification on this implementation:

- `uv sync`; `uv run pytest` — **176 passed**. No Python implementation was edited and no real-native model turn was run.
- `cd ui && bun install && bun run check && bun run build` — dependencies installed, **0 errors / 0 warnings**, production build passed. No deployment was performed.
- `cd ui && bun test tests` — **14 passed**, 47 assertions covering immutable reference resolution, corrupt local preferences, full provenance binding, apply/reload/undo, exact evidence projection, bounded diffs, and context selection equality independent of JSON key order.
- `node scripts/check_investigation_ui.mjs` — **passed in Chromium**, including the original API workflow, comparison of two saved investigations and two revisions, review isolation/cancel/apply/undo, Enter-key support navigation, reload, reference-only storage, and unchanged server objects. The 1,200-turn browser fixture retained at most 40 rendered turns while jumping to the last turn, paging, and returning to an earlier citation.
- Additional Chromium fixture checks: native returned diff, disabled out-of-packet citation, an unknown outcome rendered as its question without a fabricated result, and no page-level horizontal overflow at 900px and 390px widths. The main screenshot was inspected at 1600×1000; it is scripted visual evidence, not a human performance study.

Rendered testing also reproduced an existing context-builder bug: a polled server response reordered JSON object keys, causing `JSON.stringify` equality to incorrectly mark saved selections dirty and disable dispatch. Selection equality now compares meaningful fields while preserving selection order. Both a unit test and the rendered post-poll save/dispatch workflow cover the repair.

The prior [Cycle A screenshot](investigation-workbench.png) remains unchanged.

## Proposed backend contracts — not implemented

| Gap | Contract proposed to the integrator | Why the UI cannot establish it |
| --- | --- | --- |
| Large histories | Summary-only investigation listing with stable cursors; bounded context/record retrieval by thread + exact sequence; an explicit trace/world ID. | Current endpoints return full objects. Local sequence numbers alone do not identify a record across database changes. |
| Durable reflection | Versioned arrangement proposal and receipt with semantic target bindings, base version, requester, applied projection, and optimistic concurrency. | Browser history does not provide cross-device recovery, durable attribution, or agent-submitted proposals. |
| Pending inquiries | Inquiry ID, exact question, context/attempt binding, allowed decisions, scope/continuation state, and a server-admitted response route. | A `running`/`unknown` status is not an actionable disclosure request. |
| Claim lineage | Immutable claim anchors and evidence links scoped to artifact versions, with explicit unsupported/inferred status. | Markdown offsets cannot establish stable claim identity across revised artifacts or validate entailment. |
| Alternative lineage | Baseline investigation/context/artifact reference plus the named counterfactual change and explicit adoption target. | Two selected works are comparable views, not proof that one is a native/workspace fork of the other. |

## Continuation within this lane

This document is the UI lane's handoff, intentionally within the user-assigned `docs/evidence/` ownership. The repository-wide handoff and canonical roadmap are left to the integrator. No vision commitment, backend endpoint, Python source or `main` revision is changed.

Root owns the shared presentation model, integration and final commit. A bounded implementation lane supplied native renderers and tests; a separate browser lane extended the Chromium harness and fixtures. Independent review found and repaired mismatched restored provenance, short-context pagination after undo, cross-aperture page reset, and repeated same-work comparison requests. No ongoing worker activity is implied by this artifact.

**Next runnable step:** reproduce the script above, then integrate bounded server retrieval with a trace/world identity before treating this as a scalable long-history client. A structured inquiry or durable arrangement endpoint should arrive as a reviewed backend contract, not as simulated UI actions. Native provider behavior and agent-assisted composition remain unverified and outside this change.
