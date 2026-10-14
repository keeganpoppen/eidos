"""Composed public-history acceptance using only authored temporary records.

No native execution or owner/private evidence is opened. The private-role check
uses a new empty in-memory store, solely to exercise refusal at the read boundary.
"""
from contextlib import closing
import hashlib
import io
import json
from urllib.parse import quote

import pytest

from eidos.api import EidosAPI
from eidos.codex import AppServerClient
from eidos.trace import PrivateTraceAccessError, TraceStore


class Request:
    def __init__(self, body=None):
        raw = json.dumps(body).encode() if body is not None else b""
        self.headers = {"Content-Length": str(len(raw))}
        self.rfile = io.BytesIO(raw)


def call(api, path, *, body=None, **query):
    return api.dispatch(Request(body), "GET" if body is None else "POST", path,
                        {key: [str(value)] for key, value in query.items()})


def search(api, q, **query):
    status, result = call(api, "/api/evidence/search", q=q, **query)
    assert status == 200, result
    assert result["scope"] == "displayed-history-text/v1"
    return result


def inspect(api, hit, q):
    return call(api, "/api/evidence/hits/" + quote(hit["id"], safe=""), q=q, version=hit["version"])


def append(trace, method, params, direction="internal", *, extra=None):
    raw = json.dumps({"method": method, "params": params, **(extra or {})}, ensure_ascii=False, indent=1)
    return trace.append_line(source="synthetic/discovery-acceptance", direction=direction, raw_text=raw)


def message(trace, thread, item, text, *, turn="turn", direction="internal", extra=None):
    return append(trace, "$history/item", {"threadId": thread, "turnId": turn,
        "item": {"id": item, "type": "agentMessage", "text": text, **(extra or {})}}, direction)


def save_exact(api, detail, request_id):
    records = detail["records"]
    status, work = call(api, "/api/investigations", body={"requestId": request_id,
        "title": "Authored evidence discovered", "question": "What do these exact sources establish?",
        "selections": [{"threadId": record["threadId"], "startSeq": record["seq"],
                        "endSeq": record["seq"], "rationale": "Explicit exact source selection"}
                       for record in records]})
    assert status == 201, work
    assert work["attempt"] is work["artifact"] is None
    assert work["contexts"][0]["records"] == records
    return work


@pytest.fixture(autouse=True)
def forbid_native(monkeypatch):
    def fail(*_args, **_kwargs):
        pytest.fail("discovery/selection attempted native startup")
    monkeypatch.setattr(AppServerClient, "start", fail)


