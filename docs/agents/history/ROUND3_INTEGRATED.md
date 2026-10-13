# Current handoff — Round 3 integrated investigation

**NEMA-SEED-1 · 2026-10-13 · base `50d1bc91870b9118a84706606d6a06008dffcdf7`,
clean main.** The commit containing this handoff is the combined implementation.
The [previous handoff](INVESTIGATION_CYCLE_B_INTEGRATED.md) remains archived.

## Delivered loop and judgment

Two-thread evidence → immutable context/pin → terminal specialist inquiry →
defer/reload/offer or refusal/cancellation → separate recipient incorporation →
review expanded packet → explicitly admit A2 → retain A1, receipt and A2 → compare
saved inputs → evaluate selection/bytes → preserve adoption/rejection/rollback.
The actual UI now operates on this saved lifecycle. The original pre-send native
admission remains intact; recovery and retries never create another send.

All execution acceptance was synthetic. Default live startup is unavailable:
account-backed cloud configuration remains uncontained. No native probe or model
turn ran in this integration. Previous no-model permission is not permission for
model turns. Native interactive requests are observed but unsupported; terminal
JSON inquiry uses a new admitted attempt, never a resumed hidden native stack.

This materially advances V1-03/04/06/07/08/09/10/11/12 while leaving real-native
V1-05 and complete V1 acceptance open. It adds no ontology or TM/runtime rewrite.

## Accepted branches and integration changes

A `18f25c1` native profile/event evidence; B `f3d7228` durable terminal inquiry and
follow-up; C `c8b701e` counterfactual records/evaluator; D `6e491b5` reflective views.
Source branches/worktrees remain unchanged. Details and deferred claims are in
[the integration report](../../evidence/INTEGRATION_ROUND3.md) and
[shared contract/task packet](../ROUND3_INTEGRATION.md).

- Canonical `InvestigationStore` still owns contexts, attempts, artifacts and
  adoption. B retains exact attempt/artifact history and private successor admission.
- C baseline lookup now resolves A1 and historical receipts after A2. The new
  `investigation_experiments.py` adapter exposes only bounded owner-scoped creation,
  measurement and review/rollback over C's existing immutable store.
- Native recovery rejects completion-shaped RPC requests. Historical host profile
  evidence supplies `executionEvidence`; model text and later metadata cannot upgrade
  it. Missing legacy labels stay unknown without changing old artifact IDs.
- UI preserves A1/offered/A2 input and original/receipt/result identities, historical
  request pins, review-before-follow-up, retry IDs and visible capability refusal.
  Experiments persist on the server; arrangements remain reference-only browser data.
- Legacy HTTP chat creation/messages/model indexing are blocked until separately
  authorized and admitted, preventing a resource-gate bypass outside investigations.
  Direct Python host APIs remain privileged; this is not arbitrary-caller security.

Persistence is additive in the same trace SQLite database: B's native-continuation
admission and C's `exp_records` beside existing investigation, manifest and TM tables.
Back up the whole database. Historical packets/pins/artifacts are not relabelled.
No credentials, personal trace, auth directory or private export was committed.

## Verification and review

- `uv sync`; `uv run eidos --help`; `git diff --check`: passed.
- Full `uv run pytest`: **607 passed, 4 skipped** (explicit native probe opt-ins).
- `cd ui && bun install && bun test tests && bun run check && bun run build`:
  **38 tests / 193 assertions**, **0 errors / 0 warnings**, production build passed.
- `round3_demo.py` fresh/reopen: identical reports, two fixture sends/pins, one
  inquiry, separate source/recipient outcomes, three artifact versions, preserved
  rejection/rollback, no native model calls. [Report](../../evidence/ROUND3_DEMONSTRATION.json).
- C's six-case demo and reopen passed; three cases improve fixture coverage, all
  six meet nonregression checks. Three unchanged guardrails fail the stricter
  improvement predicate; relevant over-budget evidence remains omitted.
- Extended Chromium acceptance passed against actual synthetic API state with the
  meaningful missing acknowledgement/completion record; 16 captures regenerated.
  [Browser report](../../evidence/ROUND3_UI_ACCEPTANCE.json) and
  [joined evidence chain](../../evidence/round3-integrated-evidence-chain.png).
- Independent native, crash/authority and UI reviews ran. Actual `os._exit` and
  multi-process races verify atomic A2 pin/admission, unknown post-commit recovery,
  and disclosure-before-incorporation. Generic TM escalation remains a documented
  privileged-host counterexample; it is not exposed through owner routes.

Packet measurements are real measurements of synthetic saved inputs. The observed
2→3 records and 3,080→6,535 prompt bytes are not evidence of better model reasoning.
The six-case annotation evaluator measures fixture grounding only; real-world
quality, cost and human usability improvements remain unmeasured. Scripted browser
owner actions are not the real owner's endorsement of a context change.

## Limits and next runnable action

One specialist inquiry plus one explicit follow-up is supported. Unknown outcomes
stay visible. No full provider context, live entitlement, cloud startup containment,
interactive reply delivery, token/cost cap, universal workspace isolation or
exactly-once external effect is established. Trusted loopback is not authenticated
multiuser isolation. Nested scrolling, unbounded server history retrieval and
browser-local arrangements remain product debt.

The next consequential task is supported pre-launch containment/admission for all
native configuration sources; then separately authorized subscription-backed smoke.
Do not weaken the gate, wrap the binary to bypass it, copy credentials, rewrite
Codex state or substitute a paid API to obtain a green result.

Reproduce the integrated synthetic loop using a fresh path:

```bash
uv run python scripts/round3_demo.py --db /tmp/nema-round3-next.db
uv run python scripts/round3_demo.py --db /tmp/nema-round3-next.db --resume
```

For actual UI acceptance, run `scripts/investigation_demo.py --db <fresh-path> --serve`,
Vite on 5173, and isolated Chromium with remote debugging on 9222, then:

```bash
NEMA_UI_EVIDENCE_PREFIX=docs/evidence/round3 node scripts/check_investigation_ui.mjs
```

All three services were stopped and ports verified closed. All review/implementation
agents completed; no background, scheduled work or live resource authorization is implied.
