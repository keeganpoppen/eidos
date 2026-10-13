"""Independent capture/recovery acceptance using authored local subprocesses only.

The child is deliberately synthetic. These checks establish recording behavior,
not native admission, caller authentication, or a process resource quota.
"""
from __future__ import annotations

import base64
from dataclasses import asdict
import json
from pathlib import Path
import sys
import time

import pytest

from eidos.codex import AppServerClient, AppServerClosed, AppServerLimits
from eidos.investigation import InvestigationStore
import eidos.investigation_worker as worker_module
from eidos.investigation_worker import NativeInvestigationError, NativeInvestigationWorker
from eidos.trace import TraceStore


GOOD_RAW = ' { "method" : "fixture/kept", "params" : {"future":{"unicode":"λ🦉","unknown":[null,7]}} } '
GOOD = GOOD_RAW.encode() + b"\r\n"
GAP_METHOD = "$transport/captureGap"
SMALL = AppServerLimits(
    max_stdout_frame_bytes=8192, max_stderr_frame_bytes=2048,
    max_received_bytes=32768, max_event_count=8, max_event_bytes=16384,
    max_stderr_tail_bytes=1024, max_stderr_tail_lines=8,
)


def until(predicate, *, timeout=3):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if value := predicate():
            return value
        time.sleep(.005)
    raise AssertionError("synthetic transport did not reach its bounded checkpoint")


def child(tmp_path, body):
    script = tmp_path / "authored_capture_child.py"
    script.write_text("import os, sys, json, time\n" + body)
    return [sys.executable, str(script)]


def gaps(trace):
    return [r for r in trace.records() if r.direction == "internal" and r.method == GAP_METHOD]


def exact_fragment(params, stream):
    if params["stream"] == stream:
        return base64.b64decode(params["capturedBase64"])
    fragment = next(p for p in params["bufferedStreams"] if p["stream"] == stream)
    return base64.b64decode(fragment["capturedBase64"])


@pytest.mark.parametrize("tail", [
    b'{"broken":\n', b'\xff\n', b'[]\n',
    b'{"method":"fixture/projection","emittedAtMs":1e999}\n',
    b'{"method":"\\ud800"}\n',
    b'{"method":"fixture/nonstandard","future":NaN}\n',
    b'{"method":"fixture/nonstandard","future":Infinity}\n',
    b'{"method":"fixture/nonstandard","future":-Infinity}\n',
], ids=["malformed-json", "invalid-utf8", "array", "nonfinite-projection", "surrogate-projection",
        "nan-literal", "infinity-literal", "negative-infinity-literal"])
def test_prior_exact_frame_survives_capture_failure_and_reopen(tmp_path, tail):
    db = tmp_path / "capture.db"
    trace = TraceStore(db)
    command = child(tmp_path, f"os.write(1, {GOOD + tail!r})\nsys.stdin.read()\n")
    with AppServerClient(command, trace=trace, limits=SMALL) as client:
        assert client.recv_event(timeout=2) == json.loads(GOOD_RAW)
        failure = until(lambda: client.capture_status["failure"])
        with pytest.raises(AppServerClosed):
            client.recv_event(timeout=2)
        assert client.capture_status["retainedEventCount"] == 0
        assert client.capture_status["retainedEventBytes"] == 0
        assert failure["captureComplete"] is False
    rows = trace.records()
    accepted = [r for r in rows if r.direction == "appserver_to_client"]
    assert len(accepted) == 1
    assert accepted[0].raw_text == GOOD_RAW
    assert accepted[0].message == json.loads(GOOD_RAW)
    assert len(gaps(trace)) == 1
    diagnostic = gaps(trace)[0]
    assert diagnostic.message["params"]["limits"] == asdict(SMALL)
    assert exact_fragment(diagnostic.message["params"], "stdout") == tail
    # The malformed bytes are encoded inside valid host JSON, never inserted as
    # raw_text that TraceRecord.message or restart recovery cannot parse.
    before = [(r.source, r.direction, r.raw_text, r.message) for r in rows]
    trace.close()
    reopened = TraceStore(db)
    try:
        assert [(r.source, r.direction, r.raw_text, r.message) for r in reopened.records()] == before
    finally:
        reopened.close()


