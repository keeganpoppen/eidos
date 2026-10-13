import json
import os
from pathlib import Path
import signal
import sys
import threading
import time
import pytest

from eidos.codex import AppServerClient, AppServerClosed, CodexPlace
from eidos.trace import TraceStore
from eidos.view import render_thread_html


FAKE_SERVER = r'''
import json, sys
for line in sys.stdin:
    msg=json.loads(line)
    method=msg.get("method")
    ident=msg.get("id")
    if method == "initialize":
        print(json.dumps({"jsonrpc":"2.0","id":ident,"result":{"userAgent":"fake","platformFamily":"test"}}), flush=True)
    elif method == "initialized":
        pass
    elif method == "thread/start":
        thread={"id":"thr_fake","status":{"type":"idle"},"turns":[]}
        print(json.dumps({"jsonrpc":"2.0","id":ident,"result":{"thread":thread,"model":"fake","modelProvider":"fake"}}), flush=True)
        print(json.dumps({"jsonrpc":"2.0","method":"thread/started","params":{"thread":thread},"emittedAtMs":10}), flush=True)
    elif method == "thread/turns/list":
        turn={"id":"turn_fake","status":"completed","items":[],"error":None}
        print(json.dumps({"jsonrpc":"2.0","id":ident,"result":{"data":[turn],"nextCursor":None,"backwardsCursor":"back"}}), flush=True)
    elif method == "thread/items/list":
        entries=[
          {"turnId":"turn_fake","item":{"id":"old_user","type":"userMessage","content":[{"type":"text","text":"historical prompt"}]},"startedAtMs":1,"completedAtMs":1},
          {"turnId":"turn_fake","item":{"id":"old_agent","type":"agentMessage","text":"historical answer","phase":"final"},"startedAtMs":2,"completedAtMs":3}
        ]
        print(json.dumps({"jsonrpc":"2.0","id":ident,"result":{"data":entries,"nextCursor":None,"backwardsCursor":"back"}}), flush=True)
    elif method == "turn/start":
        turn={"id":"turn_fake","status":"inProgress","items":[],"error":None}
        print(json.dumps({"jsonrpc":"2.0","id":ident,"result":{"turn":turn}}), flush=True)
        print(json.dumps({"jsonrpc":"2.0","method":"turn/started","params":{"threadId":"thr_fake","turn":turn},"emittedAtMs":20}), flush=True)
        item={"id":"cmd_fake","type":"commandExecution","command":"pytest","aggregatedOutput":"13 passed","status":"completed"}
        print(json.dumps({"jsonrpc":"2.0","method":"item/completed","params":{"threadId":"thr_fake","turnId":"turn_fake","item":item},"emittedAtMs":21}), flush=True)
        item2={"id":"msg_fake","type":"agentMessage","text":"all green","phase":"final"}
        print(json.dumps({"jsonrpc":"2.0","method":"item/completed","params":{"threadId":"thr_fake","turnId":"turn_fake","item":item2},"emittedAtMs":22}), flush=True)
        turn["status"]="completed"
        print(json.dumps({"jsonrpc":"2.0","method":"turn/completed","params":{"threadId":"thr_fake","turn":turn},"emittedAtMs":23}), flush=True)
'''


def test_traced_codex_place_reaches_alternate_ui(tmp_path: Path):
    fake = tmp_path / "fake_app_server.py"
    fake.write_text(FAKE_SERVER)
    trace = TraceStore(tmp_path / "trace.db")
    client = AppServerClient([sys.executable, str(fake)], trace=trace)
    with client:
        place = CodexPlace("place_test", client).start()
        thread = place.start_thread(cwd=str(tmp_path))
        assert thread == "thr_fake"
        client.turn_start_text(thread, "please run tests")
        completed = client.wait_for("turn/completed", thread_id=thread, timeout=2)
        assert completed["params"]["turn"]["status"] == "completed"

    records = trace.records(thread_id="thr_fake")
    assert any(r.method == "item/completed" and r.item_type == "commandExecution" for r in records)
    html = render_thread_html(trace, "thr_fake")
    assert "pytest" in html
    assert "13 passed" in html
    assert "all green" in html