def test_split_excerpt_ignores_excluded_id_collisions_and_saves_only_contributors(tmp_path):
    path = tmp_path / "split.db"
    with closing(TraceStore(path)) as trace, closing(EidosAPI(trace)) as api:
        coords = {"threadId": "visible-a", "turnId": "turn", "itemId": "same-item"}
        first = append(trace, "item/agentMessage/delta", {**coords, "delta": "A quartz "},
                       extra={"future": {"preserve": "first unknown field"}})
        unrelated = message(trace, "visible-a", "neighbor", "UNWANTED_NEIGHBOR")
        last = append(trace, "item/agentMessage/delta", {**coords, "delta": "bridge preserves uncertainty."},
                      extra={"future": {"preserve": "second unknown field"}})
        append(trace, "item/completed", {"threadId": "visible-a", "turnId": "turn",
            "item": {"id": "same-item", "type": "agentMessage", "text": "",
                     "unknownField": "UNKNOWN_ONLY_CANARY"}})
        # Excluded records must not replace eligible text even with identical IDs.
        message(trace, "visible-a", "same-item", "PROVIDER_ONLY_CANARY", direction="provider_response")
        append(trace, "account/updated", {**coords, "item": {
            "id": "same-item", "type": "agentMessage", "text": "CONTROL_ONLY_CANARY"}})
        append(trace, "$capsule/result", {"version": 1, "threadId": "visible-a", "turnId": "turn",
            "text": "PUBLICATION_ONLY_CANARY", "provenance": {"kind": "private-capsule", "capsuleId": "authored-no-capsule"}})
        message(trace, "hidden", "same-item", "HIDDEN_ONLY_CANARY")
        trace.annotate_thread("hidden", kind="authored-internal")
        message(trace, "visible-b", "same-item", "A quartz bridge in a different thread.")

        assert len(search(api, "quartz bridge")["hits"]) == 2
        hit, = search(api, "quartz bridge", threadId="visible-a")["hits"]
        assert hit["recordSeqs"] == [first.seq, last.seq]
        assert unrelated.seq not in hit["recordSeqs"]
        for canary in ("PROVIDER_ONLY_CANARY", "CONTROL_ONLY_CANARY", "PUBLICATION_ONLY_CANARY",
                       "HIDDEN_ONLY_CANARY", "UNKNOWN_ONLY_CANARY"):
            assert search(api, canary)["hits"] == []
        status, detail = inspect(api, hit, "quartz bridge")
        assert status == 200, detail
        assert [row["rawText"] for row in detail["records"]] == [first.raw_text, last.raw_text]
        work = save_exact(api, detail, "save-split")
        packet = work["contexts"][0]
        assert "UNWANTED_NEIGHBOR" not in packet["projectedPrompt"]
        assert all(row["sha256"] == hashlib.sha256(row["rawText"].encode()).hexdigest() for row in packet["records"])

        message(trace, "visible-a", "same-item", "A later nonempty final removes the earlier match.")
        assert search(api, "quartz bridge", threadId="visible-a")["hits"] == []
        assert inspect(api, hit, "quartz bridge")[0] == 409
        assert api.investigations.get(work["id"])["contexts"][0] == packet
    with closing(TraceStore(path)) as reopened, closing(EidosAPI(reopened)) as api:
        assert api.investigations.get(work["id"]) == work


def test_other_connection_hiding_update_delete_and_rollback_invalidate_exact_discovery(tmp_path):
    path = tmp_path / "changes.db"
    with closing(TraceStore(path)) as trace, closing(EidosAPI(trace)) as api, closing(TraceStore(path)) as writer:
        originals = [message(writer, name, "item", "Literal STRASSE %_ survives") for name in ("a", "b")]
        page = search(api, "straße %_", limit=1)
        assert len(page["hits"]) == 1 and page["nextCursor"]
        old = page["hits"][0]
        writer.annotate_thread(old["threadId"], kind="now-internal")
        assert call(api, "/api/evidence/search", q="straße %_", limit=1, cursor=page["nextCursor"])[0] == 409
        assert inspect(api, old, "straße %_")[0] == 404
        visible = search(api, "straße %_")
        assert len(visible["hits"]) == 1 and visible["hits"][0]["threadId"] != old["threadId"]

        before = search(api, "rollback needle")
        writer.db.execute("BEGIN IMMEDIATE")
        message(writer, "rollback-thread", "item", "rollback needle")
        writer.db.execute("ROLLBACK")
        assert search(api, "rollback needle", knownVersion=before["version"])["unchanged"] is True

        old_visible = visible["hits"][0]
        source = next(row for row in originals if row.thread_id == old_visible["threadId"])
        changed = json.loads(source.raw_text)
        changed["params"]["item"]["text"] = "A different public phrase"
        writer.db.execute("UPDATE trace_records SET raw_text=? WHERE seq=?", (json.dumps(changed), source.seq))
        assert inspect(api, old_visible, "straße %_")[0] == 409
        replacement_page = search(api, "different public")
        replacement, = replacement_page["hits"]
        assert replacement["recordSeqs"] == [source.seq]
        exact_raw = writer.get(source.seq).raw_text
        api.evidence_discovery.rebuild()
        rebuilt_page = search(api, "different public", knownVersion=replacement_page["version"])
        assert rebuilt_page["unchanged"] is False
        rebuilt, = rebuilt_page["hits"]
        assert rebuilt["id"] == replacement["id"] and rebuilt["version"] != replacement["version"]
        assert inspect(api, replacement, "different public")[0] == 409
        status, rebuilt_detail = inspect(api, rebuilt, "different public")
        assert status == 200 and rebuilt_detail["records"][0]["rawText"] == exact_raw
        assert writer.get(source.seq).raw_text == exact_raw
        writer.db.execute("DELETE FROM trace_records WHERE seq=?", (source.seq,))
        assert inspect(api, rebuilt, "different public")[0] == 404
        assert search(api, "different public")["hits"] == []


