from pathlib import Path
import sys

from eidos.codex import AppServerClient, CodexPlace
from eidos.semantic import (
    CandidateWindow,
    CodexShadowObserver,
    ObserverSpec,
    build_story_beats,
    choose_leaf_model,
    format_story_window,
    plan_candidate_windows,
)
from eidos.semantic_tree import (
    SemanticWindow,
    TreeNode,
    _run_truncated_leaf_worker,
    pack_nodes_by_mass,
    plan_semantic_windows,
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




class FakeModelClient:
    def __init__(self, models):
        self.models = models

    def model_list(self, *, limit=100, include_hidden=False):
        return {"data": self.models}


def test_leaf_model_selection_only_switches_on_clear_catalog_signal(monkeypatch):
    monkeypatch.delenv("EIDOS_SUMMARY_MODEL", raising=False)
    client = FakeModelClient(
        [
            {
                "model": "gpt-expensive-pro",
                "displayName": "GPT Pro",
                "description": "deep high-capability model",
                "modelSpecialty": None,
                "hidden": False,
                "supportedReasoningEfforts": [{"reasoningEffort": "low"}],
            },
            {
                "model": "gpt-fast-mini",
                "displayName": "Fast Mini",
                "description": "small efficient low latency model",
                "modelSpecialty": None,
                "hidden": False,
                "supportedReasoningEfforts": [{"reasoningEffort": "low"}],
            },
        ]
    )
    assert choose_leaf_model(client) == "gpt-fast-mini"


def test_leaf_model_selection_inherits_when_catalog_is_ambiguous(monkeypatch):
    monkeypatch.delenv("EIDOS_SUMMARY_MODEL", raising=False)
    client = FakeModelClient(
        [
            {
                "model": "model-a",
                "displayName": "Model A",
                "description": "general model",
                "modelSpecialty": None,
                "hidden": False,
                "supportedReasoningEfforts": [{"reasoningEffort": "low"}],
            }
        ]
    )
    assert choose_leaf_model(client) is None


def test_leaf_model_selection_respects_explicit_override(monkeypatch):
    monkeypatch.setenv("EIDOS_SUMMARY_MODEL", "my-summary-model")
    assert choose_leaf_model(FakeModelClient([])) == "my-summary-model"


def test_story_substrate_foregrounds_dialogue_and_collapses_execution_churn():
    store = TraceStore()
    thread_id = "story-thread"
    turn_id = "turn-story"

    store.append(
        source="seed",
        direction="internal",
        message={
            "method": "item/completed",
            "params": {
                "threadId": thread_id,
                "turnId": turn_id,
                "item": {
                    "id": "user-story",
                    "type": "userMessage",
                    "content": [{"type": "text", "text": "Why is the cache invalidation wrong?"}],
                },
            },
        },
    )
    for index in range(8):
        store.append(
            source="seed",
            direction="internal",
            message={
                "method": "item/completed",
                "params": {
                    "threadId": thread_id,
                    "turnId": turn_id,
                    "item": {
                        "id": f"cmd-{index}",
                        "type": "commandExecution",
                        "command": f"rg pattern-{index} src/",
                        "aggregatedOutput": f"ordinary search output {index}",
                        "status": "completed",
                    },
                },
            },
        )
    store.append(
        source="seed",
        direction="internal",
        message={
            "method": "item/completed",
            "params": {
                "threadId": thread_id,
                "turnId": turn_id,
                "item": {
                    "id": "assistant-story",
                    "type": "agentMessage",
                    "phase": "final",
                    "text": "The invalidation key omitted the namespace, so unrelated entries collided.",
                },
            },
        },
    )

    records = store.records(thread_id=thread_id)
    window = CandidateWindow(thread_id, records[0].seq, records[-1].seq, len(records))
    beats = build_story_beats(store, window)

    assert [beat.kind for beat in beats] == ["user", "execution-support", "assistant-final"]
    assert beats[0].importance == 1.0
    assert beats[1].importance < beats[2].importance
    assert "8 execution items" in beats[1].text

    rendered = format_story_window(store, window)
    assert "SPINE · USER" in rendered
    assert "SPINE · ASSISTANT FINAL" in rendered
    assert rendered.count("EXECUTION SUPPORT") == 1
    assert "item/completed" not in rendered




FAKE_TRUNCATED_LEAF = r"""
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
        print(json.dumps({
          "jsonrpc":"2.0","id":ident,
          "result":{"thread":{"id":"leaf-thread"}}
        }), flush=True)
    elif method == "turn/start":
        print(json.dumps({
          "jsonrpc":"2.0","id":ident,
          "result":{"turn":{"id":"leaf-turn"}}
        }), flush=True)
        proposal={
          "signal":0.8,
          "assessment":"This region mattered.",
          "episodes":[{
            "id":"ep",
            "title":"Bug becomes boundary",
            "summary":"The failure exposed the real boundary.",
            "importance":0.9,
            "confidence":0.9,
            "support":[{"start":1,"end":2,"weight":1.0,"label":None}],
            "arcHints":["boundary"]
          }]
        }
        print(json.dumps({
          "jsonrpc":"2.0","method":"item/completed",
          "params":{
            "threadId":"leaf-thread","turnId":"leaf-turn",
            "item":{"id":"leaf-message","type":"agentMessage","phase":"final","text":json.dumps(proposal)}
          }
        }), flush=True)
        print(json.dumps({
          "jsonrpc":"2.0","method":"turn/completed",
          "params":{"threadId":"leaf-thread","turn":{"id":"leaf-turn","status":"completed"}}
        }), flush=True)
"""


def test_leaf_enrichment_forks_source_at_historical_cutoff(tmp_path: Path):
    store = TraceStore(tmp_path / "trace.db")
    thread_id = "source-thread"
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
                    "content": [{"type": "text", "text": "investigate"}],
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

    fake = tmp_path / "fake_leaf.py"
    fake.write_text(FAKE_TRUNCATED_LEAF)
    events = []
    value = _run_truncated_leaf_worker(
        command=[sys.executable, str(fake)],
        store=store,
        source_thread_id=thread_id,
        window=SemanticWindow(
            index=0,
            start_seq=1,
            end_seq=2,
            beat_count=1,
            semantic_mass=1.0,
        ),
        global_retro={
            "confidence": 1.0,
            "narrative": "The bug mattered.",
            "durableArcs": [],
            "deadEnds": [],
            "surprises": [],
            "attentionGuidance": [],
        },
        model=None,
        progress=lambda *args: events.append(args),
        total_windows=1,
    )

    fork = next(
        record.message
        for record in store.records()
        if record.method == "thread/fork"
    )
    assert fork["params"]["threadId"] == thread_id
    assert fork["params"]["lastTurnId"] == "turn-1"
    assert value["episodes"][0]["title"] == "Bug becomes boundary"
    assert any(event[0] == "leaf:fork" for event in events)


def test_semantic_window_planner_is_not_raw_record_count_biased():
    store = TraceStore()
    thread_id = "mass-thread"
    turn_id = "turn-mass"

    store.append(
        source="seed",
        direction="internal",
        message={
            "method": "item/completed",
            "params": {
                "threadId": thread_id,
                "turnId": turn_id,
                "item": {
                    "id": "user-mass-1",
                    "type": "userMessage",
                    "content": [{"type": "text", "text": "figure out the deployment issue"}],
                },
            },
        },
    )
    for index in range(120):
        store.append(
            source="seed",
            direction="internal",
            message={
                "method": "item/completed",
                "params": {
                    "threadId": thread_id,
                    "turnId": turn_id,
                    "item": {
                        "id": f"cmd-mass-{index}",
                        "type": "commandExecution",
                        "command": f"rg clue-{index} src/",
                        "aggregatedOutput": "ordinary search output",
                        "status": "completed",
                    },
                },
            },
        )
    store.append(
        source="seed",
        direction="internal",
        message={
            "method": "item/completed",
            "params": {
                "threadId": thread_id,
                "turnId": turn_id,
                "item": {
                    "id": "assistant-mass-1",
                    "type": "agentMessage",
                    "phase": "final",
                    "text": "The deploy path was using the wrong environment binding.",
                },
            },
        },
    )
    store.append(
        source="seed",
        direction="internal",
        message={
            "method": "item/completed",
            "params": {
                "threadId": thread_id,
                "turnId": "turn-mass-2",
                "item": {
                    "id": "user-mass-2",
                    "type": "userMessage",
                    "content": [{"type": "text", "text": "make that binding explicit"}],
                },
            },
        },
    )
    store.append(
        source="seed",
        direction="internal",
        message={
            "method": "item/completed",
            "params": {
                "threadId": thread_id,
                "turnId": "turn-mass-2",
                "item": {
                    "id": "assistant-mass-2",
                    "type": "agentMessage",
                    "phase": "final",
                    "text": "The explicit binding fixed the deployment path.",
                },
            },
        },
    )

    assert len(store.records(thread_id=thread_id)) > 120
    windows = plan_semantic_windows(
        store,
        thread_id,
        target_mass=2.0,
        overlap_beats=0,
    )
    # The 120-command burst is one low-prior execution beat, not 120 windows.
    assert len(windows) <= 3
    assert any(window.end_seq - window.start_seq > 100 for window in windows)


def test_rollup_packs_low_importance_nodes_more_densely():
    def nodes(importance: float):
        return [
            TreeNode(
                node_id=f"n-{importance}-{index}",
                title=f"node {index}",
                summary="summary",
                importance=importance,
                confidence=1.0,
                support=[{"start": index + 1, "end": index + 1, "weight": 1.0, "label": None}],
            )
            for index in range(6)
        ]

    low_groups = pack_nodes_by_mass(nodes(0.15), target_mass=1.0, max_items=10)
    high_groups = pack_nodes_by_mass(nodes(0.8), target_mass=1.0, max_items=10)

    assert len(low_groups) < len(high_groups)
    assert sum(len(group) for group in low_groups) == 6
    assert sum(len(group) for group in high_groups) == 6


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
        proposal={
          "confidence":0.93,
          "note":"",
          "nodes":[{
            "id":"episode-1","parent":None,"ordinal":0,
            "title":"Investigated the bug",
            "summary":"The thread opened by investigating the bug.",
            "confidence":0.9,
            "support":[{"start":1,"end":3,"weight":1.0,"label":None}]
          }]
        }
        print(json.dumps({
          "jsonrpc":"2.0","method":"item/completed",
          "params":{
            "threadId":"observer-thread",
            "turnId":"observer-turn",
            "item":{"id":"observer-message","type":"agentMessage","phase":"final","text":json.dumps(proposal)}
          }
        }), flush=True)
        print(json.dumps({
          "jsonrpc":"2.0","method":"turn/completed",
          "params":{"threadId":"observer-thread","turn":{"id":"observer-turn","status":"completed"}}
        }), flush=True)
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
    assert all(t["thread_id"] != "observer-thread" for t in store.threads())
    assert any(t["thread_id"] == "observer-thread" for t in store.threads(include_internal=True))
