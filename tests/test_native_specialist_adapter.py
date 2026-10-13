"""Synthetic protocol evidence; these tests do not establish native model support."""

from dataclasses import asdict

import pytest

from eidos.investigation_worker import (
    NativeInvestigationError, NativeInvestigationWorker, NativeSpecialistAdapter,
    UnsupportedNativeOperation,
)
from eidos.trace import TraceStore


CONTEXT = {"id": "context", "projectedPrompt": "Synthetic context packet.", "records": []}
ATTEMPT = {"id": "attempt", "contextId": "context", "source": "owned/incarnation"}


def append(trace, message, direction="appserver_to_client", source="owned/incarnation"):
    return trace.append(source=source, direction=direction, message=message)


def prepared(*, ack=True):
    trace = TraceStore()
    append(trace, {"id": 1, "method": "thread/start", "params": {}}, "client_to_appserver")
    append(trace, {"id": 1, "result": {"thread": {"id": "thread"}}})
    append(trace, {"id": 2, "method": "turn/start", "params": {
        "threadId": "thread", "input": [{"type": "text", "text": CONTEXT["projectedPrompt"]}],
    }}, "client_to_appserver")
    if ack:
        append(trace, {"id": 2, "result": {"turn": {"id": "turn", "status": "inProgress"}}})
    events = []
    adapter = NativeSpecialistAdapter(trace, ATTEMPT, CONTEXT, ATTEMPT["source"], events.append)
    adapter.refresh()
    return trace, adapter, events


def request(rpc_id=100, *, blocking=True, method="item/tool/requestUserInput", **params):
    return {"id": rpc_id, "method": method, "futureEnvelope": ["preserved"], "params": {
        "threadId": "thread", "turnId": "turn", "itemId": "question-item",
        "isBlocking": blocking,
        "questions": [{"id": "question", "header": "Evidence", "question": "More context?"}],
        **params,
    }}


def terminal(status="completed", *, error=None):
    return {"method": "turn/completed", "params": {"threadId": "thread", "turn": {
        "id": "turn", "status": status, "error": error, "items": [
            {"id": "answer", "type": "agentMessage", "phase": "final", "text": "Synthetic answer."},
        ],
    }}}


def test_request_event_has_durable_coordinates_and_preserves_unknown_raw_evidence():
    trace, adapter, events = prepared()
    record = append(trace, request())
    emitted = adapter.refresh()
    assert emitted == (events[-1],)
    event = emitted[0]
    assert event.kind == "request_pending"
    assert (event.attempt_id, event.context_id, event.source) == ("attempt", "context", "owned/incarnation")
    assert (event.thread_id, event.turn_id, event.item_id) == ("thread", "turn", "question-item")
    assert event.rpc_id == 100 and event.is_blocking is True
    assert event.evidence_seqs == (record.seq,)
    assert trace.get(event.evidence_seqs[0]).message["futureEnvelope"] == ["preserved"]
    assert asdict(event)["schema_version"] == 1
    assert adapter.refresh() == ()


def test_pre_ack_request_is_observed_and_subsequent_ack_must_agree():
    trace, adapter, _ = prepared(ack=False)
    append(trace, request())
    assert adapter.refresh()[-1].request_state == "pending"
    append(trace, {"id": 2, "result": {"turn": {"id": "different-turn"}}})
    assert adapter.refresh()[-1].kind == "correlation_conflict"
    assert adapter.ambiguous


def test_nonblocking_request_never_means_native_execution_is_suspended():
    trace, adapter, _ = prepared()
    append(trace, request(blocking=False))
    adapter.refresh()
    assert adapter.pending_requests[0].is_blocking is False
    append(trace, terminal())
    assert adapter.refresh()[-1].terminal_state == "completed"
    assert not adapter.ambiguous


def test_duplicate_request_keeps_one_pending_identity_and_one_default_refusal():
    trace, adapter, _ = prepared()
    first = append(trace, request())
    second = append(trace, request())
    events = adapter.refresh()
    assert [event.kind for event in events] == ["request_pending", "request_duplicate"]
    assert len(adapter.pending_requests) == 1
    assert adapter.pending_requests[0].evidence_seqs == (first.seq, second.seq)
    assert adapter.refuse_once(request()) is True
    assert adapter.refuse_once(request()) is False


