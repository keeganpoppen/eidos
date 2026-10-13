"""Synthetic, local Eidos continuation evidence; no native worker is invoked."""

from contextlib import contextmanager
from copy import deepcopy
import json

import pytest

from eidos.core import Name
from eidos.discovery import poll_inquiry
from eidos.investigation_runtime import InvestigationRuntime
from eidos.model_process import AWAIT_DISCOVERY, DISCOVER, ModelProcessRunner
from eidos.trace import TraceStore


@contextmanager
def outer_transaction(trace):
    with trace._lock:
        trace.db.execute("BEGIN IMMEDIATE")
        try:
            yield
        except BaseException:
            trace.db.execute("ROLLBACK")
            raise
        else:
            trace.db.execute("COMMIT")


def start(runtime):
    return runtime.start(
        key="continuation:synthetic", investigation_id="investigation:synthetic",
        attempt_id="attempt:synthetic",
        native_artifact={"id": "artifact:synthetic", "text": "A synthetic native result.", "unknown": {"retained": True}},
        context={"id": "context:initial", "records": [{"seq": 1, "rawText": '{"futureField":true}'}]},
        question="Is there any additional relevant evidence?",
    )


def pending(runtime):
    with outer_transaction(runtime.trace):
        state = start(runtime)
    asked = runtime.advance(state)
    assert asked["inquiryId"] is not None
    assert asked["openedOccurrenceId"] is not None
    assert asked["pending"] is False
    waiting = runtime.advance(asked)
    assert waiting["pending"] is True
    assert waiting["checkpointId"] == asked["checkpointId"]
    return waiting


def response(decision, suffix="one"):
    return {
        "id": f"response:{suffix}", "requestId": f"request:{suffix}",
        "decision": decision, "note": "An attributable synthetic source decision.",
        "evidenceContext": ({
            "id": "context:offered", "question": "Selected evidence",
            "records": [{"seq": 9, "rawText": '{"unknown":{"preserved":true}}'}],
        } if decision == "offer" else None),
    }


def answer(runtime, state, decision):
    with outer_transaction(runtime.trace):
        return runtime.respond(state, decision)


def count_occurrences(trace):
    return trace.db.execute("SELECT COUNT(*) FROM authority_occurrences").fetchone()[0]


def test_origin_exactly_links_outer_attempt_native_artifact_and_model_input():
    trace = TraceStore()
    runtime = InvestigationRuntime(trace)
    with outer_transaction(trace):
        state = start(runtime)
        replayed = start(runtime)
    assert replayed == state
    assert json.loads(json.dumps(state)) == state
    origin = runtime.trusted.named_eidos_value(state["originValueId"])["value"]
    assert origin.get("investigation_id") == state["investigationId"]
    assert origin.get("attempt_id") == state["attemptId"]
    assert origin.get("continuation_id") == state["key"]
    assert origin.get("native_artifact")["unknown"] == {"retained": True}
    assert origin.get("context")["records"][0]["rawText"] == '{"futureField":true}'
    model = runtime.trusted.named_eidos_value(state["modelId"])["value"]
    assert model.get("sources") == (Name(state["originValueId"]),)
    process = runtime.trusted.named_eidos_value(state["processId"])["value"]
    assert process.get("input").get("source") == Name(state["originValueId"])
    assert process.get("protocol") == Name(state["protocolId"])
    assert process.get("allowed_executors") == ()
    assert process.get("allowed_providers") == ()


