# Current handoff — four-lane investigation integration

**NEMA-SEED-1 · 2026-10-13 · base `ac2c093b675c5765abccaeff33a721f48f4318ce`, clean main at start.**
This describes the integration commit containing it. The previous
[Cycle A handoff](history/INVESTIGATION_CYCLE_A.md) and
[founding checkpoint](history/NEMA-SEED-1.md) remain preserved.

## Judgment and delivered loop

Nema remains an authority-local personal reflective workbench around native Codex;
Eidos makes its local continuations inspectable. This cycle integrates the four
actual branches into one work loop: two-thread packet → immutable ingredient
projection → atomic native attempt/pin → recorded outcome → local disclosure
question/defer/reload/offer or refusal → compare original answer and decision
receipt → adopt. The calculus now contributes to a visible recovery step.

The review is owner-started and uses a fixed Eidos Closure. It is **not** a question
emitted by Codex or a new model synthesis. This advances V1-03/04/07/08/09/10/12 and
a local disclosure subset of V1-06, not the complete V1 destination.

## Exact integration and migration

Reviewed source revisions: native-boundary `e18322e`, investigation-continuations
`70e7c73`, context-manifests `26a606b`, reflective-workbench `0cca35c`. All four were
clean, independently reviewed and selectively joined with new seam work. Source
branches remain unchanged; main contains one tested integration commit.

- `codex.py` and `investigation_worker.py`: cancellable native writes/deadlines/EOF,
  returned policy and enabled/unresolved MCP checks, conservative recovery. Additional
  review repairs unknown output phases and conflicting empty/type-changed completions.
- `context_manifest.py` plus new `investigation_context.py`: immutable projection of
  the existing frozen packet; shared worker policy; request pin in the claim transaction;
  evidence-only correlation. Reconciliation enforces source, exact input, request order,
  ID type/value and known native coordinates. An error cannot invalidate a native result.
- `investigation.py`/`api.py`: canonical investigation/context/attempt IDs, scoped
  read-only manifest/lineage endpoints, separately repairable observation errors.
  No second mutable current-context representation or generic manifest mutation API.
- `investigation_continuations.py`/`investigation_runtime.py`: admitted local review,
  existing ProcessRuntime/Discovery, durable decisions and reintegration. Native status
  and terminal guards remain on the native attempt. Offered packets have their own
  manifests and never repin the native request. Copied descriptions lack admission.
- `ui/src/`: context provenance, pending review with offer/refuse/defer/retry/resume,
  original native answer retained, exact artifact-version comparison, source focus,
  native patch/diff rendering, browser arrangement review/apply/undo and bounded DOM.
- `scripts/investigation_continuation_demo.py`, expanded Chromium harness and regression
  suites exercise the joined path. Raw history and unknown fields remain untouched.

Persistence is additive in the existing trace SQLite database: `cm_*`, investigation
runtime linkage, and existing TM tables beside trace/investigation tables. Back up the
whole database. Existing packets/artifacts keep their IDs. Missing legacy manifests/pins
remain unknown; old attempted work never gains an invented pre-send pin. Unattempted
legacy packets may receive a derived projection at claim. Old browser result arrangements
without artifact IDs require an explicit reviewed binding, never silent substitution.

## Evidence and independent review

Full detail, screenshots and exact branch judgments:
[INTEGRATION_CYCLE_B](../evidence/INTEGRATION_CYCLE_B.md).

- `uv sync`; `uv run pytest`: **361 passed, 2 skipped** (explicit native probes).
- `uv run eidos --help`; `git diff --check`: passed.
- `cd ui && bun install && bun run check && bun test tests && bun run build`:
  **0 errors / 0 warnings**, **17 tests / 61 assertions**, production build passed.
- Synthetic end-to-end demo at `/tmp/nema-integration-20261013-01.db`, then `--resume`:
  one native fixture turn, same attempt/checkpoint/outcome/artifact/pin; two recorded
  correlations; separate offered manifest; provider context unknown.
- Chromium harness passed twice, with final inspected evidence under
  `docs/evidence/integrated-*.png`: two-thread selection, revisions, delegation fixture,
  support navigation, context gaps, comparison, defer/reload/offer/adoption and exact
  native baseline retention. Labelled 1,200-turn/patch browser fixtures test rendering,
  not backend scalability or another model's reasoning.
- Independent reviewers attacked two-controller dispatch, actual abrupt process death,
  transaction rollback, copied authority, late callbacks and context misattribution.
  An unsolicited pre-request reply was initially miscorrelated; repaired and tested,
  along with multi-request ambiguity and Boolean/integer RPC-ID confusion.

No fresh native probe/model call occurred. The explicit authorization question for
isolated no-model probes remains unanswered as of this checkpoint. Imported Codex
0.154.0 probe artifacts are historical branch evidence. No personal history, credentials,
account data, or auth directory entered this repository.

## Accepted, rejected, still open

Accepted: existing workflow identities; immutable attributable context projections;
transactional pre-send pin; original-versus-receipt artifact versions; honest local
review; reference-only UI arrangements. Rejected: competing context controllers,
latest-result rebinding, automatic external replay from checkpoint/pin, and interpreting
local review or branch test counts as completed native/V1 proof. See
[shared contract](INVESTIGATION_INTEGRATION_CONTRACT.md) and D03/D13/D15/D21 in
[DECISIONS](../roadmap/DECISIONS.md).

Still unverified: subscription-backed model acceptance, specialist-originated inquiries,
complete instruction/skill/provider capture, full native isolation, cost/resource caps,
exactly-once external effects, durable cross-device arrangements, linked alternative
lineage, bounded server retrieval and a measured improvement cycle. Ambient MCP startup
may act **before** inventory refusal; read-only policy/temporary cwd do not contain it.
The generic outer Elaborate correlation problem is not universally solved by this review.

## Ownership and one next action

One integrator owns main. Read-only scouts became disjoint native-recovery and UI lanes
in `/tmp/nema-native-recovery-integration` and `/tmp/nema-integration-ui`; their reviewed
files were imported. Independent reviews finished. Source branch worktrees under
`/home/elkeegano.guest/eidos-codex/` were not modified. Acceptance services are stopped
before session end; no scheduled/background work is implied.

**Strongest next action:** verify this same packet against native Codex under explicit
scope, beginning with the audited no-model gate. Once explicitly authorized, run:

```bash
NEMA_NATIVE_PROBE=1 uv run pytest tests/test_native_boundary_probe.py tests/test_native_mcp_probe.py
```

Acceptance: record the installed version and actual admission result, preserve any
refusal, and do not weaken policy to make it pass. A subscription-backed model turn
then needs its own explicit account/resource authorization; no paid API substitution
or user configuration edits. This native evidence gap is more consequential than
adding another context or continuation abstraction. The delivered synthetic workflow
is fully reproducible without that authorization using the integration report.
