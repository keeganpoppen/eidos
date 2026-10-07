from __future__ import annotations

import io
import json
from pathlib import Path
import sys
import time

from eidos.api import EidosAPI, LiveCodex, thread_payload
from eidos.trace import TraceStore


def seed_thread(store: TraceStore) -> str:
    thread_id = "thread-api"
    store.append(
        source="test",
        direction="client_to_appserver",
        message={
            "id": 1,
            "method": "turn/start",
            "params": {
                "threadId": thread_id,
                "input": [{"type": "text", "text": "hello **markdown**"}],
            },
        },
    )
    store.append(
        source="test",
        direction="appserver_to_client",
        message={"id": 1, "result": {"turn": {"id": "turn-1"}}},
    )
    store.append(
        source="test",
        direction="appserver_to_client",
        message={
            "method": "item/agentMessage/delta",
            "params": {
                "threadId": thread_id,
                "turnId": "turn-1",
                "itemId": "agent-1",
                "delta": "partial **answer**",
            },
        },
    )
    return thread_id


def test_thread_payload_projects_live_partial_evidence():
    store = TraceStore()
    thread_id = seed_thread(store)
    payload = thread_payload(store, thread_id)

    assert payload["preview"] == "hello **markdown**"
    assert payload["recordCount"] == 3
    turn = payload["turns"][0]
    assert turn["id"] == "turn-1"
    agent = next(item for item in turn["items"] if item["id"] == "agent-1")
    assert agent["type"] == "agentMessage"
    assert agent["text"] == "partial **answer**"
    assert agent["complete"] is False



def test_empty_reasoning_items_are_not_projected_into_chat():
    store = TraceStore()
    thread_id = "reasoning-empty"
    store.append(
        source="test",
        direction="appserver_to_client",
        message={
            "method": "item/completed",
            "params": {
                "threadId": thread_id,
                "turnId": "turn-r",
                "item": {
                    "id": "reason-r",
                    "type": "reasoning",
                    "summary": [],
                    "content": [],
                },
            },
        },
    )
    payload = thread_payload(store, thread_id)
    assert len(payload["turns"]) == 1
    assert payload["turns"][0]["items"] == []


class DummyHandler:
    def __init__(self, body: dict | None = None) -> None:
        raw = json.dumps(body or {}).encode()
        self.headers = {"Content-Length": str(len(raw))}
        self.rfile = io.BytesIO(raw)


class FakeLive:
    def __init__(self) -> None:
        self.started: list[str | None] = []
        self.sent: list[tuple[str, str]] = []

    def start_thread(self, *, cwd: str | None = None) -> str:
        self.started.append(cwd)
        return "new-thread"

    def send(self, thread_id: str, text: str) -> str:
        self.sent.append((thread_id, text))
        return "turn-new"

    def close(self) -> None:
        pass


def test_api_create_thread_and_send_message_without_frontend_state():
    store = TraceStore()
    api = EidosAPI(store)
    fake = FakeLive()
    api.live = fake  # type: ignore[assignment]

    status, payload = api.dispatch(
        DummyHandler({"cwd": "/tmp/project"}),
        "POST",
        "/api/threads",
        {},
    )
    assert status == 201
    assert payload == {"threadId": "new-thread"}
    assert fake.started == ["/tmp/project"]

    status, payload = api.dispatch(
        DummyHandler({"text": "do the thing"}),
        "POST",
        "/api/threads/new-thread/messages",
        {},
    )
    assert status == 202
    assert payload == {"turnId": "turn-new"}
    assert fake.sent == [("new-thread", "do the thing")]


FAKE_LIVE_SERVER = r"""
import json, sys
for line in sys.stdin:
    msg=json.loads(line)
    method=msg.get("method")
    ident=msg.get("id")
    if method == "initialize":
        print(json.dumps({"jsonrpc":"2.0","id":ident,"result":{"userAgent":"fake"}}), flush=True)
    elif method == "initialized":
        pass
    elif method == "thread/start":
        thread={"id":"live-thread","status":{"type":"idle"},"turns":[]}
        print(json.dumps({"jsonrpc":"2.0","id":ident,"result":{"thread":thread}}), flush=True)
    elif method == "turn/start":
        turn={"id":"live-turn","status":"inProgress","items":[],"error":None}
        print(json.dumps({"jsonrpc":"2.0","id":ident,"result":{"turn":turn}}), flush=True)
        print(json.dumps({
          "jsonrpc":"2.0","method":"turn/started",
          "params":{"threadId":"live-thread","turn":turn}
        }), flush=True)
        print(json.dumps({
          "jsonrpc":"2.0","method":"item/agentMessage/delta",
          "params":{"threadId":"live-thread","turnId":"live-turn","itemId":"agent-1","delta":"hello "}
        }), flush=True)
        print(json.dumps({
          "jsonrpc":"2.0","method":"item/agentMessage/delta",
          "params":{"threadId":"live-thread","turnId":"live-turn","itemId":"agent-1","delta":"from live"}
        }), flush=True)
        print(json.dumps({
          "jsonrpc":"2.0","method":"item/completed",
          "params":{
            "threadId":"live-thread","turnId":"live-turn",
            "item":{"id":"agent-1","type":"agentMessage","text":"hello from live","phase":"final"}
          }
        }), flush=True)
        turn["status"]="completed"
        print(json.dumps({
          "jsonrpc":"2.0","method":"turn/completed",
          "params":{"threadId":"live-thread","turn":turn}
        }), flush=True)
"""


def test_live_codex_round_trip_is_rendered_from_persisted_trace(tmp_path: Path):
    fake = tmp_path / "fake_live_server.py"
    fake.write_text(FAKE_LIVE_SERVER)
    store = TraceStore(tmp_path / "live.db")
    live = LiveCodex(store, command=[sys.executable, str(fake)])
    try:
        thread_id = live.start_thread(cwd=str(tmp_path))
        assert thread_id == "live-thread"
        turn_id = live.send(thread_id, "say hello")
        assert turn_id == "live-turn"

        turn_start = next(
            record
            for record in store.records(thread_id=thread_id)
            if record.method == "turn/start"
        )
        assert turn_start.message["params"]["summary"] == "detailed"

        deadline = time.monotonic() + 2
        payload = thread_payload(store, thread_id)
        while time.monotonic() < deadline:
            items = [
                item
                for turn in payload["turns"]
                for item in turn["items"]
                if item["type"] == "agentMessage"
            ]
            if items and items[-1].get("text") == "hello from live":
                break
            time.sleep(0.01)
            payload = thread_payload(store, thread_id)

        agent = next(
            item
            for turn in payload["turns"]
            for item in turn["items"]
            if item["type"] == "agentMessage"
        )
        assert agent["text"] == "hello from live"
        assert agent["complete"] is True
    finally:
        live.close()