def test_same_id_changed_request_is_conflicting_and_never_a_second_authority():
    trace, adapter, _ = prepared()
    append(trace, request())
    append(trace, request(itemId="changed-item"))
    assert adapter.refresh()[-1].request_state == "conflict"
    assert adapter.ambiguous
    assert adapter.pending_requests == ()
    assert adapter.refuse_once(request()) is False
    append(trace, terminal())
    with pytest.raises(NativeInvestigationError, match="contradictory"):
        NativeInvestigationWorker(trace, ["/must/not/launch"]).recover(ATTEMPT, CONTEXT)


def test_integer_and_string_rpc_ids_are_distinct_and_boolean_is_invalid():
    trace, adapter, _ = prepared()
    append(trace, request(1))
    append(trace, request("1"))
    append(trace, request(True))
    events = adapter.refresh()
    assert events[0].request_key != events[1].request_key
    assert len(adapter.pending_requests) == 2
    assert events[-1].rpc_id is None
    assert events[-1].request_state == "unsupported"
    assert not adapter.refuse_once(request(True))


@pytest.mark.parametrize("params", [{"threadId": "foreign"}, {"turnId": "foreign"},
                                    {"isBlocking": 1}, {"questions": []}, {"itemId": None}])
def test_malformed_or_foreign_request_never_becomes_controller_pending(params):
    trace, adapter, _ = prepared()
    append(trace, request(**params))
    assert adapter.refresh()[-1].request_state == "unsupported"


def test_text_question_and_dynamic_tool_shape_do_not_create_input_capability():
    trace, adapter, _ = prepared()
    append(trace, {"method": "item/completed", "params": {
        "threadId": "thread", "turnId": "turn", "item": {
            "id": "prose", "type": "agentMessage", "text": "Could you send more evidence?",
        },
    }})
    assert adapter.refresh()[-1].kind == "observed"
    assert adapter.pending_requests == ()
    append(trace, request(method="item/tool/call", tool="request_evidence", arguments={}))
    assert adapter.refresh()[-1].request_state == "unsupported"


def test_resolution_matches_exact_rpc_type_and_thread_and_does_not_claim_an_answer():
    trace, adapter, _ = prepared()
    append(trace, request())
    adapter.refresh()
    for rpc_id, thread in [(True, "thread"), ("100", "thread"), (100, "foreign")]:
        append(trace, {"method": "serverRequest/resolved", "params": {"requestId": rpc_id, "threadId": thread}})
        assert adapter.refresh()[-1].kind == "observed"
        assert len(adapter.pending_requests) == 1
    append(trace, {"method": "serverRequest/resolved", "params": {"requestId": 100, "threadId": "thread"}})
    event = adapter.refresh()[-1]
    assert event.request_state == "resolved"
    assert "unspecified" in event.detail
    assert adapter.pending_requests == ()
    assert adapter.refuse_once(request()) is False


def test_recorded_refusal_is_not_proof_of_native_receipt_or_resolution():
    trace, adapter, _ = prepared()
    append(trace, request())
    adapter.refresh()
    append(trace, {"id": 100, "error": {"code": -32000, "message": "unsupported"}}, "client_to_appserver")
    assert adapter.refresh()[-1].request_state == "response_recorded"
    assert len(adapter.pending_requests) == 1


@pytest.mark.parametrize("reason", ["timeout", "controller cancellation", "process EOF"])
def test_local_cancellation_abandons_request_without_claiming_native_terminal(reason):
    trace, adapter, events = prepared()
    append(trace, request())
    adapter.refresh()
    adapter.close(reason)
    assert events[-2].kind == "request_abandoned"
    assert events[-2].request_state == "abandoned"
    assert events[-1].terminal_state == "unknown"
    assert adapter.pending_requests == ()
    count = len(events)
    adapter.close(reason)
    assert len(events) == count


def test_completed_turn_with_unanswered_blocking_request_remains_ambiguous():
    trace, adapter, _ = prepared()
    append(trace, request())
    append(trace, terminal())
    assert adapter.refresh()[-1].terminal_state == "unknown"
    with pytest.raises(NativeInvestigationError, match="contradictory"):
        NativeInvestigationWorker(trace, ["/must/not/launch"]).recover(ATTEMPT, CONTEXT)