def test_deep_unterminated_json_stops_at_frame_bound_before_decode(tmp_path):
    prefix = b'{"nested":' + b'[' * SMALL.max_stdout_frame_bytes
    command = child(tmp_path, f"os.write(1, {GOOD + prefix!r})\nsys.stdin.read()\n")
    trace = TraceStore(tmp_path / "deep.db")
    with AppServerClient(command, trace=trace, limits=SMALL) as client:
        assert client.recv_event(timeout=2) == json.loads(GOOD_RAW)
        failure = until(lambda: client.capture_status["failure"])
        assert failure["reason"] == "frameBytesLimit"
        assert exact_fragment(failure, "stdout") == prefix[:SMALL.max_stdout_frame_bytes + 1]
        assert client.capture_status["receivedBytes"]["stdout"] <= len(GOOD) + SMALL.max_stdout_frame_bytes + 1
    assert len(gaps(trace)) == 1
    assert [r.raw_text for r in trace.records() if r.direction == "appserver_to_client"] == [GOOD_RAW]
    trace.close()


def test_stdout_eof_does_not_silently_discard_ready_stderr_breach(tmp_path):
    command = child(tmp_path, "os.close(1)\nos.write(2, b'E' * 4096)\ntime.sleep(2)\n")
    trace = TraceStore(tmp_path / "stderr-after-stdout.db")
    with AppServerClient(command, trace=trace, limits=SMALL) as client:
        with pytest.raises(AppServerClosed):
            client.recv_event(timeout=1)
        until(lambda: client.capture_status["failure"])
        failure = client.capture_status["failure"]
        assert failure["captureComplete"] is False
        # Either preserve the bounded offending prefix or explicitly mark the
        # unread stream. A clean status cannot silently imply stderr capture.
        assert failure["stream"] in {"stderr", "transport"}
    assert len(gaps(trace)) == 1
    trace.close()


def test_stderr_breach_retains_already_received_unfinished_stdout_exactly(tmp_path):
    partial = b'{"method":"fixture/unfinished","params":{"text":"\xce'
    command = child(tmp_path,
        f"os.write(1, {GOOD!r})\n"
        "sys.stdin.readline()\n"
        f"os.write(1, {partial!r})\n"
        "sys.stdin.readline()\n"
        "os.write(2, b'E' * 4096)\n"
        "sys.stdin.read()\n")
    trace = TraceStore(tmp_path / "race.db")
    with AppServerClient(command, trace=trace, limits=SMALL) as client:
        assert client.recv_event(timeout=2) == json.loads(GOOD_RAW)
        client.notify("fixture/writePartial")
        until(lambda: client.capture_status["receivedBytes"]["stdout"] >= len(GOOD) + len(partial))
        client.notify("fixture/breachStderr")
        failure = until(lambda: client.capture_status["failure"])
        assert failure["stream"] == "stderr"
        assert failure["reason"] == "frameBytesLimit"
        assert exact_fragment(failure, "stdout") == partial
        assert exact_fragment(failure, "stderr") == b'E' * (SMALL.max_stderr_frame_bytes + 1)
        assert failure["frameComplete"] is False
        assert client.capture_status["receivedBytes"]["stderr"] <= SMALL.max_stderr_frame_bytes + 1
    assert len(gaps(trace)) == 1
    assert next(r for r in trace.records() if r.direction == "appserver_to_client").raw_text == GOOD_RAW
    trace.close()


def test_wait_for_timeouts_cannot_release_undelivered_event_reservations(tmp_path):
    event = lambda n: json.dumps({"method": "fixture/noise", "params": {"n": n}}).encode() + b'\n'
    limits = AppServerLimits(**{**asdict(SMALL), "max_event_count": 4})
    first = b''.join(event(i) for i in range(2))
    later = b''.join(event(i) for i in range(2, 5))
    command = child(tmp_path,
        f"os.write(1, {first!r})\nsys.stdin.readline()\nos.write(1, {later!r})\nsys.stdin.read()\n")
    trace = TraceStore(tmp_path / "retained.db")
    with AppServerClient(command, trace=trace, limits=limits) as client:
        until(lambda: client.capture_status["retainedEventCount"] == 2)
        for _ in range(3):
            with pytest.raises(TimeoutError):
                client.wait_for("fixture/absent", timeout=.02)
            assert client.capture_status["retainedEventCount"] == 2
            assert client.capture_status["retainedEventBytes"] == len(first)
        client.notify("fixture/release")
        until(lambda: client.capture_status["failure"])
        delivered = []
        while True:
            try:
                delivered.append(client.recv_event(timeout=1)["params"]["n"])
            except AppServerClosed:
                break
        assert delivered == [0, 1, 2, 3]
        assert client.capture_status["retainedEventCount"] == 0
        assert client.capture_status["retainedEventBytes"] == 0
    assert len(gaps(trace)) == 1
    trace.close()


