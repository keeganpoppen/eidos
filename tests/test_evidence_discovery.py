"""Source discovery over authored public history. No native/model calls."""
from copy import deepcopy
import hashlib
import json
import sqlite3
import time

import pytest

from eidos.api import EidosAPI, thread_payload
from eidos.evidence_discovery import EvidenceDiscovery, INDEX_VERSION, SCOPE
from eidos.investigation import InvestigationError, InvestigationStore
from eidos.trace import TraceRecord, TraceStore, PrivateTraceAccessError


def event(trace, method="item/completed", *, thread="history", turn="turn", item="answer",
          kind="agentMessage", text=None, direction="appserver_to_client", **fields):
    params = {"threadId": thread, "turnId": turn}
    if method in {"item/started", "item/completed", "$history/item"}:
        params["item"] = {"id": item, "type": kind, **fields}
        if text is not None:
            params["item"]["text"] = text
    else:
        params.update(itemId=item, **fields)
    return trace.append(source="authored", direction=direction, message={"method": method, "params": params})


def query(discovery, q="needle", **extra):
    return discovery.search({"q": [q], **{key: [str(value)] for key, value in extra.items()}})


def inspect(discovery, hit, q="needle"):
    return discovery.inspect(hit["id"], {"q": [q], "version": [hit["version"]]})


@pytest.fixture
def saved(tmp_path):
    trace = TraceStore(tmp_path / "search.db")
    yield trace, EvidenceDiscovery(trace)
    trace.close()


def test_split_delta_contributors_are_exact_and_save_without_interloper(saved):
    trace, discovery = saved
    first = event(trace, "item/agentMessage/delta", delta="A brittle trans")
    interloper = event(trace, item="other", text="Do not select this unrelated record")
    last = event(trace, "item/agentMessage/delta", delta="action was rejected.")
    hit, = query(discovery, "TRANSACTION")["hits"]
    assert hit["excerpt"] == "A brittle transaction was rejected."
    assert hit["recordSeqs"] == [first.seq, last.seq]
    assert hit["anchorSeq"] == first.seq
    detail = inspect(discovery, hit, "transaction")
    assert detail["hit"] == hit
    assert [record["rawText"] for record in detail["records"]] == [first.raw_text, last.raw_text]
    assert all(record["sha256"] == hashlib.sha256(record["rawText"].encode()).hexdigest()
               for record in detail["records"])
    body = {"requestId": "exact", "title": "Discovered", "question": "What was rejected?",
            "selections": [{"threadId": record["threadId"], "startSeq": record["seq"], "endSeq": record["seq"]}
                           for record in detail["records"]]}
    context = InvestigationStore(trace).create(body)["contexts"][0]
    assert [r["seq"] for r in context["records"]] == [first.seq, last.seq]
    assert interloper.raw_text not in context["projectedPrompt"]
    assert [r.raw_text for r in trace.records()] == [first.raw_text, interloper.raw_text, last.raw_text]


def test_final_replaces_deltas_empty_final_falls_back_and_started_does_not_replace(saved):
    trace, discovery = saved
    delta = event(trace, "item/agentMessage/delta", delta="old needle")
    hit, = query(discovery)["hits"]
    empty = event(trace, text="")
    assert query(discovery)["hits"][0]["recordSeqs"] == [delta.seq]
    assert thread_payload(trace, "history")["turns"][0]["items"][0]["text"] == "old needle"
    final = event(trace, text="new conclusion")
    assert query(discovery)["hits"] == []
    with pytest.raises(InvestigationError) as error:
        inspect(discovery, hit)
    assert error.value.status == 409
    new_hit, = query(discovery, "conclusion")["hits"]
    assert new_hit["id"] == hit["id"] and new_hit["version"] != hit["version"]
    assert new_hit["recordSeqs"] == [final.seq]
    event(trace, "item/started", text="late started needle")
    assert query(discovery)["hits"] == []
    assert query(discovery, "conclusion")["hits"] == [new_hit]
    later = event(trace, "$history/item", text="latest history needle")
    assert query(discovery)["hits"][0]["recordSeqs"] == [later.seq]
    assert empty.seq not in new_hit["recordSeqs"]


