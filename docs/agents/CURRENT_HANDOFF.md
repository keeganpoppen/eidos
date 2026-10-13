# Current handoff — saved work at scale

**NEMA-SEED-1 · 2026-10-13 · integration base `1ee2821` on main.** The commit
containing this handoff identifies the integration. The continuing mission remains
active; [PROGRAM](PROGRAM.md) owns conjectures and opportunity ordering. The
[previous composition integration](history/ARTIFACT_COMPOSITION_INTEGRATED.md)
retains its evidence. Public CI for `1ee2821` passed
[run 38451787604](https://github.com/keeganpoppen/eidos/actions/runs/38451787604).
Neither this integration nor a green suite completes the mission or V1.

## Delivered loop

Find old work/results among 1,000 owners, preserve selected references across
search/page/reload, inspect C→B→A support, and compose an exact result into new
work while preserving dirty drafts and historical comparison pins. V1-01/03/04/07,
C1/C5. See [measured integration](../evidence/SAVED_WORK_SCALE_INTEGRATION.md).

New read routes under `/api/investigations`: `/catalog` and `/artifacts` return
paged metadata (default20, max40), literal casefolded title search, query/kind-bound
keyset cursors and conditional versions. `/:id/view` omits unchanged owner payloads.
`/:id/artifacts/:artifactId/source` returns an exact artifact/context/attempt and
matching current source review, with optional expected `contextId`. No latest
substitution. Frozen input snapshots retain their historical review decisions.
Canonical rows/unknown fields and legacy envelopes remain intact; the SQLite read
index is replaceable. Transactions bind version and data across independent writers.
Metadata versions never validate source/adoption caches. Read routes grant no action.

Review repaired three concrete failures: blank query parameters disappeared before
validation; unchanged recovery writes needlessly dirtied every projection; a failed
owner selection could leave old work actionable or hide comparison repair controls.
Retries retain the selected owner and original save request identity.

## Verification

- Combined `uv run pytest`: **732 passed, 31 skipped** (explicit native opt-ins).
- Combined Bun: **58 tests / 287 assertions**; Svelte **0 errors / 0 warnings**;
  production build passed, including missing-owner repair controls.
- Independent API acceptance: **11 tests**, including actual HTTP bodies for
  1,000 saved owners, exact historical source ownership, invalid query/cursor
  rejection, external writer refresh and rebuild/reopen. Parent reran on main.
- Parent separately generated/reopened a fresh 1,000-owner SQLite fixture: first
  catalog construction parsed 1,000 owners; the first catalog after reopening
  parsed zero. Other measured identities, support and response sizes were equal.
- HTTP measurements: 20-owner catalog **8,189 bytes**, exact result search **555**,
  unchanged catalog/view **99**, C/B/A exact source **7,278 / 7,372 / 6,501**.
  A's full selected-owner response is **417,697 bytes**. Hot catalogs/unchanged
  views issue zero canonical source SELECTs and parse zero canonical owners.
- Actual Chromium at 1600×1100 and 390×844: search/page/selection, exact support,
  historical pins, dirty draft and preview persist across navigation/reload. The
  server committed a save before its reply was deliberately lost; reload retried
  the identical request and created one owner. Failed selection and missing-owner
  comparison repair passed. Zero full-catalog/legacy-owner GETs, zero dispatch,
  zero uncaught JS errors. Parent independently reran the complete check against
  main and inspected desktop/mobile screenshots: 8 exact source responses and
  8 unchanged owner replies. Evidence links are in the integration report.
- Native process boundary: parent independently reproduced **34 passed** with
  `NEMA_NATIVE_PROCESS_PROBE=1 uv run pytest tests/test_native_process_boundary_probe.py`.

All investigation completions are authored synthetic fixtures. The process probe
performs real native startup/inventory only, with fresh disconnected state and no
model RPC, credentials or upstream. No answer-quality or human-speed claim follows.

## Native finding and active work

The [pre-exec process experiment](../evidence/NATIVE_PROCESS_BOUNDARY_EXPERIMENT.md)
allows native threads/startup while blocking tested child creation and later exec.
An executable MCP cannot start; in-process HTTP MCP still reaches the fake broker.
Process denial therefore does not establish authenticated provider-only egress.
The previous shared-relay caller-authentication mechanism remains rejected; the
production gate is closed.

`/root/native_frontier` in `/tmp/nema-native-account-admission`, base `348f736`, is
now testing guarded real `turn/start` exclusively against a disconnected authored
SSE provider. It owns NEW `probe_native_synthetic_turn.py`, matching tests and
unique evidence. No real model/paid API/subscription calls, credentials, forwarding
or production/profile changes. Native turns and realModelCalls=0 must be reported
separately. `/root/history_ui` is independently reviewing that source, default
checks only. Results are not integrated by this commit; inspect actual status.

## Ownership, limits and next action

Accepted UI commits `ace73f6`, `c1919cf` from `/tmp/nema-saved-work-ui`; acceptance
`cec4526`, `42dad3a` from `/tmp/nema-saved-work-acceptance`; process probe `348f736`.
Parent owns backend/shared docs/main integration. Their worktrees remain recoverable.
All saved-work fixture services have been stopped after parent reproduction.

Initial API recovery still scans canonical owners. Cold/dirty indexing can parse
all changed owners. First/changed owner views remain full; source detail still
parses its full owner internally. UI retains visited owner objects. No aggregate
SQL/memory/latency bound is claimed. Browser arrangements are still local.
Generic TM remains a trusted-host interface, not arbitrary-caller security.

Next coherent product loop: save a reviewed comparison as a named immutable
reference snapshot, recover it in a fresh browser on the same database, inspect
exact historical pins, and explicitly save a changed copy. Store compiled refs,
never recompile old intent against newer results. Parent and UI scouts prefer
create-only snapshots over mutable synchronized workspace heads; independent
acceptance scout is challenging that choice. Freeze the API/selector-version
contract and task ownership before implementation. Native synthetic transport
research continues independently. No human decision blocks ordinary development.

To reproduce the completed scale loop, use a NEW disposable path with
`scripts/saved_work_scale_demo.py --db /tmp/new-saved-work.db --serve`, Vite5173 and
isolated Chromium9222, then `scripts/check_saved_work_ui.mjs` as documented in the
integration evidence. Never use an unrelated/private trace as the synthetic demo.
