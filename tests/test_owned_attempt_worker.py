"""Owned-attempt controls exercised with authored local subprocesses only."""
from pathlib import Path
import json
import sys
import threading
import time

import pytest

from eidos.private_investigation import PrivateEvidenceError, PrivateInvestigationWorker
from eidos.investigation_worker import NativeInvestigationError
from eidos.codex import NativeExecutionProfileError
from eidos.trace import TraceStore


FIXTURE = Path(__file__).parent / "fixtures" / "owned_attempt_server.py"


def preparation(session):
    login = session.request("account/login/start", {"type": "chatgptDeviceCode"})
    session.phase("awaiting-sign-in")
    while True:
        event = session.recv_event()
        if event.get("method") == "account/login/completed":
            assert event["params"]["loginId"] == login["loginId"]
            break
    assert session.recv_event()["method"] == "account/updated"
    session.phase("checking")
    session.request("account/read", {"refreshToken": False})
    session.request("config/read", {"includeLayers": False})


@pytest.fixture
def owned(tmp_path):
    trace = TraceStore(tmp_path / "main.sqlite")
    workers = []

    def create(name="one", mode="complete", hook=preparation, prep_timeout=2, turn_timeout=2):
        directory = tmp_path / name
        worker = PrivateInvestigationWorker(trace, [sys.executable, str(FIXTURE), mode, str(directory)],
            execution_evidence="synthetic", preparation=hook, preparation_timeout=prep_timeout)
        workers.append(worker)
        context = {"id": "context-" + name, "question": "A pinned question", "projectedPrompt": "C0 [evidence:7]",
                   "records": [{"seq": 7, "rawText": "authored support"}]}
        attempt = {"id": "attempt-" + name, "contextId": context["id"], "timeoutSeconds": turn_timeout,
                   "source": None, "threadId": None, "turnId": None}
        return worker, attempt, context, directory

    yield trace, create
    for worker in workers:
        worker.close()
        worker.close_evidence()
    trace.close()


def launch(worker, attempt, context):
    output, progress = {}, []
    def update(**fields):
        progress.append(fields)
        attempt.update(fields)
    def run():
        try:
            output["result"] = worker.run(attempt, context, update)
        except Exception as exc:
            output["error"] = exc
    thread = threading.Thread(target=run)
    thread.start()
    return thread, output, progress


def until(predicate):
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.005)
    pytest.fail("authored synchronization point was not reached")


def requests(directory):
    path = directory / "requests.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def join(thread):
    thread.join(3)
    assert not thread.is_alive()


def test_cancel_before_registration_never_launches_and_cannot_reuse_reservation(owned):
    trace, create = owned
    worker, attempt, context, directory = create()
    worker.cancel("unknown")
    assert worker.inspect_owned("unknown") == {"owned": False, "canCancel": False}
    worker.reserve(attempt["id"])
    assert worker.inspect_owned(attempt["id"]) == {"owned": True, "canCancel": True}
    worker.cancel(attempt["id"])
    worker.cancel(attempt["id"])
    assert worker.inspect_owned(attempt["id"]) == {"owned": True, "canCancel": False}
    thread, output, progress = launch(worker, attempt, context)
    join(thread)
    assert isinstance(output["error"], PrivateEvidenceError)
    assert progress[-1] == {"lifecycle": {"phase": "closed", "stopReason": "cancelled"}}
    worker.reserve(attempt["id"])
    with pytest.raises(PrivateEvidenceError):
        worker.run(attempt, context, lambda **fields: None)
    assert not directory.exists()
    assert worker.inspect_owned(attempt["id"]) == {"owned": False, "canCancel": False}
    assert trace.records() == []
    assert trace.db.execute("SELECT COUNT(*) FROM private_investigation_bindings").fetchone()[0] == 1
    observer, _, _, _ = create("observer")
    assert observer.recover(attempt, context) is None
    with pytest.raises(PrivateEvidenceError):
        observer.run(attempt, context, lambda **fields: pytest.fail("recovery callback"))
    assert not directory.exists()