def test_same_identifiers_in_another_thread_are_independent(saved):
    trace, discovery = saved
    first = event(trace, text="needle", thread="left")
    second = event(trace, text="needle", thread="right")
    hits = query(discovery)["hits"]
    assert len(hits) == 2 and hits[0]["id"] != hits[1]["id"]
    assert [h["recordSeqs"] for h in hits] == [[first.seq], [second.seq]]
    assert query(discovery, threadId="left")["hits"] == [hits[0]]


def test_reasoning_parts_native_indices_and_nonstring_final_precedence(saved):
    trace, discovery = saved
    one = event(trace, "item/reasoning/summaryTextDelta", summaryIndex=1, delta="second needle")
    zero = event(trace, "item/reasoning/summaryTextDelta", summaryIndex=0, delta="first needle")
    content = event(trace, "item/reasoning/textDelta", contentIndex=7, delta="content needle")
    fields = {h["field"]: h["recordSeqs"] for h in query(discovery)["hits"]}
    assert fields == {"reasoning.summary/1": [one.seq], "reasoning.summary/0": [zero.seq],
                      "reasoning.content/7": [content.seq]}
    assert query(discovery, "needlefirst")["hits"] == []  # do not concatenate parts
    final = event(trace, kind="reasoning", summary=[{"unknown": "needle"}, "final needle"], content=[None])
    hit, = query(discovery)["hits"]
    assert hit["field"] == "reasoning.summary/1" and hit["recordSeqs"] == [final.seq]
    projected = thread_payload(trace, "history")["turns"][0]["items"][0]
    assert projected["summary"] == ["{'unknown': 'needle'}", "final needle"]
    assert projected["content"] == ["None"]  # legacy renderer behavior stays unchanged


def test_known_fields_only_and_no_cross_field_phrase(saved):
    trace, discovery = saved
    user = event(trace, kind="userMessage", item="user", content=[
        {"type": "text", "text": "user needle", "future": "hidden-canary"},
        {"type": "image", "text": "hidden-canary", "path": "hidden-canary"},
        {"type": "text", "text": "other text"},
    ])
    command = event(trace, kind="commandExecution", item="cmd", command="echo needle", aggregatedOutput="output needle")
    file = event(trace, kind="fileChange", item="file", changes=[{"path": "needle.py", "patch": "hidden-canary"}])
    event(trace, item="unknown", kind="future", text="hidden-canary")
    event(trace, item="tool", kind="mcpToolCall", arguments={"text": "hidden-canary"})
    event(trace, item="nonstring", kind="commandExecution", command={"text": "hidden-canary"})
    fields = {h["field"]: h["recordSeqs"] for h in query(discovery)["hits"]}
    assert fields == {"userMessage.content/0/text": [user.seq], "commandExecution.command": [command.seq],
                      "commandExecution.output": [command.seq], "fileChange.changes/0/path": [file.seq]}
    assert query(discovery, "hidden-canary")["hits"] == []
    assert query(discovery, "needleother")["hits"] == []
    assert query(discovery, "needleoutput")["hits"] == []


def test_provider_control_and_publication_cannot_overwrite_eligible_item(saved):
    trace, discovery = saved
    first = event(trace, text="visible needle", futureField="excluded-canary")
    event(trace, direction="provider_response", text="excluded-canary")
    event(trace, direction="provider_request", text="excluded-canary")
    event(trace, "account/read", text="excluded-canary")
    event(trace, "$capsule/result", text="excluded-canary", version=1, provenance={"kind": "private-capsule"})
    event(trace, "item/reasoning/textUnexpected", contentIndex=0, delta="excluded-canary")
    assert query(discovery, "excluded-canary")["hits"] == []
    hit, = query(discovery)["hits"]
    assert hit["recordSeqs"] == [first.seq]
    # Unknowns are excluded from discovery, retained exactly on deliberate inspection.
    assert "excluded-canary" in inspect(discovery, hit)["records"][0]["rawText"]


