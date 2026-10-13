"""Server paging must conserve evidence and identity, not just shrink the DOM."""
from __future__ import annotations

import json

import pytest

from eidos.api import EidosAPI, thread_payload
from eidos.history import SourceRecordNotFound
from eidos.trace import TraceStore


def record(store, thread, turn, text="evidence", **extra):
    return store.append(source="synthetic", direction="internal", message={
        "method": "$history/item", "params": {"threadId": thread, "turnId": turn,
        "item": {"id": f"{turn}-{text}", "type": "agentMessage", "text": text,
                 "futureField": extra}},
    })


def seed(store, count=1200):
    return [record(store, "long", f"turn-{i}", f"Decision {i}", ordinal=i) for i in range(count)]


def test_complete_pagination_loads_only_selected_raw_records_and_keeps_unknown_fields(monkeypatch):
    store = TraceStore()
    evidence = seed(store)
    monkeypatch.setattr(store, "records", lambda **kw: pytest.fail("unbounded raw history read"))
    page = thread_payload(store, "long")
    assert page["recordCount"] == 1200
    assert page["window"]["totalTurns"] == 1200
    assert len(page["turns"]) == 40
    assert not page["window"]["hasEarlier"]
    seen = []
    while True:
        seen.extend(turn["id"] for turn in page["turns"])
        for turn in page["turns"]:
            item = turn["items"][0]
            assert item["raw"]["futureField"]["ordinal"] == int(turn["id"].split("-")[1])
        cursor = page["window"]["nextAnchorSeq"]
        if cursor is None:
            break
        page = thread_payload(store, "long", anchor_seq=cursor)
    assert seen == [f"turn-{i}" for i in range(1200)]
    assert page["window"]["startIndex"] == 1160
    assert page["window"]["endSeq"] == evidence[-1].seq
    previous = thread_payload(store, "long", anchor_seq=page["window"]["previousAnchorSeq"])
    assert previous["window"]["startIndex"] == 1120
    assert previous["window"]["nextAnchorSeq"] == page["window"]["anchorSeq"]


def test_window_query_does_not_materialize_other_turn_payloads(monkeypatch):
    store = TraceStore()
    seed(store)
    original = json.loads
    parsed = []

    def observe(text, *args, **kwargs):
        parsed.append(text)
        return original(text, *args, **kwargs)

    monkeypatch.setattr(json, "loads", observe)
    payload = thread_payload(store, "long", around_seq=1190)
    assert len(payload["turns"]) == 40
    assert len(parsed) == 40
    assert all('"turn-11' in text for text in parsed)


def test_idle_poll_omits_raw_projection_and_semantic_nodes_but_detects_semantic_changes(monkeypatch):
    store = TraceStore()
    seed(store, 90)
    page = thread_payload(store, "long", around_seq=70)
    with monkeypatch.context() as patch:
        patch.setattr("eidos.api.window_records", lambda *args: pytest.fail("idle raw read"))
        patch.setattr(store, "semantic_outline", lambda *args, **kw: pytest.fail("idle outline read"))
        patch.setattr("eidos.api._thread_preview", lambda *args: pytest.fail("idle preview read"))
        idle = thread_payload(store, "long", anchor_seq=page["window"]["anchorSeq"], known_version=page["version"])
    assert idle == {"id": "long", "unchanged": True, "version": page["version"], "window": page["window"]}
    store.register_semantic_observer(name="review", lens="thread")
    revision = store.put_semantic_revision(thread_id="long", lens="thread", observer="review",
        horizon_seq=90, nodes=[{"id": "decision", "title": "Dispersed support",
        "support": [{"start": 5}, {"start": 80}]}])
    changed = thread_payload(store, "long", anchor_seq=41, known_version=page["version"])
    assert changed["outline"]["revision_id"] == revision
    assert changed["version"] != page["version"]
    store.register_semantic_observer(name="review", lens="thread", reliability=0.5)
    reliability = thread_payload(store, "long", anchor_seq=41, known_version=changed["version"])
    assert reliability["version"] != changed["version"]
    assert reliability["outline"]["reliability"] == 0.5
    # A token for one page cannot suppress fetching another page or thread.
    assert "turns" in thread_payload(store, "long", anchor_seq=1, known_version=reliability["version"])
    assert "turns" in thread_payload(store, "missing", known_version=reliability["version"])