@pytest.mark.parametrize("mode", ["complete", "blocked-rpc"])
def test_cancel_wakes_preparation_without_sending_a_turn(owned, mode):
    trace, create = owned
    worker, attempt, context, directory = create(mode=mode)
    thread, output, progress = launch(worker, attempt, context)
    until(lambda: any(r.get("method") == "account/login/start" for r in requests(directory)))
    worker.cancel(attempt["id"])
    (directory / "release-login").touch()
    join(thread)
    assert isinstance(output["error"], PrivateEvidenceError)
    assert progress[-1]["lifecycle"] == {"phase": "closed", "stopReason": "cancelled"}
    assert not any(r.get("method") in {"thread/start", "turn/start"} for r in requests(directory))
    assert trace.records() == []


def test_late_successful_hook_cannot_revive_cancelled_client(owned):
    _, create = owned
    held, release = threading.Event(), threading.Event()
    def late(session):
        session.phase("awaiting-sign-in")
        held.set()
        assert release.wait(3)
        return {"future": "PRIVATE_RETURN_CANARY", "ready": True}
    worker, attempt, context, directory = create(hook=late)
    thread, output, progress = launch(worker, attempt, context)
    assert held.wait(3)
    try:
        worker.cancel(attempt["id"])
    finally:
        release.set()
    join(thread)
    assert "result" not in output
    assert progress[-1]["lifecycle"]["stopReason"] == "cancelled"
    assert not any(r.get("method") in {"thread/start", "turn/start"} for r in requests(directory))


def test_preparation_deadline_is_finite_and_separate_from_turn_budget(owned):
    trace, create = owned
    worker, attempt, context, directory = create(prep_timeout=0.12)
    thread, output, progress = launch(worker, attempt, context)
    join(thread)
    assert "error" in output
    assert progress[-1]["lifecycle"]["stopReason"] == "deadline"
    assert not any(r.get("method") == "thread/start" for r in requests(directory))
    other, attempt2, context2, directory2 = create("two", turn_timeout=0.1)
    thread, output, progress = launch(other, attempt2, context2)
    until(lambda: any(r.get("method") == "account/login/start" for r in requests(directory2)))
    time.sleep(0.16)  # Preparation intentionally exceeds the separate turn budget.
    (directory2 / "release-login").touch()
    join(thread)
    assert output["result"]["text"] == "Authored result [evidence:7]."
    assert [p["lifecycle"]["phase"] for p in progress if "lifecycle" in p] == [
        "preparing", "awaiting-sign-in", "checking", "running", "closed"]
    assert "PRIVATE_" not in "\n".join(trace.db.iterdump())


@pytest.mark.parametrize("value", [0, -1, float("inf"), float("nan")])
def test_preparation_deadline_rejects_unbounded_values(owned, value):
    _, create = owned
    with pytest.raises(ValueError, match="finite and positive"):
        create(prep_timeout=value)


@pytest.mark.parametrize("operation", [lambda s: s.request("turn/start", {}), lambda s: s.phase("PRIVATE_PHASE_CANARY")])
def test_preparation_cannot_expand_rpc_or_public_phase_vocabulary(owned, operation):
    trace, create = owned
    worker, attempt, context, directory = create(hook=operation)
    thread, output, progress = launch(worker, attempt, context)
    join(thread)
    assert "error" in output
    assert not any(r.get("method") in {"thread/start", "turn/start"} for r in requests(directory))
    assert progress[-1]["lifecycle"]["stopReason"] == "failed"
    assert "PRIVATE_" not in "\n".join(trace.db.iterdump()) + str(progress)


def test_cancel_after_send_is_unknown_and_history_cannot_restore_ownership(owned):
    trace, create = owned
    worker, attempt, context, directory = create(mode="waiting-turn", hook=None)
    thread, output, progress = launch(worker, attempt, context)
    until(lambda: attempt["turnId"] is not None)
    observer, _, _, _ = create("observer", hook=None)
    assert observer.inspect_owned(attempt["id"]) == {"owned": False, "canCancel": False}
    observer.cancel(attempt["id"])
    assert thread.is_alive()
    worker.cancel(attempt["id"])
    join(thread)
    assert output["error"].status == "unknown"
    assert worker.recover(attempt, context) is None
    observer.reserve(attempt["id"])
    assert observer.inspect_owned(attempt["id"]) == {"owned": False, "canCancel": False}
    with pytest.raises(PrivateEvidenceError):
        observer.run(attempt, context, lambda **fields: pytest.fail("recovery callback"))
    assert (directory / "launches").read_text() == "started\n"
    assert trace.records() == []


