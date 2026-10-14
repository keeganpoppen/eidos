"""Managed preparation through the real private worker, authored stdio only."""
import importlib.util
import json
from pathlib import Path
import threading

import pytest

from eidos.native_managed_contract import ManagedPolicy
from eidos.private_investigation import PrivateEvidenceError, PrivateInvestigationWorker
from eidos.trace import TraceStore
from test_owned_attempt_worker import launch, until, join, requests

_spec = importlib.util.spec_from_file_location("managed_demo", Path(__file__).parents[1] / "scripts/managed_attempt_demo.py")
demo = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(demo)


def packet(name):
    context = {"id": "context-" + name, "question": "One pinned managed question", "projectedPrompt": "C0 [evidence:7]",
               "records": [{"seq": 7, "rawText": "authored public support"}]}
    attempt = {"id": "attempt-" + name, "contextId": context["id"], "timeoutSeconds": 3,
               "source": None, "threadId": None, "turnId": None}
    return attempt, context


@pytest.fixture
def prepared(tmp_path):
    trace = TraceStore(tmp_path / "work.db")
    workers = []
    def create(*, release=False, mode="complete", profile=None):
        profile = profile or demo.authored_profile(tmp_path / "runtime", release=release, mode=mode,
            policy=ManagedPolicy(preparation_seconds=5, turn_seconds=3, lifetime_seconds=9))
        worker = PrivateInvestigationWorker(trace, managed_profile=profile)
        workers.append(worker)
        return worker, profile
    yield trace, create
    for worker in workers:
        worker.close()
        worker.close_evidence()
    trace.close()


def test_actual_managed_preparation_publishes_exact_private_result_and_reopens(prepared):
    trace, create = prepared
    worker, _ = create(release=True)
    attempt, context = packet("one")
    result = worker.run(attempt, context, lambda **fields: attempt.update(fields))
    assert result["executionEvidence"] == "synthetic"
    assert result["text"] == "Authored managed result [evidence:7]."
    assert result["citations"] == [7]
    proof = worker.resolve_result_evidence(attempt, context, result)
    records = proof["trace"].records()
    assert [r.method for r in trace.records()] == ["$capsule/result"]
    assert "NEMA-FIXTURE" not in "\n".join(trace.db.iterdump())
    assert "PRIVATE_MANAGED" not in "\n".join(trace.db.iterdump())
    assert "NEMA-FIXTURE" in "\n".join(r.raw_text for r in records)
    admission = next(r for r in records if r.method == "$native/managedAdmission")
    thread = next(r for r in records if r.method == "thread/start")
    turn = next(r for r in records if r.method == "turn/start")
    assert admission.seq < thread.seq < turn.seq
    assert admission.message["params"]["identity"]["source"] == attempt["source"]
    assert next(r for r in records if r.method == "$native/managedClose").message["params"]["complete"] is True
    assert worker.inspect_owned(attempt["id"]) == {"owned": False, "canCancel": False}
    worker.close()
    worker.close_evidence()
    reopened = TraceStore(trace.path)
    reader = PrivateInvestigationWorker(reopened, command=["/never-start"])
    try:
        assert reader.recover(attempt, context) == result
        assert reader.inspect_owned(attempt["id"]) == {"owned": False, "canCancel": False}
    finally:
        reader.close()
        reader.close_evidence()
        reopened.close()


def test_cancelled_admitted_a_does_not_lend_readiness_to_b(prepared, tmp_path):
    _, create = prepared
    worker, profile = create(mode="waiting-turn")
    a, ca = packet("A")
    ta, oa, _ = launch(worker, a, ca)
    until(lambda: worker.inspect_owned(a["id"]).get("signIn") is not None)
    directories = list((tmp_path / "runtime").iterdir())
    assert len(directories) == 1
    da = directories[0]
    (da / "release-login").touch()
    until(lambda: any(r.get("method") == "turn/start" for r in requests(da)))
    assert "signIn" not in worker.inspect_owned(a["id"])
    worker.cancel(a["id"])
    join(ta)
    assert isinstance(oa.get("error"), PrivateEvidenceError)
    assert worker.recover(a, ca) is None

    b, cb = packet("B")
    tb, ob, _ = launch(worker, b, cb)
    until(lambda: worker.inspect_owned(b["id"]).get("signIn") is not None)
    db = next(path for path in (tmp_path / "runtime").iterdir() if path != da)
    assert profile is worker.managed_profile
    assert not any(r.get("method") in {"thread/start", "turn/start"} for r in requests(db))
    assert worker.inspect_owned(a["id"]) == {"owned": False, "canCancel": False}
    worker.cancel(b["id"])
    join(tb)
    assert isinstance(ob.get("error"), PrivateEvidenceError)
    assert len([r for r in requests(da) if r.get("method") == "account/login/start"]) == 1
    assert len([r for r in requests(db) if r.get("method") == "account/login/start"]) == 1


