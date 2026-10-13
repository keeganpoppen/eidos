"""Owner control is local to the exact live attempt, independently of history."""
from __future__ import annotations

import threading
import importlib.util
import json
from pathlib import Path
import time

import pytest

from eidos.api import EidosAPI
from eidos.investigation import InvestigationError
from eidos.trace import TraceStore
from test_investigation_continuations_api import call, create_body, successful


class HeldOwner:
    execution_profile = None
    execution_evidence = "synthetic"

    def __init__(self):
        self.handles = {}
        self.calls = []
        self.entered = threading.Event()
        self.finished = set()

    def reserve(self, attempt_id):
        assert attempt_id not in self.handles
        self.handles[attempt_id] = threading.Event()
        self.calls.append(("reserve", attempt_id))

    def inspect_owned(self, attempt_id):
        stop = self.handles.get(attempt_id)
        owned = stop is not None and attempt_id not in self.finished
        return {"owned": owned, "canCancel": owned and not stop.is_set()}

    def cancel(self, attempt_id):
        self.calls.append(("cancel", attempt_id))
        self.handles[attempt_id].set()

    def run(self, attempt, context, update):
        key = attempt["id"]
        assert key in self.handles
        self.calls.append(("run", key))
        update(lifecycle={"phase": "awaiting-sign-in"})
        self.entered.set()
        assert self.handles[key].wait(3), "test did not cancel the held owner"
        update(lifecycle={"phase": "closed", "stopReason": "cancelled"})
        self.finished.add(key)
        raise RuntimeError("PRIVATE_OWNER_ERROR_CANARY")

    def recover(self, *args):
        return None

    def public_error(self, exc):
        return "Owned fixture stopped."

    def close(self):
        for stop in self.handles.values():
            stop.set()


@pytest.fixture
def owned(tmp_path):
    trace = TraceStore(tmp_path / "owned.db")
    api = EidosAPI(trace)
    api.investigation_worker.close()
    api.investigation_worker.close_evidence()
    owner = HeldOwner()
    api.investigation_worker = owner
    value = successful(call(api, body=create_body(trace)))
    try:
        yield api, trace, owner, value
    finally:
        api.close()
        trace.close()


def start(api, value):
    return successful(call(api, f"/{value['id']}/dispatch", {"contextId": value["currentContextId"]}))


def control_path(value):
    return f"/{value['id']}/attempts/{value['attempt']['id']}/control"


def test_owned_control_pins_context_and_retry_cannot_reopen_work(owned):
    api, trace, owner, value = owned
    dispatched = start(api, value)
    assert owner.entered.wait(1)
    path = control_path(dispatched)
    key = dispatched["attempt"]["id"]
    assert successful(call(api, path, method="GET")) == {"attemptId": key, "owned": True, "canCancel": True}
    pending = api.investigations.get(value["id"])
    assert pending["contexts"] == value["contexts"]
    assert pending["attempt"]["contextId"] == value["currentContextId"]
    assert pending["attempt"]["lifecycle"]["phase"] == "awaiting-sign-in"
    successful(call(api, path, {"action": "cancel"}))
    api._investigation_threads[value["id"]].join(1)
    stopped = successful(call(api, path, {"action": "cancel"}))
    assert stopped["control"] == {"attemptId": key, "owned": False, "canCancel": False}
    assert stopped["investigation"]["attempt"]["lifecycle"]["stopReason"] == "cancelled"
    assert stopped["investigation"]["status"] == "unknown"
    assert stopped["investigation"]["artifact"] is None
    assert "PRIVATE_" not in str(stopped)
    assert owner.calls == [("reserve", key), ("run", key), ("cancel", key)]
    assert start(api, value)["attempt"]["id"] == key
    assert len(owner.calls) == 3


def test_reservation_exists_before_thread_start_and_can_be_cancelled(owned, monkeypatch):
    api, trace, owner, value = owned
    original = threading.Thread.start
    held = []
    with monkeypatch.context() as patch:
        patch.setattr(threading.Thread, "start", lambda thread: held.append(thread))
        dispatched = start(api, value)
    key = dispatched["attempt"]["id"]
    assert owner.calls == [("reserve", key)]
    successful(call(api, control_path(dispatched), {"action": "cancel"}))
    assert owner.handles[key].is_set()
    original(held[0])
    held[0].join(1)
    assert not held[0].is_alive()
    assert api.investigations.get(value["id"])["status"] == "unknown"