def test_cancellation_preserves_completed_prefix_publication(owned, monkeypatch):
    _, create = owned
    worker, attempt, context, _ = create(hook=None)
    held, release = threading.Event(), threading.Event()
    original = worker._worker
    def wrapped(store):
        inner = original(store)
        recover = inner.recover
        def pause(*args):
            artifact = recover(*args)
            if artifact is not None and not release.is_set():
                held.set()
                assert release.wait(3)
            return artifact
        inner.recover = pause
        return inner
    monkeypatch.setattr(worker, "_worker", wrapped)
    thread, output, progress = launch(worker, attempt, context)
    assert held.wait(3)
    try:
        worker.cancel(attempt["id"])
    finally:
        release.set()
    join(thread)
    assert output["result"]["text"] == "Authored result [evidence:7]."
    assert progress[-1]["lifecycle"] == {"phase": "closed", "stopReason": "completed"}
    assert worker.recover(attempt, context) == output["result"]


def test_returned_preparation_session_cannot_send_later_account_requests(owned):
    _, create = owned
    sessions = []
    worker, attempt, context, directory = create(mode="waiting-turn", hook=sessions.append)
    thread, _, _ = launch(worker, attempt, context)
    until(lambda: attempt["turnId"] is not None)
    try:
        with pytest.raises(NativeInvestigationError, match="preparation has ended"):
            sessions[0].request("account/read", {"refreshToken": False})
        assert not any(r.get("method") == "account/read" for r in requests(directory))
    finally:
        worker.cancel(attempt["id"])
        join(thread)


def test_native_gate_is_checked_before_any_preparation_hook(tmp_path, monkeypatch):
    trace = TraceStore(tmp_path / "main.sqlite")
    called = []
    worker = PrivateInvestigationWorker(trace, preparation=lambda session: called.append(session))
    def denied(cwd):
        raise NativeExecutionProfileError("authored gate refusal")
    monkeypatch.setattr(worker.execution_profile, "prepare", denied)
    attempt = {"id": "native-refused", "contextId": "context", "timeoutSeconds": 1}
    context = {"id": "context", "projectedPrompt": "Do not dispatch", "records": []}
    progress = []
    try:
        with pytest.raises(PrivateEvidenceError):
            worker.run(attempt, context, lambda **fields: progress.append(fields))
        assert called == []
        assert progress[-1]["lifecycle"] == {"phase": "closed", "stopReason": "failed"}
        assert trace.records() == []
        assert not any(r.direction == "client_to_appserver" for store in worker._stores.values() for r in store.records())
    finally:
        worker.close()
        worker.close_evidence()
        trace.close()


def test_cancel_close_failure_is_private_and_retry_targets_same_live_worker(owned, monkeypatch):
    trace, create = owned
    worker, attempt, context, directory = create(mode="waiting-turn", hook=None)
    thread, output, progress = launch(worker, attempt, context)
    until(lambda: attempt["turnId"] is not None)
    inner = worker._owned[attempt["id"]].worker
    close = inner.close
    calls = []
    def fail_close():
        calls.append(inner)
        raise OSError("PRIVATE_CLOSE_FAILURE_CANARY exact authored diagnostic")
    monkeypatch.setattr(inner, "close", fail_close)
    try:
        with pytest.raises(PrivateEvidenceError) as caught:
            worker.cancel(attempt["id"])
        assert "PRIVATE_" not in str(caught.value) + worker.public_error(caught.value)
        assert worker.inspect_owned(attempt["id"]) == {"owned": True, "canCancel": False}
        assert thread.is_alive()
        assert progress[-1]["lifecycle"]["phase"] == "running"
        diagnostic = next(r for r in inner.trace.records() if r.method == "$capsule/failure")
        assert diagnostic.source == attempt["source"]
        assert diagnostic.message["params"]["detail"] == "PRIVATE_CLOSE_FAILURE_CANARY exact authored diagnostic"
        assert "PRIVATE_CLOSE_FAILURE_CANARY" not in "\n".join(trace.db.iterdump())
    finally:
        monkeypatch.setattr(inner, "close", close)
        worker.cancel(attempt["id"])
        join(thread)
    assert calls == [inner]
    assert isinstance(output["error"], PrivateEvidenceError)
    assert progress[-1]["lifecycle"]["stopReason"] == "cancelled"
    assert worker.inspect_owned(attempt["id"])["owned"] is False
    assert (directory / "launches").read_text() == "started\n"
