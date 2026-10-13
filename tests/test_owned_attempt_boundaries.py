"""Independent ownership schedules using authored subprocesses, never native Codex."""
from __future__ import annotations

from pathlib import Path
import sys
import threading

import pytest

from eidos.private_investigation import PrivateEvidenceError, PrivateInvestigationWorker
from eidos.trace import TraceStore


FIXTURE = Path(__file__).parent / "fixtures" / "private_investigation_server.py"


def packet(name):
    context = {"id": "context-" + name, "projectedPrompt": "Authored input [evidence:7].",
               "records": [{"seq": 7, "rawText": "Synthetic support."}]}
    attempt = {"id": "attempt-" + name, "contextId": context["id"], "timeoutSeconds": 3,
               "source": None, "threadId": None, "turnId": None}
    return attempt, context


def adapter(trace, marker, preparation=None):
    return PrivateInvestigationWorker(
        trace, [sys.executable, str(FIXTURE), "conclusion", str(marker)],
        execution_evidence="synthetic", preparation=preparation, preparation_timeout=3,
    )


def launch(worker, attempt, context, name):
    outcomes, updates = [], []

    def update(**fields):
        attempt.update(fields)
        updates.append(fields)

    def run():
        try:
            outcomes.append(worker.run(attempt, context, update))
        except Exception as exc:
            outcomes.append(exc)

    thread = threading.Thread(target=run, name=name)
    thread.start()
    return thread, outcomes, updates


def finish(worker, threads=()):
    worker.close()
    for thread in threads:
        thread.join(4)
        assert not thread.is_alive(), "authored worker did not close"
    worker.close_evidence()


def test_cancel_between_durable_claim_and_child_registration(tmp_path, monkeypatch):
    trace = TraceStore(tmp_path / "main.db")
    marker = tmp_path / "launches"
    worker = adapter(trace, marker)
    attempt, context = packet("registration")
    claimed, release = threading.Event(), threading.Event()
    original_claim = worker._claim

    def held_claim(*args):
        binding = original_claim(*args)
        claimed.set()
        assert release.wait(3), "test did not release the post-claim boundary"
        return binding

    monkeypatch.setattr(worker, "_claim", held_claim)
    worker.reserve(attempt["id"])
    thread, outcomes, updates = launch(worker, attempt, context, "registration")
    try:
        assert claimed.wait(2)
        assert worker.inspect_owned(attempt["id"]) == {"owned": True, "canCancel": True}
        worker.cancel("unowned-attempt")
        assert worker.inspect_owned(attempt["id"])["canCancel"] is True
        worker.cancel(attempt["id"])
        assert worker.inspect_owned(attempt["id"])["canCancel"] is False
        release.set()
        thread.join(3)
        assert not thread.is_alive()
        assert len(outcomes) == 1 and isinstance(outcomes[0], PrivateEvidenceError)
        assert not marker.exists()
        assert trace.records() == []
        assert updates[-1]["lifecycle"] == {"phase": "closed", "stopReason": "cancelled"}
        assert worker.inspect_owned(attempt["id"]) == {"owned": False, "canCancel": False}
    finally:
        release.set()
        finish(worker, [thread])
        trace.close()


def test_prelaunch_cancellation_cannot_be_resurrected_after_reopen(tmp_path):
    path, marker = tmp_path / "main.db", tmp_path / "launches"
    attempt, context = packet("cancelled-before-run")
    trace = TraceStore(path)
    worker = adapter(trace, marker)
    try:
        worker.reserve(attempt["id"])
        worker.cancel(attempt["id"])
        with pytest.raises(PrivateEvidenceError):
            worker.run(attempt, context, lambda **fields: attempt.update(fields))
        assert not marker.exists()
        assert not list(worker.root.glob("*/evidence.sqlite"))
        assert trace.db.execute("SELECT COUNT(*) FROM private_investigation_bindings").fetchone()[0] == 1
        assert trace.records() == []
    finally:
        finish(worker)
        trace.close()

    reopened = TraceStore(path)
    peer = adapter(reopened, marker)
    try:
        assert peer.inspect_owned(attempt["id"]) == {"owned": False, "canCancel": False}
        peer.cancel(attempt["id"])
        peer.reserve(attempt["id"])
        assert peer.inspect_owned(attempt["id"]) == {"owned": False, "canCancel": False}
        assert peer.recover(attempt, context) is None
        with pytest.raises(PrivateEvidenceError) as error:
            peer.run(attempt, context, lambda **_: pytest.fail("replay callback"))
        assert error.value.status == "unknown"
        assert "no task was resent" in str(error.value)
        assert not marker.exists()
        assert reopened.records() == []
        assert not list(peer.root.glob("*/evidence.sqlite"))
    finally:
        finish(peer)
        reopened.close()