def test_pending_turn_input_hydration_and_user_message_suppression(saved):
    trace, discovery = saved
    pending = trace.append(source="authored", direction="client_to_appserver", message={"id": 11, "method": "turn/start",
        "params": {"threadId": "history", "input": [{"type": "text", "text": "pending needle"},
                                                    {"type": "skill", "name": "excluded-canary"}]}})
    hit, = query(discovery)["hits"]
    assert hit["itemId"] is None and hit["turnId"] == f"pending@{pending.seq}"
    trace.append(source="authored", direction="appserver_to_client", message={"id": 11, "result": {"turn": {"id": "hydrated"}}})
    hydrated, = query(discovery)["hits"]
    assert hydrated["id"] == hit["id"] and hydrated["turnId"] == "hydrated"
    with pytest.raises(InvestigationError) as error:
        inspect(discovery, hit)
    assert error.value.status == 409
    assert inspect(discovery, hydrated)["records"][0]["rawText"] == pending.raw_text
    event(trace, turn="hydrated", kind="userMessage", content=[{"type": "text", "text": "actual user text"}])
    assert query(discovery)["hits"] == []
    assert query(discovery, "excluded-canary")["hits"] == []


def test_casefold_literal_symbols_and_exact_excerpt_contributors(saved):
    trace, discovery = saved
    ignored = event(trace, "item/agentMessage/delta", delta="x" * 1000)
    useful = event(trace, "item/agentMessage/delta", delta="before Straße 100%_literal after" + "z" * 1000)
    hit, = query(discovery, "STRASSE")["hits"]
    assert "Straße" in hit["excerpt"] and len(hit["excerpt"]) <= 240
    assert hit["recordSeqs"] == [ignored.seq, useful.seq]  # left excerpt chars include previous chunk
    specific = query(discovery, "%_literal")["hits"]
    assert len(specific) == 1
    assert query(discovery, "100___")["hits"] == []
    assert query(discovery, "%wildcard%")["hits"] == []
    # Every source character of the excerpt, including distant matching-tail chunks, is represented.
    for _ in range(300):
        event(trace, "item/agentMessage/delta", item="many", delta="a")
    many, = query(discovery, "a" * 200)["hits"]
    assert len(many["recordSeqs"]) == 238 and len(many["excerpt"]) == 239
    assert len(inspect(discovery, many, "a" * 200)["records"]) == 238


def test_long_field_is_fully_searchable_but_raw_inspection_explicitly_bounded(saved):
    trace, discovery = saved
    record = event(trace, text="x" * (140 * 1024) + "late needle")
    hit, = query(discovery)["hits"]
    assert hit["excerpt"].endswith("late needle") and len(hit["excerpt"]) <= 240
    assert hit["recordSeqs"] == [record.seq]
    with pytest.raises(InvestigationError) as error:
        inspect(discovery, hit)
    assert error.value.status == 413
    assert trace.get(record.seq).raw_text == record.raw_text


def test_inspection_limit_includes_escaped_json_and_metadata_envelope(saved):
    trace, discovery = saved
    event(trace, text='"' * 50000 + "needle")  # raw<128KiB, response re-escaping exceeds it
    hit, = query(discovery)["hits"]
    with pytest.raises(InvestigationError) as error:
        inspect(discovery, hit)
    assert error.value.status == 413


@pytest.mark.parametrize("coordinate", ["thread", "turn", "item"])
def test_search_bounds_oversized_imported_coordinates_without_truncating(saved, coordinate):
    trace, discovery = saved
    record = event(trace, "$history/item", text="needle", **{coordinate: "x" * 200000})
    with pytest.raises(InvestigationError) as error:
        query(discovery)
    assert error.value.status == 413
    assert "search response exceeds 128 KiB" in str(error.value)
    assert trace.get(record.seq).raw_text == record.raw_text
    api = EidosAPI(trace)
    try:
        status, body = api.dispatch(None, "GET", "/api/evidence/search", {"q": ["needle"]})
        assert status == 413 and "hits" not in body
    finally:
        api.close()


def test_search_bounds_combined_metadata_not_only_each_hit(saved):
    trace, discovery = saved
    for index in range(20):
        event(trace, text="needle", item=str(index) + "x" * 7000)
    assert len(query(discovery, limit=1)["hits"]) == 1
    with pytest.raises(InvestigationError) as error:
        query(discovery)
    assert error.value.status == 413