def test_history_sync_materializes_old_items_into_eidos_projection(tmp_path: Path):
    fake = tmp_path / "fake_history_server.py"
    fake.write_text(FAKE_SERVER)
    trace = TraceStore(tmp_path / "history.db")
    client = AppServerClient([sys.executable, str(fake)], trace=trace)
    with client:
        place = CodexPlace("place_test", client).start()
        thread = place.start_thread(cwd=str(tmp_path))
        counts = place.sync_thread_history(thread)
        assert counts == {"turns": 1, "items": 2}

    html = render_thread_html(trace, "thr_fake")
    assert "historical prompt" in html
    assert "historical answer" in html
    assert any(r.method == "$history/item" for r in trace.records(thread_id="thr_fake"))


def test_closed_incarnation_never_restarts_on_request(tmp_path: Path):
    fake = tmp_path / "fake_server.py"
    fake.write_text(FAKE_SERVER)
    trace = TraceStore()
    client = AppServerClient([sys.executable, str(fake)], trace=trace)
    client.initialize()
    client.close()
    before = len(trace.records())
    with pytest.raises(AppServerClosed):
        client.initialize()
    assert client.process is None
    assert len(trace.records()) == before

    unstarted = AppServerClient([sys.executable, str(fake)], trace=trace)
    unstarted.close()
    with pytest.raises(AppServerClosed):
        unstarted.start()


def test_eof_wakes_event_waiter_without_a_timeout():
    client = AppServerClient([sys.executable, "-c", "import time; time.sleep(.1)"])
    outcomes = []
    waiting = threading.Event()

    def receive():
        waiting.set()
        try:
            client.recv_event()
        except Exception as exc:
            outcomes.append(exc)

    with client:
        reader = threading.Thread(target=receive, daemon=True)
        reader.start()
        assert waiting.wait(timeout=1)
        reader.join(timeout=1)
        assert not reader.is_alive()
        assert len(outcomes) == 1
        assert isinstance(outcomes[0], AppServerClosed)
        with pytest.raises(AppServerClosed):
            client.recv_event()


def test_fragmented_terminal_event_is_drained_before_eof(tmp_path: Path):
    event = {"method": "turn/completed", "params": {"future": "retained λ"}}
    raw = json.dumps(event, ensure_ascii=False)
    script = tmp_path / "fragmented.py"
    script.write_text(
        "import os, time\n"
        f"data = {(raw + chr(10)).encode('utf-8')!r}\n"
        "for byte in data:\n"
        "    os.write(1, bytes([byte]))\n"
    )
    trace = TraceStore()
    with AppServerClient([sys.executable, str(script)], trace=trace) as client:
        assert client._closed.wait(timeout=1)
        assert client.recv_event() == event
        with pytest.raises(AppServerClosed):
            client.recv_event()
    record = next(record for record in trace.records() if record.direction == "appserver_to_client")
    assert record.message == event
    assert record.raw_text == raw


def test_process_crash_fails_pending_request_as_transport_closure():
    trace = TraceStore()
    script = "import sys; sys.stdin.readline(); sys.exit(23)"
    with AppServerClient([sys.executable, "-c", script], trace=trace) as client:
        started = time.monotonic()
        with pytest.raises(AppServerClosed):
            client.request("turn/start", {"synthetic": True}, timeout=5)
        assert time.monotonic() - started < 1
        assert client._pending == {}
        with pytest.raises(AppServerClosed):
            client.request("turn/start")
    records = [record for record in trace.records() if record.direction != "internal"]
    assert len(records) == 1
    assert records[0].method == "turn/start"
    assert records[0].direction == "client_to_appserver"


def test_failed_write_cleans_pending_request_and_never_resends(monkeypatch):
    trace = TraceStore()
    with AppServerClient([sys.executable, "-c", "import time; time.sleep(30)"], trace=trace) as client:
        def broken_write(fd, data):
            raise BrokenPipeError("synthetic broken pipe")

        monkeypatch.setattr(os, "write", broken_write)
        with pytest.raises(AppServerClosed, match="delivery may be unknown"):
            client.request("turn/start", {"synthetic": True})
        assert client._pending == {}
        with pytest.raises(AppServerClosed):
            client.request("turn/start")
    assert [record.method for record in trace.records() if record.direction != "internal"] == ["turn/start"]