def test_stale_cancellation_does_not_close_another_owned_attempt(tmp_path):
    trace, marker = TraceStore(tmp_path / "main.db"), tmp_path / "launches"
    entered = {name: threading.Event() for name in ("first", "second")}
    release_second = threading.Event()

    def prepare(preparation):
        name = threading.current_thread().name
        preparation.phase("awaiting-sign-in")
        entered[name].set()
        while name == "first" or not release_second.is_set():
            try:
                preparation.recv_event(timeout=0.02)
            except TimeoutError:
                pass

    worker = adapter(trace, marker, prepare)
    first, first_context = packet("first")
    second, second_context = packet("second")
    first_thread, first_result, _ = launch(worker, first, first_context, "first")
    second_thread = None
    try:
        assert entered["first"].wait(2)
        second_thread, second_result, _ = launch(worker, second, second_context, "second")
        assert entered["second"].wait(2)
        worker.cancel(first["id"])
        first_thread.join(3)
        assert not first_thread.is_alive()
        assert len(first_result) == 1 and isinstance(first_result[0], PrivateEvidenceError)
        for stale in (first["id"], "foreign-attempt", first["contextId"]):
            worker.cancel(stale)
        assert second_thread.is_alive()
        assert worker.inspect_owned(second["id"]) == {"owned": True, "canCancel": True}
        release_second.set()
        second_thread.join(3)
        assert not second_thread.is_alive()
        assert len(second_result) == 1 and isinstance(second_result[0], dict)
        assert second_result[0]["executionEvidence"] == "synthetic"
        assert marker.read_text().splitlines() == ["started", "started"]
        assert len(trace.records()) == 1
        assert "PRIVATE_" not in "\n".join(trace.db.iterdump())
    finally:
        release_second.set()
        finish(worker, [thread for thread in (first_thread, second_thread) if thread is not None])
        trace.close()


def test_second_adapter_cannot_acquire_live_control_or_disturb_preparation(tmp_path):
    path, marker = tmp_path / "main.db", tmp_path / "launches"
    trace = TraceStore(path)
    entered, release = threading.Event(), threading.Event()

    def prepare(preparation):
        preparation.phase("awaiting-sign-in")
        entered.set()
        while not release.is_set():
            try:
                preparation.recv_event(timeout=0.02)
            except TimeoutError:
                pass

    owner = adapter(trace, marker, prepare)
    attempt, context = packet("live-owner")
    thread, outcomes, updates = launch(owner, attempt, context, "live-owner")
    peer_trace, peer = None, None
    try:
        assert entered.wait(2)
        peer_trace = TraceStore(path)
        peer = adapter(peer_trace, marker)
        peer.reserve(attempt["id"])
        peer.cancel(attempt["id"])
        assert peer.inspect_owned(attempt["id"]) == {"owned": False, "canCancel": False}
        assert peer.recover(attempt, context) is None
        with pytest.raises(PrivateEvidenceError):
            peer.run(attempt, context, lambda **_: pytest.fail("foreign recovery callback"))
        assert owner.inspect_owned(attempt["id"]) == {"owned": True, "canCancel": True}
        assert thread.is_alive() and trace.records() == []
        assert updates[-1]["lifecycle"]["phase"] == "awaiting-sign-in"
        release.set()
        thread.join(3)
        assert not thread.is_alive()
        assert len(outcomes) == 1 and isinstance(outcomes[0], dict)
        assert peer.recover(attempt, context) == outcomes[0]
        assert marker.read_text().splitlines() == ["started"]
    finally:
        release.set()
        finish(owner, [thread])
        if peer is not None:
            finish(peer)
        if peer_trace is not None:
            peer_trace.close()
        trace.close()
