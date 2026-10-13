# Round 3: one inquiry, follow-up and improvement workflow

**2026-10-13 · NEMA-SEED-1 · implementation base
`50d1bc91870b9118a84706606d6a06008dffcdf7` on clean main.** This report describes
the single integration commit containing it. Earlier branch reports retain their
own revisions and evidence scope. Source branches/worktrees were not modified.

## Actual branches and integration judgments

| Branch / inspected commit | Accepted | Rejected or deferred interpretation |
| --- | --- | --- |
| A: `codex/native-specialist-v2` / `18f25c1` | Pre-launch configuration profile, conservative startup refusal, versioned evidence adapter, typed RPC identity, interaction/terminal recovery tests, sanitized prior no-model observations. | No claim of live readiness, account entitlement, complete containment or interactive replies. Profile `live_admitted` remains false; the unused account-type validator must be wired before any future live enablement. |
| B: `codex/specialist-initiated-inquiry` / `f3d7228` | Strict recorded terminal inquiry → existing Eidos process → source offer/refuse/defer/cancel → local incorporation → immutable expanded context → explicitly admitted A2 with history. | No hidden native continuation, automatic retry, third attempt, or receipt masquerading as a new model answer. |
| C: `codex/counterfactual-laboratory` / `c8b701e` | Immutable reference-based experiment graph, deterministic synthetic evaluator, bounded selector, six-case demonstration, explicit review/adoption/rejection/rollback. | No second native ledger/dispatcher, automatic policy activation, answer-prose entailment score, or real-model improvement claim. Fixed historical baseline lookup before joining B. |
| D: `codex/reflective-experiment-workbench` / `6e491b5` | Evidence-chain views, exact bindings/focus, inspectable arrangement proposal, optional authored presentation fixture and tests. | Its original browser fixtures were insufficient as the active workflow. Integrated B/C server-backed state, durable decision controls, real history resolution and resource gates. Authored fixture previews remain explicitly separate. |

The [contract and ownership packet](../agents/ROUND3_INTEGRATION.md) reconciles
all seven requested identity seams. There is one canonical investigation and
context lifecycle. Experiment entries are immutable references/local evaluation
records and grant no execution authority. The language, TM kernel and generic
ProcessRuntime were not rewritten.

## Delivered experience

An owner can select disjoint evidence from two threads, inspect the exact packet,
and run the explicitly synthetic acceptance worker. A meaningful missing-evidence
question appears from its recorded terminal protocol result. It survives deferral
and reload. Offering the requested acknowledgement/completion record commits source
disclosure and recipient incorporation separately. Refusal and cancellation retain
different meanings. Neither disclosure nor recovery sends another turn.

The workbench shows the expanded packet before a separate A2 admission. A1's exact
artifact/input/pin, local Eidos receipt and A2's result/input/pin remain inspectable.
Comparison resolves those historical identities after rollover and reload. Layout
changes never follow a newer result silently or mutate investigation authority.

The owner can then review a saved alternative input, persist a measured comparison,
record adoption or rejection, and roll back a decision. Evaluation alone confers
no adoption authority. The decision does not activate configuration or send work.
The UI also retains the optional authored presentation experiment, labelled as a
browser preview rather than durable owner adoption.

Live native startup is explicitly unavailable. The API rejects new live attempts
before claim and reports why; already admitted requests can still be inspected and
retried without a resend. Legacy HTTP chat creation/messages/model-backed indexing
cannot bypass this resource gate. No new no-model probe or real model smoke ran.
The earlier owner's no-model authorization was not interpreted as model authorization.

## Verification on the combined tree

- `uv sync`; `uv run eidos --help`: passed.
- `uv run pytest`: **607 passed, 4 skipped**. All four skips are explicitly opt-in
  native/no-model probes; none were run during this integration.
- `cd ui && bun install && bun test tests && bun run check && bun run build`:
  **38 tests, 193 assertions; zero Svelte errors/warnings; production build passed**.
- `uv run python scripts/round3_demo.py --db /tmp/nema-round3-final-demo.db`, then
  the same command with `--resume`: identical reports, two separately admitted
  fixture turns/pins, one inquiry, distinct original/receipt/follow-up artifacts,
  preserved rollback/rejection and zero native model calls. Partial demos are not
  silently replayed. Automated report decisions use `reviewKind: synthetic`.
- `scripts/counterfactual_demo.py` fresh and `--resume`: identical results apart
  from mode; six fixed synthetic cases, no native sends, addressable rejected work.
- Extended `scripts/check_investigation_ui.mjs`: actual isolated Chromium passed
  against the saved synthetic backend, including meaningful extra source, deferral,
  reload, offer, explicit A2, evaluation, adopt/reload/rollback/reject and retained
  baseline. [Machine-readable browser report](ROUND3_UI_ACCEPTANCE.json).
- `git diff --check` and seed/context link checks: passed.

