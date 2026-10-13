# Four lanes, one recoverable investigation

**2026-10-13 · NEMA-SEED-1 integration · base `ac2c093b675c5765abccaeff33a721f48f4318ce` on main.**
This report describes the integration commit containing it. The destination remains
an authority-local reflective workbench around native Codex, not a replacement loop.

## Inspected inputs and integration judgment

All four actual branch worktrees were clean. Independent read-only scouts inspected
implementation, tests and evidence before bounded implementation lanes began.

| Actual branch/revision | What it demonstrated | Integration decision |
| --- | --- | --- |
| `codex/native-boundary` / `e18322e` | Recorded no-model Codex 0.154.0 preflight/sandbox/MCP probes; independent rerun of 230 Python tests with 2 native skips. No model turn. | Accept transport, admission and recovery changes. Repair unknown message phases and conflicting empty terminal content before admission. |
| `codex/investigation-continuations` / `70e7c73` | 48 focused tests rerun; synthetic native result → local Eidos disclosure → restart → receipt. No UI or native-origin inquiry. | Accept only as a visible owner-started local evidence review, preserving the original answer. |
| `codex/context-manifests` / `26a606b` | 42 focused tests rerun; immutable ingredients, pins, temporal observations. No dispatch/UI consumer. | Accept with a real investigation adapter and atomic pre-send pin, not as a standalone subsystem. |
| `codex/reflective-workbench` / `0cca35c` | 14 frontend tests and check/build rerun; screenshots inspected; reference-only composition. | Accept comparison/rendering, but add exact artifact-version bindings before joining the continuation lane. |

The integrator imported reviewed content into main as one tested integration, leaving
the source branches/worktrees unchanged. Branch handoffs are historical; their test
counts do not describe the combined tree. The [shared contract](../agents/INVESTIGATION_INTEGRATION_CONTRACT.md)
now governs the joined seams.

## What materially changed

A saved investigation now owns a reviewable ingredient manifest. Its native attempt
pins a runtime projection before launch in the same transaction as admission. Recorded
native traffic becomes a separate observation with exact source/RPC correlation;
provider context stays unknown. Preview, native input, offered evidence and inner Eidos
Context retain different identities and meanings.

The owner can preserve the native answer, open a local disclosure question, defer it,
reload, offer or refuse evidence, and adopt the resulting decision receipt. Existing
ProcessRuntime carries the local continuation; no second native turn is sent. A comparison
can retain the exact original artifact while displaying the final receipt beside it.
Changing layout, inspecting support and undoing arrangements preserve those bindings.

The continuation is deliberately modest: its fixed Closure records a decision. It
does not synthesize a better model answer or establish specialist-originated V1-06.
This integration does not claim all V1 gates pass.

## Verification on the combined implementation

- `uv sync` — passed.
- `uv run pytest` — **361 passed, 2 skipped**. Skips are explicit opt-in native probes.
- `uv run eidos --help` — passed.
- `cd ui && bun install && bun run check && bun test tests && bun run build` — dependencies
  installed; **0 errors / 0 warnings**, **17 tests / 61 assertions passed**, production build passed.
- `uv run python scripts/investigation_continuation_demo.py --db /tmp/nema-integration-20261013-01.db`
  and the same command with `--resume` — passed. Both report one investigation, one
  attempt, one synthetic native turn, identical checkpoint/outcome/artifact/pin identities,
  two app-server correlations, and separate offered manifest. Provider context is unknown.
- `NEMA_UI_EVIDENCE_PREFIX=docs/evidence/integrated node scripts/check_investigation_ui.mjs`
  — passed in isolated headless Chromium with the synthetic API/Vite. Two full runs,
  with the second after visual repairs. No account/model call.
- `git diff --check` — passed. Seed-context/navigation checks are part of pytest.

The browser scenario selected disjoint source records 12/38 plus record 72 from a
second thread; excluded distractors; saved two revisions; dispatched the fixture;
reloaded; returned to exact support; compared saved work/contexts; reviewed, cancelled,
applied and undid arrangements; used keyboard support navigation; exposed unknown
context; then deferred/reloaded/offered/adopted a local review without replacing its
native baseline. The script checks reference-only composition storage and unmodified
authoritative work during presentation operations.

