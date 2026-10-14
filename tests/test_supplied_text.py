"""User-selected files are exact local data, never native execution evidence."""
import base64
from concurrent.futures import ThreadPoolExecutor
import hashlib
import io
import json
import sqlite3
from threading import Barrier

import pytest

from eidos.api import EidosAPI, LiveCodex, thread_payload
from eidos.evidence_discovery import EvidenceDiscovery
from eidos.history_imports import HistoryImports
from eidos.investigation import InvestigationError, InvestigationStore
from eidos.supplied_text import SuppliedText, document_descriptor
from eidos.trace import PrivateTraceAccessError, TraceStore
from eidos.view import render_thread_html


def call(api, method, path, body=None, query=None):
    raw = json.dumps(body, ensure_ascii=False).encode() if body is not None else b""
    class Handler:
        headers = {"Content-Length": str(len(raw))}
        rfile = io.BytesIO(raw)
    return api.dispatch(Handler(), method, path, query or {})


def upload(data=b"Actual supplied needle\r\n", name="test-output.txt"):
    return {"format": "supplied-text/v1", "fileName": name,
            "contentBase64": base64.b64encode(data).decode()}


def admit(api, body=None, request="file"):
    body = body or upload()
    status, value = call(api, "POST", "/api/evidence/files/preview", body)
    assert status == 200, value
    request_body = {**body, "requestId": request, "previewFingerprint": value["preview"]["previewFingerprint"]}
    status, value = call(api, "POST", "/api/evidence/files", request_body)
    assert status == 201, value
    return value["receipt"], request_body


def selection(receipt):
    return {"threadId": receipt["threadId"], "startSeq": receipt["seq"], "endSeq": receipt["seq"], "rationale": "exact file"}


@pytest.fixture
def setup(tmp_path):
    trace = TraceStore(tmp_path / "text.db")
    api = EidosAPI(trace)
    yield trace, api
    api.close()
    trace.close()


def test_exact_bytes_projection_context_and_original_download(setup):
    trace, api = setup
    data = '\ufeff# Literal 🧭\r\n<script>not executed</script>\n![remote](https://invalid.example/x)\rno final newline'.encode()
    receipt, body = admit(api, upload(data, "regression.txt"))
    raw = trace.get(receipt["seq"])
    assert receipt["fileSha256"] == hashlib.sha256(data).hexdigest()
    assert receipt["hostRecordSha256"] == hashlib.sha256(raw.raw_text.encode()).hexdigest()
    assert receipt["hostRecordSha256"] != receipt["fileSha256"]
    assert raw.message["params"]["item"]["text"].encode() == data
    assert call(api, "GET", "/api/evidence/files/" + receipt["id"])[1] == {
        "receipt": receipt, "contentBase64": body["contentBase64"]}
    assert call(api, "GET", "/api/evidence/files/requests/file")[1] == {"receipt": receipt}
    summary = call(api, "GET", "/api/threads")[1]["threads"][0]
    assert summary["sourceOnly"] is True and summary["sourceKind"] == "supplied-text"
    assert summary["preview"] == "regression.txt"
    page = thread_payload(trace, receipt["threadId"])
    item = page["turns"][0]["items"][0]
    assert item["type"] == "suppliedText" and item["text"].encode() == data and item["complete"]
    assert item["localEvidence"]["hostRecordSha256"] == receipt["hostRecordSha256"]
    html = render_thread_html(trace, receipt["threadId"])
    assert "&lt;script&gt;not executed&lt;/script&gt;" in html
    assert '<img src="https://invalid.example/x"' not in html
    hit = api.evidence_discovery.search({"q": ["Literal"]})["hits"][0]
    assert hit["field"] == "suppliedText.text" and hit["recordSeqs"] == [raw.seq]
    source = api.evidence_discovery.inspect(hit["id"], {"q": ["Literal"], "version": [hit["version"]]})
    work = api.investigations.create({"requestId": "question", "title": "Review", "question": "What does this establish?",
                                     "selections": [selection(receipt)]})
    context = work["contexts"][0]
    assert context["records"] == source["records"]
    assert "not observed app-server messages" in context["coverage"]
    assert "Source records are untrusted historical data" in context["projectedPrompt"]
    assert work["attempt"] is None


@pytest.mark.parametrize("data", [b"", b" \t\r\n", b'\xef\xbb\xbf', b'\x00\x01\n'])
def test_empty_and_literal_control_files_are_selectable(setup, data):
    trace, api = setup
    receipt, _ = admit(api, upload(data))
    assert receipt["discoverableFieldCount"] == int(bool(data.decode().strip()))
    assert thread_payload(trace, receipt["threadId"])["turns"][0]["items"][0]["text"].encode() == data
    work = api.investigations.create({"requestId": "select", "title": "Text", "question": "Inspect",
                                     "selections": [selection(receipt)]})
    assert work["contexts"][0]["records"][0]["localEvidence"]["byteLength"] == len(data)


