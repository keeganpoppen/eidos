# Current handoff — integrated investigation Cycle A

**Snapshot:** 2026-10-13, continuation of NEMA-SEED-1. Started from clean `main` at `b40d9ac4758ac1129fbfe0ab26c00b28f777b3ae`. This file describes the implementation commit containing it, without predicting that commit's hash. The [founding handoff](history/NEMA-SEED-1.md) is preserved.

## Chosen slice and judgment

The strongest immediate advance was a saved two-thread investigation through the existing recorder/workbench: semantic/item evidence selection → exact immutable context preview/revisions → one native attempt → recovery/result/source return → adopt/reject conclusion. This advances V1-02/03/04/05/07/08/12 in one integrated path. It avoids another disconnected protocol demo.

Nema remains an authority-local reflective world around native Codex. This slice makes selected context and work addressable; it does not complete the transformative whole. The calculus and generic ProcessRuntime are unchanged. The native-send failure boundary needs a durable pre-send attempt even if a later adapter uses ProcessRuntime; the separate outer Elaborate/inner Model pending correlation remains open.

## Exact implementation changes

- `src/eidos/investigation.py`: additive SQLite investigation/request tables in TraceStore's database; immutable parent-linked contexts with frozen exact records/hash, thread-scoped inclusive ranges, prompt preview and explicit coverage; request fingerprinting, transactional dispatch claim, attributable artifact and conclusion adoption. One attempt per investigation; an alternative is a separate investigation. No existing trace rows are rewritten.
- `src/eidos/investigation_worker.py`: fixed native adapter, fresh temporary cwd, recorded incarnation before launch, one turn, fixed native policy, MCP tool-inventory refusal, deadline/output handling, owned-process cancellation, evidence-only recovery with exact source/turn/input matching. No caller-selected executor/cwd/model/provider over HTTP.
- `api.py` / `serve.py`: durable investigation endpoints, one local worker at a time, restart reconciliation without resend, recovered native mappings, bounded JSON body, trusted loopback browser admission. Generic TM authority remains unexposed.
- `codex.py`: closure is terminal for one app-server incarnation; serialized start/close; terminate owned child before closing buffered stdin to unblock stalled writes. Independent deadline watchdog covers the send-before-RPC-timeout gap.
- `ui/src/`: investigation pane; item and disjoint semantic selection; saved context/revision comparison; explicit dispatch; pending/unknown/result views; exact source/native-output return; adopt/reject receipt; browser draft/focus/save-retry persistence; guarded navigation and long-ID wrapping.
- Tests: new context, worker and API integration suites; native lifecycle regression. `scripts/investigation_demo.py`, synthetic app-server fixture, and dependency-free Chromium workflow script provide reproduction.
- [Contract](INVESTIGATION_CONTRACT.md), [acceptance report](../evidence/INVESTIGATION_CYCLE_A.md), [screenshot](../evidence/investigation-workbench.png), README, STATE and D01/D15/D21 realization note document the boundaries. No vision destination or seed identity changed.

## Verification actually performed

- Baseline: 129 Python tests; UI check/build passed.
- Final implementation: `uv run pytest` — **176 passed**. `uv sync` and `uv run eidos --help` passed. `bun install`; `bun run check` — **0 errors / 0 warnings**; `bun run build` passed.
- `node scripts/check_investigation_ui.mjs` — passed in headless Chromium at 1600×1000, against a synthetic 48-turn / 96-record database. Selected semantic records 12/38 plus native item 72 from the second thread; exact preview excluded distractors; saved two revisions; dispatched one fake worker; reloaded; followed a citation to highlighted source; adopted and reloaded receipt. Final screenshot inspected. No human speed claim.
- Failure/counterexamples: interleaved threads, unknown fields and exact bytes, index enrichment/reimport after preview, altered request identity, stale revision, concurrent dispatch/revision/adoption, absent native acknowledgements/mappings, failed terminal with text, completion-before-outer-commit, no implicit replay, unsupported citation, unsafe/unresolved MCP inventory, shutdown between RPCs, blocked large stdin write and deadline, browser cross-origin/rebinding admission.
- Codex **0.154.0** local version/schema inspection only. All worker executions were synthetic. No provider API or subscription-backed model turn was run; no personal native history was imported.

## Review and boundaries

Three actual read-only scouts preceded disjoint implementation worktrees. Independent authority/recovery review found and reproduced the native incarnation restart race and transport backpressure gap; both were repaired and tested. It also led to recovering missing navigation mappings. Independent product review accepted the bounded slice after fixing dropdown reset, durable retry IDs, stale source navigation, and synthetic demo restart. One integrator owns shared interfaces and the final commit.

This is a trusted single-owner service, not authenticated remote capability transfer. Native config enforcement, full tool isolation, true provider context, complete native continuation recovery, OS resource quotas, token/cost bounds, and exactly-once external effects are unproved. Known MCP tools block the new specialist before a turn; unknown native outcomes stay visible and cannot silently launch again. Adoption records a conclusion, not a file patch or instruction update.

Still missing: visible resumable offer/refuse/defer inquiry wired through ProcessRuntime; native history reconciliation when local completion evidence is absent; linked comparison between alternative investigations; complete context manifests; reflective arrangement/adoption and a measured improvement loop. Existing ordinary chat/semantic observer APIs retain their previous narrower behavior; this patch does not retrofit all of them with investigation idempotency. Context snapshots/listing are bounded per packet but not optimized for thousands of investigations.

## Ownership and next action

All three worker tasks finished; no scheduled or background development is implied. Source worktrees were `/tmp/nema-context-b40d9ac`, `/tmp/nema-worker-b40d9ac`, `/tmp/nema-ui-b40d9ac`; their owned patches were imported and reviewed. Temporary demo/browser services used for acceptance are stopped before the session ends. Synthetic databases under `/tmp` are not repository artifacts.

**One runnable next action:** choose a fresh path and run:

```bash
uv run python scripts/investigation_demo.py --db /tmp/nema-next-investigation.db --serve
```

Then open the UI with `cd ui && bun run dev -- --host 127.0.0.1` and follow the [acceptance workflow](../evidence/INVESTIGATION_CYCLE_A.md). It must retain the same artifact/adoption after restarting with `--resume --serve`.

The next development recommendation is a narrowly scoped **real-native verification of this same synthetic packet** under authorized account resources, beginning with the worker's policy/tool preflight. Record native acceptance/rejection and actual outcome without weakening the gate or modifying user Codex configuration. Only then extend the durable outer identity into a useful resumable evidence inquiry. No human decision blocks reproducing the delivered synthetic loop.