def test_offer_resumes_same_process_after_database_restart_with_exact_cut_evidence(tmp_path, monkeypatch):
    path = tmp_path / "investigations.sqlite"
    trace = TraceStore(path)
    runtime = InvestigationRuntime(trace)
    original_respond = ModelProcessRunner._respond
    operations = []

    def only_local_operations(self, **kwargs):
        operation = kwargs["suspended"].operation
        assert operation in {DISCOVER, AWAIT_DISCOVERY}
        operations.append(operation)
        return original_respond(self, **kwargs)

    monkeypatch.setattr(ModelProcessRunner, "_respond", only_local_operations)
    waiting = pending(runtime)
    assert operations == [DISCOVER]
    previous_checkpoint = waiting["checkpointId"]
    before = count_occurrences(trace)
    assert runtime.advance(waiting) == waiting
    assert count_occurrences(trace) == before
    trace.close()

    trace = TraceStore(path)
    runtime = InvestigationRuntime(trace)
    offered_response = response("offer")
    offered, public = answer(runtime, waiting, offered_response)
    assert offered["processId"] == waiting["processId"]
    assert offered["checkpointId"] == previous_checkpoint
    assert offered["responderId"] is None
    assert poll_inquiry(runtime.trusted, waiting["inquiryId"])["status"] == "offer"
    cut = runtime.trusted.causal_cut(public["disclosureCutId"])
    assert cut["instance_name"] == waiting["sourceDomainId"]
    projection = cut["projections"][0]
    evidence_name = projection["description"].get("evidence").value
    packet = runtime.trusted.named_eidos_value(evidence_name)["value"]
    assert packet.get("evidence_context") == offered_response["evidenceContext"]
    receipt = runtime.trusted.named_eidos_value(public["responseValueId"])["value"]
    assert receipt.get("note") == offered_response["note"]
    assert receipt.get("occurrence") == Name(public["occurrenceId"])
    assert receipt.get("cut") == Name(public["disclosureCutId"])
    assert cut["parent_occurrence"] == receipt.get("selection_occurrence").value
    assert runtime.trusted.authority_occurrence(public["occurrenceId"])["kind"] == "DiscoveryOffer"
    assert answer(runtime, waiting, offered_response) == (offered, public)
    trace.close()

    trace = TraceStore(path)
    runtime = InvestigationRuntime(trace)
    completed = runtime.advance(offered)
    assert completed["outcomeId"] is not None
    assert completed["pending"] is False
    assert completed["processId"] == waiting["processId"]
    assert completed["initialCheckpointId"] == waiting["initialCheckpointId"]
    assert completed["checkpointId"] == previous_checkpoint
    outcome = runtime.trusted.named_eidos_value(completed["outcomeId"])["value"]
    assert outcome.get("run") == Name(waiting["processId"])
    proposal = outcome.get("proposal")
    assert proposal.get("claims") == ()
    assert proposal.get("receipt").get("cut") == Name(public["disclosureCutId"])
    assert proposal.get("receipt").get("disclosure") == Name(public["occurrenceId"])
    received = runtime.trusted.authority_occurrence(outcome.get("events")[-1].value)
    assert received["fact"]["causal_source"] == public["occurrenceId"]
    assert runtime.advance(offered) == completed
    assert runtime.advance(completed) == completed
    assert operations == [DISCOVER, AWAIT_DISCOVERY]
    trace.close()


def test_deferral_keeps_requester_live_and_refusal_has_distinct_causal_receipt():
    trace = TraceStore()
    runtime = InvestigationRuntime(trace)
    waiting = pending(runtime)
    checkpoint = runtime.trusted.named_eidos_value(waiting["checkpointId"])["value"]
    waiting_socket = checkpoint.get("suspension").socket.name.value
    deferred, deferred_public = answer(runtime, waiting, response("defer", "defer"))
    assert deferred["responderId"] is not None
    assert deferred["checkpointId"] == waiting["checkpointId"]
    assert runtime.trusted.authority_occurrence(deferred_public["occurrenceId"])["kind"] == "DiscoveryDefer"
    before = count_occurrences(trace)
    assert runtime.advance(deferred) == deferred
    assert count_occurrences(trace) == before
    assert runtime.trusted.projection(waiting_socket)["disposition"] == "live"
    refused, public = answer(runtime, deferred, response("refuse", "refuse"))
    assert runtime.trusted.authority_occurrence(public["occurrenceId"])["kind"] == "DiscoveryRefuse"
    assert public["disclosureCutId"] is None
    assert public["occurrenceId"] != deferred_public["occurrenceId"]
    completed = runtime.advance(refused)
    assert completed["contextName"] == waiting["contextName"]
    outcome = runtime.trusted.named_eidos_value(completed["outcomeId"])["value"]
    receipt = outcome.get("proposal").get("receipt")
    assert receipt.get("$kind") == "DiscoveryRefused"
    assert receipt.get("decision") == Name(public["occurrenceId"])
    assert runtime.trusted.projection(waiting_socket)["disposition"] == "spent"


