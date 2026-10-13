"""Synthetic local ledger counterexamples; no native/model execution evidence."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
from pathlib import Path

import pytest

from eidos.investigation import InvestigationStore
from eidos.investigation_alternatives import ExperimentStore
from eidos.trace import TraceStore


QUESTION = "Which recovery rule and limitation should be retained?"


def _world(path: Path | None = None, *, cases=("motivation",), evidence_class="synthetic"):
    trace = TraceStore(path) if path else TraceStore()
    investigations = InvestigationStore(trace)
    store = ExperimentStore(investigations)
    first = trace.append(source="synthetic/a", direction="internal", message={
        "method": "$fixture/evidence", "params": {"threadId": "a"},
        "text": "Retain unknown outcomes.", "relatedEvidence": [2],
        "futureField": {"nested": [None, "retained"]},
    }).seq
    second = trace.append(source="synthetic/b", direction="internal", message={
        "method": "$fixture/evidence", "params": {"threadId": "b"},
        "text": "Do not silently replay external work.",
    }).seq

    def create(name, selected):
        return investigations.create({
            "requestId": name, "title": name, "question": QUESTION,
            "selections": [{"threadId": thread, "startSeq": seq, "endSeq": seq}
                           for thread, seq in selected],
        })

    baseline = create("baseline", [("a", first)])
    baseline, _ = investigations.claim(baseline["id"], baseline["currentContextId"])
    output = trace.append(source="synthetic/output", direction="internal", message={
        "method": "$fixture/output", "params": {"threadId": "result"},
        "text": "Retain unknown outcomes.",
    }).seq
    baseline = investigations.complete(baseline["id"], {
        "text": "Retain unknown outcomes. [evidence:1]", "outputSeqs": [output],
    })
    alternative = create("alternative", [("a", first), ("b", second)])
    horizon = store.freeze_horizon([first, second], evidence_class=evidence_class,
                                   rationale="Explicit synthetic availability set.")
    base_ref = store.snapshot_baseline(baseline["id"], baseline["currentContextId"], baseline["artifact"]["id"])
    alt_ref = store.snapshot_context(alternative["id"], alternative["currentContextId"])
    before = store.version("context-selection", "P0", {"rule": "retain seed"})
    after = store.version("context-selection", "P1", {"rule": "add linked relevant source"})
    criteria = {
        "version": "fixture-case-v1", "question": QUESTION,
        "relevantRecordIds": [first, second], "requiredFacets": ["rule", "limit"],
        "maxAdditionalBytes": 10000,
        "factSupport": {
            "unknown": {"value": "retained", "recordIds": [first], "facet": "rule"},
            "replay": {"value": "prohibited", "recordIds": [second], "facet": "limit"},
        },
    }
    proposal = store.propose("proposal", before_version=before, after_version=after,
                             criteria={"version": "suite-v1", "cases": {case: criteria for case in cases}},
                             rationale="Include the related recovery limitation.")
    bundle = {"baseline": baseline, "alternative": alternative, "horizon": horizon,
              "base_ref": base_ref, "alt_ref": alt_ref, "before": before, "after": after,
              "proposal": proposal, "criteria": criteria, "record_ids": [first, second]}
    return trace, investigations, store, bundle


def _experiment(store, bundle, name="experiment", *, case="motivation", **changes):
    arguments = dict(proposal=bundle["proposal"].name, baseline=bundle["base_ref"],
                     alternative_context=bundle["alt_ref"], horizon=bundle["horizon"],
                     case_id=case, assumptions=["Synthetic fixture; no workspace or external effects."])
    arguments.update(changes)
    return store.experiment(name, **arguments)


def _outcomes(store, experiment, *, candidate_failures=()):
    result = []
    for variant in ("baseline", "alternative"):
        attempt, created = store.prepare_attempt(f"{experiment}/{variant}", experiment=experiment, variant=variant)
        assert created
        claims = [{"key": "unknown", "value": "retained", "citations": [1], "facet": "rule"}]
        if variant == "alternative":
            claims.append({"key": "replay", "value": "prohibited", "citations": [2], "facet": "limit"})
        outcome = store.finish_attempt(f"{attempt.name}/outcome", attempt=attempt.name,
                                       answer="Fixture interpretation.", claims=claims,
                                       failures=candidate_failures if variant == "alternative" else ())
        result.append(outcome)
    return result


def _evaluation(store, bundle, name="experiment", *, case="motivation"):
    experiment = _experiment(store, bundle, name, case=case)
    baseline, alternative = _outcomes(store, experiment.name)
    return store.evaluate(f"{name}/evaluation", experiment=experiment.name,
                          baseline_outcome=baseline.name, alternative_outcome=alternative.name)


def test_snapshots_preserve_exact_references_unknown_fields_and_restart(tmp_path):
    path = tmp_path / "trace.db"
    trace, investigations, store, bundle = _world(path)
    original = {value["id"]: deepcopy(value) for value in (bundle["baseline"], bundle["alternative"])}
    before_trace = [(r.seq, r.raw_text) for r in trace.records()]
    experiment = _experiment(store, bundle)
    base = store.objects.get(bundle["base_ref"])
    context = store.objects.get(base.ref("context"))
    assert context.ref("manifest") != base.ref("attemptManifest")
    assert store.objects.get(base.ref("requestPin")).ref("manifest") == base.ref("attemptManifest")
    assert json.loads(context.data["context"]["records"][0]["rawText"])["futureField"] == {"nested": [None, "retained"]}
    context.data["context"]["records"][0]["rawText"] = "caller mutation"
    experiment.data["assumptions"].append("caller mutation")
    _evaluation(store, bundle, "additional")
    assert [(r.seq, r.raw_text) for r in trace.records()] == before_trace
    for identity, snapshot in original.items():
        assert investigations.get(identity) == snapshot
    expected = store.get(experiment.name)
    trace.close()
    reopened = TraceStore(path)
    try:
        recovered = ExperimentStore(InvestigationStore(reopened))
        assert recovered.get(experiment.name) == expected
        assert recovered.objects.get(context.cid).data["context"] == bundle["baseline"]["contexts"][0]
    finally:
        reopened.close()


def test_exact_native_artifact_survives_visible_artifact_replacement():
    trace, investigations, store, bundle = _world()
    baseline = deepcopy(bundle["baseline"])
    native = deepcopy(baseline["artifact"])
    baseline["nativeArtifact"] = native
    baseline["artifact"] = None
    with investigations._transaction():
        investigations._save(baseline)
    assert store.snapshot_baseline(baseline["id"], native["contextId"], native["id"]) == bundle["base_ref"]
    baseline["artifact"] = {**native, "id": "artifact_receipt", "kind": "eidos-evidence-review", "text": "later receipt"}
    with investigations._transaction():
        investigations._save(baseline)
    assert store.snapshot_baseline(baseline["id"], native["contextId"], native["id"]) == bundle["base_ref"]
    assert store.objects.get(store.objects.get(bundle["base_ref"]).ref("artifact")).data == native
    with pytest.raises(ValueError, match="owned"):
        store.snapshot_baseline(baseline["id"], native["contextId"], "guessed-artifact")
    with pytest.raises(ValueError, match="provenance"):
        store.snapshot_baseline(baseline["id"], "other-context", native["id"])


def test_equal_content_retains_distinct_experiment_attempt_and_outcome_occurrences():
    _, _, store, bundle = _world()
    first, second = (_experiment(store, bundle, name) for name in ("first", "second"))
    assert first.cid == second.cid and first.name != second.name
    first_outcomes = _outcomes(store, first.name)
    second_outcomes = _outcomes(store, second.name)
    for left, right in zip(first_outcomes, second_outcomes):
        assert left.cid == right.cid and left.name != right.name
        assert left.experiment != right.experiment and left.parent != right.parent
        assert store.get(left.parent).cid == store.get(right.parent).cid
        assert left.data["historicalWorldChanged"] is False
        assert store.get(left.parent).data["authority"] == "none"
    assert len(store.list(kind="experiment")) == 2
    assert len(store.list(experiment="first", kind="outcome")) == 2


def test_repeated_pending_attempt_is_not_a_new_execution_and_changed_names_conflict():
    _, _, store, bundle = _world()
    experiment = _experiment(store, bundle)
    first, created = store.prepare_attempt("attempt", experiment=experiment.name, variant="baseline")
    replay, created_again = store.prepare_attempt("attempt", experiment=experiment.name, variant="baseline")
    assert created and not created_again and first == replay
    assert store.list(kind="outcome") == ()
    with pytest.raises(ValueError, match="different"):
        store.prepare_attempt("attempt", experiment=experiment.name, variant="alternative")
    with pytest.raises(ValueError, match="different"):
        _experiment(store, bundle, assumptions=["altered retry"])
    outcome = store.finish_attempt("outcome", attempt="attempt", answer="Same", claims=[])
    assert store.finish_attempt("outcome", attempt="attempt", answer="Same", claims=[]) == outcome
    with pytest.raises(ValueError, match="different"):
        store.finish_attempt("outcome", attempt="attempt", answer="Different", claims=[])
    with pytest.raises(ValueError, match="terminal"):
        store.finish_attempt("competing", attempt="attempt", answer="Same", claims=[])


def test_concurrent_attempt_completion_has_one_terminal_outcome(tmp_path):
    path = tmp_path / "trace.db"
    first_trace, _, first, bundle = _world(path)
    experiment = _experiment(first, bundle)
    first.prepare_attempt("attempt", experiment=experiment.name, variant="alternative")
    second_trace = TraceStore(path)
    second = ExperimentStore(InvestigationStore(second_trace))

    def finish(item):
        index, store = item
        try:
            return store.finish_attempt(f"outcome-{index}", attempt="attempt", answer=f"result {index}", claims=[])
        except ValueError as error:
            return error

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(finish, enumerate((first, second))))
        assert sum(isinstance(outcome, ValueError) for outcome in outcomes) == 1
        assert len(first.list(kind="outcome", parent="attempt")) == 1
        assert first.list(kind="outcome") == second.list(kind="outcome")
    finally:
        first_trace.close()
        second_trace.close()


def test_constructor_and_mutations_join_outer_transaction_without_commit():
    trace = TraceStore()
    investigations = InvestigationStore(trace)
    trace.db.execute("BEGIN IMMEDIATE")
    store = ExperimentStore(investigations)
    version = store.version("context", "v1", {"private": "transient"})
    assert trace.db.in_transaction
    trace.db.execute("ROLLBACK")
    assert trace.db.execute("SELECT name FROM sqlite_master WHERE name='exp_records'").fetchone() is None
    with pytest.raises(KeyError):
        investigations.contexts.store.get(version)
    store = ExperimentStore(investigations)
    before = store.version("context", "v1", {})
    after = store.version("context", "v2", {})
    trace.db.execute("BEGIN IMMEDIATE")
    store.propose("rolled-back", before_version=before, after_version=after,
                  criteria={"version": "v1", "cases": {"x": {"question": "x"}}}, rationale="test rollback")
    assert trace.db.in_transaction
    trace.db.execute("ROLLBACK")
    with pytest.raises(KeyError):
        store.get("rolled-back")


def test_native_branch_is_descriptive_only_and_simulation_requires_mock_effects():
    _, _, store, bundle = _world()
    native = _experiment(store, bundle, "native", mode="native_branch")
    with pytest.raises(ValueError, match="separately admitted"):
        store.prepare_attempt("native-attempt", experiment=native.name, variant="alternative")
    assert store.list(kind="attempt") == ()
    with pytest.raises(ValueError, match="mocked effects"):
        _experiment(store, bundle, "missing-mocks", mode="simulation")
    simulation = _experiment(store, bundle, "simulation", mode="simulation", mock_effects={"filesystem": "no-op"})
    baseline, alternative = _outcomes(store, simulation.name)
    assert baseline.data["mode"] == alternative.data["mode"] == "simulation"
    assert alternative.data["historicalWorldChanged"] is False
    assert alternative.data["externalEffects"] == "none"


def test_post_horizon_evidence_is_rejected_without_changing_existing_experiment():
    trace, investigations, store, bundle = _world()
    existing = _experiment(store, bundle)
    later = trace.append(source="synthetic/b", direction="internal", message={
        "method": "$fixture/evidence", "params": {"threadId": "b"}, "text": "Later answer leakage",
    }).seq
    alternative = bundle["alternative"]
    revised = investigations.revise(alternative["id"], {
        "requestId": "later-context", "parentContextId": alternative["currentContextId"],
        "question": QUESTION, "selections": [{"threadId": "b", "startSeq": later, "endSeq": later}],
    })
    late_context = store.snapshot_context(revised["id"], revised["currentContextId"])
    with pytest.raises(ValueError, match="outside the frozen horizon"):
        _experiment(store, bundle, "leaky", alternative_context=late_context)
    assert store.get(existing.name) == existing


def test_same_sequence_with_altered_raw_bytes_fails_horizon_check():
    trace, investigations, store, bundle = _world()
    record = json.loads(trace.get(2).raw_text)
    record["text"] = "Mutated source bytes"
    trace.db.execute("UPDATE trace_records SET raw_text=? WHERE seq=2", (json.dumps(record),))
    altered = investigations.create({
        "requestId": "altered", "title": "altered", "question": QUESTION,
        "selections": [{"threadId": "b", "startSeq": 2, "endSeq": 2}],
    })
    ref = store.snapshot_context(altered["id"], altered["currentContextId"])
    with pytest.raises(ValueError, match="differs from the frozen horizon"):
        _experiment(store, bundle, "altered", alternative_context=ref)


def test_fixture_evaluation_rejects_recorded_evidence_and_never_claims_model_gain():
    _, _, store, bundle = _world(evidence_class="recorded")
    experiment = _experiment(store, bundle)
    baseline, alternative = _outcomes(store, experiment.name)
    with pytest.raises(ValueError, match="recorded real-world"):
        store.evaluate("evaluation", experiment=experiment.name, baseline_outcome=baseline.name,
                       alternative_outcome=alternative.name)
    _, _, synthetic, fixture = _world()
    evaluation = _evaluation(synthetic, fixture)
    assert evaluation.data["evidence_class"] == "synthetic"
    assert evaluation.data["measured_model_reasoning_improvement"] is False
    assert evaluation.data["comparison"]["measured_model_reasoning_improvement"] is False
    assert evaluation.data["alternative"]["resources"]["observedCost"] is None


def test_identical_outcome_content_cannot_be_borrowed_from_another_experiment():
    _, _, store, bundle = _world()
    first = _experiment(store, bundle, "first")
    second = _experiment(store, bundle, "second")
    base, alt = _outcomes(store, first.name)
    other_base, other_alt = _outcomes(store, second.name)
    assert alt.cid == other_alt.cid
    with pytest.raises(ValueError, match="experiment variant"):
        store.evaluate("borrowed", experiment=first.name, baseline_outcome=base.name,
                       alternative_outcome=other_alt.name)
    with pytest.raises(ValueError, match="experiment variant"):
        store.evaluate("swapped", experiment=first.name, baseline_outcome=alt.name,
                       alternative_outcome=base.name)


def test_review_requires_every_predeclared_case_and_rejection_remains_addressable():
    _, _, store, bundle = _world(cases=("motivation", "regression"))
    motivation = _evaluation(store, bundle)
    with pytest.raises(ValueError, match="every predeclared case"):
        store.review("incomplete", proposal="proposal", evaluations=[motivation.name], decision="adopt",
                     actor="fixture reviewer", rationale="Synthetic review", review_kind="synthetic")
    regression = _evaluation(store, bundle, "regression", case="regression")
    review = store.review("review", proposal="proposal", evaluations=[motivation.name, regression.name],
                          decision="reject", actor="fixture reviewer", rationale="Retain as counterexample", review_kind="synthetic")
    with pytest.raises(ValueError, match="rejected"):
        store.adopt("adoption", review=review.name)
    assert store.get("review") == review
    assert store.get(motivation.name).data["caseId"] == "motivation"
    assert len(store.list(kind="experiment", parent="proposal")) == 2


def test_adoption_and_rollback_derive_versions_from_exact_reviewed_proposal():
    _, _, store, bundle = _world()
    evaluation = _evaluation(store, bundle)
    review = store.review("review", proposal="proposal", evaluations=[evaluation.name], decision="adopt",
                          actor="fixture reviewer", rationale="Synthetic bounded improvement", review_kind="synthetic")
    adoption = store.adopt("adoption", review=review.name)
    assert adoption.content.ref("version") == bundle["after"]
    assert adoption.content.ref("rollbackVersion") == bundle["before"]
    assert adoption.data["scope"] == "synthetic demonstration only"
    assert adoption.data["activation"].startswith("not performed")
    assert store.adopt("adoption", review=review.name) == adoption
    rollback = store.rollback("rollback", adoption=adoption.name, actor="fixture reviewer", rationale="Test reversibility")
    assert rollback.content.ref("version") == bundle["before"]
    assert store.get("adoption") == adoption
    assert store.get("review") == review
    with pytest.raises(ValueError, match="terminal"):
        store.rollback("another-rollback", adoption=adoption.name, actor="fixture reviewer", rationale="duplicate")


@pytest.mark.parametrize("evaluate_first", [False, True])
def test_rejection_can_retain_empty_or_partial_evaluation(evaluate_first):
    _, _, store, bundle = _world(cases=("motivation", "regression"))
    evaluations = [_evaluation(store, bundle).name] if evaluate_first else []
    review = store.review("rejection", proposal="proposal", evaluations=evaluations, decision="reject",
                          actor="fixture reviewer", rationale="Stop without inventing missing results", review_kind="synthetic")
    expected_missing = ["regression"] if evaluate_first else ["motivation", "regression"]
    assert review.data["missingCaseIds"] == expected_missing
    assert review.data["evaluations"] == evaluations
    with pytest.raises(ValueError, match="rejected"):
        store.adopt("forbidden", review=review.name)
    assert store.get(review.name) == review


def test_repeated_review_preserves_pending_and_omitted_snapshot_after_later_completion():
    _, _, store, bundle = _world()
    selected = _evaluation(store, bundle, "selected")
    omitted = _evaluation(store, bundle, "omitted")
    waiting = _experiment(store, bundle, "waiting")
    pending, _ = store.prepare_attempt("pending", experiment=waiting.name, variant="alternative")
    arguments = dict(proposal="proposal", evaluations=[selected.name], decision="adopt",
                     actor="fixture reviewer", rationale="Explicit synthetic review", review_kind="synthetic")
    review = store.review("review", **arguments)
    assert review.data["omittedEvaluationNames"] == [omitted.name]
    assert review.data["pendingAttemptNames"] == [pending.name]
    store.finish_attempt("late-outcome", attempt=pending.name, answer="Later observation", claims=[])
    later = _evaluation(store, bundle, "later")
    assert store.review("review", **arguments) == review
    assert later.name not in store.get("review").data["omittedEvaluationNames"]
    for changed in ({"rationale": "changed rationale"}, {"actor": "different actor"},
                    {"evaluations": [selected.name, later.name]}, {"decision": "reject"}):
        with pytest.raises(ValueError, match="different content or lineage"):
            store.review("review", **{**arguments, **changed})


def test_reported_execution_failure_prevents_positive_comparison_recommendation():
    _, _, store, bundle = _world()
    experiment = _experiment(store, bundle)
    baseline, alternative = _outcomes(store, experiment.name, candidate_failures=["Mock interpretation interrupted"])
    evaluation = store.evaluate("evaluation", experiment=experiment.name, baseline_outcome=baseline.name,
                                alternative_outcome=alternative.name)
    data = evaluation.data
    assert data["comparison"]["checks"]["fixtureImprovement"] is True
    assert data["comparison"]["checks"]["noReportedExecutionFailures"] is False
    assert data["comparison"]["passes"] is False
    assert data["comparison"]["recommendation"] == "retain_counterexample"
    assert data["outcomeFailures"]["alternative"] == ["Mock interpretation interrupted"]
    assert data["answerTextEvaluated"] is False
    assert data["retainedArtifactEvaluated"] is False


def test_unknown_snapshot_extensions_remain_data_without_reviving_authority():
    _, investigations, store, bundle = _world()
    baseline = deepcopy(bundle["baseline"])
    baseline["artifact"]["futureExtension"] = {"historicalAuthority": "synthetic-spent-handle"}
    baseline["contexts"][0]["futureExtension"] = {"scope": "historical description"}
    with investigations._transaction():
        investigations._save(baseline)
    reference = store.snapshot_baseline(baseline["id"], baseline["currentContextId"], baseline["artifact"]["id"])
    frozen = store.objects.get(reference)
    assert store.objects.get(frozen.ref("artifact")).data["futureExtension"] == baseline["artifact"]["futureExtension"]
    assert store.objects.get(frozen.ref("context")).data["context"]["futureExtension"] == baseline["contexts"][0]["futureExtension"]
    experiment = _experiment(store, bundle, baseline=reference)
    attempt, _ = store.prepare_attempt("attempt", experiment=experiment.name, variant="baseline")
    assert attempt.data["authority"] == "none"
    assert attempt.data["externalEffects"] == "none"
