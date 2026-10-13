# Current handoff — exact result composition

**NEMA-SEED-1 · 2026-10-13 · integration base `29a164a` on main.** The commit
containing this handoff identifies the integration. [PROGRAM](PROGRAM.md) owns the
continuing mission and revisable conjectures. The
[previous history integration](history/HISTORY_PAGING_INTEGRATED.md) retains its
commands and measured limits. Neither this integration nor a green suite completes
the mission or V1.

## Delivered loop

Use an exact earlier result as context for new work, inspect its original packet,
and follow a synthetic C→B→A chain to the controlling raw evidence. Source adoption
is a separate frozen decision. Derived claims and inherited citations do not become
direct evidence, and copied inquiries/receipts grant no continuation authority.
The UI offers current and historical result versions, artifact-only drafts, frozen
preview, revision differences and a read-only provenance view with a backstack.

This advances V1-03/04/07 and conjecture C1. Canonical Investigation/context/attempt/
artifact identities remain the source; no competing controller or provenance store
was added. Legacy prompt/context/manifest hashes are unchanged without artifact
inputs. A2 keeps the original frozen inputs. Context-selection comparisons use v2
only when artifacts occur and compare complete frozen input content except rationale.
Review found and fixed a counterexample where unchanged artifact IDs hid a dropped
rejection snapshot. See [D28](../roadmap/DECISIONS.md) and the
[integration evidence](../evidence/ARTIFACT_COMPOSITION_INTEGRATION.md).

## Verification

- Combined `uv run pytest`: **697 passed, 6 skipped** (explicit native opt-ins).
- Combined Bun: **52 tests / 259 assertions**; Svelte **0 errors / 0 warnings**;
  production build passed, including the final mobile wrapping fix.
- Parent independently generated and reopened the A→B→C SQLite demo; reports were
  byte-identical. Independent API acceptance covers wrong owner, forged snapshots,
  citation laundering, unknown fields, limits and no-startup selection/inspection.
- Actual Chromium at 1600×1100 and 390×844 recovered original raw bytes and source
  adoption, created/revised an artifact-only draft, and preserved dirty unsaved
  question/rationale/selection through navigation and reload. Two POSTs only
  (create/revision), zero dispatch; actual mobile width 390 with no horizontal
  overflow in the workbench/dialog/document. Report and screenshots are linked
  from the integration evidence. Parent independently reran this complete browser
  check against integrated main; it passed with the same frozen context IDs.
- `NEMA_NATIVE_GATEWAY_PROBE=1 uv run pytest tests/test_native_gateway_probe.py`:
  **26 passed**, independently reproduced by parent on the integrated tree.

All artifact completions and HTTP gateway actors are authored synthetic fixtures.
No native model call, credential mount, private trace or paid API usage occurred.
No claim of answer-quality, human-speed or complete provider-context improvement.

## Native finding and active work

The shared synthetic gateway **failed caller authentication**: an unexpected MCP
sibling submits identical approved content first and consumes the intended permit;
the relay makes both attempts appear as the same peer. Transport restrictions and
outer namespace controls survive the tested attacks. The mechanism is rejected;
production startup remains closed. See the
[report](../evidence/NATIVE_GATEWAY_ADMISSION_EXPERIMENT.md).

The next independent lane is active in `/tmp/nema-native-account-admission`, base
`711c3d1`. It owns only a new process-boundary probe/tests/evidence. It tests kernel
process/exec restrictions installed before native configuration loads while allowing
native threads. All state is disposable and disconnected; no credentials or models.
This distinguishes the trusted native service from attempted children, not native
service compromise. Check actual worker status before assuming it continues.

## Integration ownership and limits

Accepted source commits: UI `4bc4de4`, `6befeb2`; independent API/demo `61a0740` and
browser acceptance `0de5146`; native gateway `711c3d1`. Parent owns backend,
compatibility tests, review fixes, shared docs and main commit. Worktrees remain
recoverable at `/tmp/nema-artifact-context-ui` and
`/tmp/nema-artifact-context-acceptance`.

Whole investigation catalogs/source owners still load as complete objects; lazy
lineage traversal does not bound a large owner's history transfer. Browser drafts
persist references/rationale locally; modal navigation itself is not persisted.
Unsupported claims remain inspectable. Generic TM/Python host APIs remain trusted,
not arbitrary-caller security boundaries. Native authenticated egress, policy/auth
lifecycle, resource admission and useful live execution remain open.

## Next runnable steps

Assess the active native process experiment and choose the next integrated
capability from PROGRAM. Do not reopen the failed shared-relay mechanism with
another copied token. Preserve this tested composition loop as the baseline.

Reproduce it using a new disposable path:

```sh
uv run python scripts/artifact_composition_demo.py --db /tmp/nema-artifact-next.db
uv run python scripts/artifact_composition_demo.py --db /tmp/nema-artifact-next.db --resume --serve
```

The demo marks synthetic host completions and rejects unrelated resume databases.
Use its report with `scripts/check_artifact_composition_ui.mjs`, Vite and isolated
Chromium as described in the integration evidence. No human decision currently
blocks ordinary development.
