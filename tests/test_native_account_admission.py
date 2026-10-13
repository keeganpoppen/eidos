"""Worker account admission over a synthetic subprocess; no native/model calls."""
from __future__ import annotations

import json
import sys
from types import SimpleNamespace

import pytest

from eidos.codex import NativeExecutionProfile, NativeLaunch
from eidos.investigation_worker import NativeInvestigationError, NativeInvestigationWorker
from eidos.trace import TraceStore


SERVER = r'''
import json, os, sys
account_reply = json.loads(sys.argv[1])
def emit(message):
    print(json.dumps(message), flush=True)
for line in sys.stdin:
    message = json.loads(line)
    ident, method = message.get("id"), message.get("method")
    if method == "initialize":
        result = {"userAgent": "synthetic-account-admission"}
    elif method == "account/read":
        assert message["params"] == {"refreshToken": False}
        emit({"id": ident, **account_reply})
        continue
    elif method == "thread/start":
        result = {"thread": {"id": "thread", "environments": []},
                  "sandbox": {"type": "readOnly", "networkAccess": False},
                  "approvalPolicy": "never", "cwd": os.getcwd()}
    elif method == "mcpServerStatus/list":
        result = {"data": [], "nextCursor": None}
    elif method == "turn/start":
        emit({"id": ident, "result": {"turn": {"id": "turn"}}})
        emit({"method": "turn/completed", "params": {
            "threadId": "thread", "turn": {"id": "turn", "status": "completed",
            "items": [{"id": "answer", "type": "agentMessage", "phase": "final_answer",
                       "text": "Synthetic account admission result."}]}}})
        continue
    else:
        continue
    emit({"id": ident, "result": result})
'''

CONTEXT = {"id": "context", "projectedPrompt": "Inspect synthetic evidence.", "records": []}
CHATGPT = {"account": {"type": "chatgpt", "planType": "pro", "futureAccount": ["kept"]},
           "requiresOpenaiAuth": True, "futureResponse": {"kept": True}}


class FixtureProfile(NativeExecutionProfile):
    """Test-only profile for Python fixture execution, never a NativeLaunch."""

    VERSION = "synthetic-account-profile/1"

    def __init__(self, command):
        self.command = command

    def prepare(self, cwd):
        return SimpleNamespace(
            command=self.command, env={"PATH": "/usr/bin:/bin"}, live_admitted=True,
            evidence={"version": self.VERSION, "liveAdmitted": True},
            require_live_admission=lambda: None,
        )


def execute(tmp_path, reply, *, profiled=True):
    script = tmp_path / "synthetic_account_server.py"
    script.write_text(SERVER)
    trace = TraceStore()
    command = (sys.executable, str(script), json.dumps(reply))
    worker = NativeInvestigationWorker(trace, command, execution_evidence="synthetic")
    if profiled:
        worker.execution_profile = FixtureProfile(command)
    state = {"id": "attempt", "contextId": "context", "timeoutSeconds": 3}
    try:
        result = worker.run(state, CONTEXT, lambda **fields: state.update(fields))
        error = None
    except NativeInvestigationError as exc:
        result, error = None, exc
    finally:
        worker.close()
        records = trace.records()
        trace.close()
    return result, error, records, state


@pytest.mark.parametrize("reply", [
    {"result": {"account": None, "requiresOpenaiAuth": True}},
    {"result": {"account": {"type": "apiKey"}, "requiresOpenaiAuth": True}},
    {"result": {"account": {"type": "amazonBedrock"}, "requiresOpenaiAuth": True}},
    {"result": {"account": {"type": "future"}, "requiresOpenaiAuth": True}},
    {"result": {"account": {"type": "chatgpt"}}},
    {"result": {"account": {"type": "chatgpt"}, "requiresOpenaiAuth": False}},
    {"result": {"account": {"type": "chatgpt"}, "requiresOpenaiAuth": 1}},
    {"result": {"account": "chatgpt", "requiresOpenaiAuth": True}},
    {"result": None},
    {"result": []},
    {},
    {"error": {"code": -32000, "message": "Synthetic account lookup failure"}},
])
def test_account_refusal_prevents_thread_and_turn_creation(tmp_path, reply):
    result, error, records, state = execute(tmp_path, reply)
    assert result is None
    assert error is not None and error.status == "failed"
    assert "subscription admission failed" in str(error)
    requests = [r.method for r in records if r.direction == "client_to_appserver"]
    assert requests == ["initialize", "initialized", "account/read"]
    assert "threadId" not in state and "turnId" not in state


def test_chatgpt_acknowledgement_precedes_thread_and_turn_and_preserves_evidence(tmp_path):
    result, error, records, _ = execute(tmp_path, {"result": CHATGPT})
    assert error is None and result["text"] == "Synthetic account admission result."
    requests = [r for r in records if r.direction == "client_to_appserver"]
    assert [r.method for r in requests] == [
        "initialize", "initialized", "account/read", "thread/start",
        "mcpServerStatus/list", "turn/start",
    ]
    account_request = requests[2]
    assert account_request.message["params"] == {"refreshToken": False}
    account_reply = next(r for r in records if r.direction == "appserver_to_client"
                         and r.message.get("id") == account_request.message["id"])
    assert account_reply.message["result"] == CHATGPT
    assert account_reply.seq < requests[3].seq < requests[-1].seq
    # A synthetic profile must not manufacture actual native provenance.
    assert result["executionEvidence"] == "unverified"


def test_trusted_host_fixture_does_not_require_native_account_rpc(tmp_path):
    result, error, records, _ = execute(tmp_path, {"result": None}, profiled=False)
    assert error is None and result["executionEvidence"] == "synthetic"
    assert all(r.method != "account/read" for r in records)


def test_real_launch_has_no_account_gate_opt_out():
    launch = NativeLaunch(("must-not-launch",), {}, {}, ())
    assert launch.live_admitted is False
    with pytest.raises(RuntimeError, match="cloud configuration"):
        launch.require_live_admission()
