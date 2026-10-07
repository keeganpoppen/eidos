from __future__ import annotations

import io
import json

from eidos.api import EidosAPI, thread_payload
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
