"""Joined inquiry, history, evaluation and owner-decision boundary regressions."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from eidos.api import EidosAPI
from eidos.trace import TraceStore
from test_investigation_continuations_api import Handler
from test_specialist_inquiries import (SpecialistWorker, answer, call, create_body, next_body,
                                      pending_specialist, successful, wait_for, native_turns)


@pytest.fixture
def joined(tmp_path):
    trace = TraceStore(tmp_path / "joined.db")
    api = EidosAPI(trace)
    pending, body = pending_specialist(api, trace)
    extra = create_body(trace, "additional")
    answered = answer(api, pending, extra)
    baseline = answered["nativeArtifact"]
    request = {"requestId": "comparison", "baselineArtifactId": baseline["id"],
               "baselineContextId": baseline["contextId"],
               "alternativeContextId": answered["continuation"]["nativeNext"]["contextId"],
               "rationale": "Evaluate retaining original evidence with the separately offered records."}
    try:
        yield api, trace, answered, request
    finally:
        api.close()
        trace.close()


def test_evaluate_saved_alternative_then_reject_preserves_all_authority(joined):
    api, trace, value, request = joined
    path = f"/{value['id']}/experiments"
    before = api.investigations.get(value["id"])
    result = successful(call(api, path, request))
    evaluation = result["evaluation"]
    assert evaluation["passes"] and len(evaluation["addedRecordIds"]) == 2
    assert evaluation["additionalPromptBytes"] > 0
    assert evaluation["modelCalls"] == 0 and not evaluation["measuredModelReasoningImprovement"]
    assert result["review"] is None and result["adoption"] is None
    assert api.investigations.get(value["id"]) == before
    assert len(native_turns(trace)) == 1
    assert successful(call(api, path, request)) == result
    assert call(api, path, {**request, "rationale": "altered"})[0] == 409
    decision = {"requestId": "decline", "decision": "reject", "rationale": "Bytes alone do not establish usefulness."}
    reviewed = successful(call(api, path + f"/{result['id']}/review", decision))
    assert reviewed["status"] == "rejected" and reviewed["adoption"] is None
    assert call(api, path + f"/{result['id']}/rollback", {"requestId": "bad", "rationale": "bad"})[0] == 409
    assert api.investigations.get(value["id"]) == before


def test_baseline_survives_followup_rollover_and_review_restart(joined):
    api, trace, value, request = joined
    api.investigation_worker = SpecialistWorker(trace, question=False)
    successful(call(api, f"/{value['id']}/continue", next_body(value)))
    completed = wait_for(api, value["id"], lambda v: v["attempt"].get("continuedFrom") and v["status"] == "completed")
    path = f"/{value['id']}/experiments"
    result = successful(call(api, path, request))
    assert result["baseline"]["attemptId"] == completed["attemptHistory"][0]["id"]
    assert result["baseline"]["artifactId"] == completed["nativeArtifact"]["id"]
    # A historical receipt is separately addressable, never the A2 conclusion.
    receipt = completed["artifactHistory"][0]
    receipt_result = successful(call(api, path, {**request, "requestId": "receipt-pair", "baselineArtifactId": receipt["id"]}))
    assert receipt_result["baseline"]["artifactId"] == receipt["id"]
    decision = {"requestId": "accept-selection", "decision": "adopt", "rationale": "Retain this bounded selection for review."}
    adopted = successful(call(api, path + f"/{result['id']}/review", decision))
    assert adopted["status"] == "adopted" and adopted["adoption"]["activation"] == "not-performed"
    assert successful(call(api, path + f"/{result['id']}/review", decision)) == adopted
    rollback = {"requestId": "rollback", "rationale": "Keep the earlier context candidate."}
    rolled = successful(call(api, path + f"/{result['id']}/rollback", rollback))
    api.close()
    other = EidosAPI(trace)
    try:
        assert successful(call(other, path + f"/{result['id']}", method="GET")) == rolled
        assert rolled["status"] == "rolled-back"
        assert len(native_turns(trace)) == 2
        assert other.investigations.get(value["id"]) == completed
    finally:
        other.close()


@pytest.mark.parametrize("field", ["evidenceClass", "executor", "holder", "outputGrants", "evaluation", "actor"])
def test_untrusted_comparison_cannot_select_authority_or_evaluator(joined, field):
    api, trace, value, request = joined
    assert call(api, f"/{value['id']}/experiments", {**request, field: "forged"})[0] == 400
    assert not api.investigation_experiments.ledger.list()
    assert len(native_turns(trace)) == 1


def test_scoped_names_and_atomic_comparison_failure(joined, monkeypatch):
    api, trace, value, request = joined
    path = f"/{value['id']}/experiments"
    record = api.investigation_experiments.ledger._record
    def crash(name, kind, *args, **kwargs):
        if kind == "workbench":
            raise RuntimeError("crash before comparison publication")
        return record(name, kind, *args, **kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(api.investigation_experiments.ledger, "_record", crash)
        with pytest.raises(RuntimeError):
            api.investigation_experiments.create(value["id"], request)
    assert not api.investigation_experiments.ledger.list()
    result = successful(call(api, path, request))
    foreign = api.investigations.create(create_body(trace, "foreign"))
    assert call(api, f"/{foreign['id']}/experiments/{result['id']}", method="GET")[0] == 404
    assert call(api, path, {**request, "requestId": "wrong", "alternativeContextId": foreign["currentContextId"]})[0] == 409


def test_concurrent_requests_preserve_one_comparison_and_one_review(joined):
    api, trace, value, request = joined
    second_trace = TraceStore(trace.db.execute("PRAGMA database_list").fetchone()[2])
    second = EidosAPI(second_trace)
    barrier = Barrier(2)
    def create(controller):
        barrier.wait()
        return controller.investigation_experiments.create(value["id"], request)
    try:
        with ThreadPoolExecutor(2) as pool:
            results = list(pool.map(create, [api, second]))
        assert results[0] == results[1]
        assert len(api.investigation_experiments.ledger.list(kind="workbench")) == 1
        decision = {"requestId": "race-review", "decision": "adopt", "rationale": "Bounded decision."}
        def review(controller):
            barrier.wait()
            return controller.investigation_experiments.decide(value["id"], results[0]["id"], "review", decision)
        with ThreadPoolExecutor(2) as pool:
            reviews = list(pool.map(review, [api, second]))
        assert reviews[0] == reviews[1]
        assert len(api.investigation_experiments.ledger.list(kind="review")) == 1
    finally:
        second.close()
        second_trace.close()


def test_native_resource_gate_preserves_unattempted_packet(tmp_path):
    trace = TraceStore(tmp_path / "gated.db")
    api = EidosAPI(trace)
    try:
        body = create_body(trace)
        value = api.investigations.create(body)
        capabilities = successful(call(api, "/capabilities", method="GET"))
        assert not capabilities["nativeExecution"]["available"]
        assert capabilities["specialistInquiry"]["interactive"] is False
        assert call(api, f"/{value['id']}/dispatch", {"contextId": value["currentContextId"]})[0] == 409
        assert api.investigations.get(value["id"]) == value
        assert not native_turns(trace)
    finally:
        api.close()
        trace.close()


@pytest.mark.parametrize("path", ["/api/threads", "/api/threads/synthetic/messages", "/api/threads/synthetic/observe"])
def test_legacy_controls_cannot_bypass_resource_gate(tmp_path, path, monkeypatch):
    trace = TraceStore(tmp_path / "legacy.db")
    api = EidosAPI(trace)
    def forbidden(*args, **kwargs):
        pytest.fail("resource gate allowed a live adapter call")
    monkeypatch.setattr(api.live, "start_thread", forbidden)
    monkeypatch.setattr(api.live, "send", forbidden)
    monkeypatch.setattr(api, "start_observer", forbidden)
    try:
        assert api.dispatch(Handler({"text": "do work"}), "POST", path, {})[0] == 409
        assert trace.records() == []
    finally:
        api.close()
        trace.close()