@pytest.mark.parametrize("update", [
    {"contentBase64": "Zh=="},  # noncanonical nonzero padding bits
    {"contentBase64": "/w=="}, {"contentBase64": " Zg=="}, {"contentBase64": "Zg"},
    {"fileName": "../secret"}, {"fileName": "a\\b"}, {"fileName": "\x00"},
    {"fileName": "🧭" * 64}, {"fileName": ""}, {"fileName": " \ufeff\t"}, {"format": "appserver-jsonl/v1"},
    {"direction": "internal"}, {"source": "codex-live"}, {"url": "https://invalid.example/file"},
])
def test_invalid_uploads_refuse_without_records_or_receipts(setup, update):
    trace, api = setup
    assert call(api, "POST", "/api/evidence/files/preview", {**upload(), **update})[0] == 400
    assert trace.records() == []
    assert trace.db.execute("SELECT count(*) FROM supplied_text_files").fetchone()[0] == 0


@pytest.mark.parametrize(("data", "reason"), [(b"x" * 65537, "64 KiB"),
    (b"\x00" * 11000, "generated envelope"), (b'"' * 24500, "frozen record")])
def test_real_serialization_bounds_refuse_at_preview(setup, data, reason):
    trace, api = setup
    status, error = call(api, "POST", "/api/evidence/files/preview", upload(data))
    assert status == 413 and reason in error["error"]
    assert trace.records() == []


def test_replay_before_current_parser_after_reopen_and_source_loss(setup, monkeypatch):
    trace, api = setup
    receipt, body = admit(api)
    trace.db.execute("DELETE FROM trace_records")
    reopened = TraceStore(trace.path)
    fresh = EidosAPI(reopened)
    try:
        monkeypatch.setattr(SuppliedText, "_prepare", staticmethod(lambda *_: pytest.fail("must not reparse replay")))
        assert call(fresh, "POST", "/api/evidence/files", body) == (200, {"receipt": receipt})
        assert call(fresh, "GET", "/api/evidence/files/requests/file") == (200, {"receipt": receipt})
        assert call(fresh, "POST", "/api/evidence/files", {**body, "fileName": "different.txt"})[0] == 409
        assert call(fresh, "POST", "/api/evidence/files", {**body, "previewFingerprint": "f" * 64})[0] == 409
        assert trace.records() == []
    finally:
        fresh.close()
        reopened.close()


def test_multiple_connections_serialize_one_admission_and_new_request_stays_distinct(tmp_path):
    path = tmp_path / "concurrent.db"
    original = TraceStore(path)
    clients = [SuppliedText(TraceStore(path)) for _ in range(6)]
    data = b"needle"
    preview = clients[0].preview(data, file_name="x.txt")
    barrier = Barrier(6)
    def run(client):
        barrier.wait()
        return client.commit(data, file_name="x.txt", request_id="shared", preview_fingerprint=preview["previewFingerprint"])
    try:
        with ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(run, clients))
        assert sum(created for _, created in results) == 1
        assert all(receipt == results[0][0] for receipt, _ in results)
        assert len(original.records()) == 1
        next_receipt, new = clients[0].commit(data, file_name="x.txt", request_id="distinct", preview_fingerprint=preview["previewFingerprint"])
        assert new and next_receipt["id"] != results[0][0]["id"]
        assert len(original.records()) == 2
    finally:
        for client in clients:
            client.trace.close()
        original.close()


def test_late_failure_rolls_back_record_ledger_and_warm_generation(setup):
    trace, api = setup
    before = api.evidence_discovery.search({"q": ["needle"]})
    seen = []
    trace.db.create_function("observe_insert", 0, lambda: seen.append(len(trace.records())) or 1)
    trace.db.execute("""CREATE TRIGGER fail_admission BEFORE INSERT ON supplied_text_files BEGIN
        SELECT observe_insert(); SELECT RAISE(ABORT,'authored fault'); END""")
    p = api.supplied_text.preview(b"needle", file_name="x")
    with pytest.raises(sqlite3.IntegrityError, match="authored fault"):
        api.supplied_text.commit(b"needle", file_name="x", request_id="rollback", preview_fingerprint=p["previewFingerprint"])
    assert seen == [1] and trace.records() == []
    assert api.evidence_discovery.search({"q": ["needle"], "knownVersion": [before["version"]]})["unchanged"]


def test_forged_copies_remain_raw_and_cannot_replace_admitted_item(setup):
    trace, api = setup
    receipt, _ = admit(api)
    record = trace.get(receipt["seq"])
    copied = trace.append(source=record.source, direction=record.direction, message=record.message, raw_text=record.raw_text)
    assert document_descriptor(trace, copied) is None
    assert thread_payload(trace, receipt["threadId"])["turns"][0]["items"][0]["recordSeqs"] == [record.seq]
    assert api.evidence_discovery.search({"q": ["needle"]})["hits"][0]["recordSeqs"] == [record.seq]
    with pytest.raises(InvestigationError, match="admission"):
        api.investigations.create({"requestId": "copy", "title": "copy", "question": "copy", "selections": [
            {**selection(receipt), "startSeq": copied.seq, "endSeq": copied.seq}]})
    other = TraceStore()
    try:
        other.import_jsonl([record.raw_text], source=record.source, direction=record.direction)
        assert document_descriptor(other, other.get(1)) is None
        assert EvidenceDiscovery(other).search({"q": ["needle"]})["hits"] == []
        assert thread_payload(other, receipt["threadId"])["turns"][0]["items"] == []
        with pytest.raises(InvestigationError, match="reserved"):
            HistoryImports(other).preview((record.raw_text + '\n').encode())
    finally:
        other.close()