def test_stop_signals_blocked_startup_guard_and_prevents_late_child(prepared, tmp_path, monkeypatch):
    import eidos.codex as codex
    from eidos.native_managed import ManagedExecutionProfile
    trace, create = prepared
    entered, release = threading.Event(), threading.Event()
    class HeldStartup(demo.AuthoredRuntime):
        def require_contained_startup(self):
            super().require_contained_startup()
            entered.set()
            assert release.wait(3)
    def runtime(cwd, **kwargs):
        return HeldStartup(tmp_path / "held-startup", cwd, **kwargs)
    worker, _ = create(profile=ManagedExecutionProfile(runtime_factory=runtime))
    popen_calls = []
    original = codex.subprocess.Popen
    def record_popen(*args, **kwargs):
        popen_calls.append(args)
        return original(*args, **kwargs)
    monkeypatch.setattr(codex.subprocess, "Popen", record_popen)
    attempt, context = packet("startup")
    running, outcome, _ = launch(worker, attempt, context)
    stopping = None
    try:
        assert entered.wait(2)
        inner = worker._owned[attempt["id"]].worker
        stopping = threading.Thread(target=worker.cancel, args=(attempt["id"],))
        stopping.start()
        assert inner._cancelled.wait(1), "Stop must signal before waiting for the startup lock"
    finally:
        release.set()
        join(running)
        if stopping is not None:
            join(stopping)
    assert isinstance(outcome.get("error"), PrivateEvidenceError)
    assert popen_calls == []
    assert trace.records() == []
    assert worker.inspect_owned(attempt["id"]) == {"owned": False, "canCancel": False}


@pytest.mark.parametrize("cleanup_fails,marker_fails", [(True, False), (True, True), (False, True)])
def test_unconfirmed_managed_cleanup_blocks_publication_even_with_completed_terminal(
        prepared, tmp_path, monkeypatch, cleanup_fails, marker_fails):
    trace, create = prepared
    from eidos.native_managed import ManagedExecutionProfile
    class FailedCleanup(demo.AuthoredRuntime):
        def close(self, reason="closed", *, wait=True):
            report = super().close(reason, wait=wait)
            return {"allWorkersJoined": False, "errors": ["PRIVATE_CLEANUP_CANARY"]} if cleanup_fails else report
    def runtime(cwd, **kwargs):
        result = FailedCleanup(tmp_path / "bad-cleanup", cwd, **kwargs)
        (result.directory / "release-login").touch()
        return result
    profile = ManagedExecutionProfile(runtime_factory=runtime)
    worker, _ = create(profile=profile)
    if marker_fails:
        from eidos.private_investigation import _PrivateTrace
        append = _PrivateTrace.append
        def reject_marker(self, **kwargs):
            if kwargs.get("message", {}).get("method") == "$native/managedClose":
                raise PrivateEvidenceError("record-limit-reached")
            return append(self, **kwargs)
        monkeypatch.setattr(_PrivateTrace, "append", reject_marker)
    attempt, context = packet("cleanup")
    with pytest.raises(PrivateEvidenceError):
        worker.run(attempt, context, lambda **fields: attempt.update(fields))
    assert trace.records() == []
    private = next(iter(worker._stores.values()))
    assert any(r.method == "turn/completed" for r in private.records())
    if marker_fails:
        assert not any(r.method == "$native/managedClose" for r in private.records())
        assert worker.recover(attempt, context) is None
    else:
        assert any(r.method == "$native/managedClose" and r.message["params"]["complete"] is False for r in private.records())
        with pytest.raises(PrivateEvidenceError):
            worker.recover(attempt, context)


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "foreign", "incomplete", "late-native", "early"])
def test_historical_managed_completion_requires_one_matching_final_closure(prepared, tmp_path, mutation):
    from eidos.investigation_worker import NativeInvestigationError
    _, create = prepared
    worker, _ = create(release=True)
    attempt, context = packet("closure")
    result = worker.run(attempt, context, lambda **fields: attempt.update(fields))
    original = worker.resolve_result_evidence(attempt, context, result)["trace"].records()
    closure = next(record for record in original if record.method == "$native/managedClose")
    copied = TraceStore(tmp_path / "copied.db")
    try:
        def append(record, message=None):
            copied.append(source=record.source, direction=record.direction, message=message or record.message)
        for record in original:
            if mutation == "early" and record.method == "turn/completed":
                append(closure)
            if record is closure:
                if mutation in {"missing", "early"}:
                    continue
                message = json.loads(record.raw_text)
                if mutation == "foreign":
                    message["params"]["identity"]["attemptId"] = "attempt-other"
                if mutation == "incomplete":
                    message["params"]["complete"] = False
                append(record, message)
                if mutation == "duplicate":
                    append(record)
            else:
                append(record)
        if mutation == "late-native":
            copied.append(source=attempt["source"], direction="appserver_to_client",
                          message={"method": "future/nativeEvent", "params": {"unknown": "preserved"}})
        recovered_worker = worker._worker(copied)
        if mutation == "missing":
            assert recovered_worker.recover(attempt, context) is None
        else:
            with pytest.raises(NativeInvestigationError, match="shutdown remains unconfirmed"):
                recovered_worker.recover(attempt, context)
    finally:
        copied.close()


def test_late_or_foreign_admission_cannot_relabel_existing_source(prepared):
    _, create = prepared
    worker, _ = create(release=True)
    attempt, context = packet("receipt")
    result = worker.run(attempt, context, lambda **fields: attempt.update(fields))
    proof = worker.resolve_result_evidence(attempt, context, result)
    private = proof["trace"]
    admission = next(r for r in private.records() if r.method == "$native/managedAdmission")
    forged = json.loads(admission.raw_text)
    forged["params"]["identity"]["attemptId"] = "attempt-other"
    private.append(source=attempt["source"], direction="internal", message=forged)
    recovered = worker._worker(private).recover(attempt, context)
    assert recovered["executionEvidence"] == "unverified"
    assert worker.inspect_owned(attempt["id"]) == {"owned": False, "canCancel": False}