def test_second_connection_updates_annotations_and_cursors(saved):
    trace, discovery = saved
    first = event(trace, text="first needle")
    event(trace, item="other", text="second needle")
    page = query(discovery, limit=1)
    assert page["nextCursor"]
    second = query(discovery, limit=1, cursor=page["nextCursor"])
    assert second["hits"][0]["id"] != page["hits"][0]["id"]
    other = TraceStore(trace.path)
    try:
        other.annotate_thread("history", kind="semantic-observer")
        assert query(discovery)["hits"] == []
        with pytest.raises(InvestigationError) as missing:
            inspect(discovery, page["hits"][0])
        assert missing.value.status == 404
        with pytest.raises(InvestigationError) as stale:
            query(discovery, limit=1, cursor=page["nextCursor"])
        assert stale.value.status == 409
        other.db.execute("DELETE FROM thread_annotations")
        restored = query(discovery)["hits"][0]
        assert restored == page["hits"][0]
        raw = json.loads(first.raw_text)
        raw["future"] = {"kept": True}
        other.db.execute("UPDATE trace_records SET raw_text=? WHERE seq=?", (json.dumps(raw), first.seq))
        with pytest.raises(InvestigationError) as changed:
            inspect(discovery, restored)
        assert changed.value.status == 409
        refreshed = query(discovery)["hits"][0]
        assert refreshed["version"] != restored["version"]
        assert "kept" in inspect(discovery, refreshed)["records"][0]["rawText"]
        other.db.execute("UPDATE trace_records SET thread_id='moved' WHERE seq=?", (first.seq,))
        assert query(discovery, threadId="history")["hits"][0]["recordSeqs"] != [first.seq]
        assert query(discovery, threadId="moved")["hits"][0]["recordSeqs"] == [first.seq]
        other.db.execute("DELETE FROM trace_records WHERE seq=?", (first.seq,))
        assert query(discovery, threadId="moved")["hits"] == []
    finally:
        other.close()


def test_version_binds_query_page_filter_limit_and_rebuild(saved):
    trace, discovery = saved
    event(trace, text="first needle")
    event(trace, item="second", text="second needle")
    page = query(discovery, limit=1)
    assert query(discovery, " NEEDLE ", limit=1, knownVersion=page["version"])["unchanged"] is True
    assert query(discovery, " " * 200 + "NEEDLE ", limit=1, knownVersion=page["version"])["unchanged"] is True
    for changes in ({"q": "first"}, {"limit": 2}, {"threadId": "history"}, {"cursor": page["nextCursor"]}):
        assert query(discovery, **{"limit": 1, "knownVersion": page["version"], **changes})["unchanged"] is False
    for changes in ({"q": "first"}, {"limit": 2}, {"threadId": "history"}):
        with pytest.raises(InvestigationError) as wrong:
            query(discovery, **{"limit": 1, "cursor": page["nextCursor"], **changes})
        assert wrong.value.status == 400
    before_raw = [r.raw_text for r in trace.records()]
    discovery.rebuild()
    with pytest.raises(InvestigationError) as stale:
        query(discovery, limit=1, cursor=page["nextCursor"])
    assert stale.value.status == 409
    with pytest.raises(InvestigationError) as old_hit:
        inspect(discovery, page["hits"][0])
    assert old_hit.value.status == 409
    assert [r.raw_text for r in trace.records()] == before_raw
    current = query(discovery)["hits"][0]
    trace.db.execute("UPDATE evidence_discovery_meta SET schema_version='older'")
    upgraded = EvidenceDiscovery(trace)
    assert query(upgraded)["hits"][0]["version"] != current["version"]
    assert trace.db.execute("SELECT schema_version FROM evidence_discovery_meta").fetchone()[0] == INDEX_VERSION


@pytest.mark.parametrize("params", [
    {}, {"q": [""]}, {"q": ["   "]}, {"q": ["x" * 201]}, {"q": ["\ud800"]},
    {"q": ["needle", "other"]}, {"q": "needle"}, {"q": ["needle"], "oops": ["1"]},
    *[{"q": ["needle"], "limit": [value]} for value in ("0", "41", "-1", "+1", "1.0", "１", "", "9" * 5000)],
    {"q": ["needle"], "threadId": [""]}, {"q": ["needle"], "knownVersion": [""]},
    {"q": ["needle"], "cursor": ["malformed"]},
])
def test_invalid_query_refuses(saved, params):
    _, discovery = saved
    with pytest.raises(InvestigationError) as failure:
        discovery.search(params)
    assert failure.value.status == 400