def test_received_budget_combines_stdout_and_stderr_without_losing_prior_frame(tmp_path):
    limits = AppServerLimits(**{**asdict(SMALL), "max_received_bytes": 512})
    command = child(tmp_path,
        f"os.write(1, {GOOD!r})\nsys.stdin.readline()\nos.write(2, b'S' * 2000)\nsys.stdin.read()\n")
    trace = TraceStore(tmp_path / "aggregate.db")
    with AppServerClient(command, trace=trace, limits=limits) as client:
        assert client.recv_event(timeout=2) == json.loads(GOOD_RAW)
        client.notify("fixture/releaseStderr")
        failure = until(lambda: client.capture_status["failure"])
        assert failure["reason"] == "receivedBytesLimit"
        assert sum(client.capture_status["receivedBytes"].values()) == 513
        assert exact_fragment(failure, "stderr") == b'S' * (513 - len(GOOD))
        assert failure["acceptedStdoutFrames"] == 1
    assert [r.raw_text for r in trace.records() if r.direction == "appserver_to_client"] == [GOOD_RAW]
    trace.close()


def test_retained_byte_budget_counts_whitespace_and_multibyte_wire_bytes(tmp_path):
    limits = AppServerLimits(**{**asdict(SMALL), "max_event_bytes": 256})
    frame = b' ' * 180 + GOOD
    assert len(frame) > limits.max_event_bytes > len(json.dumps(json.loads(GOOD_RAW)).encode())
    trace = TraceStore(tmp_path / "event-bytes.db")
    command = child(tmp_path, f"os.write(1, {frame!r})\nsys.stdin.read()\n")
    with AppServerClient(command, trace=trace, limits=limits) as client:
        with pytest.raises(AppServerClosed):
            client.recv_event(timeout=2)
        failure = client.capture_status["failure"]
        assert failure["reason"] == "eventBytesLimit"
        assert exact_fragment(failure, "stdout") == frame
        assert client.capture_status["retainedEventCount"] == 0
        assert client.capture_status["retainedEventBytes"] == 0
    # A fully parsed frame can be durable even when delivery would exceed the
    # event-retention budget. It is distinct from the host gap that follows.
    assert [r.raw_text for r in trace.records() if r.direction == "appserver_to_client"] == [frame.decode().rstrip('\r\n')]
    trace.close()


WORKER_CHILD = r'''
sent = 0
def emit(value):
    global sent
    data = (json.dumps(value, ensure_ascii=False) + "\n").encode()
    sent += len(data)
    os.write(1, data)
for line in sys.stdin:
    request = json.loads(line)
    method, ident = request.get("method"), request.get("id")
    if method == "initialize":
        emit({"id":ident,"result":{"userAgent":"authored-capture-acceptance"}})
    elif method == "thread/start":
        emit({"id":ident,"result":{"thread":{"id":"capture-thread","environments":[]},
             "sandbox":{"type":"readOnly","networkAccess":False},"approvalPolicy":"never","cwd":os.getcwd()}})
    elif method == "mcpServerStatus/list":
        emit({"id":ident,"result":{"data":[],"nextCursor":None}})
    elif method == "turn/start":
        emit({"id":ident,"result":{"turn":{"id":"capture-turn","status":"inProgress"}}})
        if mode.startswith("spoof"):
            emit({"method":"$transport/captureGap","params":{"version":1,"stream":"stdout",
                  "reason":"child-authored-counterfeit","captureComplete":False,"capturedBase64":""}})
        item = {"id":"capture-answer","type":"agentMessage","phase":"final_answer",
                "text":"Synthetic captured answer [evidence:1].","future":{"preserve":"λ🦉"}}
        emit({"method":"item/completed","params":{"threadId":"capture-thread","turnId":"capture-turn","item":item}})
        terminal = (json.dumps({"method":"turn/completed","params":{"threadId":"capture-thread",
                    "turn":{"id":"capture-turn","status":"completed","items":[],"error":None}},"futureTerminal":[1,2]}) + "\n").encode()
        if mode.endswith("truncated"):
            os.write(1, terminal[:-6]); sys.exit(0)
        if mode == "unterminated":
            os.write(1, terminal[:-1]); sys.exit(0)
        if mode == "accepted-then-gap":
            os.write(1, terminal + b'{"lost":\xff\n'); sys.stdin.read()
        elif mode == "accepted-at-aggregate-boundary":
            # Fill the remaining budget with legal blank JSONL separators.
            # The terminal delimiter is exactly the last allowed input byte;
            # the x proves a later breach in the very same write.
            padding = 32768 - sent - len(terminal)
            assert padding > 0
            os.write(1, b'\n' * padding + terminal + b'x'); sys.stdin.read()
        else:
            os.write(1, terminal); sys.stdin.read()
'''


