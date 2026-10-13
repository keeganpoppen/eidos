"""Authored local pipes only; these tests never launch Codex or a model."""
import base64
from dataclasses import asdict, replace
import json
import sys
import threading
import time

import pytest

from eidos.codex import AppServerClient, AppServerClosed, AppServerLimits
from eidos.trace import TraceStore


def wait_until(predicate):
    deadline = time.monotonic() + 3
    while not predicate():
        assert time.monotonic() < deadline
        time.sleep(.005)


def child(script, trace, **limits):
    return AppServerClient([sys.executable, "-c", script], trace=trace,
                           limits=replace(AppServerLimits(), **limits))


def gaps(trace):
    return [r.message["params"] for r in trace.records()
            if r.direction == "internal" and r.method == "$transport/captureGap"]


def native(trace):
    return [r for r in trace.records() if r.direction == "appserver_to_client"]


@pytest.mark.parametrize("value", [0, -1, True, 1.5, float("inf"), None])
def test_limits_reject_nonpositive_or_noninteger_values(value):
    with pytest.raises(ValueError):
        AppServerLimits(max_received_bytes=value)


@pytest.mark.parametrize("stream,fd,field", [
    ("stdout", 1, "max_stdout_frame_bytes"), ("stderr", 2, "max_stderr_frame_bytes"),
])
def test_unterminated_flood_is_stopped_before_unbounded_line_allocation(stream, fd, field):
    trace = TraceStore()
    script = f"import os\nwhile True: os.write({fd}, b'x' * 4096)"
    with child(script, trace, **{field: 64}) as client:
        assert client._closed.wait(2)
        wait_until(lambda: client.process.poll() is not None)
        diagnostic, = gaps(trace)
        assert diagnostic["reason"] == "frameBytesLimit"
        assert diagnostic["stream"] == stream
        assert base64.b64decode(diagnostic["capturedBase64"]) == b"x" * 65
        assert diagnostic["receivedBytes"][stream] == 65
        assert diagnostic["frameComplete"] is False
        assert diagnostic["captureComplete"] is False
        assert diagnostic["limits"] == asdict(client.limits)
        with pytest.raises(AppServerClosed):
            client.recv_event()
    assert not native(trace)


@pytest.mark.parametrize("raw,reason", [
    (b'{not-json}\n', "invalidJson"),
    (b'{"method":"bad\xff"}\n', "invalidUtf8"),
    (b'[1,2]\n', "nonObjectJson"),
    (b'{"method":"surrogate\\ud800"}\n', "traceProjectionError"),
    (b'{"method":"timestamp","emittedAtMs":1e1000}\n', "traceProjectionError"),
    (b'{"number":' + b'9' * 5000 + b'}\n', "invalidJson"),
    (b'{"x":' * 100000 + b'0' + b'}' * 100000 + b'\n', "invalidJson"),
    (b'{"method":"fixture/nonstandard","future":NaN}\n', "invalidJson"),
    (b'{"method":"fixture/nonstandard","future":Infinity}\n', "invalidJson"),
    (b'{"method":"fixture/nonstandard","future":-Infinity}\n', "invalidJson"),
], ids=["malformed", "utf8", "array", "surrogate", "timestamp", "integer", "deep",
        "nan", "infinity", "negative-infinity"])
def test_invalid_frames_preserve_exact_bytes_in_valid_internal_envelope(tmp_path, raw, reason):
    # A file avoids argv-size limits for the recursion counterexample.
    data = tmp_path / "synthetic-bytes"
    data.write_bytes(raw)
    trace = TraceStore(tmp_path / "trace.db")
    script = f"import os,pathlib; os.write(1,pathlib.Path({str(data)!r}).read_bytes())"
    with child(script, trace) as client:
        assert client._closed.wait(3)
        diagnostic, = gaps(trace)
        assert diagnostic["reason"] == reason
        assert diagnostic["frameComplete"] is True
        assert base64.b64decode(diagnostic["capturedBase64"]) == raw
        assert client.capture_status["diagnosticError"] is None
    assert not native(trace)
    trace.close()
    reopened = TraceStore(tmp_path / "trace.db")
    assert gaps(reopened) == [diagnostic]
    assert all(isinstance(record.message, dict) for record in reopened.records())
    reopened.close()