def test_late_ack_after_timeout_remains_evidence_without_resend():
    trace = TraceStore()
    script = (
        "import json, sys, time; "
        "request = json.loads(sys.stdin.readline()); "
        "time.sleep(.15); "
        "print(json.dumps({'id': request['id'], 'result': {'turn': {'id': 'late'}}}), flush=True); "
        "sys.stdin.read()"
    )
    with AppServerClient([sys.executable, "-c", script], trace=trace) as client:
        with pytest.raises(TimeoutError):
            client.request("turn/start", timeout=.05)
        assert client._pending == {}
        late = client.recv_event(timeout=1)
        assert late["result"]["turn"]["id"] == "late"
    assert len([record for record in trace.records() if record.method == "turn/start"]) == 1
    assert len([record for record in trace.records() if "result" in record.message]) == 1


def test_request_deadline_includes_blocked_pipe_write():
    trace = TraceStore()
    with AppServerClient([sys.executable, "-c", "import time; time.sleep(30)"], trace=trace) as client:
        started = time.monotonic()
        with pytest.raises(TimeoutError, match="write deadline"):
            client.request("turn/start", {"text": "λ" * 1_000_000}, timeout=.1)
        assert time.monotonic() - started < 1
        assert client._pending == {}
        # The stream may contain a partial frame; its incarnation is terminal.
        with pytest.raises(AppServerClosed):
            client.request("turn/start")
    assert [record.method for record in trace.records() if record.direction != "internal"] == ["turn/start"]


def test_request_deadline_includes_waiting_for_another_writer():
    with AppServerClient([sys.executable, "-c", "import time; time.sleep(30)"]) as client:
        with client._write_lock:
            started = time.monotonic()
            with pytest.raises(TimeoutError, match="write deadline"):
                client.request("turn/start", timeout=.05)
            assert time.monotonic() - started < .5
        assert client._pending == {}


@pytest.mark.skipif(os.name != "posix", reason="POSIX synthetic descendant lifecycle")
def test_close_cancels_writer_when_descendant_keeps_stdin_open():
    script = (
        "import json, subprocess, sys, time; "
        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'], "
        "stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); "
        "print(json.dumps({'method': 'ready', 'params': {'pid': child.pid}}), flush=True); "
        "time.sleep(30)"
    )
    trace = TraceStore()
    client = AppServerClient([sys.executable, "-c", script], trace=trace).start()
    descendant = client.recv_event(timeout=2)["params"]["pid"]
    outcomes = []

    def send():
        try:
            client.request("turn/start", {"text": "x" * 2_000_000}, timeout=10)
        except Exception as exc:
            outcomes.append(exc)

    writer = threading.Thread(target=send, daemon=True)
    closers = [threading.Thread(target=client.close, daemon=True) for _ in range(2)]
    try:
        writer.start()
        deadline = time.monotonic() + 1
        while not any(record.method == "turn/start" for record in trace.records()):
            assert time.monotonic() < deadline
            time.sleep(.01)
        # The synthetic descendant keeps the read end alive even after its
        # direct parent is terminated. Concurrent close must still finish.
        for closer in closers:
            closer.start()
        for closer in closers:
            closer.join(timeout=1)
            assert not closer.is_alive()
        writer.join(timeout=1)
        assert not writer.is_alive()
        assert len(outcomes) == 1
        assert isinstance(outcomes[0], AppServerClosed)
        assert client._pending == {}
        os.kill(descendant, 0)  # Closing the owned parent did not kill children.
    finally:
        try:
            os.kill(descendant, signal.SIGTERM)
        except ProcessLookupError:
            pass
        for closer in closers:
            if closer.ident is not None:
                closer.join(timeout=2)
        client.close()
        writer.join(timeout=2)
    assert len([record for record in trace.records() if record.method == "turn/start"]) == 1