def test_control_rejects_foreign_attempt_and_execution_parameters(owned):
    api, trace, owner, value = owned
    dispatched = start(api, value)
    assert owner.entered.wait(1)
    other = successful(call(api, body=create_body(trace, "foreign")))
    foreign = control_path(dispatched).replace(value["id"], other["id"])
    assert call(api, foreign, {"action": "cancel"})[0] == 404
    assert call(api, control_path(dispatched), {"action": "cancel", "command": "untrusted"})[0] == 400
    assert call(api, control_path(dispatched), {"action": "start"})[0] == 400
    assert successful(call(api, control_path(dispatched), method="GET"))["canCancel"] is True
    assert not any(name == "cancel" for name, _ in owner.calls)


def test_new_controller_cannot_reconstruct_owned_control(owned):
    api, trace, owner, value = owned
    dispatched = start(api, value)
    assert owner.entered.wait(1)
    peer_trace = TraceStore(trace.path)
    peer = EidosAPI(peer_trace)
    try:
        before = list(owner.calls)
        control = successful(call(peer, control_path(dispatched), method="GET"))
        assert control == {"attemptId": dispatched["attempt"]["id"], "owned": False, "canCancel": False}
        repeated = successful(call(peer, control_path(dispatched), {"action": "cancel"}))
        assert repeated["control"] == control
        assert owner.calls == before
        assert not owner.handles[dispatched["attempt"]["id"]].is_set()
        assert successful(call(api, control_path(dispatched), method="GET"))["canCancel"] is True
    finally:
        peer.close()
        peer_trace.close()


def test_cancel_failure_is_fixed_public_error_and_exact_owned_retry(owned, monkeypatch):
    api, _, owner, value = owned
    dispatched = start(api, value)
    assert owner.entered.wait(1)
    key = dispatched["attempt"]["id"]
    original = owner.cancel
    attempts = []
    def fault(identifier):
        attempts.append(identifier)
        if len(attempts) == 1:
            raise OSError("PRIVATE_CANCEL_ERROR_CANARY")
        original(identifier)
    monkeypatch.setattr(owner, "cancel", fault)
    assert call(api, control_path(dispatched), {"action": "cancel"}) == (
        503, {"error": "Attempt stop was not confirmed; retry this same attempt."})
    successful(call(api, control_path(dispatched), {"action": "cancel"}))
    api._investigation_threads[dispatched["id"]].join(1)
    assert attempts == [key, key]


@pytest.mark.parametrize("bad", [
    {"phase": "running", "code": "PRIVATE_CODE"}, {"phase": "closed", "stopReason": ["failed"]},
    {"phase": "running", "stopReason": "cancelled"}, {"phase": "ready", "authority": True},
])
def test_lifecycle_rejects_non_descriptive_fields(owned, bad):
    api, _, _, value = owned
    claimed, _ = api.investigations.claim(value["id"], value["currentContextId"])
    with pytest.raises(InvestigationError, match="invalid attempt lifecycle"):
        api.investigations.update_attempt(value["id"], expected_attempt_id=claimed["attempt"]["id"], lifecycle=bad)
    assert api.investigations.get(value["id"]) == claimed


def test_closed_lifecycle_does_not_reopen_or_change_result_status(owned):
    api, _, _, value = owned
    claimed, _ = api.investigations.claim(value["id"], value["currentContextId"])
    key = claimed["attempt"]["id"]
    def update(**fields):
        return api.investigations.update_attempt(value["id"], expected_attempt_id=key, **fields)
    update(status="failed")
    closed = update(lifecycle={"phase": "closed", "stopReason": "failed"})
    assert closed["status"] == "failed"
    assert closed["attempt"]["lifecycle"]["version"] == 1
    assert update(lifecycle={"phase": "running"}) == closed
    assert update(lifecycle={"phase": "closed", "stopReason": "completed"}) == closed


def test_stop_observation_after_completion_preserves_the_exact_artifact(owned):
    api, trace, _, value = owned
    claimed, _ = api.investigations.claim(value["id"], value["currentContextId"])
    key = claimed["attempt"]["id"]
    record = trace.append(source="authored-result", direction="internal", message={
        "method": "$history/item", "params": {"threadId": "authored", "turnId": "authored-turn",
        "item": {"id": "result", "type": "agentMessage", "text": "Recorded completion."}}})
    completed = api.investigations.complete(value["id"], {"text": "Recorded completion.",
        "outputSeqs": [record.seq], "executionEvidence": "synthetic"}, expected_attempt_id=key)
    closed = api.investigations.update_attempt(value["id"], expected_attempt_id=key,
        lifecycle={"phase": "closed", "stopReason": "cancelled"}, status="unknown", error="Late closure.")
    assert closed["artifact"] == completed["artifact"]
    assert closed["status"] == closed["attempt"]["status"] == "completed"
    assert closed["attempt"]["error"] is None
    assert closed["attempt"]["lifecycle"]["stopReason"] == "cancelled"