def test_accepted_terminal_survives_bad_suffix_and_later_frames_are_not_admitted():
    terminal = '{"method":"turn/completed","params":{"unknown":"retained λ"}}\r\n'.encode()
    bad = b'not json\n'
    later = b'{"method":"later"}\n'
    trace = TraceStore()
    with child(f"import os; os.write(1,{terminal + bad + later!r})", trace) as client:
        assert client._closed.wait(2)
        assert client.recv_event() == json.loads(terminal)
        with pytest.raises(AppServerClosed):
            client.recv_event()
        assert client.capture_status["retainedEventCount"] == 0
    assert [r.raw_text for r in native(trace)] == [terminal.decode().rstrip("\r\n")]
    diagnostic, = gaps(trace)
    assert base64.b64decode(diagnostic["capturedBase64"]) == bad
    assert base64.b64decode(diagnostic["bufferedStreams"][0]["capturedBase64"]) == later


def test_stderr_breach_preserves_buffered_partial_stdout_and_shared_byte_accounting():
    partial = b'{"method":"turn/completed"'
    trace = TraceStore()
    script = f"import os,time; os.write(1,{partial!r}); time.sleep(.08); os.write(2,b'x'*500)"
    with child(script, trace, max_received_bytes=64) as client:
        assert client._closed.wait(2)
        diagnostic, = gaps(trace)
        assert diagnostic["reason"] == "receivedBytesLimit"
        assert sum(diagnostic["receivedBytes"].values()) == 65
        assert diagnostic["stream"] == "stderr"
        buffered, = diagnostic["bufferedStreams"]
        assert buffered["stream"] == "stdout"
        assert base64.b64decode(buffered["capturedBase64"]) == partial
        assert buffered["frameComplete"] is False
    assert not native(trace)


def test_exact_byte_limit_accepts_fragmented_utf8_frame():
    wire = '{"method":"retained","params":{"unknown":"λ"}}\n'.encode()
    trace = TraceStore()
    script = f"import os\nfor byte in {wire!r}: os.write(1,bytes([byte]))"
    with child(script, trace, max_received_bytes=len(wire), max_stdout_frame_bytes=len(wire)) as client:
        assert client._closed.wait(2)
        assert client.recv_event() == json.loads(wire)
        assert client.capture_status["failure"] is None
    assert gaps(trace) == []


def test_aggregate_boundary_preserves_same_complete_prefix_for_both_segmentations():
    terminal = b'{"method":"turn/completed","params":{"unknown":"retained"}}\n'
    results = []
    for split in (False, True):
        trace = TraceStore()
        # The split writer waits until the consumer observed the first frame;
        # this compares genuinely separate reads with one combined pipe write.
        script = (
            f"import os,sys; os.write(1,{terminal!r}); sys.stdin.readline(); os.write(1,b'x')"
            if split else f"import os; os.write(1,{terminal + b'x'!r})"
        )
        with child(script, trace, max_received_bytes=len(terminal)) as client:
            if split:
                assert client.recv_event(timeout=2) == json.loads(terminal)
                client.notify("release-proof-byte")
            assert client._closed.wait(2)
            if not split:
                assert client.recv_event() == json.loads(terminal)
            with pytest.raises(AppServerClosed):
                client.recv_event()
            diagnostic, = gaps(trace)
            assert diagnostic["reason"] == "receivedBytesLimit"
            assert base64.b64decode(diagnostic["capturedBase64"]) == b"x"
            assert diagnostic["receivedBytes"] == {"stdout": len(terminal) + 1, "stderr": 0}
            assert diagnostic["acceptedStdoutFrames"] == 1
            results.append([record.raw_text for record in native(trace)])
    assert results == [[terminal.decode().rstrip("\n")]] * 2


