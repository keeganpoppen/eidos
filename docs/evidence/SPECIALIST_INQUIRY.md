# Specialist inquiry acceptance evidence

2026-10-13; implementation base `50d1bc91870b9118a84706606d6a06008dffcdf7`;
branch `codex/specialist-initiated-inquiry`. The commit containing this report is
the delivered revision. All traces are synthetic. No native model call, native
probe, private history, credentials or external service was used.

## Reproduce

```bash
uv sync
uv run pytest
uv run eidos --help
git diff --check
```

Final verification: **415 passed, 2 skipped**. The skipped tests are explicitly
opt-in native probes. CLI help and diff whitespace validation passed. The three
new suites contribute **54 passing tests**. UI code was not changed or rendered;
this is Python/API acceptance, not UI or subscription-backed native acceptance.
A verification run during handoff drafting found the then-missing report link;
the report was completed and the final suite rerun.

## Tested user loop

`test_specialist_defer_reload_disclose_continue_and_adopt_same_investigation`
records a synthetic native specialist's explicit final missing-evidence question
and terminal outcome. The controller binds its cause to the original frozen input,
request pin, attempt, output event and immutable result, then starts the existing
Eidos Discover/AwaitDiscovery program. The owner defers, closes/reopens the API,
offers a newly recorded source range, and resumes the same outer investigation.
The old context does not gain the new record; the offered context and follow-up
preview do. Source disclosure and recipient incorporation are distinct occurrences.
A separate `/continue` request admits A2 and a new pin before launch. The returned
artifact carries causal lineage; adoption retains A1 and its unmodified result.

## Failure and boundary matrix

| Seam | Evidence |
| --- | --- |
| Native question admission before/after durable save; first checkpoint | `test_native_question_admission_and_checkpoint_recovery_use_same_recorded_turn` |
| New attempt before claim commit, after claim/before launch, before/after native request, after native result/before local completion | `test_new_native_attempt_interruptions_never_resend_unknown_work` |
| Source preparation, TM commit, requester incorporation, outer reintegration | `test_specialist_response_crash_recovery_preserves_one_causal_progression` plus unchanged Cycle B failure suites |
| Source committed but requester realization failed | `test_source_commit_and_failed_recipient_realization_remain_distinct` |
| Duplicate question recovery and concurrent new-attempt requests | `test_independent_duplicate_recovery_admits_one_specialist_inquiry`, `test_concurrent_continuation_requests_admit_exactly_one_new_attempt` |
| Cross-investigation replay, unknown fields/authority injection, stale callbacks | `test_response_replay_and_copied_names_cannot_change_scope_or_advance`, `test_stale_first_attempt_callbacks_cannot_mutate_running_second_attempt` |
| Cancel versus offer/refuse, admitted response before runtime, historical revival | `test_specialist_inquiry_boundaries.py`, `test_cancel_revokes_host_admission_and_retries_do_not_revive_it` |
| Copied completed JSON at startup, mismatched source/thread/turn/context, malformed terminal protocol | `test_investigation_inquiry_adapter.py` |
| Public local-review origin forged into specialist origin; native cause edited | `test_forged_native_fields_on_completed_cycle_b_review_cannot_admit_native_work`, `test_changed_public_native_cause_cannot_prepare_or_claim_after_answer` |
| Completion-to-admission adoption race | `test_terminal_result_cannot_be_adopted_or_seized_before_inquiry_admission` |
| A2 requests further evidence | `test_followup_question_remains_needs_evidence_without_adoption_or_third_attempt` |

Independent read-only review reproduced three authority/admission counterexamples
before repair, then verified the fixes and typed contract against the 54 new tests.
The unchanged existing Cycle B suites passed with the integrated implementation.

## Interpretation limits

The fixture writes coherent app-server-shaped records and uses the existing
worker's evidence-only recovery reader. It does not demonstrate real model inquiry
quality, native interactive request support, actual provider input capture or
external exactly-once effects. Existing worker policy and native isolation limits
are unchanged. Native execution remains one admitted turn per attempt; this slice
supports one inquiry and one follow-up. A source offer is not entailment. Private
host linkage is an owner-service admission boundary, not arbitrary-caller Python
security or authenticated remote delegation.

See the [native/API contract](../agents/SPECIALIST_INQUIRY_CONTRACT.md) and
[typed UI contract](../agents/SPECIALIST_INQUIRY_API.ts).