def test_actual_rpc_hydration_and_user_message_suppression_preserve_saved_evidence(tmp_path):
    path = tmp_path / "hydration.db"
    with closing(TraceStore(path)) as trace, closing(EidosAPI(trace)) as api, closing(TraceStore(path)) as writer:
        pending = writer.append(source="synthetic/pending-rpc", direction="client_to_appserver", message={
            "id": 27, "method": "turn/start", "params": {"threadId": "pending-thread",
            "input": [{"type": "text", "text": "Remember the ochre fallback"},
                      {"type": "localImage", "path": "ATTACHMENT_ONLY_CANARY"}]}})
        first = search(api, "ochre fallback")
        old, = first["hits"]
        status, detail = inspect(api, old, "ochre fallback")
        assert status == 200, detail
        work = save_exact(api, detail, "save-pending-source")
        writer.append(source="synthetic/pending-rpc", direction="appserver_to_client", message={
            "id": 27, "result": {"turn": {"id": "acknowledged-turn"}}})
        assert writer.get(pending.seq).turn_id == "acknowledged-turn"
        current = search(api, "ochre fallback", knownVersion=first["version"])
        assert current["unchanged"] is False
        hit, = current["hits"]
        assert hit["turnId"] == "acknowledged-turn" and hit["recordSeqs"] == [pending.seq]
        assert inspect(api, old, "ochre fallback")[0] in (404, 409)
        assert search(api, "ATTACHMENT_ONLY_CANARY")["hits"] == []
        append(writer, "item/completed", {"threadId": "pending-thread", "turnId": "acknowledged-turn",
            "item": {"id": "user-item", "type": "userMessage", "content": [{"type": "text", "text": "Explicit later user input"}]}})
        assert search(api, "ochre fallback")["hits"] == []
        assert inspect(api, hit, "ochre fallback")[0] in (404, 409)
        assert api.investigations.get(work["id"]) == work
        assert work["contexts"][0]["records"][0]["rawText"] == pending.raw_text


def test_bounded_list_refuses_oversized_exact_raw_and_private_role_at_reads(tmp_path):
    from eidos.evidence_discovery import EvidenceDiscovery
    with closing(TraceStore(tmp_path / "oversized.db")) as trace, closing(EidosAPI(trace)) as api:
        message(trace, "large", "item", "large visible needle " + "x" * 20000,
                extra={"unknownLargePayload": "z" * (129 * 1024)})
        page = search(api, "visible needle")
        hit, = page["hits"]
        assert len(hit["excerpt"]) <= 240
        assert "rawText" not in json.dumps(page) and len(json.dumps(page).encode()) < 4096
        status, error = inspect(api, hit, "visible needle")
        assert status == 413 and "records" not in error
        assert api.investigations.list() == []
        # Metadata is part of the list envelope too: a short excerpt does not
        # bound an imported Unicode thread identity or its UTF-8 byte count.
        message(trace, "\U0001f9ed" * 40000, "item", "metadata budget needle")
        status, error = call(api, "/api/evidence/search", q="metadata budget needle")
        assert status == 413 and "hits" not in error
        discovery = EvidenceDiscovery(trace)
        trace.role = "private-control"  # Synthetic role switch checks every read, not only construction.
        try:
            with pytest.raises(PrivateTraceAccessError):
                discovery.search({"q": ["visible needle"], "knownVersion": [page["version"]]})
            with pytest.raises(PrivateTraceAccessError):
                discovery.inspect(hit["id"], {"q": ["visible needle"], "version": [hit["version"]]})
        finally:
            trace.role = "workbench"
    with closing(TraceStore(role="private-control")) as empty_private:
        with pytest.raises(PrivateTraceAccessError):
            EvidenceDiscovery(empty_private)