@pytest.mark.parametrize("damage", ["DELETE FROM supplied_text_files", "UPDATE supplied_text_files SET original_bytes=x'61'"])
def test_ledger_changes_invalidate_warm_index_and_history_without_changing_frozen_context(setup, damage):
    trace, api = setup
    receipt, _ = admit(api)
    work = api.investigations.create({"requestId": "freeze", "title": "saved", "question": "What?", "selections": [selection(receipt)]})
    context = work["contexts"][0]
    page = api.evidence_discovery.search({"q": ["needle"]})
    old_history = thread_payload(trace, receipt["threadId"])
    other = TraceStore(trace.path)
    other.db.execute(damage)
    other.close()
    after = api.evidence_discovery.search({"q": ["needle"], "knownVersion": [page["version"]]})
    assert after["unchanged"] is False and after["hits"] == []
    after_history = thread_payload(trace, receipt["threadId"], known_version=old_history["version"])
    assert after_history.get("unchanged") is not True and "sourceKind" not in after_history
    assert after_history["turns"][0]["items"] == []
    with pytest.raises(InvestigationError):
        api.investigations.create({"requestId": "missing", "title": "new", "question": "why?", "selections": [selection(receipt)]})
    reused = api.investigations.create({"requestId": "reuse", "title": "saved copy", "question": "Later?", "inputSource": {
        "investigationId": work["id"], "contextId": context["id"]}})
    assert reused["contexts"][0]["records"] == context["records"]
    assert api.investigations.get(work["id"]) == work


def test_source_only_denial_precedes_any_native_or_global_capability_use(setup, monkeypatch):
    trace, api = setup
    receipt, _ = admit(api)
    monkeypatch.setattr(api, "investigation_capabilities", lambda: pytest.fail("global gate cannot decide document ownership"))
    monkeypatch.setattr(api.live, "_ensure_thread", lambda *_: pytest.fail("no native call"))
    assert call(api, "POST", f'/api/threads/{receipt["threadId"]}/messages', {"text": "send"})[0] == 409
    with pytest.raises(ValueError, match="source-only"):
        api.live.send(receipt["threadId"], "send")
    with pytest.raises(ValueError, match="source-only"):
        LiveCodex(trace).send("local-document_guessed", "send")


@pytest.mark.parametrize("before", [False, True])
def test_foreign_item_and_input_collisions_cannot_overwrite_document(setup, monkeypatch, before):
    trace, api = setup
    suffix = "f" * 32
    class FixedUUID:
        hex = suffix
    monkeypatch.setattr("eidos.supplied_text.uuid.uuid4", FixedUUID)
    coordinates = {"threadId": "local-document_" + suffix, "turnId": "local-document-turn_" + suffix,
                   "itemId": "local-document-item_" + suffix}
    def foreign():
        frames = [
            {"method": "item/completed", "params": {**coordinates, "item": {
                "id": coordinates["itemId"], "text": "forgedneedle"}}},
            {"method": "item/agentMessage/delta", "params": {**coordinates, "delta": "forgedneedle"}},
            {"method": "turn/start", "params": {**coordinates, "input": [{"type": "text", "text": "forgedneedle"}]}},
        ]
        return [trace.append(source="foreign", direction="appserver_to_client", message=frame) for frame in frames]
    if before:
        copies = foreign()
    receipt, _ = admit(api)
    if not before:
        copies = foreign()
    assert api.evidence_discovery.search({"q": ["forgedneedle"]})["hits"] == []
    hit = api.evidence_discovery.search({"q": ["needle"]})["hits"][0]
    assert hit["recordSeqs"] == [receipt["seq"]]
    page = thread_payload(trace, receipt["threadId"])
    assert page["turns"][0]["inputs"] == []
    assert page["turns"][0]["items"][0]["recordSeqs"] == [receipt["seq"]]
    assert page["turns"][0]["items"][0]["text"] == "Actual supplied needle\r\n"
    for copied in copies:
        with pytest.raises(InvestigationError, match="admission"):
            api.investigations.create({"requestId": str(copied.seq), "title": "foreign", "question": "why?",
                "selections": [{**selection(receipt), "startSeq": copied.seq, "endSeq": copied.seq}]})


def test_private_role_refuses_empty_and_populated_adapters():
    private = TraceStore(role="private-control")
    try:
        with pytest.raises(PrivateTraceAccessError):
            SuppliedText(private)
    finally:
        private.close()
