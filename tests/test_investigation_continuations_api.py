"""Cycle B local API/runtime evidence; the native fixture never calls a provider."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import io
import json
from pathlib import Path
import sys
import time

import pytest

from eidos.api import EidosAPI
from eidos.investigation_worker import NativeInvestigationWorker
from eidos.trace import TraceStore


FAKE = Path(__file__).parent / "fixtures/investigation_appserver.py"


class Handler:
    def __init__(self, body=None):
        raw = json.dumps({} if body is None else body).encode()
        self.headers = {"Content-Length": str(len(raw)), "Content-Type": "application/json"}
        self.rfile = io.BytesIO(raw)


def call(api, path="", body=None, *, method="POST"):
    return api.dispatch(Handler(body), method, "/api/investigations" + path, {})


def successful(result):
    status, body = result
    assert 200 <= status < 300, (status, body)
    return body


def create_body(trace, key="review"):
    selections = []
    for suffix, text in (("decision", "Persist the attempt before dispatch."),
                         ("alternative", "An absent acknowledgement leaves delivery unknown.")):
        thread = f"{key}-{suffix}"
        record = trace.append(source="synthetic-cycle-b", direction="internal", message={
            "method": "$history/item",
            "params": {"threadId": thread, "turnId": f"{thread}-turn", "item": {
                "id": thread, "type": "agentMessage", "text": text,
                "futureField": {"retain": [1, "exact source"]},
            }},
        })
        selections.append({"threadId": thread, "startSeq": record.seq,
                           "endSeq": record.seq, "rationale": "review source evidence"})
    return {"requestId": f"create-{key}", "title": "Evidence review",
            "question": "Which evidence supports the recovery policy?", "selections": selections}


def finish_native(api, body):
    investigation = successful(call(api, body=body))
    successful(call(api, f"/{investigation['id']}/dispatch", {
        "contextId": investigation["currentContextId"],
    }))
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        value = api.investigations.get(investigation["id"])
        if value["status"] in {"completed", "failed", "unknown"}:
            assert value["status"] == "completed", value
            return value
        time.sleep(0.01)
    raise AssertionError("synthetic native fixture did not complete")


@pytest.fixture
def native(tmp_path):
    trace = TraceStore(tmp_path / "investigation.db")
    api = EidosAPI(trace)
    api.investigation_worker = NativeInvestigationWorker(trace, command=[sys.executable, str(FAKE)])
    body = create_body(trace)
    completed = finish_native(api, body)
    try:
        yield api, trace, completed, body
    finally:
        api.close()
        trace.close()


def continuation_body(investigation):
    return {"requestId": "start-review", "attemptId": investigation["attempt"]["id"],
            "question": "Will the owner disclose the selected supporting records?"}


def begin(api, investigation):
    return successful(call(api, f"/{investigation['id']}/continuation", continuation_body(investigation)))


def inquiry_path(investigation):
    return f"/{investigation['id']}/inquiries/{investigation['continuation']['inquiry']['id']}"


def occurrences(api, *, domain=None):
    query = "SELECT name,kind,domain_name FROM authority_occurrences"
    params = ()
    if domain is not None:
        query += " WHERE domain_name=?"
        params = (domain,)
    return [tuple(row) for row in api.investigation_runtime.trusted.db.execute(
        query + " ORDER BY name", params,
    ).fetchall()]


def checkpoint_socket(api, checkpoint):
    trusted = api.investigation_runtime.trusted
    value = trusted.named_eidos_value(checkpoint)["value"]
    return trusted.projection(value.get("suspension").socket.name.value)


def test_defer_offer_artifact_adoption_and_restart_keep_one_investigation(native, tmp_path):
    api, trace, completed, body = native
    original_records = [(record.seq, record.raw_text) for record in trace.records()]
    pending = begin(api, completed)
    identifier = pending["id"]
    continuation = pending["continuation"]
    assert pending["status"] == "pending"
    assert pending["attempt"] == completed["attempt"]
    assert pending["nativeArtifact"] == completed["artifact"]
    assert pending["artifact"] is None
    repeated_dispatch = successful(call(api, f"/{identifier}/dispatch", {
        "contextId": pending["currentContextId"],
    }))
    assert repeated_dispatch["attempt"] == completed["attempt"]
    assert repeated_dispatch["continuation"]["id"] == continuation["id"]
    assert continuation["origin"] == "synthetic-eidos"
    assert continuation["attemptId"] == completed["attempt"]["id"]
    assert continuation["inquiry"]["question"] == continuation["question"]
    checkpoint = continuation["checkpointId"]
    trusted = api.investigation_runtime.trusted
    checkpoint_value = trusted.named_eidos_value(checkpoint)["value"]
    assert checkpoint_value.get("process").value == continuation["processId"]
    process_value = trusted.named_eidos_value(continuation["processId"])["value"]
    assert process_value.get("protocol").value == continuation["protocolId"]
    assert checkpoint_socket(api, checkpoint)["disposition"] == "live"
    before_reads = occurrences(api)
    for _ in range(2):
        assert successful(call(api, inquiry_path(pending), method="GET")) == continuation["inquiry"]
        assert successful(call(api, f"/{identifier}", method="GET")) == pending
    assert occurrences(api) == before_reads
    assert call(api, f"/{identifier}/adoption", {
        "artifactId": completed["artifact"]["id"], "decision": "adopt",
    })[0] == 409

    requester_before = occurrences(api, domain=continuation["processId"])
    defer_body = {"requestId": "response-defer", "decision": "defer", "note": "Reviewing source scope."}
    deferred = successful(call(api, inquiry_path(pending) + "/responses", defer_body))
    defer = deferred["continuation"]["inquiry"]["responses"][0]
    assert defer["decision"] == "defer" and defer["status"] == "committed"
    assert defer["evidenceContext"] is None
    assert trusted.authority_occurrence(defer["occurrenceId"])["kind"] == "DiscoveryDefer"
    assert deferred["continuation"]["checkpointId"] == checkpoint
    assert deferred["continuation"]["inquiry"]["status"] == "deferred"
    assert deferred["artifact"] is None and deferred["continuation"]["outcomeId"] is None
    assert checkpoint_socket(api, checkpoint)["disposition"] == "live"
    assert occurrences(api, domain=continuation["processId"]) == requester_before
    after_defer = occurrences(api)
    assert successful(call(api, f"/{identifier}/resume", {}))["continuation"]["checkpointId"] == checkpoint
    assert occurrences(api) == after_defer

    # A fresh controller reopens the same pending unit and cannot call native.
    api.close()
    restarted_trace = TraceStore(tmp_path / "investigation.db")
    restarted = EidosAPI(restarted_trace)
    try:
        restored = successful(call(restarted, f"/{identifier}", method="GET"))
        assert restored["continuation"]["id"] == continuation["id"]
        assert restored["continuation"]["checkpointId"] == checkpoint
        assert restored["attempt"] == completed["attempt"]
        offered = successful(call(restarted, inquiry_path(restored) + "/responses", {
            "requestId": "response-offer", "decision": "offer", "note": "Disclose these records.",
            "selections": body["selections"],
        }))
        assert offered["continuation"]["error"] is None
        result = successful(call(restarted, f"/{identifier}/resume", {}))
        assert result["id"] == identifier and result["status"] == "completed"
        assert result["attempt"] == completed["attempt"]
        assert result["continuation"]["status"] == "completed"
        inquiry = result["continuation"]["inquiry"]
        offer = inquiry["responses"][-1]
        assert offer["decision"] == "offer" and offer["status"] == "committed"
        assert inquiry["status"] == "offer"
        assert offer["evidenceContext"]["selections"] == body["selections"]
        for record in offer["evidenceContext"]["records"]:
            assert record["rawText"] == restarted_trace.get(record["seq"]).raw_text
            assert json.loads(record["rawText"])["params"]["item"]["futureField"]
        tm = restarted.investigation_runtime.trusted
        source_event = tm.authority_occurrence(offer["occurrenceId"])
        outcome = tm.named_eidos_value(result["continuation"]["outcomeId"])["value"]
        assert source_event["kind"] == "DiscoveryOffer"
        assert source_event["domain_name"] != continuation["processId"]
        assert outcome.get("run").value == continuation["processId"]
        requester_events = {event.value for event in outcome.get("events")}
        assert requester_events and offer["occurrenceId"] not in requester_events
        receipt = outcome.get("proposal").get("receipt")
        assert receipt.get("disclosure").value == offer["occurrenceId"]
        artifact = result["artifact"]
        assert artifact["kind"] == "eidos-evidence-review"
        assert artifact["text"].startswith(completed["artifact"]["text"])
        for field, expected in {
            "nativeArtifactId": completed["artifact"]["id"], "continuationId": continuation["id"],
            "processId": continuation["processId"], "outcomeId": result["continuation"]["outcomeId"],
            "inquiryId": inquiry["id"], "responseId": offer["id"],
            "decisionOccurrenceId": offer["occurrenceId"],
            "evidenceContextId": offer["evidenceContext"]["id"],
        }.items():
            assert artifact[field] == expected
        terminal_occurrences = occurrences(restarted)
        # Retrying a previously successful deferral after an offer is harmless.
        assert successful(call(restarted, inquiry_path(result) + "/responses", defer_body)) == result
        assert successful(call(restarted, f"/{identifier}/continuation", continuation_body(completed))) == result
        assert successful(call(restarted, f"/{identifier}/recover", {})) == result
        assert occurrences(restarted) == terminal_occurrences
        adoption = {"artifactId": artifact["id"], "decision": "adopt", "note": "Evidence reviewed."}
        adopted = successful(call(restarted, f"/{identifier}/adoption", adoption))
        assert successful(call(restarted, f"/{identifier}/adoption", adoption)) == adopted
        assert call(restarted, f"/{identifier}/adoption", {**adoption, "decision": "reject"})[0] == 409
        assert [(record.seq, record.raw_text) for record in restarted_trace.records()] == original_records
        assert len([record for record in restarted_trace.records() if record.method == "turn/start"]) == 1
    finally:
        restarted.close()
        restarted_trace.close()


def test_refusal_has_distinct_source_and_requester_records_and_no_disclosure(native):
    api, _, completed, _ = native
    pending = begin(api, completed)
    prior_context = pending["continuation"]["contextName"]
    refusal_body = {"requestId": "refuse-review", "decision": "refuse", "note": "Outside the reviewed scope."}
    successful(call(api, inquiry_path(pending) + "/responses", refusal_body))
    result = successful(call(api, f"/{pending['id']}/resume", {}))
    response = result["continuation"]["inquiry"]["responses"][0]
    tm = api.investigation_runtime.trusted
    decision = tm.authority_occurrence(response["occurrenceId"])
    outcome = tm.named_eidos_value(result["continuation"]["outcomeId"])["value"]
    receipt = outcome.get("proposal").get("receipt")
    assert decision["kind"] == "DiscoveryRefuse"
    assert decision["domain_name"] != result["continuation"]["processId"]
    assert receipt.get("$kind") == "DiscoveryRefused"
    assert receipt.get("decision").value == response["occurrenceId"]
    assert response["disclosureCutId"] is None and response["evidenceContext"] is None
    assert result["artifact"]["evidenceContextId"] is None
    assert result["continuation"]["contextName"] == prior_context
    assert not any(kind == "DiscoveryOffer" for _, kind, _ in occurrences(api))
    before = occurrences(api)
    assert successful(call(api, inquiry_path(result) + "/responses", refusal_body)) == result
    assert occurrences(api) == before
    rejected = successful(call(api, f"/{pending['id']}/adoption", {
        "artifactId": result["artifact"]["id"], "decision": "reject", "note": "Insufficient disclosure.",
    }))
    assert rejected["adoption"]["decision"] == "reject"


def test_request_ids_bind_operations_and_payloads_and_terminal_responses_conflict(native):
    api, _, completed, body = native
    pending = begin(api, completed)
    prefix = f"/{pending['id']}"
    before = occurrences(api)
    assert successful(call(api, prefix + "/continuation", continuation_body(completed))) == pending
    assert call(api, prefix + "/continuation", {**continuation_body(completed), "question": "Changed"})[0] == 409
    assert call(api, prefix + "/continuation", {**continuation_body(completed), "requestId": "second-review"})[0] == 409
    assert call(api, inquiry_path(pending) + "/responses", {
        "requestId": "start-review", "decision": "defer",
    })[0] == 409
    assert occurrences(api) == before
    deferred_body = {"requestId": "same-response", "decision": "defer", "note": "First wording"}
    deferred = successful(call(api, inquiry_path(pending) + "/responses", deferred_body))
    assert successful(call(api, inquiry_path(pending) + "/responses", deferred_body)) == deferred
    assert call(api, inquiry_path(pending) + "/responses", {**deferred_body, "note": "Changed"})[0] == 409
    refused = successful(call(api, inquiry_path(pending) + "/responses", {
        "requestId": "terminal-response", "decision": "refuse",
    }))
    assert call(api, inquiry_path(refused) + "/responses", {
        "requestId": "competing-response", "decision": "offer", "selections": body["selections"],
    })[0] == 409


@pytest.mark.parametrize("native_status", ["dispatching", "running", "failed", "unknown"])
def test_unresolved_or_failed_native_attempt_cannot_open_continuation(tmp_path, native_status):
    trace = TraceStore(tmp_path / "blocked.db")
    api = EidosAPI(trace)
    try:
        created = successful(call(api, body=create_body(trace)))
        claimed, _ = api.investigations.claim(created["id"], created["currentContextId"])
        if native_status != "dispatching":
            api.investigations.update_attempt(created["id"], status=native_status)
        assert call(api, f"/{created['id']}/continuation", continuation_body(claimed))[0] == 409
        restored = successful(call(api, f"/{created['id']}", method="GET"))
        assert restored["attempt"]["id"] == claimed["attempt"]["id"]
        assert restored["attempt"]["status"] == native_status
        assert not restored.get("continuation")
        assert not [record for record in trace.records() if record.method == "turn/start"]
    finally:
        api.close()
        trace.close()


def test_inquiry_is_scoped_and_http_cannot_supply_live_authority(native):
    api, trace, completed, _ = native
    pending = begin(api, completed)
    other = successful(call(api, body=create_body(trace, "other")))
    inquiry = pending["continuation"]["inquiry"]["id"]
    foreign = f"/{other['id']}/inquiries/{inquiry}"
    before = occurrences(api)
    assert call(api, foreign, method="GET")[0] == 404
    assert call(api, foreign + "/responses", {"requestId": "foreign", "decision": "refuse"})[0] == 404
    assert call(api, f"/{pending['id']}/inquiries/unknown", method="GET")[0] == 404
    for field in ("holder", "executor", "program", "protocol", "projection", "checkpoint", "cut", "authority"):
        historical_name = pending["continuation"]["initialCheckpointId"]
        assert call(api, f"/{pending['id']}/continuation", {
            **continuation_body(completed), field: historical_name,
        })[0] == 400
        assert call(api, inquiry_path(pending) + "/responses", {
            "requestId": f"inject-{field}", "decision": "refuse", field: historical_name,
        })[0] == 400
        assert call(api, f"/{pending['id']}/resume", {field: historical_name})[0] == 400
    for path in ("/api/trusted/commit_projection_occurrence", "/api/processes/advance",
                 "/api/investigations/commit_projection_occurrence"):
        assert api.dispatch(Handler({"checkpoint": pending["continuation"]["checkpointId"]}), "POST", path, {})[0] == 404
    assert occurrences(api) == before


@pytest.mark.parametrize("decision", ["defer", "refuse"])
def test_only_offer_can_supply_selections_and_offer_requires_them(native, decision):
    api, _, completed, body = native
    pending = begin(api, completed)
    before = occurrences(api)
    assert call(api, inquiry_path(pending) + "/responses", {
        "requestId": "invalid-selections", "decision": decision, "selections": body["selections"],
    })[0] == 400
    assert call(api, inquiry_path(pending) + "/responses", {
        "requestId": "missing-selections", "decision": "offer",
    })[0] == 400
    assert occurrences(api) == before
    assert not successful(call(api, inquiry_path(pending), method="GET"))["responses"]


def test_concurrent_terminal_responses_admit_one_causal_decision(native):
    api, _, completed, body = native
    pending = begin(api, completed)
    responses = [
        {"requestId": "race-offer", "decision": "offer", "selections": body["selections"]},
        {"requestId": "race-refuse", "decision": "refuse", "note": "Scope denied."},
    ]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda body: call(api, inquiry_path(pending) + "/responses", body), responses))
    assert sum(200 <= status < 300 for status, _ in results) == 1, results
    assert sum(status == 409 for status, _ in results) == 1, results
    final = successful(call(api, f"/{pending['id']}/resume", {}))
    admitted = final["continuation"]["inquiry"]["responses"]
    assert len(admitted) == 1 and admitted[0]["status"] == "committed"
    decisions = [row for row in occurrences(api) if row[1] in {"DiscoveryOffer", "DiscoveryRefuse"}]
    assert len(decisions) == 1 and decisions[0][0] == admitted[0]["occurrenceId"]
    assert final["artifact"]["responseId"] == admitted[0]["id"]


def test_adopted_native_result_cannot_be_reopened(native):
    api, _, completed, _ = native
    successful(call(api, f"/{completed['id']}/adoption", {
        "artifactId": completed["artifact"]["id"], "decision": "adopt",
    }))
    assert call(api, f"/{completed['id']}/continuation", continuation_body(completed))[0] == 409


def test_duplicate_response_across_independent_controllers_commits_once(native, tmp_path):
    first, _, completed, _ = native
    pending = begin(first, completed)
    second_trace = TraceStore(tmp_path / "investigation.db")
    second = EidosAPI(second_trace)
    response = {"requestId": "concurrent-delivery", "decision": "refuse", "note": "One reviewed answer."}
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(
                lambda api: call(api, inquiry_path(pending) + "/responses", response),
                (first, second),
            ))
        views = [successful(result) for result in results]
        assert all(view["continuation"]["error"] is None for view in views), views
        responses = [view["continuation"]["inquiry"]["responses"] for view in views]
        assert all(len(values) == 1 for values in responses)
        assert len({values[0]["id"] for values in responses}) == 1
        final = successful(call(first, f"/{pending['id']}/resume", {}))
        assert final["status"] == "completed"
        assert successful(call(second, f"/{pending['id']}", method="GET")) == final
        decisions = [row for row in occurrences(first) if row[1] == "DiscoveryRefuse"]
        assert len(decisions) == 1
        assert final["artifact"]["decisionOccurrenceId"] == decisions[0][0]
        assert len([record for record in second_trace.records() if record.method == "turn/start"]) == 1
    finally:
        second.close()
        second_trace.close()
