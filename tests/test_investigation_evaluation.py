"""Synthetic fixture protocol checks, not measurements of model reasoning."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json

import pytest

from eidos.investigation_evaluation import compare_evaluations, evaluate_outcome, select_context


def record(seq, **payload):
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return {"seq": seq, "rawText": raw, "sha256": hashlib.sha256(raw.encode()).hexdigest()}


@pytest.fixture
def fixture():
    return {
        "evidence": [
            record(1, thread="decision", text="Inspect before retry", relatedEvidence=[2, 9]),
            record(2, thread="operations", text="Operation started; outcome unknown", relatedEvidence=[3, 1]),
            record(3, thread="unrelated", text="Unrelated deployment"),
        ],
        "criteria": {"version": "recovery-fixture/v1", "question": "May we retry?",
                     "relevantRecordIds": [1, 2], "requiredFacets": ["action", "status"],
                     "factSupport": {
                         "inspect": {"value": "inspect first", "recordIds": [1], "facet": "action"},
                         "unknown": {"value": "unknown", "recordIds": [2], "facet": "status"},
                         "both": {"value": True, "recordIds": [1, 2], "facet": "action"}},
                     "maxAdditionalBytes": 1000},
        "claims": [{"key": "inspect", "value": "inspect first", "citations": [1], "facet": "action"},
                   {"key": "unknown", "value": "unknown", "citations": [2], "facet": "status"}],
    }


def evaluate(fixture, selected=(1, 2), claims=None, prompt="Synthetic projection"):
    return evaluate_outcome(fixture["criteria"], fixture["evidence"], selected,
                            fixture["claims"] if claims is None else claims,
                            {"projectedPrompt": prompt, "modelCalls": 0})


def test_complete_fixture_support_is_a_proxy_and_keeps_cost_unknown(fixture):
    report = evaluate(fixture, prompt="ééé")
    assert report["passes"] is True
    assert report["selection"]["recall"] == {"numerator": 2, "denominator": 2, "value": 1.0}
    assert report["grounding"]["groundedClaims"] == 2
    assert report["usefulness"]["kind"] == "grounded-required-facet-coverage-proxy"
    assert report["resources"]["projectedBytes"] == 6
    assert report["resources"]["tokenEstimate"] == 2
    assert report["resources"]["observedTokens"] is None
    assert report["resources"]["observedCost"] is None
    assert report["evidence_class"] == "synthetic"
    assert report["measured_model_reasoning_improvement"] is False
    assert report["evaluatedSurface"] == "structured_fixture_claims_only"
    assert report["answerTextEvaluated"] is False


def test_report_is_detached_and_horizon_not_a_max_sequence_number(fixture):
    report = evaluate(fixture)
    saved = deepcopy(report)
    fixture["claims"][0]["value"] = "changed later"
    fixture["criteria"]["question"] = "changed later"
    fixture["evidence"][0]["rawText"] = "changed later"
    assert report == saved
    # Membership, rather than an inferred global clock, defines the horizon.
    fixture = {**fixture, "evidence": [record(1), record(2), record(20)]}
    report = evaluate(fixture, selected=[1, 2, 9], claims=[])
    assert report["hindsight"]["selectedOutsideHorizon"] == [9]


def test_irrelevant_context_harms_precision_and_missing_evidence_harms_recall(fixture):
    report = evaluate(fixture, selected=[1, 3], claims=[fixture["claims"][0]])
    assert report["selection"]["omittedRelevantRecordIds"] == [2]
    assert report["selection"]["irrelevantSelectedRecordIds"] == [3]
    assert report["selection"]["precision"]["value"] == 0.5
    assert report["selection"]["recall"]["value"] == 0.5
    assert report["usefulness"]["missingFacets"] == ["status"]
    assert report["passes"] is False


@pytest.mark.parametrize("patch,reason", [
    ({"value": "retry"}, "incorrect_value"),
    ({"facet": "status"}, "incorrect_facet"),
    ({"key": "invented"}, "unknown_claim"),
    ({"citations": []}, "empty_support"),
    ({"citations": [1, 3]}, "incorrect_support"),
    ({"citations": [9]}, "hindsight_citation"),
])
def test_citation_membership_is_not_entailment(fixture, patch, reason):
    claim = {**fixture["claims"][0], **patch}
    report = evaluate(fixture, claims=[claim])
    assert reason in report["grounding"]["claims"][0]["failures"]
    assert report["grounding"]["groundedClaims"] == 0
    assert report["grounding"]["unsupportedClaimKeys"] == [claim["key"]]


def test_unselected_and_leaked_citations_are_independently_reported(fixture):
    report = evaluate(fixture, selected=[1], claims=[fixture["claims"][1]])
    assert report["grounding"]["claims"][0]["failures"] == ["unselected_citation"]
    assert report["hindsight"]["leakageCount"] == 0
    report = evaluate(fixture, selected=[1], claims=[{**fixture["claims"][1], "citations": [9]}])
    assert report["hindsight"]["selectedOutsideHorizon"] == []
    assert report["hindsight"]["citedOutsideHorizon"] == [9]
    assert report["hindsight"]["leakageCount"] == 1


def test_all_support_is_required_and_bool_does_not_equal_integer(fixture):
    claim = {"key": "both", "value": True, "citations": [1], "facet": "action"}
    assert evaluate(fixture, claims=[claim])["grounding"]["groundedClaims"] == 0
    claim["citations"] = [1, 2]
    assert evaluate(fixture, claims=[claim])["grounding"]["groundedClaims"] == 1
    claim["value"] = 1
    assert evaluate(fixture, claims=[claim])["grounding"]["groundedClaims"] == 0


@pytest.mark.parametrize("mutation", [
    lambda f: f["evidence"].append(f["evidence"][0]),
    lambda f: f["evidence"][0].update(sha256="invented"),
    lambda f: f["claims"].append(f["claims"][0]),
    lambda f: f["claims"].append({**f["claims"][0], "value": "opposite"}),
    lambda f: f["claims"][0].update(citations=[1, 1]),
    lambda f: f["claims"][0].update(citations=[True]),
    lambda f: f["claims"][0].update(value=float("nan")),
    lambda f: f["criteria"]["factSupport"]["inspect"].update(recordIds=[]),
    lambda f: f["criteria"]["factSupport"]["inspect"].update(recordIds=[9]),
    lambda f: f["criteria"].update(maxAdditionalBytes=-1),
    lambda f: f["criteria"].update(requiredFacets=[]),
    lambda f: f["criteria"].update(relevantRecordIds=[1, 1]),
])
def test_malformed_and_contradictory_inputs_fail_closed(fixture, mutation):
    mutation(fixture)
    with pytest.raises(ValueError):
        evaluate(fixture)


@pytest.mark.parametrize("selected", [[1, 1], [True], [-1], "1", [1.0]])
def test_malformed_selection_rejected(fixture, selected):
    with pytest.raises(ValueError):
        evaluate(fixture, selected=selected)


@pytest.mark.parametrize("calls", [True, 1, -1, None])
def test_fixture_cannot_claim_real_model_evaluation(fixture, calls):
    with pytest.raises(ValueError, match="modelCalls"):
        evaluate_outcome(fixture["criteria"], fixture["evidence"], [1], [],
                         {"projectedPrompt": "p", "modelCalls": calls})


def test_controlled_comparison_records_benefit_and_resource_tradeoff(fixture):
    baseline = evaluate(fixture, selected=[1], claims=[fixture["claims"][0]], prompt="small")
    candidate = evaluate(fixture, prompt="larger prompt")
    comparison = compare_evaluations(baseline, candidate)
    assert comparison["passes"] is True
    assert comparison["deltas"]["selectionRecall"] == 0.5
    assert comparison["deltas"]["usefulnessCoverage"] == 0.5
    assert comparison["resourceTradeoff"]["additionalBytes"] == 8
    assert comparison["resourceTradeoff"]["observedAdditionalCost"] is None
    assert comparison["recommendation"] == "review_bounded_fixture_improvement"
    assert comparison["measured_model_reasoning_improvement"] is False
    assert comparison["evaluatedSurface"] == "structured_fixture_claims_only"
    assert comparison["answerTextEvaluated"] is False
    assert compare_evaluations(candidate, candidate)["passes"] is False


def test_comparison_fails_overbudget_and_context_precision_regression(fixture):
    fixture["criteria"]["maxAdditionalBytes"] = 1
    baseline = evaluate(fixture, selected=[1], claims=[fixture["claims"][0]], prompt="a")
    candidate = evaluate(fixture, selected=[1, 2, 3], prompt="much larger")
    comparison = compare_evaluations(baseline, candidate)
    assert comparison["passes"] is False
    assert comparison["checks"]["boundedAdditionalContext"] is False
    assert comparison["checks"]["selectionPrecisionNondecreasing"] is False


def test_comparison_rejects_changed_criteria_horizon_or_evidence_class(fixture):
    baseline = evaluate(fixture)
    for key in ("criteriaId", "evidenceHorizonId", "evidence_class"):
        candidate = {**baseline, key: "different"}
        with pytest.raises(ValueError):
            compare_evaluations(baseline, candidate)


def test_p1_is_one_hop_deterministic_and_keeps_hindsight_outside(fixture):
    p0 = select_context("P0", fixture["evidence"], [1], max_records=3, max_bytes=10000)
    p1 = select_context("P1", fixture["evidence"], [1], max_records=3, max_bytes=10000)
    assert p0["selectedRecordIds"] == [1]
    assert p1["selectedRecordIds"] == [1, 2]
    assert p1["omissions"] == [{"recordId": 9, "reason": "outside_frozen_horizon"}]
    assert p1["inputBytes"] == len(p1["projectedPrompt"].encode())
    assert "Unrelated deployment" not in p1["projectedPrompt"]
    assert select_context("P1", list(reversed(fixture["evidence"])), [1], max_records=3, max_bytes=10000) == p1


def test_seeds_never_truncate_and_link_expansion_reports_budget_omissions(fixture):
    p0 = select_context("P0", fixture["evidence"], [1], max_records=3, max_bytes=10000)
    for budget in ({"max_records": 1, "max_bytes": 10000},
                   {"max_records": 3, "max_bytes": p0["inputBytes"]}):
        p1 = select_context("P1", fixture["evidence"], [1], **budget)
        assert p1["selectedRecordIds"] == [1]
        assert p1["omissions"][0]["reason"] in {"record_budget", "bytes_budget"}
    with pytest.raises(ValueError, match="seed records exceed"):
        select_context("P1", fixture["evidence"], [1, 2], max_records=1, max_bytes=10000)
    with pytest.raises(ValueError, match="seed records exceed"):
        select_context("P1", fixture["evidence"], [1], max_records=3, max_bytes=1)


def test_cycles_and_shared_links_do_not_duplicate_records():
    records = [record(1, relatedEvidence=[1, 2, 3]), record(2, relatedEvidence=[1, 3]), record(3)]
    result = select_context("P1", records, [2, 1], max_records=3, max_bytes=10000)
    assert result["selectedRecordIds"] == [1, 2, 3]
    assert result["omissions"] == []


@pytest.mark.parametrize("links", [[True], [2, 2], "2", [float("inf")]])
def test_malformed_links_are_rejected(links):
    with pytest.raises(ValueError):
        select_context("P1", [record(1, relatedEvidence=links)], [1], max_records=2, max_bytes=10000)


def test_invalid_policy_or_missing_seed_cannot_fall_back(fixture):
    for policy, seeds in (("native", [1]), ("P1", [9])):
        with pytest.raises(ValueError):
            select_context(policy, fixture["evidence"], seeds, max_records=3, max_bytes=10000)