def test_exact_source_jump_rejects_interleaved_thread_and_loads_whole_turn():
    store = TraceStore()
    first = record(store, "long", "same", "first")
    other = record(store, "neighbor", "same", "other")
    last = record(store, "long", "same", "last")
    page = thread_payload(store, "long", around_seq=last.seq)
    assert page["turns"][0]["startSeq"] == first.seq
    assert page["turns"][0]["endSeq"] == last.seq
    assert [item["text"] for item in page["turns"][0]["items"]] == ["first", "last"]
    with pytest.raises(SourceRecordNotFound, match="does not belong"):
        thread_payload(store, "long", around_seq=other.seq)
    with pytest.raises(SourceRecordNotFound):
        thread_payload(store, "long", around_seq=9999)


def test_append_and_late_old_turn_events_keep_saved_page_anchor():
    store = TraceStore()
    records = seed(store, 81)
    page = thread_payload(store, "long", around_seq=60)
    first_ids = [turn["id"] for turn in page["turns"]]
    record(store, "long", "turn-0", "late old event")
    record(store, "long", "turn-81", "new event")
    changed = thread_payload(store, "long", anchor_seq=page["window"]["anchorSeq"], known_version=page["version"])
    assert [turn["id"] for turn in changed["turns"]] == first_ids
    assert changed["window"]["anchorSeq"] == records[40].seq
    assert changed["window"]["nextAnchorSeq"] == records[80].seq
    assert changed["window"]["totalTurns"] == 82


def test_projected_membership_distinguishes_interleaved_items_and_turns():
    store = TraceStore()
    start = store.append(source="fixture", direction="internal", message={
        "method": "item/started", "params": {"threadId": "long", "turnId": "old",
        "item": {"id": "tool", "type": "commandExecution", "command": "fixture only"}},
    })
    other_item = record(store, "long", "old", "separate item in same turn")
    other_turn = record(store, "long", "new", "decision in later turn")
    end = store.append(source="fixture", direction="internal", message={
        "method": "item/completed", "params": {"threadId": "long", "turnId": "old",
        "item": {"id": "tool", "type": "commandExecution", "aggregatedOutput": "late result"}},
    })
    page = thread_payload(store, "long", around_seq=other_turn.seq)
    old, new = page["turns"]
    tool, separate = old["items"]
    assert old["startSeq"] < other_turn.seq < old["endSeq"]
    assert old["recordSeqs"] == [start.seq, other_item.seq, end.seq]
    assert new["recordSeqs"] == [other_turn.seq]
    assert tool["startSeq"] < other_item.seq < tool["endSeq"]
    assert tool["recordSeqs"] == [start.seq, end.seq]
    assert separate["recordSeqs"] == [other_item.seq]


def test_pending_send_keeps_evidence_anchor_when_native_ack_correlates_turn():
    store = TraceStore()
    request = store.append(source="native-fixture", direction="client_to_appserver", message={
        "id": 7, "method": "turn/start", "params": {"threadId": "long", "input": [{"type": "text", "text": "question"}]},
    })
    pending = thread_payload(store, "long")
    assert pending["turns"][0]["id"] == f"pending@{request.seq}"
    assert pending["turns"][0]["startSeq"] == request.seq
    store.append(source="native-fixture", direction="appserver_to_client", message={"id": 7, "result": {"turn": {"id": "native-turn"}}})
    acknowledged = thread_payload(store, "long", anchor_seq=request.seq, known_version=pending["version"])
    assert acknowledged["turns"][0]["id"] == "native-turn"
    assert acknowledged["turns"][0]["inputs"] == [{"type": "text", "text": "question"}]
    assert acknowledged["window"]["anchorSeq"] == request.seq
    assert acknowledged["window"]["totalTurns"] == 1