@pytest.mark.parametrize("statuses", [("completed", "failed"), ("failed", "completed")])
def test_conflicting_terminal_observations_are_unknown(statuses):
    trace, adapter, _ = prepared()
    for status in statuses:
        append(trace, terminal(status))
    assert adapter.refresh()[-1].terminal_state == "unknown"


def test_restarted_projection_is_evidence_only_and_cannot_answer_historical_request():
    trace, adapter, _ = prepared()
    append(trace, request())
    adapter.refresh()
    records_before = trace.records()
    replay = NativeSpecialistAdapter(trace, ATTEMPT, CONTEXT, ATTEMPT["source"])
    replay.refresh()
    pending = replay.pending_requests[0]
    with pytest.raises(UnsupportedNativeOperation, match="cannot authorize"):
        replay.respond(pending.request_key, {"question": {"answers": ["disclose"]}})
    assert trace.records() == records_before


def test_foreign_incarnation_never_creates_a_pending_request():
    trace, adapter, _ = prepared()
    append(trace, request(), source="foreign/incarnation")
    assert adapter.refresh() == ()
    assert adapter.pending_requests == ()


def test_projection_rejects_an_explicit_source_that_contradicts_the_attempt():
    trace, _, _ = prepared()
    with pytest.raises(ValueError, match="source contradicts"):
        NativeSpecialistAdapter(trace, ATTEMPT, CONTEXT, "foreign/incarnation")


@pytest.mark.parametrize("mutation", ["prompt", "thread", "duplicate"])
def test_unadmitted_or_ambiguous_turn_dispatch_does_not_create_pending_input(mutation):
    trace, _, _ = prepared()
    if mutation == "prompt":
        context = {**CONTEXT, "projectedPrompt": "Substituted context."}
    else:
        context = CONTEXT
        append(trace, {"id": 3, "method": "turn/start", "params": {
            "threadId": "foreign" if mutation == "thread" else "thread",
            "input": [{"type": "text", "text": CONTEXT["projectedPrompt"]}],
        }}, "client_to_appserver")
    adapter = NativeSpecialistAdapter(trace, ATTEMPT, context, ATTEMPT["source"])
    append(trace, request())
    assert adapter.refresh()[-1].request_state == "unsupported"
    assert adapter.ambiguous


@pytest.mark.parametrize("ids", [[""], ["same", "same"]])
def test_ambiguous_question_ids_are_not_pending_input(ids):
    trace, adapter, _ = prepared()
    append(trace, request(questions=[{"id": value, "header": "Evidence", "question": "More?"} for value in ids]))
    assert adapter.refresh()[-1].request_state == "unsupported"


def test_recorded_response_without_native_resolution_is_ambiguous_at_completion():
    trace, adapter, _ = prepared()
    append(trace, request())
    append(trace, {"id": 100, "error": {"code": -32000, "message": "unsupported"}}, "client_to_appserver")
    append(trace, terminal())
    assert adapter.refresh()[-1].terminal_state == "unknown"
    with pytest.raises(NativeInvestigationError, match="contradictory"):
        NativeInvestigationWorker(trace, ["/must/not/launch"]).recover(ATTEMPT, CONTEXT)


def test_late_request_after_local_close_does_not_resurrect_a_pending_interaction():
    trace, adapter, _ = prepared()
    adapter.close("controller cancellation")
    append(trace, request())
    assert adapter.refresh()[-1].request_state == "abandoned"
    assert adapter.pending_requests == ()
    assert not adapter.refuse_once(request())


def test_refresh_reads_only_new_source_records_without_materializing_global_history(monkeypatch):
    trace, adapter, _ = prepared()
    for index in range(30):
        append(trace, {"method": "unrelated", "params": {"index": index}}, source="foreign/incarnation")
    monkeypatch.setattr(trace, "records", lambda **kwargs: pytest.fail("adapter must not materialize global history"))
    assert adapter.refresh() == ()
    last_foreign = adapter._cursor
    observed = append(trace, request())
    assert observed.seq > last_foreign
    assert adapter.refresh()[-1].evidence_seqs == (observed.seq,)
    assert adapter.refresh() == ()
