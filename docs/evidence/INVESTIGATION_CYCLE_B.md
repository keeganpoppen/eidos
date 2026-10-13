# Investigation continuations — Cycle B acceptance evidence

**2026-10-13; implementation base `ac2c093`; isolated branch `codex/investigation-continuations`.** Local synthetic evidence for V1-06/07/12. The [contract](../agents/INVESTIGATION_CYCLE_B_CONTRACT.md) gives the operational model and UI integration details. No native model call or rendered UI acceptance is claimed.

## Verified loop

The synthetic app-server receives one native turn only after durable Attempt admission. Its recorded completion becomes a native artifact. The owner then admits a fixed Eidos review under the same Investigation and Attempt. Existing ProcessRuntime commits Discover, saves its waiting checkpoint and exposes the Inquiry. Defer commits in the source domain while the waiting requester remains live. Reopening the SQLite database resumes that same inquiry/checkpoint. Offer binds frozen source records to a source Cut and commits DiscoveryOffer; alternatively DiscoveryRefuse retains the prior Context. AwaitDiscovery incorporates the terminal decision in the requester domain, and ModelProcessFinish produces the outcome. The final artifact links those records and the original native artifact; adoption records a conclusion choice.

The review is synthetic and owner-started because the current native worker explicitly rejects interactive requests. The resulting text appends an evidence-decision receipt; no new native analysis is implied.

## Commands and results

- `uv sync` — passed.
- Baseline `uv run pytest` — 176 passed.
- Final `uv run pytest` — **224 passed**.
- `uv run eidos --help` and `git diff --check` — passed.
- `uv run python scripts/investigation_continuation_demo.py --db /tmp/nema-cycle-b-integrated-20261013.db` — passed.
- Same command with `--resume` — passed; identical process, inquiry, outcome, artifact and native-attempt IDs.

The demonstration reported `counts={investigations:1, attempts:1, nativeTurnStarts:1}`, `sameCheckpointAfterRestart=true`, source kinds `DiscoveryDefer` and `DiscoveryOffer`, and `adoption=adopt`. The temporary SQLite artifact contains synthetic data only and is not committed. The script rejects an existing creation path or an unmarked resume database. It uses the repository's Python app-server fixture, not an account/provider.

## Boundary evidence

| Boundary / counterexample | Test module and observed disposition |
| --- | --- |
| Attempt preparation fails before durable admission | `test_investigation_continuation_failures.py`: transaction rolls back; no worker launch. |
| Claim commits but worker thread cannot start | Same attempt becomes unknown; repeated dispatch never executes; shutdown succeeds. |
| Native incarnation mapping cannot persist | Worker stops before app-server launch. |
| Native output recorded before artifact commit; native failed terminal includes text | Existing `test_investigation_api.py` / `test_investigation_worker.py`: evidence-only recovery, failure remains failure, no resend. |
| Outer continuation/response intent write fails | No semantic work or request receipt survives rollback; exact retry admits once. |
| Inner genesis/preparation/occurrence/checkpoint/outer-pointer failure | Original investigation/continuation recovers; one committed Discover, one pending inquiry. |
| Source prepare/commit/bind/response-link failure | Source transaction rolls back to the frozen admitted response; retry commits one decision. |
| Source committed, requester cannot resume | Response remains addressable; retry incorporates the same occurrence. |
| Inner finish committed, outcome pointer or outer reintegration missing | Existing checkpoint repairs one ModelProcessOutcome and one final artifact. |
| HTTP result lost after reintegration | Same request returns existing completed state and artifact. |
| Concurrent duplicate and competing requests | `test_investigation_continuations_api.py` / `test_investigation_continuation_concurrency.py`: independent SQLite connections retain one process/response/outcome; competing terminal decision conflicts. |
| Stale pending/error arrives after another controller progresses | Completed result stays unchanged; a deferred source's successor authority and response survive stale progress. |
| Pending polling and repeated defer request after terminal decision | No invented requester occurrence; old defer retry returns current state without spending authority again. |
| Guessed/cross-investigation inquiry; copied historical checkpoint | Scoped 404/conflict or strict request rejection; no generic TM route, caller-selected holder/program/executor, or runtime admission from copied descriptions. |
| Native failure/unknown followed by continuation request | Request conflicts; native uncertainty never becomes semantic success. |
| Late native completion/failure callback during review | Existing native artifact and semantic state remain unchanged. |

The runtime tests additionally inspect exact immutable origin/attempt/context data, disclosed Cut provenance, source versus recipient authority domains, ModelProcessOutcome causal sources, and no registered external executors. These are local trusted-host guarantees. They do not prove authenticated remote authority, complete provider context, native interactive resumption, or exactly-once external effects.

## Migration and UI handoff

Tables/fields are additive, legacy schemaVersion 1 rows remain valid, and adoption before review prevents artifact replacement. See the [contract's final compatibility details](../agents/INVESTIGATION_CYCLE_B_CONTRACT.md#final-implementation--compatibility-details). UI changes are deliberately left to the separate implementer: pending question, offer/refuse/defer, source response history, native artifact versus final receipt, and retry/error states have exact wire fields there.