def test_nested_response_failure_rolls_back_source_authority_and_repairs(monkeypatch):
    trace = TraceStore()
    runtime = InvestigationRuntime(trace)
    waiting = pending(runtime)
    original = runtime.machine.persist
    before = count_occurrences(trace)

    def fail_receipt(**kwargs):
        if kwargs["kind"] == "investigation-response":
            raise RuntimeError("after response occurrence before outer linkage")
        return original(**kwargs)

    monkeypatch.setattr(runtime.machine, "persist", fail_receipt)
    with pytest.raises(RuntimeError, match="after response occurrence"):
        answer(runtime, waiting, response("offer"))
    assert count_occurrences(trace) == before
    assert runtime.trusted.projection(waiting["discloserId"])["disposition"] == "live"
    assert runtime.trusted.projection(waiting["evidenceProjectionId"])["disposition"] == "live"
    assert poll_inquiry(runtime.trusted, waiting["inquiryId"])["status"] == "pending"
    monkeypatch.setattr(runtime.machine, "persist", original)
    offered, _ = answer(runtime, waiting, response("offer"))
    assert runtime.advance(offered)["outcomeId"] is not None


def test_committed_discover_survives_missing_successor_checkpoint(monkeypatch):
    trace = TraceStore()
    runtime = InvestigationRuntime(trace)
    with outer_transaction(trace):
        state = start(runtime)
    original = runtime.machine.checkpoint

    def fail_checkpoint(**kwargs):
        raise RuntimeError("after Discover commit before successor checkpoint")

    monkeypatch.setattr(runtime.machine, "checkpoint", fail_checkpoint)
    with pytest.raises(RuntimeError, match="after Discover commit"):
        runtime.advance(state)
    assert count_occurrences(trace) == 1
    monkeypatch.setattr(runtime.machine, "checkpoint", original)
    repaired = runtime.advance(state)
    assert repaired["inquiryId"] is not None
    assert count_occurrences(trace) == 1
    assert runtime.advance(repaired)["pending"] is True


def test_committed_finish_survives_missing_outcome_binding(monkeypatch):
    trace = TraceStore()
    runtime = InvestigationRuntime(trace)
    waiting = pending(runtime)
    answered, _ = answer(runtime, waiting, response("refuse"))
    original = runtime.trusted.bind_eidos_value

    def fail_outcome(**kwargs):
        if kwargs["value"].get("$kind") == "ModelProcessOutcome":
            raise RuntimeError("after finish commit before outcome binding")
        return original(**kwargs)

    monkeypatch.setattr(runtime.trusted, "bind_eidos_value", fail_outcome)
    with pytest.raises(RuntimeError, match="after finish commit"):
        runtime.advance(answered)
    before = count_occurrences(trace)
    monkeypatch.setattr(runtime.trusted, "bind_eidos_value", original)
    completed = runtime.advance(answered)
    assert completed["outcomeId"] is not None
    assert count_occurrences(trace) == before
    assert runtime.advance(answered) == completed


def test_runtime_cannot_close_trace_connection_and_failed_outer_start_rolls_back(monkeypatch):
    trace = TraceStore()
    runtime = InvestigationRuntime(trace)
    original = ModelProcessRunner.start

    def fail_start(self, **kwargs):
        raise RuntimeError("before process start")

    monkeypatch.setattr(ModelProcessRunner, "start", fail_start)
    with pytest.raises(RuntimeError, match="before process start"):
        with outer_transaction(trace):
            start(runtime)
    assert trace.db.execute("SELECT COUNT(*) FROM names").fetchone()[0] == 0
    monkeypatch.setattr(ModelProcessRunner, "start", original)
    with outer_transaction(trace):
        state = start(runtime)
    runtime.trusted.close()
    assert trace.db.execute("SELECT COUNT(*) FROM names").fetchone()[0] > 0
    assert runtime.advance(state)["inquiryId"] is not None


def test_mismatched_outer_process_is_rejected_before_advancement():
    trace = TraceStore()
    runtime = InvestigationRuntime(trace)
    with outer_transaction(trace):
        state = start(runtime)
    forged = deepcopy(state)
    forged["processId"] = "a-different-process"
    with pytest.raises(ValueError, match="another investigation process"):
        runtime.advance(forged)
    assert count_occurrences(trace) == 0
