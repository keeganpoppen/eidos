# Current handoff — stable history and native startup boundary

**NEMA-SEED-1 · 2026-10-13 · integration base `ad73408` on main.** The commit
containing this handoff is the tested integration. The continuing program is in
[PROGRAM](../PROGRAM.md); the [previous Round 3 handoff](ROUND3_INTEGRATED.md)
retains earlier decisions and their evidence.

## Delivered loop

Recover a decision and distant rejected alternative from 1,200 persisted turns;
follow each exact source; preserve a selected map and page through reload; build a
frozen two-record context; retain focus while an independent writer adds a new
turn and late old-turn evidence. Actual source membership, not min/max interval
overlap, controls highlights and navigation. Narrow layouts expose selected source
links in the transcript header. Idle polling keeps existing evidence objects.

This advances V1-01/02/03. It does not establish human reorientation speed, a byte
bound on a huge turn, or all V1 acceptance. Source-only records without a turn
remain outside the conversation projection. Browser arrangements are still local.

Backend: new `history.py`, additive `(thread_id,turn_id,seq)` index, snapshot-bound
paging in `api.py`, and `project_records` in `view.py`. API accepts `anchorSeq`,
`aroundSeq`, `limit` (1–40), and `knownVersion`; full pages include `window`,
`version`, and exact `recordSeqs` per turn/item. An unchanged envelope contains no
turns or outline. Raw evidence and historical semantic revisions remain unchanged.
See [D27](../../roadmap/DECISIONS.md) and the
[integration evidence](../../evidence/PAGED_HISTORY_INTEGRATION.md).

## Native progress and remaining boundary

The worker now validates a recorded `account/read` acknowledgement before creating
a native thread. Default live startup remains unadmitted. A real Codex 0.154.0
no-model experiment under bubblewrap 0.12.0 established tested startup isolation:
an enabled synthetic MCP ran before inventory but failed outside reads/writes,
network connections, packet remount and nested-namespace attempts; its detached
child stopped on closure. The parent independently reran the experiment.
[Report, exact command and next test](../../evidence/NATIVE_OUTER_ADMISSION_EXPERIMENT.md).

No existing credentials, private native configuration, model turns or paid API
usage occurred. The probe is not a production launcher or general security proof.
Authenticated egress, real policy/auth lifecycle and aggregate resource admission
remain open. Unknown outcomes, host privilege and provider-context gaps from Round
3 remain explicit; no gate was weakened to obtain a green test.

## Verification and integration

- `uv sync`; CLI help; `git diff --check`: passed.
- `uv run pytest`: **653 passed, 5 skipped** (explicit native opt-ins).
- `NEMA_NATIVE_OUTER_PROBE=1 uv run pytest tests/test_native_outer_boundary_probe.py`:
  **8 passed**, including actual disconnected no-model native startup.
- `cd ui && bun install && bun test tests && bun run check && bun run build`:
  **46 tests / 225 assertions**, **0 errors / 0 warnings**, build passed.
- Actual Chromium: persisted HTTP history, exact wrong-thread rejection, complete
  tool turn, disjoint support/reload, unchanged polls, writer append, and preserved
  keyboard focus/scroll. First page: **42,835 decoded bytes**; unchanged responses
  **at most 297 bytes**. These measure this fixture, not general bounds or speed.
- Supplementary browser review challenges delayed response races and narrow source
  navigation; linked artifacts and reproduction are in the integration report.

Accepted lane content: UI `dc906cb`, `f2dff07`, `76afb59`; acceptance `8183ac6`,
`afaae8a`, `bdabf82` plus final evidence; native `86b3767`, `dc9767c`. Parent owns
backend and combined integration. Branches/worktrees preserve recoverable history.
No personal trace, credential, auth directory or private export was committed.

## Continuing program and next actions

Next semantic integration: use exact investigation artifacts as bounded context
inputs. Preserve canonical artifact/context/attempt identity, source classifications,
unsupported citations and original support without recursively copying transcripts
or importing authority. A→B→C must recover A's controlling evidence from C. Preserve
legacy prompt/manifests; propagate inputs through follow-up reconstruction and make
experiment retention metrics account for artifacts. The UI scout identified those
compatibility obligations; implementation has not yet been claimed.

In parallel, the native lane continues a synthetic gateway experiment in
`/tmp/nema-native-account-admission` from `dc9767c`. It owns new probe/tests/evidence
only. A namespace-local relay will be challenged by a competing startup descendant;
identical headers or a shared relay are not proof of caller identity. No credentials
or real forwarding are authorized by the probe contract. Parent owns all production
interfaces and the final integration. Confirm actual agent/process status before
assuming this lane is still running in a later session.

Reproduce source acceptance with a fresh disposable database:

```sh
uv run python scripts/investigation_demo.py --db /tmp/nema-history-next.db --long-history --serve
# Start Vite on 5173 and isolated Chromium debugging on 9222.
NEMA_UI_DEMO_DB=/tmp/nema-history-next.db NEMA_UI_EVIDENCE_PREFIX=/tmp/nema-history-next node scripts/check_investigation_ui.mjs
```

The full check appends fixture records once; use a new database for another full
run. All execution within it is synthetic. The mission continues beyond this
integration; neither the vision nor V1 is declared complete.
