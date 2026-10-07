from eidos.trace import TraceStore
from eidos.view import project_thread, render_thread_html


def test_trace_store_preserves_raw_and_correlates_response():
    store = TraceStore()
    request = '{"jsonrpc":"2.0","id":7,"method":"turn/start","params":{"threadId":"thr1","input":[{"type":"text","text":"hello"}]}}'
    response = '{"jsonrpc":"2.0","id":7,"result":{"turn":{"id":"turn1"}}}'
    store.append_line(source="codex", direction="client_to_appserver", raw_text=request, observed_at_ms=1)
    record = store.append_line(source="codex", direction="appserver_to_client", raw_text=response, observed_at_ms=2)
    assert record.raw_text == response
    assert record.response_to == "turn/start"
    assert record.turn_id == "turn1"
    request_record = store.get(1)
    assert request_record.thread_id == "thr1"
    assert request_record.turn_id == "turn1"


def test_thread_projection_and_renderer_use_persisted_native_items():
    store = TraceStore()
    messages = [
        {"jsonrpc":"2.0","id":1,"method":"turn/start","params":{"threadId":"thr1","input":[{"type":"text","text":"fix it"}]}},
        {"jsonrpc":"2.0","method":"turn/started","params":{"threadId":"thr1","turn":{"id":"turn1"}}},
        {"jsonrpc":"2.0","method":"item/completed","params":{"threadId":"thr1","turnId":"turn1","item":{"id":"cmd1","type":"commandExecution","command":"pytest","aggregatedOutput":"12 passed","status":"completed"}}},
        {"jsonrpc":"2.0","method":"item/completed","params":{"threadId":"thr1","turnId":"turn1","item":{"id":"msg1","type":"agentMessage","text":"done","phase":"final"}}},
        {"jsonrpc":"2.0","method":"turn/completed","params":{"threadId":"thr1","turn":{"id":"turn1","status":"completed"}}},
    ]
    for message in messages:
        store.append(source="codex", direction="appserver_to_client" if "id" not in message else "client_to_appserver", message=message)
    view = project_thread(store, "thr1")
    assert len(view.turns) >= 1
    turn = next(t for t in view.turns if t.turn_id == "turn1")
    assert turn.items["cmd1"].item_type == "commandExecution"
    html = render_thread_html(store, "thr1")
    assert "pytest" in html
    assert "12 passed" in html
    assert "done" in html


def test_rpc_ids_are_correlated_only_within_one_source_connection():
    store = TraceStore()
    store.append(source="conn-a", direction="client_to_appserver", message={"id":1,"method":"thread/list","params":{}})
    store.append(source="conn-b", direction="client_to_appserver", message={"id":1,"method":"model/list","params":{}})
    a = store.append(source="conn-a", direction="appserver_to_client", message={"id":1,"result":{}})
    b = store.append(source="conn-b", direction="appserver_to_client", message={"id":1,"result":{}})
    assert a.response_to == "thread/list"
    assert b.response_to == "model/list"
