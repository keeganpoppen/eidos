"""Persisted synthetic navigation evidence, not a native or usability benchmark."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from eidos.investigation import InvestigationStore
from eidos.trace import TraceStore
from eidos.view import project_thread


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "investigation_demo.py"
spec = importlib.util.spec_from_file_location("history_demo", SCRIPT)
assert spec is not None and spec.loader is not None
demo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(demo)


@pytest.fixture
def seeded(tmp_path):
    path = tmp_path / "history.db"
    store = TraceStore(path)
    packet = demo.seed(store, long_history=True)
    yield path, store, packet
    store.close()


def test_long_history_is_persisted_without_retargeting_original_workflow(seeded):
    _, store, packet = seeded
    threads = {row["thread_id"]: row for row in store.threads()}
    assert threads["fixture-design"]["turn_count"] == 24
    assert threads["fixture-experiment"]["turn_count"] == 24
    assert threads[demo.LONG_HISTORY_THREAD]["turn_count"] == 1200
    assert threads[demo.LONG_HISTORY_THREAD]["first_seq"] == 97
    assert [source["startSeq"] for source in packet["selections"]] == [12, 38, 72]
    assert "saved turn/start acknowledgement" in store.get(14).raw_text
    assert all(record.source.startswith("synthetic-") for record in store.records())
    assert not any(record.method == "turn/start" for record in store.records())
    # The old packet remains an ordinary admissible context after the new seed.
    work = InvestigationStore(store).create(packet)
    assert [record["seq"] for record in work["contexts"][0]["records"]] == [12, 38, 72]


def test_distant_support_and_tool_detour_are_exact_selectable_evidence(seeded):
    _, store, _ = seeded
    outline = store.semantic_outline(demo.LONG_HISTORY_THREAD)
    spans = outline["nodes"][0]["support"]
    assert len(spans) == 2
    rejection, decision = [store.get(span["start"]) for span in spans]
    assert rejection.item_id == "fixture-long-history-turn-20-answer"
    assert decision.item_id == "fixture-long-history-turn-1100-answer"
    assert decision.seq - rejection.seq > 2000
    assert all(span["start"] == span["end"] for span in spans)
    work = InvestigationStore(store).create({
        "requestId": "long-history-evidence", "title": "Recover the controlling decision",
        "question": "Which decision addresses the earlier rejected retry, and why?",
        "selections": [{"threadId": demo.LONG_HISTORY_THREAD, "startSeq": span["start"],
                        "endSeq": span["end"], "rationale": span["label"]} for span in spans],
    })
    context = work["contexts"][0]
    assert [record["seq"] for record in context["records"]] == [rejection.seq, decision.seq]
    assert "Routine review" not in context["projectedPrompt"]
    assert "synthetic recovery case" not in context["projectedPrompt"]

    view = project_thread(store, demo.LONG_HISTORY_THREAD)
    tool_turn = view.turns[600]
    command = tool_turn.items["fixture-long-history-turn-600-command"]
    assert len(command.events) == 98  # start, 96 deltas, complete
    assert command.final_item["aggregatedOutput"].count("synthetic recovery case") == 96
    assert command.final_item["futureField"]["executed"] is False
    neighbor, = store.records(thread_id="fixture-history-neighbor")
    assert command.events[0].seq < neighbor.seq < command.events[-1].seq
    assert neighbor.seq not in {record.seq for record in tool_turn.events}
    assert neighbor.item_id not in tool_turn.items


def test_repeat_seed_refuses_and_resume_preserves_source_identity(seeded, monkeypatch, capsys):
    path, store, _ = seeded
    before = [(record.seq, record.raw_text) for record in store.records()]
    outline = store.semantic_outline(demo.LONG_HISTORY_THREAD)
    with pytest.raises(ValueError, match="empty trace database"):
        demo.seed(store)
    assert [(record.seq, record.raw_text) for record in store.records()] == before
    monkeypatch.setattr("sys.argv", [str(SCRIPT), "--db", str(path), "--resume", "--long-history"])
    demo.main()
    assert "Reopening synthetic demo" in capsys.readouterr().out
    reopened = TraceStore(path)
    try:
        assert [(record.seq, record.raw_text) for record in reopened.records()] == before
        assert reopened.semantic_outline(demo.LONG_HISTORY_THREAD) == outline
    finally:
        reopened.close()


def test_default_demo_keeps_the_original_small_two_thread_fixture():
    store = TraceStore()
    try:
        demo.seed(store)
        assert len(store.records()) == 96
        assert {row["thread_id"] for row in store.threads()} == {"fixture-design", "fixture-experiment"}
    finally:
        store.close()


def test_append_preserves_sources_and_adds_late_evidence_before_a_new_turn(seeded):
    path, store, _ = seeded
    before = [(record.seq, record.raw_text) for record in store.records()]
    outline = store.semantic_outline(demo.LONG_HISTORY_THREAD)
    appended = demo.append_long_history(store)
    assert appended["totalTurns"] == 1201
    assert [(record.seq, record.raw_text) for record in store.records()][:len(before)] == before
    assert store.get(appended["lateSeq"]).turn_id == "fixture-long-history-turn-20"
    assert store.get(appended["appendedSeq"]).turn_id == "fixture-long-history-turn-1200"
    assert store.semantic_outline(demo.LONG_HISTORY_THREAD) == outline
    reopened = TraceStore(path)
    try:
        assert reopened.get(appended["appendedSeq"]).item_id == "fixture-long-history-appended-answer"
    finally:
        reopened.close()
    with pytest.raises(ValueError, match="unextended synthetic long-history"):
        demo.append_long_history(store)