The 1,200-turn history, competing patch and unsupported citation are explicitly
browser-only synthetic rendering fixtures. They establish bounded default rendering,
not backend scalability or a second model's disagreement. Checks include 900px/390px
page wrapping and the final comparison's individual aperture widths.

## Rendered evidence

The integrator and UI reviewer inspected the screenshots. Review found and fixed
an inner horizontal scrollbar and ambiguous same-title artifact captions. The expanded
provenance capture verifies visible gaps rather than merely text inside collapsed details.

| Capture | Scope |
| --- | --- |
| [Saved comparison](integrated-server-comparison.png) | Two server-derived synthetic investigations and retained frozen evidence. |
| [Context changes](integrated-context-diff.png) | Exact question, range, rationale and source-hash difference. |
| [Context provenance](integrated-context-provenance.png) | Selected/projected ingredients, provider/native gaps and immutable request pin. The adjacent history retains the labelled browser stress fixture. |
| [Pending local review](integrated-local-review.png) | Same inquiry after deferral/reload, native completed versus local pending, visible decisions. |
| [Original answer and receipt](integrated-review-comparison.png) | Explicitly pinned native baseline and separately identified local review receipt. |
| [Presentation fixture](integrated-workbench.png) | Labelled competing patch and exact support; not another observed model outcome. |

Original branch screenshots and Cycle A evidence remain preserved alongside these captures.

## Independent attacks and repairs

- Native recovery accepted unfamiliar phases and ignored empty repeated terminal
  text before checking identity. Both repaired; conflicts/unknown phases remain unknown,
  including changed item type and non-string output. Equivalent repeats remain recoverable.
- New manifest correlation initially accepted an unsolicited same-ID reply preceding
  its request. Repaired with sequence order and exact RPC ID type/value; Boolean IDs
  cannot impersonate integer IDs. Multiple turn requests or mismatched pinned input
  now report an ambiguity error without rewriting earlier evidence.
- An independent two-controller/two-connection dispatch race produced one attempt,
  one native fixture turn, one request pin and two observations; recovery sent nothing.
- Abrupt `os._exit(73)` before claim COMMIT reopened as draft with zero pins/sends.
  Separate abrupt exits inside source transaction, after inner outcome commit and
  before reintegration each recovered one offer, one outcome and one synthetic turn.
- Committed native output with failed derived correlation preserves the native result;
  restart repairs the projection without repinning or resending. Offered evidence has
  a separate manifest. Old index hydration cannot alter frozen historical ingredients.
- Guessed/cross-investigation inquiries/contexts, copied public continuation descriptions,
  changed request IDs, competing terminal decisions and late native callbacks retain
  their rejection/idempotency boundaries. No generic authority or executor route was added.

Reproducible regressions are in `test_investigation_context_integration.py`, the
continuation failure/concurrency suites, native transport/worker suites, and frontend
comparison/request tests. Abrupt-exit scratch databases were synthetic and stayed under
`/tmp`; they are supplementary local observations, not durable public proof artifacts.

## Honest limits and next gate

No fresh native probe or model turn was performed in this integration session. The
explicit question authorizing disposable **no-model** probes was unanswered when
this report was written. The imported [native report](NATIVE_BOUNDARY.md) and
[matrix](NATIVE_BOUNDARY_0_154_0.json) remain historical branch evidence.

Native startup integrations may act before inventory refusal; the temporary cwd and
read-only native policy do not contain arbitrary ambient MCP processes. No complete
provider/instruction/skill capture, account entitlement, hidden-stack resumption,
native filesystem fork, exactly-once external effects, token/cost cap, authenticated
multiuser boundary, or measured human speed improvement is claimed.

The remaining decisive gate is one explicitly authorized, subscription-backed native
run of this same synthetic packet in an audited native configuration. Start with the
bounded no-model preflight in CURRENT_HANDOFF; retain refusals as evidence and do not
weaken the admission gate to obtain a green result. Further ontology is lower priority.
