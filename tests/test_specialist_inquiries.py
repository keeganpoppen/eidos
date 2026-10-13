"""Synthetic specialist/API evidence, with no provider, credentials, or subprocess.

Recorded native events exercise the existing worker's recovery reader. They do
not establish that native interactive callbacks are supported or a hidden model
continuation survives; the second turn always has a separate outer admission.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
from threading import Barrier, Event
import time

import pytest

from eidos.api import EidosAPI
from eidos.investigation import InvestigationError
from eidos.investigation_worker import NativeInvestigationWorker
from eidos.process_runtime import ProcessRuntime
from eidos.trace import TraceStore

from test_investigation_continuations_api import (
    call, checkpoint_socket, create_body, inquiry_path, occurrences, successful,
)


QUESTION = {
    "schemaVersion": 1,
    "kind": "nema-needs-evidence",
    "question": "Which recorded event supports the claimed recovery guarantee?",
    "cause": "The selected evidence omits the acknowledgement and terminal outcome.",
}


class Crash(BaseException):
    """Abrupt local interruption, bypassing ordinary visible error handling."""


def die(*args, **kwargs):
    raise Crash("synthetic interruption")


class SpecialistWorker(NativeInvestigationWorker):
    """Only writes synthetic evidence; reuses real recovery attribution checks."""

    def __init__(self, trace, *, question=True, failure=None, entered=None, release=None):
        super().__init__(trace, command=["/must/not/execute-native"])
        self.question = question
        self.failure = failure
        self.entered = entered
        self.release = release
        self.launched = []

    def run(self, attempt, context, update):
        self.launched.append(attempt["id"])
        if self.entered is not None:
            self.entered.set()
        if self.release is not None:
            assert self.release.wait(5), "test did not release synthetic native result"
        state = dict(attempt)

        def remember(**fields):
            update(**fields)
            state.update(fields)

        source = "synthetic-specialist:" + attempt["id"]
        thread = "synthetic-thread:" + attempt["id"]
        turn = "synthetic-turn:" + attempt["id"]
        remember(source=source, threadId=thread)
        if self.failure == "before-request":
            raise RuntimeError("interrupted before native request")
        self.trace.append(source=source, direction="client_to_appserver", message={
            "id": 1, "method": "turn/start", "params": {
                "threadId": thread,
                "input": [{"type": "text", "text": context["projectedPrompt"]}],
            },
        })
        if self.failure == "after-request":
            raise RuntimeError("interrupted after native request")
        self.trace.append(source=source, direction="appserver_to_client", message={
            "id": 1, "result": {"turn": {"id": turn}},
        })
        remember(turnId=turn, status="running")
        text = json.dumps(QUESTION) if self.question else (
            "The offered material is attributable evidence, not established truth. "
            f"Review the recorded claim [evidence:{context['records'][0]['seq']}]."
        )
        item = {"id": "result", "type": "agentMessage", "phase": "final_answer", "text": text,
                "futureNativeField": {"preserve": ["unknown", 42]}}
        self.trace.append(source=source, direction="appserver_to_client", message={
            "method": "item/completed", "params": {
                "threadId": thread, "turnId": turn, "item": item,
            },
        })
        self.trace.append(source=source, direction="appserver_to_client", message={
            "method": "turn/completed", "params": {
                "threadId": thread,
                "turn": {"id": turn, "status": "completed", "items": [item], "error": None},
            },
        })
        return self.recover(state, context)


def wait_for(api, identifier, predicate):
    deadline = time.monotonic() + 5
    last = None
    while time.monotonic() < deadline:
        last = api.investigations.get(identifier)
        if predicate(last):
            return last
        time.sleep(0.01)
    raise AssertionError(f"synthetic worker did not settle: {last!r}")


def native_turns(trace):
    return [record for record in trace.records() if record.method == "turn/start"]


def pending_specialist(api, trace, *, key="specialist"):
    api.investigation_worker = SpecialistWorker(trace)
    body = create_body(trace, key)
    created = successful(call(api, body=body))
    successful(call(api, f"/{created['id']}/dispatch", {"contextId": created["currentContextId"]}))
    result = wait_for(api, created["id"], lambda value: (
        value.get("continuation") is not None and value["continuation"]["inquiry"] is not None
    ))
    assert result["continuation"]["origin"] == "native-specialist"
    assert result["continuation"]["inquiry"]["status"] == "pending"
    assert len(native_turns(trace)) == 1
    return result, body


@pytest.fixture
def specialist(tmp_path):
    trace = TraceStore(tmp_path / "specialist.db")
    api = EidosAPI(trace)
    pending, body = pending_specialist(api, trace)
    try:
        yield api, trace, pending, body
    finally:
        api.close()
        trace.close()


def answer(api, pending, body, *, key="offer"):
    offered = successful(call(api, inquiry_path(pending) + "/responses", {
        "requestId": key, "decision": "offer", "selections": body["selections"],
        "note": "This is an attributed source claim, subject to review.",
    }))
    result = successful(call(api, f"/{pending['id']}/resume", {}))
    assert result["continuation"]["inquiry"]["status"] == "answered"
    assert result["continuation"]["nativeNext"]["status"] == "awaiting-admission"
    assert offered["continuation"]["id"] == result["continuation"]["id"]
    return result


def next_body(answered, request_id="admit-second-native"):
    continuation = answered["continuation"]
    return {"requestId": request_id, "continuationId": continuation["id"],
            "contextId": continuation["nativeNext"]["contextId"]}


def test_specialist_defer_reload_disclose_continue_and_adopt_same_investigation(specialist, tmp_path):
    api, trace, pending, body = specialist
    identifier = pending["id"]
    continuation = pending["continuation"]
    original = pending["nativeArtifact"]
    original_records = [(record.seq, record.raw_text) for record in trace.records()]
    checkpoint = continuation["checkpointId"]
    assert continuation["question"] == QUESTION["question"]
    assert continuation["attemptId"] == pending["attempt"]["id"]
    cause = continuation["cause"]
    assert cause["investigationId"] == identifier
    assert cause["attemptId"] == pending["attempt"]["id"]
    assert cause["contextId"] == pending["attempt"]["contextId"]
    event = cause["nativeEvent"]
    assert event["source"] == pending["attempt"]["source"]
    assert event["threadId"] == pending["attempt"]["threadId"]
    assert event["turnId"] == pending["attempt"]["turnId"]
    assert event["seq"] in original["outputSeqs"]
    assert trace.get(event["seq"]).message["params"]["item"]["futureNativeField"]
    requester_before = occurrences(api, domain=continuation["processId"])
    request = {"requestId": "defer-before-reload", "decision": "defer", "note": "Check disclosure scope."}
    deferred = successful(call(api, inquiry_path(pending) + "/responses", request))
    assert deferred["continuation"]["inquiry"]["status"] == "deferred"
    assert deferred["continuation"]["checkpointId"] == checkpoint
    assert checkpoint_socket(api, checkpoint)["disposition"] == "live"
    assert occurrences(api, domain=continuation["processId"]) == requester_before
    offered_source = trace.append(source="synthetic-offered-source", direction="internal", message={
        "method": "$history/item", "params": {
            "threadId": "additional-source", "turnId": "additional-turn", "item": {
                "id": "unverified-claim", "type": "agentMessage",
                "text": "Source claim: each request ran exactly once. This claim is not independently verified.",
                "futureField": {"preserved": "source assertion only"},
            },
        },
    })
    additional = {"selections": [{"threadId": "additional-source", "startSeq": offered_source.seq,
                                 "endSeq": offered_source.seq, "rationale": "Review the missing source assertion."}]}
    api.close()

    restored_trace = TraceStore(tmp_path / "specialist.db")
    restored = EidosAPI(restored_trace)
    try:
        reloaded = successful(call(restored, f"/{identifier}", method="GET"))
        assert reloaded["continuation"]["inquiry"]["status"] == "deferred"
        assert reloaded["continuation"]["checkpointId"] == checkpoint
        answered = answer(restored, reloaded, additional)
        assert answered["attempt"] == pending["attempt"]
        assert answered["nativeArtifact"] == original
        assert len(native_turns(restored_trace)) == 1
        response = answered["continuation"]["inquiry"]["responses"][-1]
        assert response["decision"] == "offer"
        assert response["evidenceContext"]["selections"] == additional["selections"]
        for record in response["evidenceContext"]["records"]:
            assert record["rawText"] == restored_trace.get(record["seq"]).raw_text
        tm = restored.investigation_runtime.trusted
        disclosure = tm.authority_occurrence(response["occurrenceId"])
        assert disclosure["kind"] == "DiscoveryOffer"
        assert disclosure["domain_name"] != continuation["processId"]
        outcome = tm.named_eidos_value(answered["continuation"]["outcomeId"])["value"]
        assert response["occurrenceId"] not in {event.value for event in outcome.get("events")}
        assert checkpoint_socket(restored, checkpoint)["disposition"] != "live"
        admitted_context = next(c for c in answered["contexts"] if c["id"] == next_body(answered)["contextId"])
        assert admitted_context["parentContextId"] == pending["attempt"]["contextId"]
        assert QUESTION["question"] in admitted_context["projectedPrompt"]
        assert "availability, not factual truth" in admitted_context["projectedPrompt"]
        assert "No hidden model stack is being resumed" in admitted_context["projectedPrompt"]
        assert offered_source.seq in {record["seq"] for record in admitted_context["records"]}
        assert offered_source.seq not in {record["seq"] for record in pending["contexts"][0]["records"]}
        restored.investigation_worker = SpecialistWorker(restored_trace, question=False)
        request = next_body(answered)
        successful(call(restored, f"/{identifier}/continue", request))
        final = wait_for(restored, identifier, lambda value: (
            value["attempt"]["id"] != pending["attempt"]["id"] and value["attempt"]["status"] == "completed"
        ))
        assert final["id"] == identifier and final["nativeArtifact"] == original
        assert final["attemptHistory"] == [pending["attempt"]]
        assert final["artifact"]["attemptId"] == final["attempt"]["id"]
        assert answered["artifact"] in final["artifactHistory"]
        assert final["attempt"]["contextId"] == admitted_context["id"]
        assert final["continuation"]["nativeNext"]["status"] == "dispatched"
        assert final["adoption"] is None
        assert len(native_turns(restored_trace)) == 2
        assert successful(call(restored, f"/{identifier}/continue", request)) == final
        assert successful(call(restored, f"/{identifier}/recover", {})) == final
        adopted = successful(call(restored, f"/{identifier}/adoption", {
            "artifactId": final["artifact"]["id"], "decision": "adopt", "note": "Reviewed source and inference.",
        }))
        assert adopted["adoption"]["artifactId"] == final["artifact"]["id"]
        assert [(restored_trace.get(seq).seq, restored_trace.get(seq).raw_text) for seq, _ in original_records] == original_records
    finally:
        restored.close()
        restored_trace.close()


def test_response_replay_and_copied_names_cannot_change_scope_or_advance(specialist):
    api, trace, pending, body = specialist
    other = successful(call(api, body=create_body(trace, "other")))
    foreign = f"/{other['id']}/inquiries/{pending['continuation']['inquiry']['id']}"
    before = occurrences(api)
    response = {"requestId": "bound-response", "decision": "defer", "note": "Original note"}
    assert call(api, foreign + "/responses", response)[0] == 404
    deferred = successful(call(api, inquiry_path(pending) + "/responses", response))
    committed = occurrences(api)
    assert committed != before
    assert successful(call(api, inquiry_path(pending) + "/responses", response)) == deferred
    assert call(api, inquiry_path(pending) + "/responses", {**response, "note": "Altered note"})[0] == 409
    for field in ("holder", "executor", "checkpoint", "projection", "authority", "protocol"):
        assert call(api, inquiry_path(pending) + "/responses", {
            **response, "requestId": "inject-" + field, field: pending["continuation"]["checkpointId"],
        })[0] == 400
    copied = json.loads(json.dumps(deferred))
    copied["id"] = "copied-specialist"
    trace.db.execute("INSERT INTO investigations VALUES (?,?,?)", (
        copied["id"], copied["createdAtMs"], json.dumps(copied),
    ))
    assert call(api, "/copied-specialist/resume", {})[0] == 409
    assert occurrences(api) == committed
    answered = answer(api, pending, body)
    assert call(api, f"/{other['id']}/continue", next_body(answered))[0] == 409
    assert call(api, f"/{pending['id']}/continue", {
        **next_body(answered), "contextId": pending["attempt"]["contextId"],
    })[0] == 409
    assert len(native_turns(trace)) == 1


def test_refusal_retains_distinct_source_decision_without_disclosure(specialist):
    api, trace, pending, _ = specialist
    refused = successful(call(api, inquiry_path(pending) + "/responses", {
        "requestId": "refusal", "decision": "refuse", "note": "No source disclosure authorized.",
    }))
    assert refused["continuation"]["inquiry"]["status"] == "refused"
    response = refused["continuation"]["inquiry"]["responses"][0]
    assert response["evidenceContext"] is None and response["disclosureCutId"] is None
    assert not [event for event in occurrences(api) if event[1] == "DiscoveryOffer"]
    assert len(native_turns(trace)) == 1


def test_cancel_revokes_host_admission_and_retries_do_not_revive_it(specialist):
    api, trace, pending, body = specialist
    checkpoint = pending["continuation"]["checkpointId"]
    cancellation = {"requestId": "cancel-question", "note": "Stop this evidence inquiry."}
    cancelled = successful(call(api, inquiry_path(pending) + "/cancel", cancellation))
    assert cancelled["continuation"]["inquiry"]["status"] == "cancelled"
    assert cancelled["nativeArtifact"] == pending["nativeArtifact"]
    assert cancelled["continuation"]["checkpointId"] == checkpoint
    assert call(api, f"/{pending['id']}/resume", {})[0] == 409
    committed = occurrences(api)
    assert successful(call(api, inquiry_path(pending) + "/cancel", cancellation)) == cancelled
    assert successful(call(api, f"/{pending['id']}/recover", {})) == cancelled
    assert api.investigations.get(pending["id"]) == cancelled
    assert call(api, inquiry_path(pending) + "/responses", {
        "requestId": "too-late", "decision": "offer", "selections": body["selections"],
    })[0] == 409
    assert call(api, inquiry_path(pending) + "/cancel", {**cancellation, "note": "Changed"})[0] == 409
    assert occurrences(api) == committed and len(native_turns(trace)) == 1


def test_concurrent_continuation_requests_admit_exactly_one_new_attempt(specialist, tmp_path):
    api, trace, pending, body = specialist
    answered = answer(api, pending, body)
    peer_trace = TraceStore(tmp_path / "specialist.db")
    peer = EidosAPI(peer_trace)
    entered, release = Event(), Event()
    api.investigation_worker = SpecialistWorker(trace, question=False, entered=entered, release=release)
    peer.investigation_worker = SpecialistWorker(peer_trace, question=False, entered=entered, release=release)
    barrier = Barrier(2)
    request = next_body(answered)

    def admit(controller):
        barrier.wait(timeout=5)
        return successful(call(controller, f"/{pending['id']}/continue", request))

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            first, duplicate = list(pool.map(admit, (api, peer)))
        assert first["attempt"]["id"] == duplicate["attempt"]["id"]
        assert first["attempt"]["id"] != pending["attempt"]["id"]
        assert entered.wait(5)
        assert len(api.investigation_worker.launched + peer.investigation_worker.launched) == 1
        assert call(peer, f"/{pending['id']}/continue", next_body(answered, "competing-admission"))[0] == 409
        release.set()
        final = wait_for(api, pending["id"], lambda value: value["attempt"]["status"] == "completed")
        causal = occurrences(api)
        assert successful(call(peer, f"/{pending['id']}/continue", request)) == final
        assert successful(call(peer, f"/{pending['id']}/recover", {})) == final
        assert occurrences(api) == causal and len(native_turns(trace)) == 2
    finally:
        release.set()
        peer.close()
        peer_trace.close()


def test_stale_first_attempt_callbacks_cannot_mutate_running_second_attempt(specialist):
    api, trace, pending, body = specialist
    answered = answer(api, pending, body)
    entered, release = Event(), Event()
    api.investigation_worker = SpecialistWorker(trace, question=False, entered=entered, release=release)
    try:
        admitted = successful(call(api, f"/{pending['id']}/continue", next_body(answered)))
        assert entered.wait(5)
        current = api.investigations.get(pending["id"])
        assert current["attempt"]["id"] == admitted["attempt"]["id"]
        with pytest.raises(InvestigationError) as stale:
            api.investigations.update_attempt(
                pending["id"], expected_attempt_id=pending["attempt"]["id"],
                status="failed", error="late first-attempt failure",
            )
        assert stale.value.status == 409
        assert api.investigations.get(pending["id"]) == current
        original = pending["nativeArtifact"]
        payload = {key: original[key] for key in ("text", "outputSeqs", "citations", "unsupportedCitations")}
        with pytest.raises(InvestigationError) as stale:
            api.investigations.complete(
                pending["id"], payload, expected_attempt_id=pending["attempt"]["id"],
            )
        assert stale.value.status == 409
        assert api.investigations.get(pending["id"]) == current
    finally:
        release.set()
    final = wait_for(api, pending["id"], lambda value: value["attempt"]["status"] == "completed")
    assert final["nativeArtifact"] == pending["nativeArtifact"]
    assert len(native_turns(trace)) == 2


@pytest.mark.parametrize("boundary", ["before-admission", "after-admission", "before-request", "after-request", "after-result"])
def test_new_native_attempt_interruptions_never_resend_unknown_work(specialist, tmp_path, monkeypatch, boundary):
    api, trace, pending, body = specialist
    answered = answer(api, pending, body)
    identifier = pending["id"]
    request = next_body(answered)
    worker = SpecialistWorker(trace, question=False, failure=(
        boundary if boundary in {"before-request", "after-request"} else None
    ))
    api.investigation_worker = worker
    with monkeypatch.context() as fault:
        if boundary == "before-admission":
            original = api.investigations._save
            def save(value):
                if value["attempt"]["id"] != pending["attempt"]["id"]:
                    die()
                return original(value)
            fault.setattr(api.investigations, "_save", save)
            with pytest.raises(Crash):
                call(api, f"/{identifier}/continue", request)
            assert api.investigations.get(identifier) == answered
            assert not worker.launched and len(native_turns(trace)) == 1
            return
        if boundary == "after-admission":
            import threading
            def cannot_launch(self):
                raise RuntimeError("interrupted after second attempt admission")
            fault.setattr(threading.Thread, "start", cannot_launch)
        elif boundary == "after-result":
            def lost_completion(*args, **kwargs):
                raise RuntimeError("interrupted after native result before local completion")
            fault.setattr(api.investigations, "complete", lost_completion)
        if boundary == "after-admission":
            with pytest.raises(RuntimeError, match="after second attempt admission"):
                api.continue_investigation(identifier, request)
        else:
            successful(call(api, f"/{identifier}/continue", request))
        interrupted = wait_for(api, identifier, lambda value: (
            value["attempt"]["id"] != pending["attempt"]["id"] and value["attempt"]["status"] == "unknown"
        ))
    assert interrupted["attemptHistory"] == [pending["attempt"]]
    expected_turns = 2 if boundary in {"after-request", "after-result"} else 1
    assert len(native_turns(trace)) == expected_turns
    api.close()
    restored_trace = TraceStore(tmp_path / "specialist.db")
    restored = EidosAPI(restored_trace)
    restored.investigation_worker = SpecialistWorker(restored_trace, question=False)
    try:
        recovered = successful(call(restored, f"/{identifier}/recover", {}))
        expected = "completed" if boundary == "after-result" else "unknown"
        assert recovered["attempt"]["status"] == expected
        assert recovered["attempt"]["id"] == interrupted["attempt"]["id"]
        assert recovered["nativeArtifact"] == pending["nativeArtifact"]
        assert successful(call(restored, f"/{identifier}/continue", request))["attempt"] == recovered["attempt"]
        assert call(restored, f"/{identifier}/continue", next_body(answered, "do-not-resend"))[0] == 409
        assert not restored.investigation_worker.launched
        assert len(native_turns(restored_trace)) == expected_turns
    finally:
        restored.close()
        restored_trace.close()


@pytest.mark.parametrize("boundary", ["preparation", "before-tm", "after-tm", "reintegration"])
def test_specialist_response_crash_recovery_preserves_one_causal_progression(specialist, tmp_path, monkeypatch, boundary):
    api, trace, pending, body = specialist
    identifier = pending["id"]
    before = pending["continuation"]
    response_body = {"requestId": "durable-specialist-offer", "decision": "offer", "selections": body["selections"]}
    tm = api.investigation_runtime.trusted
    with monkeypatch.context() as fault:
        if boundary == "preparation":
            original = tm.bind_eidos_value
            def bind(**kwargs):
                if kwargs["value"].get("$kind") == "CutDisclosure":
                    die()
                return original(**kwargs)
            fault.setattr(tm, "bind_eidos_value", bind)
        elif boundary in {"before-tm", "after-tm"}:
            original = tm.commit_projection_occurrence
            def commit(**kwargs):
                if boundary == "before-tm" and kwargs["kind"] == "DiscoveryOffer":
                    die()
                result = original(**kwargs)
                if boundary == "after-tm" and kwargs["kind"] == "ModelInteraction":
                    die()
                return result
            fault.setattr(tm, "commit_projection_occurrence", commit)
        else:
            fault.setattr(api.investigation_continuations, "_complete", die)
        with pytest.raises(Crash):
            call(api, inquiry_path(pending) + "/responses", response_body)
    interrupted = api.investigations.get(identifier)
    response_before = interrupted["continuation"]["inquiry"]["responses"][0]
    assert response_before["evidenceContext"]["records"]
    assert interrupted["nativeArtifact"] == pending["nativeArtifact"]
    assert len(native_turns(trace)) == 1
    api.close()
    restored_trace = TraceStore(tmp_path / "specialist.db")
    restored = EidosAPI(restored_trace)
    try:
        result = successful(call(restored, f"/{identifier}/resume", {}))
        assert result["continuation"]["inquiry"]["status"] == "answered"
        assert result["continuation"]["nativeNext"]["status"] == "awaiting-admission"
        assert result["continuation"]["processId"] == before["processId"]
        assert result["continuation"]["inquiry"]["id"] == before["inquiry"]["id"]
        response = result["continuation"]["inquiry"]["responses"][0]
        assert response["id"] == response_before["id"]
        assert response["evidenceContext"] == response_before["evidenceContext"]
        if response_before["occurrenceId"] is not None:
            assert response["occurrenceId"] == response_before["occurrenceId"]
        causal = occurrences(restored)
        assert len([event for event in causal if event[1] == "DiscoveryOffer"]) == 1
        assert len([event for event in causal if event[1] == "ModelProcessFinish"]) == 1
        assert successful(call(restored, inquiry_path(result) + "/responses", response_body)) == result
        assert successful(call(restored, f"/{identifier}/resume", {})) == result
        assert occurrences(restored) == causal
        assert len(native_turns(restored_trace)) == 1
    finally:
        restored.close()
        restored_trace.close()


@pytest.mark.parametrize("boundary", ["before-admission", "after-admission", "before-checkpoint", "after-checkpoint"])
def test_native_question_admission_and_checkpoint_recovery_use_same_recorded_turn(tmp_path, monkeypatch, boundary):
    trace = TraceStore(tmp_path / "specialist.db")
    api = EidosAPI(trace)
    api.investigation_worker = SpecialistWorker(trace)
    created = api.investigations.create(create_body(trace))
    claimed, admitted = api.investigations.claim(created["id"], created["currentContextId"])
    assert admitted
    artifact = api.investigation_worker.run(
        claimed["attempt"], claimed["contexts"][0],
        lambda **fields: api.investigations.update_attempt(claimed["id"], **fields),
    )
    completed = api.investigations.complete(created["id"], artifact)
    identifier = completed["id"]
    with monkeypatch.context() as fault:
        if boundary == "before-admission":
            original = api.investigations._save
            def save(value):
                if value.get("continuation") is not None:
                    die()
                return original(value)
            fault.setattr(api.investigations, "_save", save)
        elif boundary == "after-admission":
            fault.setattr(api.investigation_runtime, "start", die)
        else:
            original = ProcessRuntime.checkpoint
            def checkpoint(self, **kwargs):
                if boundary == "before-checkpoint" and kwargs["step"] == 1:
                    die()
                result = original(self, **kwargs)
                if boundary == "after-checkpoint" and kwargs["step"] == 1:
                    die()
                return result
            fault.setattr(ProcessRuntime, "checkpoint", checkpoint)
        with pytest.raises(Crash):
            api.recover_investigation(identifier)
    interrupted = api.investigations.get(identifier)
    assert interrupted["attempt"] == completed["attempt"]
    if boundary == "before-admission":
        assert interrupted.get("continuation") is None
    else:
        assert interrupted["continuation"]["id"]
    api.close()
    trace.close()
    restored_trace = TraceStore(tmp_path / "specialist.db")
    restored = EidosAPI(restored_trace)
    try:
        result = successful(call(restored, f"/{identifier}/recover", {}))
        assert result["continuation"]["origin"] == "native-specialist"
        assert result["continuation"]["inquiry"]["status"] == "pending"
        assert result["nativeArtifact"] == completed["artifact"]
        assert result["attempt"] == completed["attempt"]
        if interrupted.get("continuation"):
            assert result["continuation"]["id"] == interrupted["continuation"]["id"]
        requester = occurrences(restored, domain=result["continuation"]["processId"])
        assert len(requester) == 1
        causal = occurrences(restored)
        assert successful(call(restored, f"/{identifier}/recover", {})) == result
        assert occurrences(restored) == causal
        assert len(native_turns(restored_trace)) == 1
    finally:
        restored.close()
        restored_trace.close()


def test_source_commit_and_failed_recipient_realization_remain_distinct(specialist, monkeypatch):
    api, trace, pending, body = specialist
    checkpoint = pending["continuation"]["checkpointId"]
    with monkeypatch.context() as fault:
        def temporarily_unavailable(*args, **kwargs):
            raise RuntimeError("recipient realization temporarily unavailable")
        fault.setattr(api.investigation_runtime, "advance", temporarily_unavailable)
        interrupted = successful(call(api, inquiry_path(pending) + "/responses", {
            "requestId": "source-offered-before-recipient", "decision": "offer", "selections": body["selections"],
        }))
    continuation = interrupted["continuation"]
    assert continuation["realizationStatus"] == "failed"
    assert "temporarily unavailable" in continuation["error"]
    assert continuation["checkpointId"] == checkpoint and continuation["outcomeId"] is None
    assert checkpoint_socket(api, checkpoint)["disposition"] == "live"
    response = continuation["inquiry"]["responses"][0]
    assert response["status"] == "committed"
    assert api.investigation_runtime.trusted.authority_occurrence(response["occurrenceId"])["kind"] == "DiscoveryOffer"
    assert not [event for event in occurrences(api) if event[1] == "ModelProcessFinish"]
    assert interrupted["artifact"] is None
    result = successful(call(api, f"/{pending['id']}/resume", {}))
    assert result["continuation"]["inquiry"]["status"] == "answered"
    assert result["continuation"]["error"] is None
    assert result["continuation"]["inquiry"]["responses"][0] == response
    assert len(native_turns(trace)) == 1


def test_independent_duplicate_recovery_admits_one_specialist_inquiry(tmp_path):
    trace = TraceStore(tmp_path / "specialist.db")
    api = EidosAPI(trace)
    peer_trace = TraceStore(tmp_path / "specialist.db")
    peer = EidosAPI(peer_trace)
    api.investigation_worker = SpecialistWorker(trace)
    try:
        created = api.investigations.create(create_body(trace))
        claimed, admitted = api.investigations.claim(created["id"], created["currentContextId"])
        assert admitted
        artifact = api.investigation_worker.run(
            claimed["attempt"], claimed["contexts"][0],
            lambda **fields: api.investigations.update_attempt(claimed["id"], **fields),
        )
        completed = api.investigations.complete(created["id"], artifact)
        barrier = Barrier(2)
        def recover(controller):
            barrier.wait(timeout=5)
            return successful(call(controller, f"/{completed['id']}/recover", {}))
        with ThreadPoolExecutor(max_workers=2) as pool:
            first, duplicate = list(pool.map(recover, (api, peer)))
        assert first["continuation"]["id"] == duplicate["continuation"]["id"]
        assert first["continuation"]["inquiry"]["id"] == duplicate["continuation"]["inquiry"]["id"]
        assert first["continuation"]["processId"] == duplicate["continuation"]["processId"]
        assert first["nativeArtifact"] == completed["artifact"]
        assert len(occurrences(api, domain=first["continuation"]["processId"])) == 1
        assert len(native_turns(trace)) == 1
    finally:
        peer.close()
        peer_trace.close()
        api.close()
        trace.close()


def test_followup_question_remains_needs_evidence_without_adoption_or_third_attempt(specialist):
    api, trace, pending, body = specialist
    answered = answer(api, pending, body)
    api.investigation_worker = SpecialistWorker(trace, question=True)
    request = next_body(answered)
    successful(call(api, f"/{pending['id']}/continue", request))
    unresolved = wait_for(api, pending["id"], lambda value: bool(value.get("inquiryAdmissionError")))
    assert unresolved["status"] == "needs-evidence"
    assert unresolved["attempt"]["status"] == "completed"
    assert unresolved["artifact"]["kind"] == "native-needs-evidence"
    assert "one specialist inquiry" in unresolved["inquiryAdmissionError"]
    assert "no further native attempt" in unresolved["inquiryAdmissionError"]
    assert unresolved["nativeArtifact"] == pending["nativeArtifact"]
    assert unresolved["continuation"]["inquiry"]["id"] == pending["continuation"]["inquiry"]["id"]
    assert unresolved["attemptHistory"] == [pending["attempt"]]
    assert call(api, f"/{pending['id']}/adoption", {
        "artifactId": unresolved["artifact"]["id"], "decision": "adopt",
    })[0] == 409
    assert successful(call(api, f"/{pending['id']}/recover", {})) == unresolved
    assert successful(call(api, f"/{pending['id']}/continue", request)) == unresolved
    assert call(api, f"/{pending['id']}/continue", next_body(answered, "third-attempt"))[0] == 409
    assert len(native_turns(trace)) == 2