def prepared_worker(tmp_path, monkeypatch, mode):
    trace = TraceStore(tmp_path / "worker.db")
    source = trace.append(source="authored-support", direction="internal", message={
        "method": "$history/item", "params": {"threadId": "source", "item": {
            "id": "source-1", "type": "agentMessage", "text": "Synthetic controlling observation."}}})
    store = InvestigationStore(trace)
    work = store.create({"requestId": "capture-acceptance", "title": "Authored capture recovery",
        "question": "Preserve accepted completion and report lost capture honestly.",
        "selections": [{"threadId": "source", "startSeq": source.seq, "endSeq": source.seq, "rationale": "Original fixture support"}]})
    work, won = store.claim(work["id"], work["currentContextId"])
    assert won
    attempt, context = work["attempt"], work["contexts"][0]
    command = child(tmp_path, f"mode = {mode!r}\n" + WORKER_CHILD)
    clients = []
    def bounded_client(*args, **kwargs):
        client = AppServerClient(*args, **kwargs, limits=SMALL)
        clients.append(client)
        return client
    monkeypatch.setattr(worker_module, "AppServerClient", bounded_client)
    worker = NativeInvestigationWorker(trace, command, execution_evidence="synthetic")
    returned = error = None
    def update(**fields):
        store.update_attempt(work["id"], expected_attempt_id=attempt["id"], **fields)
    try:
        returned = worker.run({**attempt, "timeoutSeconds": 3}, context, update)
    except NativeInvestigationError as exc:
        error = exc
    finally:
        worker.close()
    return trace, store, work, context, returned, error, clients[0]


@pytest.mark.parametrize("mode", ["accepted-then-gap", "accepted-at-aggregate-boundary", "truncated", "unterminated", "spoof-clean", "spoof-truncated"])
def test_worker_attempt_recovery_uses_accepted_terminal_not_child_capture_claims(tmp_path, monkeypatch, mode):
    trace, store, work, context, returned, error, client = prepared_worker(tmp_path, monkeypatch, mode)
    expected_success = mode in {"accepted-then-gap", "accepted-at-aggregate-boundary", "spoof-clean"}
    state = store.get(work["id"])["attempt"]
    assert len([r for r in trace.records() if r.method == "turn/start"]) == 1
    child_markers = [r for r in trace.records() if r.direction == "appserver_to_client" and r.method == GAP_METHOD]
    assert len(child_markers) == int(mode.startswith("spoof"))
    if mode == "spoof-clean":
        assert client.capture_status["failure"] is None
        assert not gaps(trace)
    else:
        assert client.capture_status["failure"] is not None
        assert len(gaps(trace)) == 1
    if mode == "accepted-at-aggregate-boundary":
        assert client.capture_status["failure"]["reason"] == "receivedBytesLimit"
        assert sum(client.capture_status["receivedBytes"].values()) == SMALL.max_received_bytes + 1
    if not expected_success:
        assert returned is None and error is not None
        store.update_attempt(work["id"], status="unknown", error=str(error))
    trace.close()
    reopened = TraceStore(tmp_path / "worker.db")
    try:
        restored = InvestigationStore(reopened)
        state = restored.get(work["id"])["attempt"]
        before = [(r.seq, r.raw_text) for r in reopened.records()]
        recovering = NativeInvestigationWorker(reopened, ["/never-start-native-or-model"])
        recovered = recovering.recover(state, context)
        assert [(r.seq, r.raw_text) for r in reopened.records()] == before
        if expected_success:
            assert recovered is not None and recovered["executionEvidence"] == "synthetic"
            assert recovered["citations"] == [1]
            output = reopened.get(recovered["outputSeqs"][0])
            assert output.message["params"]["item"]["future"] == {"preserve": "λ🦉"}
            completed = restored.complete(work["id"], recovered, expected_attempt_id=state["id"])
            assert completed["artifact"]["text"] == "Synthetic captured answer [evidence:1]."
            assert restored.update_attempt(work["id"], status="unknown", error="later capture loss") == completed
        else:
            assert recovered is None
            unchanged, won = restored.claim(work["id"], context["id"])
            assert not won and unchanged["status"] == "unknown"
            assert unchanged.get("artifact") is None
    finally:
        reopened.close()