The browser's scripted owner actions exercise the human-facing API; they are not
evidence that the real owner endorsed a context change. UI arrangements and the
1,200-turn stress/competing-patch fixtures remain browser-only synthetic evidence.
Bounded DOM rendering does not establish bounded server retrieval or measured
human reorientation speed.

## What improved, and what was only proposed

| Evidence | Established scope | Not established |
| --- | --- | --- |
| Joined workflow/UI | Durable inquiry and response, no send on disclosure/retry, preserved A1/receipt/A2 and exact contexts, inspectable durable alternative decisions. | Real specialist behavior or a human usability benchmark. |
| Saved-packet evaluator | Exact record/byte differences, retained/omitted evidence and input bound. Browser fixture: 2 → 3 records and 3,080 → 6,535 UTF-8 prompt bytes. | Better answer quality, lower cost or causal effect of selection alone. Expanded prompts also add prior output, notes and instructions. |
| C's deterministic selector | Discovery and structural held-out fixture coverage improve 1/2 → 2/2, with 773/767 additional canonical prompt bytes. Discovery, heldout and cycle improve; all six cases meet nonregression checks. | Real-world generalization or improved model reasoning. Three unchanged guardrail cases do not pass the stricter improvement predicate; the budget case still omits relevant evidence. |
| Context/presentation proposal | Reviewable candidate and explicit adoption/rejection/rollback records; browser presentation preview can be undone. | Automatically activated selector, skill, policy or native authority. |

See [the joined synthetic report](ROUND3_DEMONSTRATION.json) and
[the original counterfactual report](COUNTERFACTUAL_LABORATORY.md). Scores grade
structured fixture annotations only; retained baseline prose is ungraded.

## Independent attacks, repairs and presentation review

- Native reviewer independently exercised containment/provenance. Repaired an
  RPC request envelope falsely admissible as an ordinary completion notification.
  Added host-only historical execution classification; child metadata, copied text,
  later metadata and a changed current worker cannot upgrade old output.
- Inquiry reviewer used **actual `os._exit` subprocess deaths** before/after A2
  commit and after source disclosure. A2 pin, private admission, attempt history
  and current context commit together. Post-commit recovery retains one unknown
  attempt and sends nothing. Separate processes racing exact/competing requests
  admit one successor. Source disclosure can exist before recipient incorporation.
- Authority review rejects HTTP output grants/holders/executors/checkpoints,
  copied public continuation state and cross-investigation identities. The test
  demonstrating arbitrary successors through privileged generic TM is retained:
  the trusted Python API is **not** an arbitrary-caller security boundary.
- Experiment tests cover atomic rollback, exact retry, two connections racing
  creation/review, owned identities, same-question constraint and history lookup
  after A2. Experiments cannot choose a native executor or synthetic entailment
  evaluator through request fields. Adoption/rollback do not alter canonical work.
- Independent screenshot and read-only Chromium review at 1600px/390px found no
  horizontal overflow in inspected canonical views. Repaired misleading native
  labels, stale fixture-endpoint wording, historical context/pin resolution,
  pending-chain binding mismatch, checkbox alignment and overwhelming visible IDs.
  Added active-section jump controls. Nested scrolling remains usability debt.

Regression files: `test_round3_recovery.py`, `test_round3_native_review.py`,
`test_round3_experiments_api.py`, `test_round3_demo.py`, inherited inquiry/native/
counterfactual suites and the frontend binding/retry tests. These are evidence
for specific local seams, not exactly-once external effects or multiuser security.

## Rendered artifacts

- [Durable specialist inquiry](round3-specialist-inquiry.png).
- [Unsent expanded input and separate follow-up admission](round3-followup-admission.png).
- [Saved measured alternative](round3-evaluated-alternative.png).
- [Preserved decisions](round3-preserved-decisions.png).
- [Original evidence, offered packet and A2 result](round3-integrated-evidence-chain.png).
- [Context provenance](round3-context-provenance.png) and
  [earlier local review chain](round3-recorded-evidence-chain.png).

All captures use synthetic data. Original branch screenshots/reports remain
historical evidence, not fresh observations of this integration.

## Remaining gate and next action

The next consequential work is a supported pre-launch admission strategy for
account-backed native configuration, including cloud/managed sources, followed
by independently authorized subscription-backed smoke testing. Do not bypass the
profile with a renamed executable/wrapper or substitute paid API calls. Real
interactive response delivery, account entitlement, full provider context,
resource/cost bounds, cancellation of remote effects, workspace isolation and
exactly-once external execution remain unverified.

The current prototype is a trusted loopback owner service, not authenticated
multiuser security. One inquiry plus one explicit follow-up is the bound. Browser
arrangements remain local. Reproduce the joined synthetic loop using `round3_demo.py`
or the Chromium commands in [CURRENT_HANDOFF](../agents/CURRENT_HANDOFF.md) while
working on that gate. No background or scheduled work is implied.
