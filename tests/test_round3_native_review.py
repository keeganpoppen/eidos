"""Independent containment/provenance checks; all protocol evidence is synthetic."""
from __future__ import annotations

from pathlib import Path
import sys

import pytest

from eidos.codex import NativeExecutionProfile
from eidos.investigation_worker import NativeInvestigationError, NativeInvestigationWorker
from eidos.trace import TraceStore


CONTEXT = {"id": "context", "projectedPrompt": "A synthetic evidence packet.", "records": []}
ATTEMPT = {"id": "attempt", "contextId": "context", "source": "owned/review",
           "threadId": "thread", "turnId": "turn", "timeoutSeconds": 2}


def recorded_result(*profiles, after=None):
    trace = TraceStore()
    for direction, params, source in profiles:
        trace.append(source=source, direction=direction, message={
            "method": "$native/profile", "params": params,
        })
    trace.append(source=ATTEMPT["source"], direction="client_to_appserver", message={
        "id": 1, "method": "turn/start", "params": {
            "threadId": "thread", "input": [{"type": "text", "text": CONTEXT["projectedPrompt"]}],
        },
    })
    trace.append(source=ATTEMPT["source"], direction="appserver_to_client", message={
        "id": 1, "result": {"turn": {"id": "turn"}},
    })
    trace.append(source=ATTEMPT["source"], direction="appserver_to_client", message={
        "method": "turn/completed", "params": {"threadId": "thread", "turn": {
            "id": "turn", "status": "completed", "items": [{
                "id": "answer", "type": "agentMessage", "phase": "final_answer",
                "text": "Synthetic evidence, including the phrase native-observed.",
            }],
        }},
    })
    if after is not None:
        trace.append(source=ATTEMPT["source"], direction="internal", message={
            "method": "$native/profile", "params": after,
        })
    return trace


SYNTHETIC = {"admission": "custom-command-trusted-host", "executionEvidence": "synthetic"}
ADMITTED = {"admission": "admitted", "profile": {
    "version": NativeExecutionProfile.VERSION,
    "binarySha256": NativeExecutionProfile.BINARY_SHA256,
    "liveAdmitted": True,
}}


@pytest.mark.parametrize("profiles,expected", [
    ([], "unverified"),
    ([("internal", SYNTHETIC, ATTEMPT["source"])], "synthetic"),
    ([("internal", {"admission": "custom-command-trusted-host"}, ATTEMPT["source"])], "unverified"),
    ([("appserver_to_client", ADMITTED, ATTEMPT["source"])], "unverified"),
    ([("internal", ADMITTED, "foreign/incarnation")], "unverified"),
    ([("internal", {"admission": "admitted", "profile": {"liveAdmitted": True}}, ATTEMPT["source"])], "unverified"),
    ([("internal", SYNTHETIC, ATTEMPT["source"]),
      ("internal", {"admission": "refused"}, ATTEMPT["source"])], "unverified"),
])
def test_output_provenance_requires_preceding_host_admission_in_same_incarnation(profiles, expected):
    trace = recorded_result(*profiles)
    try:
        original = [(r.seq, r.raw_text) for r in trace.records()]
        result = NativeInvestigationWorker(trace, ["must-not-launch"]).recover(ATTEMPT, CONTEXT)
        assert result["executionEvidence"] == expected
        assert [(r.seq, r.raw_text) for r in trace.records()] == original
    finally:
        trace.close()


def test_later_profile_or_current_constructor_cannot_relabel_historical_output():
    trace = recorded_result(after=ADMITTED)
    try:
        worker = NativeInvestigationWorker(trace, ["must-not-launch"], execution_evidence="synthetic")
        assert worker.recover(ATTEMPT, CONTEXT)["executionEvidence"] == "unverified"
    finally:
        trace.close()


def test_native_observation_cannot_be_declared_by_constructor():
    trace = TraceStore()
    try:
        with pytest.raises(ValueError, match="only synthetic or unverified"):
            NativeInvestigationWorker(trace, ["must-not-launch"], execution_evidence="native-observed")
    finally:
        trace.close()


def test_fixture_provenance_survives_recovery_with_a_different_worker():
    trace = TraceStore()
    fixture = Path(__file__).parent / "fixtures/investigation_appserver.py"
    worker = NativeInvestigationWorker(
        trace, [sys.executable, str(fixture)], execution_evidence="synthetic",
    )
    state = {**ATTEMPT, "source": None, "threadId": None, "turnId": None}
    try:
        result = worker.run(state, CONTEXT, lambda **fields: state.update(fields))
        assert result["executionEvidence"] == "synthetic"
        replay = NativeInvestigationWorker(trace, ["must-not-launch"])
        assert replay.recover(state, CONTEXT) == result
    finally:
        worker.close()
        trace.close()


def test_terminal_inquiry_protocol_origin_does_not_assert_genuine_model_execution():
    from eidos.investigation_inquiries import terminal_inquiry
    from test_investigation_inquiry_adapter import recorded_inquiry

    store, worker, identifier, _, _ = recorded_inquiry()
    try:
        state = store.get(identifier)
        recovered = worker.recover(state["attempt"], state["contexts"][0])
        assert recovered["executionEvidence"] == "unverified"
        assert terminal_inquiry(store, identifier, worker)["origin"] == "native-specialist"
    finally:
        store.trace.close()


@pytest.mark.parametrize("method", ["turn/completed", "item/completed"])
def test_server_request_envelope_cannot_supply_a_completion_notification(method):
    trace = TraceStore()
    try:
        trace.append(source=ATTEMPT["source"], direction="client_to_appserver", message={
            "id": 1, "method": "turn/start", "params": {
                "threadId": "thread", "input": [{"type": "text", "text": CONTEXT["projectedPrompt"]}],
            },
        })
        item = {"id": "answer", "type": "agentMessage", "phase": "final_answer", "text": "Synthetic answer"}
        params = {"threadId": "thread"}
        if method == "turn/completed":
            params["turn"] = {"id": "turn", "status": "completed", "items": [item]}
        else:
            params.update(turnId="turn", item=item)
        trace.append(source=ATTEMPT["source"], direction="appserver_to_client", message={
            "id": 50, "method": method, "params": params,
        })
        if method == "item/completed":
            trace.append(source=ATTEMPT["source"], direction="appserver_to_client", message={
                "method": "turn/completed", "params": {"threadId": "thread", "turn": {
                    "id": "turn", "status": "completed", "items": [],
                }},
            })
        original = [(r.seq, r.raw_text) for r in trace.records()]
        with pytest.raises(NativeInvestigationError, match="RPC request"):
            NativeInvestigationWorker(trace, ["must-not-launch"]).recover(ATTEMPT, CONTEXT)
        assert [(r.seq, r.raw_text) for r in trace.records()] == original
    finally:
        trace.close()