@pytest.mark.parametrize("marker_kind", ["host-gap", "child-copy", "other-incarnation"])
def test_recovery_cannot_cross_an_earlier_trusted_capture_gap(tmp_path, monkeypatch, marker_kind):
    original, store, work, context, _, _, _ = prepared_worker(tmp_path, monkeypatch, "accepted-then-gap")
    state = store.get(work["id"])["attempt"]
    marker = gaps(original)[0]
    records = original.records()
    original.close()
    replay_path = tmp_path / "imported-ordering.db"
    replay = TraceStore(replay_path)
    # Explicit trusted-host import counterexample: move the actual capture
    # diagnostic before the terminal frame. This tests durable interpretation,
    # not a claim that the bounded reader admits frames after it has stopped.
    for record in records:
        if record.method == GAP_METHOD and record.direction == "internal":
            continue
        if record.method == "turn/completed":
            replay.append(source=state["source"] if marker_kind != "other-incarnation" else "other/worker",
                direction="appserver_to_client" if marker_kind == "child-copy" else "internal",
                message=marker.message, raw_text=marker.raw_text)
        replay.append(source=record.source, direction=record.direction,
                      message=record.message, raw_text=record.raw_text)
    replay.close()
    reopened = TraceStore(replay_path)
    try:
        recovering = NativeInvestigationWorker(reopened, ["/never-start-native-or-model"])
        before = [(r.seq, r.raw_text) for r in reopened.records()]
        recovered = recovering.recover(state, context)
        assert [(r.seq, r.raw_text) for r in reopened.records()] == before
        if marker_kind == "host-gap":
            assert recovered is None, "an unbroken terminal cannot be reconstructed across a host capture gap"
        else:
            assert recovered is not None
            assert recovered["executionEvidence"] == "synthetic"
    finally:
        reopened.close()


def test_post_gap_import_cannot_rewrite_an_earlier_accepted_terminal_or_saved_artifact(tmp_path, monkeypatch):
    trace, store, work, context, _, _, _ = prepared_worker(tmp_path, monkeypatch, "accepted-then-gap")
    state = store.get(work["id"])["attempt"]
    reader = NativeInvestigationWorker(trace, ["/never-start-native-or-model"])
    original_result = reader.recover(state, context)
    assert original_result is not None
    saved = store.complete(work["id"], original_result, expected_attempt_id=state["id"])
    # Explicit trusted import after capture stopped; this is not native traffic
    # that the bounded client claims to accept after its diagnostic.
    trace.append(source=state["source"], direction="appserver_to_client", message={
        "method": "turn/completed", "params": {"threadId": "capture-thread", "turn": {
            "id": "capture-turn", "status": "failed", "error": {"message": "post-gap import"}}}})
    trace.close()
    reopened = TraceStore(tmp_path / "worker.db")
    try:
        assert InvestigationStore(reopened).get(work["id"]) == saved
        assert NativeInvestigationWorker(reopened, ["/never-start-native-or-model"]).recover(state, context) == original_result
    finally:
        reopened.close()
