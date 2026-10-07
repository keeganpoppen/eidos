import json
from pathlib import Path
import sys

from eidos.codex import AppServerClient, CodexPlace
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
