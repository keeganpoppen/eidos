from pathlib import Path
import sys

from eidos.codex import AppServerClient, CodexPlace
from eidos.semantic import (
    CandidateWindow,
    CodexShadowObserver,
    ObserverSpec,
    plan_candidate_windows,
)
from eidos.trace import TraceStore
from eidos.view import render_thread_html


def seed_thread(store: TraceStore, thread_id: str = "thread-main") -> None:
    store.append(
        source="seed",
        direction="internal",
        message={
            "method": "turn/started",
            "params": {"threadId": thread_id, "turn": {"id": "turn-1"}},
        },
    )
    store.append(
        source="seed",
        direction="internal",
        message={
            "method": "item/completed",
            "params": {
                "threadId": thread_id,
                "turnId": "turn-1",
                "item": {
                    "id": "user-1",
                    "type": "userMessage",
                    "content": [{"type": "text", "text": "investigate the bug"}],
                },
            },
        },
    )
    store.append(
        source="seed",
        direction="internal",
        message={
            "method": "turn/completed",
            "params": {
                "threadId": thread_id,
                "turn": {"id": "turn-1", "status": "completed"},
            },
        },
    )


def test_semantic_revisions_preserve_competing_noncontiguous_maps():
    store = TraceStore()
    seed_thread(store)
    store.register_semantic_observer(name="fast", lens="thread", reliability=0.5)
    store.register_semantic_observer(name="careful", lens="thread", reliability=1.2)

    store.put_semantic_revision(
        thread_id="thread-main",
        lens="thread",
        observer="fast",
        horizon_seq=3,
        confidence=0.9,
        nodes=[
            {
                "id": "x",
                "title": "First take",
                "summary": "A quick interpretation.",
                "confidence": 0.9,
                "support": [{"start": 1, "end": 1}, {"start": 3, "end": 3}],
            }
        ],
    )
    chosen = store.put_semantic_revision(
        thread_id="thread-main",
        lens="thread",
        observer="careful",
        horizon_seq=3,
        confidence=0.8,
        nodes=[
            {
                "id": "x2",
                "title": "Returned to the same issue",
                "summary": "The episode has non-contiguous support.",
                "confidence": 0.95,
                "support": [
                    {"start": 1, "end": 1, "weight": 0.8},
                    {"start": 3, "end": 3, "weight": 1.0},
                ],
            }
        ],
    )

    outline = store.semantic_outline("thread-main")
    assert outline is not None
    assert outline["revision_id"] == chosen
    assert outline["nodes"][0]["support"][1]["start"] == 3
    assert len(store.semantic_revisions("thread-main", lens="thread")) == 2

    html = render_thread_html(store, "thread-main")
    assert "Returned to the same issue" in html
    assert "[[1,1],[3,3]]" in html


def test_candidate_windows_are_plumbing_not_turn_boundaries():
    store = TraceStore()
    for index in range(1, 301):
        method = "turn/completed" if index in {110, 225, 300} else "item/completed"
        params = {
            "threadId": "t",
            "turnId": f"turn-{index // 100}",
            "item": {"id": f"i-{index}", "type": "agentMessage", "text": str(index)},
        }
        if method == "turn/completed":
            params = {
                "threadId": "t",
                "turn": {"id": f"turn-{index // 100}", "status": "completed"},
            }
        store.append(source="seed", direction="internal", message={"method": method, "params": params})
    windows = plan_candidate_windows(store, "t", target_records=120, overlap_records=20)
    assert len(windows) >= 2
    assert windows[0].end_seq in {110, 225}
    assert windows[1].start_seq <= windows[0].end_seq


def test_live_reasoning_deltas_survive_empty_completed_item():
    store = TraceStore()
    base = {"threadId": "t", "turnId": "turn-1", "itemId": "reason-1"}
    store.append(
        source="live",
        direction="appserver_to_client",
        message={"method": "turn/started", "params": {"threadId": "t", "turn": {"id": "turn-1"}}},
    )
    store.append(
        source="live",
        direction="appserver_to_client",
        message={
            "method": "item/reasoning/summaryTextDelta",
            "params": {**base, "summaryIndex": 0, "delta": "Summary from live deltas"},
        },
    )
    store.append(
        source="live",
        direction="appserver_to_client",
        message={
            "method": "item/reasoning/textDelta",
            "params": {**base, "contentIndex": 0, "delta": "Raw-ish live reasoning"},
        },
    )
    store.append(
        source="live",
        direction="appserver_to_client",
        message={
            "method": "item/completed",
            "params": {
                "threadId": "t",
                "turnId": "turn-1",
                "item": {"id": "reason-1", "type": "reasoning", "summary": [], "content": []},
            },
        },
    )
    html = render_thread_html(store, "t")
    assert "Summary from live deltas" in html
    assert "Raw-ish live reasoning" in html


FAKE_OBSERVER = r"""
import json, sys
for line in sys.stdin:
    msg=json.loads(line)
    method=msg.get("method")
    ident=msg.get("id")
    if method == "initialize":
        print(json.dumps({"jsonrpc":"2.0","id":ident,"result":{}}), flush=True)
    elif method == "initialized":
        pass
    elif method == "thread/fork":
        print(json.dumps({"jsonrpc":"2.0","id":ident,"result":{"thread":{"id":"observer-thread"}}}), flush=True)
    elif method == "turn/start":
        print(json.dumps({"jsonrpc":"2.0","id":ident,"result":{"turn":{"id":"observer-turn"}}}), flush=True)
        print(json.dumps({
          "jsonrpc":"2.0","method":"turn/completed",
          "params":{"threadId":"observer-thread","turn":{"id":"observer-turn","status":"completed"}}
        }), flush=True)
    elif method == "thread/items/list":
        proposal={
          "confidence":0.93,
          "nodes":[{
            "id":"episode-1","parent":None,"ordinal":0,
            "title":"Investigated the bug",
            "summary":"The thread opened by investigating the bug.",
            "confidence":0.9,
            "support":[{"start":1,"end":3,"weight":1.0,"label":None}]
          }]
        }
        print(json.dumps({"jsonrpc":"2.0","id":ident,"result":{"data":[{
          "turnId":"observer-turn",
          "item":{"id":"observer-message","type":"agentMessage","phase":"final","text":json.dumps(proposal)}
        }],"nextCursor":None,"backwardsCursor":None}}), flush=True)
"""


def test_shadow_observer_persists_structured_revision(tmp_path: Path):
    store = TraceStore(tmp_path / "trace.db")
    seed_thread(store)
    fake = tmp_path / "fake_observer.py"
    fake.write_text(FAKE_OBSERVER)
    client = AppServerClient([sys.executable, str(fake)], trace=store)
    with client:
        place = CodexPlace("observer", client).start()
        observer = CodexShadowObserver(place, store)
        revision = observer.observe_window(
            source_thread_id="thread-main",
            window=CandidateWindow("thread-main", 1, 3, 3),
            spec=ObserverSpec(
                name="cartographer",
                angle="Describe the significant semantic episodes.",
                effort="low",
            ),
        )
    outline = store.semantic_outline("thread-main", revision_id=revision)
    assert outline is not None
    assert outline["observer"] == "cartographer"
    assert outline["nodes"][0]["title"] == "Investigated the bug"
