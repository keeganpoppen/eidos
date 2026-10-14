"""Independent supplied-file acceptance; all inputs and databases are authored.

No native process, model, account, existing private store or filesystem source
lookup participates. Direct SQL/legacy injections below explicitly model damage
by the trusted host, not supported product writes.
"""
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack, closing
from copy import deepcopy
import base64
import hashlib
import io
import json
import sqlite3
import threading
from urllib.parse import quote

import pytest

from eidos.api import EidosAPI
from eidos.codex import AppServerClient
from eidos.trace import PrivateTraceAccessError, TraceStore


ROOT = "/api/evidence/files"
FORMAT = "supplied-text/v1"


def encoded(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()


def digest(value):
    return hashlib.sha256(value).hexdigest()


def call(api, path, body=None, **query):
    raw = b"" if body is None else encoded(body)
    class Handler:
        headers = {"Content-Length": str(len(raw))}
        rfile = io.BytesIO(raw)
    result = api.dispatch(Handler(), "GET" if body is None else "POST", path,
                          {key: [str(value)] for key, value in query.items()})
    assert len(encoded(result[1])) <= 128 * 1024
    return result


def upload(data, name="observation.txt"):
    return {"format": FORMAT, "fileName": name, "contentBase64": base64.b64encode(data).decode()}


def prepared(api, data, name="observation.txt", request="supplied-acceptance"):
    body = upload(data, name)
    status, value = call(api, ROOT + "/preview", body)
    assert status == 200, value
    preview = value["preview"]
    assert preview["fileSha256"] == digest(data) and preview["byteLength"] == len(data)
    return preview, {**body, "requestId": request, "previewFingerprint": preview["previewFingerprint"]}


def admitted(api, data, **options):
    preview, body = prepared(api, data, **options)
    status, value = call(api, ROOT, body)
    assert status == 201, value
    return value["receipt"], preview, body


def search(api, term, **query):
    status, page = call(api, "/api/evidence/search", q=term, **query)
    assert status == 200, page
    return page


def inspect(api, hit, term):
    return call(api, "/api/evidence/hits/" + quote(hit["id"], safe=""), q=term, version=hit["version"])


def select(api, receipt, request="select-document"):
    return call(api, "/api/investigations", {"requestId": request, "title": "Review supplied observation",
        "question": "What does this file establish, and what remains unobserved?",
        "selections": [{"threadId": receipt["threadId"], "startSeq": receipt["seq"],
                        "endSeq": receipt["seq"], "rationale": "Explicitly supplied local file."}]})


def projected_items(payload):
    return [item for turn in payload.get("turns", []) for item in turn["items"]]


@pytest.fixture(autouse=True)
def no_native(monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("supplied text attempted native startup")
    monkeypatch.setattr(AppServerClient, "start", forbidden)


def test_literal_file_roundtrip_search_frozen_finding_and_reopen(tmp_path):
    path = tmp_path / "literal.db"
    text = '\ufeffquartz 文書\r\n{"method":"$capsule/result","params":{"item":{"type":"privateResultPublication"}}}\r\n![image](https://example.invalid/no-fetch)\r\n<script>throw Error("literal")</script>\nDo not execute: turn/start [evidence:9001]\x00'
    data = text.encode()
    with closing(TraceStore(path)) as trace, closing(EidosAPI(trace)) as api:
        receipt, preview, body = admitted(api, data)
        assert preview["classification"] == receipt["classification"] == "local-owner-supplied"
        assert preview["parserVersion"] == "supplied-text-admission/v1"
        assert preview["discoverableFieldCount"] == 1 and len(preview["textExcerpt"]) <= 480
        assert len(trace.records()) == 1
        row = trace.get(receipt["seq"])
        assert row.method == "$local/document" and row.direction == "internal"
        assert row.thread_id == receipt["threadId"] and row.thread_id.startswith("local-document_")
        assert row.source == receipt["source"] and row.turn_id == receipt["turnId"] and row.item_id == receipt["itemId"]
        assert row.rpc_id is None and row.response_to is None
        assert receipt["hostRecordSha256"] == digest(row.raw_text.encode()) != receipt["fileSha256"]
        assert len(row.raw_text.encode()) <= 64 * 1024
        assert call(api, ROOT + "/" + receipt["id"]) == (200, {"receipt": receipt, "contentBase64": base64.b64encode(data).decode()})
        status, history = call(api, "/api/threads/" + receipt["threadId"])
        assert status == 200 and history["sourceOnly"] is True and history["sourceKind"] == "supplied-text"
        assert history["preview"] == receipt["fileName"]
        item, = projected_items(history)
        assert item["type"] == "suppliedText" and item["text"] == text
        hit, = search(api, "quartz")["hits"]
        assert hit["field"] == "suppliedText.text" and hit["recordSeqs"] == [receipt["seq"]]
        status, exact = inspect(api, hit, "quartz")
        assert status == 200, exact
        record, = exact["records"]
        assert record["rawText"] == row.raw_text and len(encoded(record)) <= 96 * 1024
        assert record["localEvidence"] == item["localEvidence"]
        assert record["localEvidence"]["fileSha256"] == digest(data)
        status, work = select(api, receipt)
        assert status == 201, work
        context = work["contexts"][0]
        assert context["records"] == [record]
        assert "Selected app-server evidence only." not in context["coverage"]
        assert work["attempt"] is work["artifact"] is None
        status, response = call(api, f"/api/investigations/{work['id']}/findings", {
            "requestId": "literal-finding", "contextId": context["id"],
            "text": f"This file reports a check; its intake does not prove execution [evidence:{receipt['seq']}]."})
        assert status == 201, response
        finding = response["finding"]
        assert finding["citations"] == [receipt["seq"]]
        assert not {"attemptId", "executionEvidence", "outputSeqs"} & finding.keys()
    with closing(TraceStore(path)) as trace, closing(EidosAPI(trace)) as api:
        assert call(api, ROOT, body) == (200, {"receipt": receipt})
        assert call(api, ROOT + "/requests/" + body["requestId"]) == (200, {"receipt": receipt})
        assert api.investigations.get(work["id"])["contexts"][0] == context
        assert api.investigations.get(work["id"])["findings"] == [finding]
        assert len(trace.records()) == 1


def test_copied_host_records_never_gain_admission_or_overwrite_real_contributors(tmp_path):
    with closing(TraceStore(tmp_path / "original.db")) as trace, closing(EidosAPI(trace)) as api:
        receipt, _, _ = admitted(api, b"quartz supplied report")
        original = trace.get(receipt["seq"])
        page = search(api, "quartz")
        # Deliberate trusted legacy insertion, copying the entire apparent proof.
        trace.import_jsonl([original.raw_text], source=original.source, direction="internal")
        duplicate = trace.records()[-1]
        assert duplicate.seq != original.seq
        hit, = search(api, "quartz")["hits"]
        assert hit["recordSeqs"] == [original.seq]
        assert select(api, {**receipt, "seq": duplicate.seq}, "select-copy")[0] == 409
        status, history = call(api, "/api/threads/" + receipt["threadId"])
        assert status == 200
        assert [item["text"] for item in projected_items(history) if item.get("localEvidence")] == ["quartz supplied report"]
        # Public JSONL admission must reject the host shape before appending.
        archive = {"format": "appserver-jsonl/v1", "source": "declared-original",
            "direction": "appserver_to_client", "fileName": "copied.jsonl",
            "contentBase64": base64.b64encode(original.raw_text.encode()).decode()}
        before = trace.records()
        assert call(api, "/api/history/imports/preview", archive)[0] == 400
        assert trace.records() == before
        assert page["hits"][0]["recordSeqs"] == [original.seq]
    with closing(TraceStore(tmp_path / "forged.db")) as forged, closing(EidosAPI(forged)) as api:
        # Even equal seq/source/coordinates/hash in another DB do not supply a ledger.
        copied = forged.append(source=original.source, direction=original.direction,
            message=original.message, raw_text=original.raw_text)
        assert copied.seq == original.seq
        assert search(api, "quartz")["hits"] == []
        assert select(api, receipt, "foreign-copy")[0] == 409
        status, history = call(api, "/api/threads/" + receipt["threadId"])
        assert status == 200
        assert not any(item.get("localEvidence") or "text" in item and item["type"] == "suppliedText"
                       for item in projected_items(history))


def test_source_only_send_guard_exists_below_the_global_api_gate(tmp_path, monkeypatch):
    with closing(TraceStore(tmp_path / "send.db")) as trace, closing(EidosAPI(trace)) as api:
        receipt, _, _ = admitted(api, b"Source files are descriptions, not native threads.")
        calls = []
        def forbidden_thread(identifier):
            calls.append(identifier)
            pytest.fail("source-only group reached native thread loading")
        monkeypatch.setattr(api.live, "_ensure_thread", forbidden_thread)
        # Exercise the actual lower adapter, independently of the API's closed gate.
        for identifier in (receipt["threadId"], "local-document_missing-ledger"):
            with pytest.raises(ValueError):
                api.live.send(identifier, "Do not dispatch this.")
        assert calls == []
        assert call(api, "/api/threads/" + receipt["threadId"] + "/messages", {"text": "Do not dispatch."})[0] == 409


@pytest.mark.parametrize("data", [b"x" * (64 * 1024 + 1), b"\x00" * 12_000,
                                 b"\\" * 26_000, b"bad\xffutf8"])
def test_bad_or_escaped_oversize_preview_leaves_no_durable_record(tmp_path, data):
    with closing(TraceStore(tmp_path / "bounds.db")) as trace, closing(EidosAPI(trace)) as api:
        status, response = call(api, ROOT + "/preview", upload(data))
        assert status in {400, 413}, response
        assert trace.records() == []
        assert call(api, ROOT + "/requests/never-created")[0] == 404


def test_six_connections_commit_one_receipt_and_exact_replay_after_raw_loss(tmp_path, monkeypatch):
    path = tmp_path / "concurrent.db"
    data = "\ufeffquartz report\r\nsecond line".encode()
    with ExitStack() as stack:
        traces = [stack.enter_context(closing(TraceStore(path))) for _ in range(6)]
        apis = [stack.enter_context(closing(EidosAPI(trace))) for trace in traces]
        _, body = prepared(apis[0], data)
        barrier = threading.Barrier(6)
        def submit(index):
            barrier.wait(timeout=10)
            return call(apis[index], ROOT, body)
        with ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(submit, range(6)))
        assert sorted(status for status, _ in results) == [200] * 5 + [201]
        receipt = results[0][1]["receipt"]
        assert all(value == {"receipt": receipt} for _, value in results)
        assert len(traces[0].records()) == 1
        traces[0].db.execute("DELETE FROM trace_records")
    with closing(TraceStore(path)) as trace, closing(EidosAPI(trace)) as api:
        import eidos.supplied_text as supplied_module
        with monkeypatch.context() as future:
            future.setattr(supplied_module, "PARSER_VERSION", "supplied-text-admission/future")
            def forbidden_parse(*_args):
                pytest.fail("an exact prior receipt must not reparse source bytes")
            future.setattr(supplied_module.SuppliedText, "_prepare", staticmethod(forbidden_parse))
            assert call(api, ROOT, body) == (200, {"receipt": receipt})
            assert call(api, ROOT + "/requests/" + body["requestId"]) == (200, {"receipt": receipt})
            assert call(api, ROOT, {**body, "previewFingerprint": "0" * 64})[0] == 409
        assert trace.records() == []
        assert call(api, ROOT, {**body, "fileName": "changed-label.txt"})[0] == 409
        assert call(api, ROOT, {**body, "contentBase64": base64.b64encode(data + b"\n").decode()})[0] == 409
        # New operation identity intentionally means a distinct admission.
        assert call(api, ROOT, {**body, "requestId": "intentional-second"})[0] == 201
        assert len(trace.records()) == 1


@pytest.mark.parametrize("position", ["before", "after"])
@pytest.mark.parametrize("shape", ["typeless-completion", "typed-completion", "delta"])
def test_native_shaped_coordinate_collision_cannot_replace_or_extend_document(tmp_path, position, shape):
    with closing(TraceStore(tmp_path / "collision.db")) as trace, closing(EidosAPI(trace)) as api:
        placeholder = trace.append(source="authored-position-reservation", direction="internal", message={})
        receipt, _, _ = admitted(api, b"quartz original document")
        original = trace.get(receipt["seq"])
        warm = search(api, "quartz")
        params = {"threadId": receipt["threadId"], "turnId": receipt["turnId"]}
        method = "item/completed"
        if shape == "delta":
            method = "item/agentMessage/delta"
            params.update(itemId=receipt["itemId"], delta="foreignneedle")
        else:
            params["item"] = {"id": receipt["itemId"], "text": "foreignneedle"}
            if shape == "typed-completion":
                params["item"]["type"] = "agentMessage"
        foreign = trace.append(source="authored-foreign-native", direction="appserver_to_client",
                               message={"method": method, "params": params})
        if position == "before":
            # Trusted-store schedule injection, preserving the genuine ledger's
            # exact positive seq while placing an ordinary event before it.
            trace.db.execute("DELETE FROM trace_records WHERE seq=?", (placeholder.seq,))
            trace.db.execute("UPDATE trace_records SET seq=? WHERE seq=?", (placeholder.seq, foreign.seq))
        page = search(api, "quartz", knownVersion=warm["version"])
        hit, = page["hits"]
        assert hit["field"] == "suppliedText.text" and hit["recordSeqs"] == [original.seq]
        assert search(api, "foreignneedle")["hits"] == []
        status, exact = inspect(api, hit, "quartz")
        assert status == 200, exact
        assert [record["seq"] for record in exact["records"]] == [original.seq]
        status, history = call(api, "/api/threads/" + receipt["threadId"])
        assert status == 200 and history["sourceOnly"] is True
        item, = projected_items(history)
        assert item["type"] == "suppliedText" and item["text"] == "quartz original document"
        assert item["recordSeqs"] == [original.seq]
        assert trace.get(original.seq).raw_text == original.raw_text


def test_unknown_native_type_remains_raw_while_reserved_names_in_strings_are_inert(tmp_path):
    from eidos.history_imports import HistoryImports
    with closing(TraceStore(tmp_path / "unknown.db")) as trace:
        importer = HistoryImports(trace)
        for ordinal, kind in enumerate(({"unknown": "preserve"}, ["suppliedText"], None)):
            raw = encoded({"method": "item/completed", "params": {
                "threadId": f"ordinary-{ordinal}", "turnId": "turn", "item": {
                    "id": "item", "type": kind,
                    "text": "$local/document suppliedText are literal ordinary text"}}})
            preview = importer.preview(raw, source="authored")
            receipt, created = importer.commit(raw, request_id=f"unknown-{ordinal}",
                preview_fingerprint=preview["previewFingerprint"], source="authored",
                require_discoverable=False)
            assert created
            row = trace.records()[-1]
            assert row.raw_text.encode() == raw
            assert row.message["params"]["item"]["type"] == kind
            assert receipt["recordCount"] == 1


def test_private_role_cannot_create_or_use_the_supplied_file_adapter():
    from eidos.supplied_text import SuppliedText, ensure_schema
    with closing(TraceStore(role="private-control")) as trace:
        before = trace.db.execute("SELECT name FROM sqlite_master ORDER BY name").fetchall()
        with pytest.raises(PrivateTraceAccessError):
            SuppliedText(trace)
        with pytest.raises(PrivateTraceAccessError):
            ensure_schema(trace)
        assert trace.db.execute("SELECT name FROM sqlite_master ORDER BY name").fetchall() == before
        assert trace.records() == []


@pytest.mark.parametrize("data", [b"", b" \t\r\n"])
def test_empty_or_whitespace_file_is_still_exact_selectable_evidence(tmp_path, data):
    with closing(TraceStore(tmp_path / "empty.db")) as trace, closing(EidosAPI(trace)) as api:
        receipt, preview, _ = admitted(api, data)
        assert preview["discoverableFieldCount"] == 0
        assert search(api, "anything")["hits"] == []
        status, history = call(api, "/api/threads/" + receipt["threadId"])
        assert status == 200 and history["sourceOnly"] is True
        item, = projected_items(history)
        assert item["text"].encode() == data and item["recordSeqs"] == [receipt["seq"]]
        status, owner = select(api, receipt)
        assert status == 201, owner
        record, = owner["contexts"][0]["records"]
        assert record["localEvidence"]["byteLength"] == len(data)
        assert record["localEvidence"]["fileSha256"] == digest(data)


def test_basename_whitespace_rule_matches_receipt_rendering_without_normalizing_name(tmp_path):
    with closing(TraceStore(tmp_path / "name.db")) as trace, closing(EidosAPI(trace)) as api:
        for name in ("\ufeff", " \ufeff ", "\u0085"):
            assert call(api, ROOT + "/preview", upload(b"quartz", name))[0] == 400
        assert trace.records() == []
        receipt, _, _ = admitted(api, b"quartz", name="\ufeffobservation.txt")
        assert receipt["fileName"] == "\ufeffobservation.txt"
        status, owner = select(api, receipt)
        assert status == 201
        assert owner["contexts"][0]["records"][0]["localEvidence"]["fileName"] == receipt["fileName"]


@pytest.mark.parametrize("damage", ["delete-ledger", "replace-original-bytes", "change-envelope-hash"])
def test_independent_ledger_damage_invalidates_warm_search_history_and_new_selection(tmp_path, damage):
    path = tmp_path / "ledger.db"
    with closing(TraceStore(path)) as trace, closing(EidosAPI(trace)) as api, closing(TraceStore(path)) as writer:
        receipt, _, _ = admitted(api, b"quartz exact source")
        page = search(api, "quartz")
        hit, = page["hits"]
        status, history = call(api, "/api/threads/" + receipt["threadId"])
        assert status == 200 and history["sourceOnly"] is True
        assert search(api, "quartz", knownVersion=page["version"])["unchanged"] is True
        # Deliberate trusted-store damage; raw trace bytes remain unchanged.
        if damage == "delete-ledger":
            writer.db.execute("DELETE FROM supplied_text_files WHERE id=?", (receipt["id"],))
        elif damage == "replace-original-bytes":
            writer.db.execute("UPDATE supplied_text_files SET original_bytes=? WHERE id=?", (b"different report", receipt["id"]))
        else:
            writer.db.execute("UPDATE supplied_text_files SET host_record_sha256=? WHERE id=?", ("0" * 64, receipt["id"]))
        assert trace.get(receipt["seq"]).raw_text
        after = search(api, "quartz", knownVersion=page["version"])
        assert after["unchanged"] is False and after["hits"] == []
        assert inspect(api, hit, "quartz")[0] in {404, 409}
        assert select(api, receipt, "damaged-new-selection")[0] == 409
        status, changed = call(api, "/api/threads/" + receipt["threadId"], knownVersion=history["version"])
        assert status == 200 and changed.get("unchanged") is not True
        assert changed.get("sourceKind") != "supplied-text"
        assert not any(item.get("localEvidence") for item in projected_items(changed))
        api.evidence_discovery.rebuild()
        assert search(api, "quartz")["hits"] == []


def test_frozen_document_survives_ledger_and_raw_loss_in_copied_inputs_and_findings(tmp_path):
    path = tmp_path / "frozen.db"
    with closing(TraceStore(path)) as trace, closing(EidosAPI(trace)) as api:
        receipt, _, _ = admitted(api, b"quartz observation: a local intake receipt is not a command receipt.\r\n")
        status, original = select(api, receipt)
        assert status == 201, original
        context = deepcopy(original["contexts"][0])
        finding, _ = api.investigations.create_finding(original["id"], {
            "requestId": "original-finding", "contextId": context["id"],
            "text": f"Preserve intake versus execution [evidence:{receipt['seq']}]."})
        # Source unavailability is deliberate and confined to this authored DB.
        trace.db.execute("DELETE FROM supplied_text_files")
        trace.db.execute("DELETE FROM trace_records")
        copied = api.investigations.create({"requestId": "copy-frozen-document", "title": "Continue the review",
            "question": "What remains unknown?", "inputSource": {
                "investigationId": original["id"], "contextId": context["id"]}})
        assert copied["contexts"][0]["records"] == context["records"]
        assert "Selected app-server evidence only." not in copied["contexts"][0]["coverage"]
        assert copied["attempt"] is copied["artifact"] is None
        downstream = api.investigations.create({"requestId": "use-finding", "title": "Review derived conclusion",
            "question": "Does the recorded distinction support this review?", "artifactInputs": [{
                "investigationId": original["id"], "artifactId": finding["id"], "rationale": "Exact reviewed finding."}]})
        assert downstream["contexts"][0]["artifactInputs"][0]["artifact"] == finding
        status, source = call(api, f"/api/investigations/{original['id']}/artifacts/{finding['id']}/source", contextId=context["id"])
        assert status == 200, source
        assert source["context"] == context and source["attempt"] is None
        assert trace.records() == [] and search(api, "quartz")["hits"] == []
    with closing(TraceStore(path)) as trace, closing(EidosAPI(trace)) as api:
        assert api.investigations.get(original["id"])["contexts"][0] == context
        assert api.investigations.get(copied["id"]) == copied
        assert api.investigations.get(downstream["id"]) == downstream
        assert trace.records() == []


def test_failure_after_record_append_rolls_back_record_blob_and_receipt(tmp_path):
    with closing(TraceStore(tmp_path / "rollback.db")) as trace, closing(EidosAPI(trace)) as api:
        _, body = prepared(api, b"quartz all-or-nothing")
        trace.db.execute("CREATE TRIGGER acceptance_refuse_supplied_receipt BEFORE INSERT ON supplied_text_files "
                         "BEGIN SELECT RAISE(ABORT,'authored late admission failure'); END")
        # The real last-write failure is injected at SQLite, not a mocked parser.
        try:
            status, response = call(api, ROOT, body)
            assert status >= 400, response
        except sqlite3.DatabaseError:
            pass
        assert trace.records() == []
        assert trace.db.execute("SELECT count(*) FROM supplied_text_files").fetchone()[0] == 0
        assert call(api, ROOT + "/requests/" + body["requestId"])[0] == 404
        trace.db.execute("DROP TRIGGER acceptance_refuse_supplied_receipt")
        assert call(api, ROOT, body)[0] == 201
        assert len(trace.records()) == 1