def test_saved_native_event_anchor_survives_late_ack_merging_an_earlier_pending_send():
    store = TraceStore()
    request = store.append(source="native", direction="client_to_appserver", message={
        "id": 7, "method": "turn/start", "params": {"threadId": "long", "input": [{"type": "text", "text": "question"}]},
    })
    event = record(store, "long", "native-turn", "answer before acknowledgement")
    seed(store, 45)
    saved = thread_payload(store, "long", anchor_seq=event.seq)
    assert saved["turns"][0]["id"] == "native-turn"
    assert saved["window"]["anchorSeq"] == event.seq
    store.append(source="native", direction="appserver_to_client", message={"id": 7, "result": {"turn": {"id": "native-turn"}}})
    reopened = thread_payload(store, "long", anchor_seq=event.seq, known_version=saved["version"])
    assert reopened["turns"][0]["id"] == "native-turn"
    assert reopened["window"]["anchorSeq"] == request.seq
    assert reopened["turns"][0]["inputs"] == [{"type": "text", "text": "question"}]
    assert reopened["turns"][0]["items"][0]["text"] == "answer before acknowledgement"


def test_pinned_map_must_be_a_thread_revision_owned_by_this_history():
    store = TraceStore()
    seed(store, 3)
    revision = store.put_semantic_revision(thread_id="neighbor", lens="thread", observer="fixture",
        horizon_seq=3, nodes=[])
    other_lens = store.put_semantic_revision(thread_id="long", lens="other", observer="fixture",
        horizon_seq=3, nodes=[])
    for ref in [revision, other_lens, "invented-revision"]:
        with pytest.raises(SourceRecordNotFound, match="semantic revision"):
            thread_payload(store, "long", revision_id=ref)


def test_snapshot_version_and_projection_agree_under_an_external_writer(tmp_path, monkeypatch):
    path = tmp_path / "history.db"
    store = TraceStore(path)
    other = TraceStore(path)
    seed(store, 2)
    import eidos.api as api_module
    original = api_module.window_records

    def concurrent_append(*args):
        record(other, "long", "turn-0", "arrived during read")
        return original(*args)

    with monkeypatch.context() as patch:
        patch.setattr(api_module, "window_records", concurrent_append)
        before = thread_payload(store, "long")
    assert before["recordCount"] == 2
    assert len(before["turns"][0]["items"]) == 1
    after = thread_payload(store, "long", known_version=before["version"])
    assert after["recordCount"] == 3
    assert len(after["turns"][0]["items"]) == 2
    other.close()
    store.close()


@pytest.mark.parametrize("query", [
    {"limit": ["0"]}, {"limit": ["41"]}, {"limit": ["-2"]}, {"aroundSeq": ["x"]},
    {"anchorSeq": ["0"]}, {"anchorSeq": ["1", "2"]},
    {"aroundSeq": ["999999999999999999999999999999999"]},
    {"anchorSeq": ["1"], "aroundSeq": ["2"]},
])
def test_http_rejects_invalid_or_unbounded_page_selectors(query):
    store = TraceStore()
    seed(store, 5)
    api = EidosAPI(store)
    try:
        status, body = api.dispatch(None, "GET", "/api/threads/long", query)
        assert status == 400
        assert body["error"]
    finally:
        api.close()


def test_thread_list_and_empty_thread_do_not_read_entire_history(monkeypatch):
    store = TraceStore()
    seed(store)
    monkeypatch.setattr(store, "records", lambda **kw: pytest.fail("unbounded history read"))
    api = EidosAPI(store)
    try:
        status, listing = api.dispatch(None, "GET", "/api/threads", {})
        assert status == 200
        assert listing["threads"][0]["turn_count"] == 1200
        empty = thread_payload(store, "empty")
        assert empty["turns"] == []
        assert empty["window"]["totalTurns"] == 0
        assert empty["window"]["anchorSeq"] is None
        status, body = api.dispatch(None, "GET", "/api/threads/long", {"aroundSeq": ["9999"]})
        assert status == 404
    finally:
        api.close()