@pytest.mark.parametrize("suffix", [b'{"method":"not-admitted"}\n', b'{"method":"partial'])
def test_aggregate_gap_keeps_partial_suffix_and_never_uses_proof_byte_as_delimiter(suffix):
    accepted = b'{"method":"accepted"}\n'
    # All but the last suffix byte fit. When that last byte is a newline it
    # still cannot complete an admitted native frame beyond the byte budget.
    wire = accepted + suffix
    trace = TraceStore()
    with child(f"import os; os.write(1,{wire!r})", trace, max_received_bytes=len(wire) - 1) as client:
        assert client._closed.wait(2)
        assert client.recv_event() == json.loads(accepted)
        with pytest.raises(AppServerClosed):
            client.recv_event()
    assert [record.raw_text for record in native(trace)] == [accepted.decode().rstrip("\n")]
    diagnostic, = gaps(trace)
    assert diagnostic["reason"] == "receivedBytesLimit"
    assert base64.b64decode(diagnostic["capturedBase64"]) == suffix
    assert diagnostic["frameComplete"] is False


def test_eof_without_delimiter_is_not_an_accepted_completion():
    wire = b'{"method":"turn/completed"}'
    trace = TraceStore()
    with child(f"import os; os.write(1,{wire!r})", trace) as client:
        assert client._closed.wait(2)
        with pytest.raises(AppServerClosed):
            client.recv_event()
    diagnostic, = gaps(trace)
    assert diagnostic["reason"] == "truncatedFrame"
    assert base64.b64decode(diagnostic["capturedBase64"]) == wire
    assert not native(trace)


def test_wait_for_skipped_events_still_count_and_full_queue_wakes_pending_rpc():
    first = b'{"method":"other","params":{"index":0}}\n'
    trace = TraceStore()
    script = f"import os,sys; os.write(1,{first!r}*3); sys.stdin.readline(); os.write(1,{first!r}); sys.stdin.read()"
    with child(script, trace, max_event_count=3) as client:
        wait_until(lambda: client.capture_status["retainedEventCount"] == 3)
        outcomes = []
        def skip():
            try:
                client.wait_for("absent", timeout=2)
            except Exception as exc:
                outcomes.append(exc)
        waiter = threading.Thread(target=skip)
        waiter.start()
        wait_until(lambda: not client._events)
        with pytest.raises(AppServerClosed):
            client.request("release", timeout=2)
        waiter.join(2)
        assert not waiter.is_alive()
        assert isinstance(outcomes[0], AppServerClosed)
        assert gaps(trace)[0]["reason"] == "eventCountLimit"
        assert len(native(trace)) == 4  # Overflow frame is still raw evidence.
        assert client.capture_status["retainedEventCount"] == 3
        assert [client.recv_event() for _ in range(3)] == [json.loads(first)] * 3
        assert client.capture_status["retainedEventCount"] == 0
        assert client.capture_status["retainedEventBytes"] == 0
        with pytest.raises(AppServerClosed):
            client.recv_event()


def test_repeated_wait_for_timeouts_transfer_reservations_and_release_once():
    wire = b'{"method":"other"}\n'
    trace = TraceStore()
    script = f"import os,sys; os.write(1,{wire!r}*2); sys.stdin.readline(); os.write(1,{wire!r}); sys.stdin.read()"
    with child(script, trace, max_event_count=2) as client:
        wait_until(lambda: client.capture_status["retainedEventCount"] == 2)
        for _ in range(3):
            with pytest.raises(TimeoutError):
                client.wait_for("missing", timeout=.01)
            assert client.capture_status["retainedEventBytes"] == len(wire) * 2
        client.recv_event()
        client.notify("release")
        wait_until(lambda: len(native(trace)) == 3)
        assert client.capture_status["failure"] is None
        assert [client.recv_event() for _ in range(2)] == [json.loads(wire)] * 2
        assert client.capture_status["retainedEventBytes"] == 0


