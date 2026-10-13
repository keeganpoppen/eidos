# Round 3 integration contract and task packet

Base: `50d1bc91870b9118a84706606d6a06008dffcdf7`; main integrator owns the
combined API, canonical docs and final commit. This amendment supersedes the
Cycle B contract's deferred specialist/alternative seams, preserving its identities
and pre-send admission. It does not revise the language or expose generic TM.

## One user-visible lifecycle

Select frozen evidence from two threads → inspect context → admit an attempt →
receive a terminal evidence inquiry → defer, offer, refuse or cancel → incorporate
the source decision locally → inspect a separately frozen follow-up → explicitly
admit one new attempt → retain original output, receipt and returned artifact →
compare saved context versions → evaluate selection/size → record adoption,
rejection or rollback. All execution in this integration acceptance is synthetic.
Live startup and interactive native replies remain unavailable.

| Identity | Canonical meaning |
| --- | --- |
| Investigation | The existing `InvestigationStore` record. No replacement controller. |
| Attempt A1/A2 | One native-operation admission each; pin, request identity, history and private follow-up admission commit before launch. Retry/recovery is never admission of another send. |
| Eidos continuation | A host-admitted `ProcessRuntime` disclosure/incorporation process. It is not a native suspended stack. |
| Original/offered/expanded context | Separate immutable packets and manifests. An offer never rewrites A1's input; A2 pins its own expanded packet. |
| Inquiry/response | Exact continuation-owned inquiry and request-ID-bound source decisions. A source occurrence is distinct from recipient incorporation. |
| Artifact | A1 output, Eidos receipt and A2 output retain distinct IDs. Exact history lookup includes `attemptHistory` and `artifactHistory`. |
| Execution evidence | `synthetic`, `native-observed` or `unverified`, derived from preceding trusted-host profile evidence. Text and child-supplied metadata cannot upgrade it. Missing legacy attribution remains unknown. |
| Experiment | Existing `ExperimentStore` reference graph over exact baseline/artifact/attempt/context, alternative and frozen horizon. Local evaluation reservations confer no native authority. |
| Evaluation | Either C's structured synthetic fixture checks or the workbench's saved-packet measurements. Neither evaluates natural-language reasoning. |
| Review/adoption | Explicit bounded owner-service decision, separate from evaluation. No configuration, prompt policy, skill, authority or native execution is activated. |
| Arrangement | Browser reference bindings and focus only; not investigation or decision state. |

## Exposed seams

B's strict final JSON protocol uses `mode: terminal-needs-evidence`. Only recorded
final output belonging to the exact admitted request can become a specialist
inquiry. Native `requestUserInput` is observed but unsupported; the worker refuses
such requests. Terminal JSON does not claim to be an interactive native request.
One inquiry and one explicit follow-up are supported. A2 needing more evidence
remains visible and unadoptable with an explicit bounded-cycle error.

The immutable request pin and private native-continuation ledger remain the only
follow-up admission path. Public JSON copies, Names, holder strings, model output
and experiment records cannot create successor authority. Generic TM commit still
accepts arbitrary grants from trusted Python callers: it remains privileged,
unexposed and unsuitable as an arbitrary-caller security boundary.

`GET /api/investigations/capabilities` is a read-only policy projection, not a
native probe. Default live dispatch is rejected before attempt admission. It
requires separate resource authorization and an admitted native profile; neither
is supplied by the earlier no-model authorization. Legacy HTTP chat creation,
message sending and model-backed indexing are also closed so they cannot bypass
this gate. Synthetic investigation availability does not grant legacy live access.

The bounded experiment adapter exposes:

- `GET/POST /api/investigations/:id/experiments`; creation accepts only request ID,
  exact baseline artifact/context, alternative context and rationale.
- `GET /api/investigations/:id/experiments/:comparisonId`.
- `POST .../:comparisonId/review` with request ID, adopt/reject and rationale.
- `POST .../:comparisonId/rollback` with request ID and rationale.

Creation uses one transaction and reuses the existing immutable graph. It fixes
the same question, records two local interpretation outcomes and measures record
retention and UTF-8 prompt bytes. It does not execute or evaluate the baseline's
answer. Follow-up packets also include prior output, notes and instructions;
this is not an isolated causal comparison. Clients cannot supply evaluators,
entailment labels, output grants, executors, actors or arbitrary native handles.
Reads are scoped to the investigation; same-ID altered writes conflict.

## Ownership, tests and integration point

Read-only scouts inspected actual A/B/C/D commits before implementation. The
integrator selectively imported disjoint files; source worktrees remain unchanged.
Shared main ownership during integration was explicit:

- Integrator: API, investigation compatibility, experiment adapter/tests, joined
  demo, canonical context and final commit.
- UI lane: `ui/` and Chromium harness; implements B/C contracts and tests rendered
  behavior against saved server state.
- Independent native reviewer: worker recovery/provenance fixes and adversarial
  tests; subsequently independent read-only screenshots/Chromium usability review.
- Independent inquiry reviewer: subprocess-death/concurrent-request/authority
  tests; review of the experiment admission path.

No worker changed `trusted.py`; no new ontology or universal scheduler was added.
Acceptance commands, artifacts, rejected/deferred work and remaining obligations
are in [the integration report](../evidence/INTEGRATION_ROUND3.md). The next session
starts from [CURRENT_HANDOFF](CURRENT_HANDOFF.md), not the branch handoffs.