def test_authored_preparation_cancel_release_and_restart_use_real_api(tmp_path):
    spec = importlib.util.spec_from_file_location("owned_demo", Path(__file__).parents[1] / "scripts/owned_attempt_demo.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    path = tmp_path / "owned-demo.db"
    marker = module.seed(path)
    directory = Path(marker["fixtureDirectory"])
    trace = TraceStore(path)
    api = module.make_api(trace)

    def until(identifier, predicate):
        deadline = time.monotonic() + 4
        while time.monotonic() < deadline:
            value = successful(call(api, "/" + identifier, method="GET"))
            assert "PRIVATE_" not in json.dumps(value)
            if predicate(value):
                return value
            time.sleep(.005)
        pytest.fail("authored API preparation did not reach the expected state")

    def requests():
        return [json.loads(line) for line in (directory / "requests.jsonl").read_text().splitlines()]

    try:
        cancel = marker["investigations"]["cancel"]
        dispatched = successful(call(api, "/" + cancel["investigationId"] + "/dispatch", {"contextId": cancel["contextId"]}))
        key = dispatched["attempt"]["id"]
        pending = until(dispatched["id"], lambda v: v["attempt"].get("lifecycle", {}).get("phase") == "awaiting-sign-in")
        assert pending["contexts"] == dispatched["contexts"]
        assert successful(call(api, control_path(dispatched), method="GET"))["canCancel"] is True
        successful(call(api, control_path(dispatched), {"action": "cancel"}))
        api._investigation_threads[dispatched["id"]].join(3)
        assert not api._investigation_threads[dispatched["id"]].is_alive()
        stopped = successful(call(api, control_path(dispatched), {"action": "cancel"}))
        assert stopped["control"] == {"attemptId": key, "owned": False, "canCancel": False}
        assert stopped["investigation"]["attempt"]["lifecycle"]["stopReason"] == "cancelled"
        assert stopped["investigation"]["status"] == "unknown"
        (directory / "release-login").touch()
        assert not any(r.get("method") in {"thread/start", "turn/start"} for r in requests())
        assert (directory / "launches").read_text() == "started\n"

        # A separate admitted attempt can proceed; stale stop remains scoped.
        (directory / "release-login").unlink()
        release = marker["investigations"]["release"]
        second = successful(call(api, "/" + release["investigationId"] + "/dispatch", {"contextId": release["contextId"]}))
        until(second["id"], lambda v: v["attempt"].get("lifecycle", {}).get("phase") == "awaiting-sign-in")
        successful(call(api, control_path(dispatched), {"action": "cancel"}))
        assert successful(call(api, control_path(second), method="GET"))["canCancel"] is True
        (directory / "release-login").touch()
        completed = until(second["id"], lambda v: v["status"] == "completed")
        api._investigation_threads[second["id"]].join(3)
        turn = [r for r in requests() if r.get("method") == "turn/start"]
        context = next(c for c in second["contexts"] if c["id"] == release["contextId"])
        assert len(turn) == 1 and turn[0]["params"]["input"] == [{"type": "text", "text": context["projectedPrompt"]}]
        assert completed["artifact"]["executionEvidence"] == "synthetic"
        assert completed["artifact"]["outputEvidence"]["kind"] == "private-capsule-publication"
        assert "PRIVATE_" not in "\n".join(trace.db.iterdump())
    finally:
        api.close()
        trace.close()

    before = requests()
    assert (directory / "launches").read_text() == "started\nstarted\n"
    assert module.inspect(path) == marker
    reopened = TraceStore(path)
    api = module.make_api(reopened)
    try:
        for value in (dispatched, second):
            state = successful(call(api, control_path(value), method="GET"))
            assert state == {"attemptId": value["attempt"]["id"], "owned": False, "canCancel": False}
            assert successful(call(api, control_path(value), {"action": "cancel"}))["control"] == state
        assert successful(call(api, "/" + second["id"], method="GET"))["artifact"] == completed["artifact"]
        assert requests() == before
        assert (directory / "launches").read_text() == "started\nstarted\n"
    finally:
        api.close()
        reopened.close()