def test_inspection_refuses_wrong_query_version_and_missing_hit(saved):
    trace, discovery = saved
    event(trace, text="needle")
    hit, = query(discovery)["hits"]
    for hit_id, params, status in (
        (hit["id"], {"q": ["needle"], "version": ["wrong"]}, 409),
        (hit["id"], {"q": ["elsewhere"], "version": [hit["version"]]}, 409),
        ("missing", {"q": ["needle"], "version": [hit["version"]]}, 404),
        (hit["id"], {"q": ["needle"], "version": [hit["version"]], "extra": ["1"]}, 400),
    ):
        with pytest.raises(InvestigationError) as failure:
            discovery.inspect(hit_id, params)
        assert failure.value.status == status


def test_private_role_refused_before_index_schema_and_again_on_reads():
    # Empty authored store only, not anyone's private data.
    private = TraceStore(role="private-control")
    try:
        with pytest.raises(PrivateTraceAccessError):
            EvidenceDiscovery(private)
        assert private.db.execute("SELECT name FROM sqlite_master WHERE name LIKE 'evidence_discovery%'").fetchall() == []
    finally:
        private.close()
    public = TraceStore()
    try:
        discovery = EvidenceDiscovery(public)
        public.role = "private-control"
        for action in (lambda: query(discovery), discovery.rebuild,
                       lambda: discovery.inspect("hit", {"q": ["q"], "version": ["v"]})):
            with pytest.raises(PrivateTraceAccessError):
                action()
    finally:
        public.close()


def test_hot_search_avoids_source_json_parsing_and_unchanged_field_reads(saved, monkeypatch):
    trace, discovery = saved
    for n in range(1200):
        event(trace, turn=f"turn-{n}", item=f"item-{n}", text=f"Decision {n} needle")
    original = TraceRecord.message.fget
    parsed = 0
    def count(record):
        nonlocal parsed
        parsed += 1
        return original(record)
    monkeypatch.setattr(TraceRecord, "message", property(count))
    started = time.perf_counter()
    page = query(discovery)
    cold_ms = (time.perf_counter() - started) * 1000
    cold_parsed = parsed
    parsed = 0
    read_raw = read_fields = 0
    def audit(action, table, column, database, trigger):
        nonlocal read_raw, read_fields
        if action == sqlite3.SQLITE_READ and table == "trace_records" and column == "raw_text":
            read_raw += 1
        if action == sqlite3.SQLITE_READ and table == "evidence_discovery_fields":
            read_fields += 1
        return sqlite3.SQLITE_OK
    trace.db.set_authorizer(audit)
    try:
        started = time.perf_counter()
        assert query(discovery, knownVersion=page["version"])["unchanged"] is True
        warm_ms = (time.perf_counter() - started) * 1000
        assert parsed == read_raw == read_fields == 0
        assert query(discovery, "Decision 1199")["hits"]
        assert parsed == read_raw == 0
        assert read_fields > 0
    finally:
        trace.db.set_authorizer(None)
    assert cold_parsed == 1200
    print(f"discovery cost: cold={cold_ms:.2f}ms/{cold_parsed} raw parses; warm unchanged={warm_ms:.2f}ms/0 raw parses")


def test_api_routes_projector_and_legacy_payload_shape(saved):
    trace, _ = saved
    record = event(trace, text="needle")
    before = deepcopy(thread_payload(trace, "history"))
    api = EidosAPI(trace)
    try:
        status, page = api.dispatch(None, "GET", "/api/evidence/search", {"q": ["needle"]})
        assert status == 200 and page["scope"] == SCOPE
        hit, = page["hits"]
        status, detail = api.dispatch(None, "GET", f"/api/evidence/hits/{hit['id']}",
                                      {"q": ["needle"], "version": [hit["version"]]})
        assert status == 200 and detail["records"][0]["rawText"] == record.raw_text
        assert thread_payload(trace, "history") == before
        assert api.dispatch(None, "POST", "/api/evidence/search", {})[0] == 404
        assert api.dispatch(None, "GET", "/api/evidence/search", {"q": [" "]})[0] == 400
    finally:
        api.close()