def test_event_byte_budget_uses_original_wire_whitespace():
    wire = b'   {"method":"x"}   \n'
    trace = TraceStore()
    with child(f"import os; os.write(1,{wire!r}*2)", trace, max_event_bytes=len(wire)) as client:
        assert client._closed.wait(2)
        assert client.capture_status["retainedEventBytes"] == len(wire)
        assert gaps(trace)[0]["reason"] == "eventBytesLimit"
        assert client.recv_event() == {"method": "x"}


def test_child_cannot_establish_host_capture_status_and_tail_is_bounded():
    fake = b'{"method":"$transport/captureGap","params":{"version":1,"captureComplete":false}}\n'
    trace = TraceStore()
    script = f"import os,time; os.write(1,{fake!r}); os.write(2,b'line1\\nline2\\nline3\\n'); time.sleep(.1)"
    with child(script, trace, max_stderr_tail_bytes=12, max_stderr_tail_lines=2) as client:
        assert client._closed.wait(2)
        assert client.recv_event() == json.loads(fake)
        assert client.capture_status["failure"] is None
        assert client.stderr_tail == ["line2", "line3"]
        assert client.capture_status["stderrTailBytes"] == 12
    assert gaps(trace) == []
    assert native(trace)[0].method == "$transport/captureGap"


def test_storage_diagnostic_failure_still_wakes_waiters(monkeypatch):
    trace = TraceStore()
    original = trace.append
    def fail_gap(**kwargs):
        if kwargs["message"].get("method") == "$transport/captureGap":
            raise OSError("synthetic unavailable storage")
        return original(**kwargs)
    monkeypatch.setattr(trace, "append", fail_gap)
    with child("import os; os.write(1,b'bad\\n')", trace) as client:
        assert client._closed.wait(2)
        with pytest.raises(AppServerClosed):
            client.recv_event()
        assert client.capture_status["failure"]["reason"] == "invalidJson"
        assert client.capture_status["diagnosticError"] == "OSError"
    assert gaps(trace) == []


def test_stdout_eof_wakes_rpc_but_stderr_is_still_bounded():
    trace = TraceStore()
    script = "import os,sys,time; sys.stdin.readline(); os.close(1); time.sleep(.1); os.write(2,b'x'*100); time.sleep(3)"
    with child(script, trace, max_stderr_frame_bytes=32) as client:
        with pytest.raises(AppServerClosed):
            client.request("synthetic-pending", timeout=2)
        wait_until(lambda: client.capture_status["failure"] is not None)
        diagnostic, = gaps(trace)
        assert diagnostic["stream"] == "stderr"
        assert diagnostic["reason"] == "frameBytesLimit"
        assert diagnostic["capturedBytes"] == 33


def test_concurrent_event_waiters_wake_and_release_each_reservation_once():
    trace = TraceStore()
    with child("import sys; sys.stdin.readline(); print('{\"method\":\"one\"}',flush=True)", trace) as client:
        results = []
        def receive():
            try:
                results.append(client.wait_for("one", timeout=2))
            except Exception as exc:
                results.append(exc)
        waiters = [threading.Thread(target=receive) for _ in range(2)]
        for waiter in waiters:
            waiter.start()
        client.notify("release")
        for waiter in waiters:
            waiter.join(2)
            assert not waiter.is_alive()
        assert sum(isinstance(value, dict) for value in results) == 1
        assert sum(isinstance(value, AppServerClosed) for value in results) == 1
        assert client.capture_status["retainedEventCount"] == 0
        assert client.capture_status["retainedEventBytes"] == 0
