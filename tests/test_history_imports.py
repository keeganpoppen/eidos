"""Authored explicit-file imports only; no native process or personal history."""
import base64
from concurrent.futures import ThreadPoolExecutor
from email.message import Message
import hashlib
import io
import json
import sqlite3
import threading
import uuid

import pytest

from eidos.api import EidosAPI, thread_payload
from eidos.cli import main
from eidos.evidence_discovery import EvidenceDiscovery
from eidos.history_imports import (
    FORMAT, MAX_FILE_BYTES, MAX_LINE_BYTES, MAX_LINES, MAX_UPLOAD_BYTES,
    HistoryImports, operation_identity,
)
from eidos.investigation import InvestigationError
from eidos.trace import PrivateTraceAccessError, TraceStore
import eidos.history_imports as importer_module


def event(text="needle ", *, thread="supplied", item="answer"):
    return json.dumps({"method": "item/agentMessage/delta", "params": {
        "threadId": thread, "turnId": "turn", "itemId": item, "delta": text},
        "future": {"unknown": [True, "保留"]}}, ensure_ascii=False).encode()


def commit(imports, data, request="request", **options):
    preview = imports.preview(data, **options)
    return imports.commit(data, request_id=request, preview_fingerprint=preview["previewFingerprint"], **options)


class Handler:
    def __init__(self, body=None, *, raw=None, headers=None):
        raw = raw if raw is not None else json.dumps(body or {}).encode()
        self.rfile = io.BytesIO(raw)
        self.headers = headers if headers is not None else {"Content-Length": str(len(raw)), "Content-Type": "application/json"}


def body(data, **extra):
    return {"format": FORMAT, "source": "authored public archive", "direction": "appserver_to_client",
            "fileName": "supplied.jsonl", "contentBase64": base64.b64encode(data).decode(), **extra}


def call(api, suffix="", *, method="POST", value=None, handler=None, query=None):
    return api.dispatch(handler or Handler(value), method, "/api/history/imports" + suffix, query or {})


def test_exact_original_bytes_and_offsets_repeated_lines_and_unterminated_tail(tmp_path):
    trace = TraceStore(tmp_path / "work.db")
    imports = HistoryImports(trace)
    raw = event("A\u2028needle ")
    data = b" \t\r\n" + raw + b"\r\n\n" + raw + b"\r" + b'{"unknown":{"verbatim":true}}'
    preview = imports.preview(data)
    assert trace.records() == []
    assert preview["recordCount"] == 3
    assert preview["blankLineCount"] == 2 and preview["physicalLineCount"] == 5
    assert preview["summary"] == {"threadCount": 1, "turnCount": 1, "unscopedRecordCount": 1, "discoverableFieldCount": 1}
    receipt, created = commit(imports, data)
    assert created and receipt["fileSha256"] == hashlib.sha256(data).hexdigest()
    assert trace.db.execute("SELECT original_bytes FROM history_imports").fetchone()[0] == data
    assert len(trace.records()) == 3
    assert trace.get(1).raw_text == raw.decode() == trace.get(2).raw_text
    assert thread_payload(trace, "supplied")["turns"][0]["items"][0]["text"] == "A\u2028needle A\u2028needle "
    mappings = []
    cursor = None
    while True:
        page = imports.records(receipt["id"], limit=1, cursor=cursor)
        mappings.extend(page["records"])
        cursor = page["nextCursor"]
        if cursor is None:
            break
    assert [r["line"] for r in mappings] == [2, 4, 5]
    for r in mappings:
        raw_bytes = data[r["byteStart"]:r["contentByteEnd"]]
        assert raw_bytes.decode() == trace.get(r["seq"]).raw_text
        assert hashlib.sha256(raw_bytes).hexdigest() == r["rawSha256"]
        assert data[r["contentByteEnd"]:r["byteEnd"]] in (b"", b"\r", b"\n", b"\r\n")
    assert mappings[-1]["byteEnd"] == len(data)
    trace.close()


@pytest.mark.parametrize("tail", [
    b"{broken", b"[]", b"null", b'\xff', b'\xef\xbb\xbf{}',
    b'{"future":NaN}', b'{"future":Infinity}', b'{"future":-Infinity}', b'{"future":1e999}',
    b'{"future":"\\ud800"}', b'{"\\udfff":1}', b'{"emittedAtMs":9223372036854775808}',
    b'{"future":' + b'[' * 65 + b'0' + b']' * 65 + b'}',
])
def test_controlled_malformed_tail_errors_leave_no_prefix_or_receipt(tail):
    trace = TraceStore()
    imports = HistoryImports(trace)
    with pytest.raises(InvestigationError) as error:
        imports.preview(event() + b"\n" + tail)
    assert error.value.status == 400
    assert "line 2" in error.value.message and "future" not in error.value.message
    assert trace.records() == []
    assert trace.db.execute("SELECT COUNT(*) FROM history_imports").fetchone()[0] == 0
    trace.close()


@pytest.mark.parametrize("data", [b"", b"\r\n \t\n", b" " * (MAX_FILE_BYTES + 1),
                                        b" " * (MAX_LINE_BYTES + 1), b"\n" * (MAX_LINES + 1)])
def test_file_line_count_and_empty_bounds(data):
    trace = TraceStore()
    with pytest.raises(InvestigationError) as error:
        HistoryImports(trace).preview(data)
    assert error.value.status == (400 if len(data) < 10 else 413)
    assert trace.records() == []
    trace.close()


def test_exact_line_limit_includes_crlf_and_depth_boundary():
    trace = TraceStore()
    imports = HistoryImports(trace)
    exact = b'{"x":"' + b'x' * (MAX_LINE_BYTES - 10) + b'"}\r\n'
    assert len(exact) == MAX_LINE_BYTES
    assert imports.preview(exact)["recordCount"] == 1
    with pytest.raises(InvestigationError) as error:
        imports.preview(exact[:-2] + b" \r\n")
    assert error.value.status == 413
    assert imports.preview(b'{"x":' + b'[' * 63 + b'0' + b']' * 63 + b'}')["recordCount"] == 1
    trace.close()


def test_receipt_replay_precedes_parser_collision_and_deleted_source_checks(tmp_path, monkeypatch):
    path = tmp_path / "trace.db"
    trace = TraceStore(path)
    imports = HistoryImports(trace)
    data = event()
    receipt, _ = commit(imports, data, file_name="before.jsonl")
    mapping = imports.records(receipt["id"])
    trace.close()
    trace = TraceStore(path)
    imports = HistoryImports(trace)
    trace.db.execute("DELETE FROM trace_records")
    def cannot_parse(*args):
        raise AssertionError("receipt replay cannot reparse")
    monkeypatch.setattr(HistoryImports, "_prepare", cannot_parse)
    assert imports.get_request("request") == receipt
    assert imports.commit(data, request_id="request", preview_fingerprint="previous-version", file_name="renamed.jsonl") == (receipt, False)
    assert imports.records(receipt["id"]) == mapping and trace.records() == []
    for changed in ({"data": data + b"\n"}, {"source": "changed"}, {"direction": "client_to_appserver"}):
        options = {"data": data, "request_id": "request", "preview_fingerprint": "old", **changed}
        with pytest.raises(InvestigationError) as error:
            imports.commit(**options)
        assert error.value.status == 409
    trace.close()


def test_late_insert_failure_rolls_back_rows_archive_mapping_and_index():
    trace = TraceStore()
    discovery = EvidenceDiscovery(trace)
    imports = HistoryImports(trace)
    before = discovery.search({"q": ["needle"]})["version"]
    trace.db.execute("CREATE TRIGGER fail_import BEFORE INSERT ON history_import_lines BEGIN SELECT RAISE(ABORT, 'authored failure'); END")
    with pytest.raises(sqlite3.IntegrityError):
        commit(imports, event() + b"\n" + event(thread="other"))
    assert trace.records() == []
    for table in ("history_imports", "history_import_lines", "evidence_discovery_dirty"):
        assert trace.db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
    assert discovery.search({"q": ["needle"], "knownVersion": [before]})["unchanged"] is True
    trace.close()


@pytest.mark.parametrize("prior", ["raw", "annotation", "semantic"])
def test_thread_collisions_include_nonraw_presentation_state(prior):
    trace = TraceStore()
    imports = HistoryImports(trace)
    preview = imports.preview(event())
    if prior == "raw":
        trace.append(source="unrelated", direction="internal", message=json.loads(event()))
    elif prior == "annotation":
        trace.annotate_thread("supplied", kind="hidden")
    else:
        trace.put_semantic_revision(thread_id="supplied", lens="thread", observer="authored", horizon_seq=0, nodes=[], confidence=1)
    with pytest.raises(InvestigationError) as error:
        imports.commit(event(), request_id="new", preview_fingerprint=preview["previewFingerprint"])
    assert error.value.status == 409
    assert trace.db.execute("SELECT COUNT(*) FROM history_imports").fetchone()[0] == 0
    trace.close()


@pytest.mark.parametrize("message", [
    {"method": "$capsule/result", "params": {}},
    {"method": "$capsule/unknown", "params": {}},
    {"method": "$history/item", "params": {"item": {"type": "privateResultPublication"}}},
    {"method": "item/completed", "params": {"item": {"type": "privateResultPublication"}}},
])
def test_reserved_publication_shapes_refused_without_substring_censorship(message):
    trace = TraceStore()
    imports = HistoryImports(trace)
    with pytest.raises(InvestigationError, match="reserved host"):
        imports.preview(event() + b"\n" + json.dumps(message).encode())
    data = event("$capsule/result privateResultPublication remain ordinary text")
    receipt, _ = commit(imports, data)
    assert receipt["recordCount"] == 1 and trace.get(1).raw_text.encode() == data
    trace.close()


def test_origin_label_cannot_hydrate_or_modify_existing_native_request():
    trace = TraceStore()
    trace.append(source="live", direction="client_to_appserver", message={"id": 77, "method": "turn/start", "params": {"threadId": "live-thread"}})
    original = trace.get(1)
    data = b'{"id":77,"result":{"turn":{"id":"borrowed-turn"}}}\n' + event()
    receipt, _ = commit(HistoryImports(trace), data, source="live")
    assert receipt["source"] == "live" and receipt["captureSource"] != "live"
    assert trace.get(1) == original
    assert trace.get(2).thread_id is None and trace.get(2).response_to is None
    assert {r.source for r in trace.records()[1:]} == {receipt["captureSource"]}
    trace.close()


def test_parallel_connections_one_receipt_and_distinct_operations_cannot_merge(tmp_path):
    path = tmp_path / "shared.db"
    first = TraceStore(path)
    HistoryImports(first)
    first.close()
    barrier = threading.Barrier(6)
    def admit(index, same):
        trace = TraceStore(path)
        imports = HistoryImports(trace)
        preview = imports.preview(event())
        barrier.wait()
        try:
            return imports.commit(event(), request_id="same" if same else f"different-{index}", preview_fingerprint=preview["previewFingerprint"])
        except InvestigationError as error:
            return error.status
        finally:
            trace.close()
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(lambda i: admit(i, True), range(6)))
    assert sum(created for _, created in results) == 1
    assert all(receipt == results[0][0] for receipt, _ in results)
    with ThreadPoolExecutor(max_workers=6) as pool:
        assert list(pool.map(lambda i: admit(i, False), range(6))) == [409] * 6
    trace = TraceStore(path)
    assert len(trace.records()) == 1
    trace.close()


def test_legacy_import_is_atomic_preserves_correlation_and_joins_outer_transaction():
    trace = TraceStore()
    request = '{"id":7,"method":"turn/start","params":{"threadId":"t"}}'
    response = '{"id":7,"result":{"turn":{"id":"u"}}}'
    assert trace.import_jsonl([request], source="legacy", direction="client_to_appserver") == 1
    with pytest.raises(InvestigationError):
        trace.import_jsonl([response, "bad"], source="legacy")
    assert trace.get(1).turn_id is None and len(trace.records()) == 1
    trace.db.execute("BEGIN IMMEDIATE")
    assert trace.import_jsonl([response], source="legacy") == 1
    assert trace.get(1).turn_id == "u" and trace.db.in_transaction
    trace.db.execute("ROLLBACK")
    assert trace.get(1).turn_id is None and len(trace.records()) == 1
    assert trace.import_jsonl([response], source="legacy") == 1
    assert trace.import_jsonl([response], source="legacy") == 1
    assert len(trace.records()) == 3 and trace.get(1).turn_id == "u"
    trace.close()


def test_legacy_midappend_error_rolls_back_savepoint_not_callers_writes(monkeypatch):
    trace = TraceStore()
    trace.db.execute("BEGIN IMMEDIATE")
    trace.append(source="caller", direction="internal", message={"prior": True})
    original = trace.append
    def failing(**kwargs):
        if kwargs["message"].get("stop"):
            raise OSError("authored insertion failure")
        return original(**kwargs)
    monkeypatch.setattr(trace, "append", failing)
    with pytest.raises(OSError):
        trace.import_jsonl(['{"valid":1}', '{"stop":true}'])
    assert trace.db.in_transaction and len(trace.records()) == 1
    trace.db.execute("COMMIT")
    assert trace.get(1).message == {"prior": True}
    trace.close()


def test_byte_commit_refuses_outer_transaction_and_private_role():
    private = TraceStore(role="private-control")
    with pytest.raises(PrivateTraceAccessError):
        HistoryImports(private)
    private.close()
    trace = TraceStore()
    imports = HistoryImports(trace)
    preview = imports.preview(event())
    trace.db.execute("BEGIN IMMEDIATE")
    with pytest.raises(InvestigationError) as error:
        imports.commit(event(), request_id="r", preview_fingerprint=preview["previewFingerprint"])
    assert error.value.status == 409 and trace.db.in_transaction
    trace.db.execute("ROLLBACK")
    trace.role = "private-control"
    for fn in (lambda: imports.preview(event()), lambda: imports.get_request("r"), lambda: imports.records("r"),
               lambda: imports.commit(event(), request_id="r", preview_fingerprint="r")):
        with pytest.raises(PrivateTraceAccessError):
            fn()
    trace.close()


def test_api_preview_commit_replay_mapping_and_raw_only_admission():
    trace = TraceStore()
    api = EidosAPI(trace)
    supplied = body(event())
    status, value = call(api, "/preview", value=supplied)
    assert status == 200 and value["preview"]["committable"] and trace.records() == []
    request = {**supplied, "requestId": "http", "previewFingerprint": value["preview"]["previewFingerprint"]}
    status, result = call(api, value=request)
    assert status == 201
    assert call(api, value=request) == (200, result)
    assert call(api, "/requests/http", method="GET") == (200, result)
    assert call(api, f"/{result['receipt']['id']}/records", method="GET")[1]["records"][0]["seq"] == 1
    unknown = body(b'{"future":{"kept":true}}')
    status, value = call(api, "/preview", value=unknown)
    assert status == 200 and value["preview"]["committable"] is False
    assert value["preview"]["reason"] == "no-discoverable-history"
    assert call(api, value={**unknown, "requestId": "unknown", "previewFingerprint": value["preview"]["previewFingerprint"]})[0] == 422
    assert len(trace.records()) == 1
    api.close(); trace.close()


@pytest.mark.parametrize("change", [
    {"captureSource": "live"}, {"direction": "internal"}, {"direction": "provider_response"},
    {"source": "x" * 257}, {"source": "\ud800"}, {"fileName": "../private.jsonl"},
    {"format": "guessed"}, {"contentBase64": "{}"}, {"contentBase64": "e30=\n"},
])
def test_api_rejects_unbounded_or_unknown_envelope_fields(change):
    trace = TraceStore(); api = EidosAPI(trace)
    status, value = call(api, "/preview", value={**body(event()), **change})
    assert status == 400 and set(value) == {"error"} and trace.records() == []
    api.close(); trace.close()


def test_api_duplicate_fields_short_body_and_upload_limits():
    trace = TraceStore(); api = EidosAPI(trace)
    raw = json.dumps(body(event())).encode()
    duplicate = raw[:-1] + b',"source":"other"}'
    assert call(api, "/preview", handler=Handler(raw=duplicate))[0] == 400
    assert call(api, "/preview", handler=Handler(raw=raw, headers={"Content-Length": str(len(raw) + 1)}))[0] == 400
    assert call(api, "/preview", handler=Handler(raw=b"", headers={"Content-Length": str(MAX_UPLOAD_BYTES + 1)}))[0] == 413
    for key in ("Transfer-Encoding", "Content-Encoding"):
        assert call(api, "/preview", handler=Handler(raw=raw, headers={"Content-Length": str(len(raw)), key: "identity"}))[0] == 400
    headers = Message(); headers["Content-Length"] = str(len(raw)); headers["Content-Length"] = str(len(raw))
    assert call(api, "/preview", handler=Handler(raw=raw, headers=headers))[0] == 400
    api.close(); trace.close()


def test_cli_binary_receipt_rename_replay_preview_and_raw_only(tmp_path, capsys, monkeypatch):
    file = tmp_path / "authored.jsonl"; db = tmp_path / "trace.db"
    data = event() + b"\r\n\r\n"
    file.write_bytes(data)
    main(["import-jsonl", str(db), str(file), "--preview", "--json"])
    assert json.loads(capsys.readouterr().out)["preview"]["recordCount"] == 1
    trace = TraceStore(db); assert trace.records() == []; trace.close()
    main(["import-jsonl", str(db), str(file)])
    assert "imported 1 records" in capsys.readouterr().out
    renamed = tmp_path / "renamed.jsonl"; file.rename(renamed)
    with monkeypatch.context() as patch:
        patch.setattr(HistoryImports, "_prepare", lambda *a: pytest.fail("CLI replay must precede parser"))
        main(["import-jsonl", str(db), str(renamed), "--json"])
    receipt = json.loads(capsys.readouterr().out)["receipt"]
    assert receipt["fileName"] == "authored.jsonl" and receipt["requestId"].startswith("history_")
    trace = TraceStore(db)
    assert len(trace.records()) == 1 and trace.db.execute("SELECT original_bytes FROM history_imports").fetchone()[0] == data
    trace.close()
    file.write_bytes(b'{"unknown":"preserved"}')
    main(["import-jsonl", str(db), str(file), "--direction", "provider_response"])
    assert "0 readable fields" in capsys.readouterr().out


def test_identity_excludes_display_name_and_fingerprint_is_canonical():
    data = event()
    expected = {"format": FORMAT, "source": "Unicode 🧭", "direction": "appserver_to_client",
                "fileSha256": hashlib.sha256(data).hexdigest(), "byteLength": len(data)}
    identity = operation_identity(data, source=expected["source"], direction=expected["direction"])
    assert identity["operationFingerprint"] == hashlib.sha256(json.dumps(expected, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def test_generated_capture_collision_refuses_before_appending(monkeypatch):
    fixed = uuid.UUID(int=1)
    trace = TraceStore()
    imports = HistoryImports(trace)
    trace.append(source="history-import:import_" + fixed.hex, direction="internal", message={"prior": True})
    monkeypatch.setattr(importer_module.uuid, "uuid4", lambda: fixed)
    with pytest.raises(InvestigationError) as error:
        commit(imports, event())
    assert error.value.status == 409 and len(trace.records()) == 1
    assert trace.db.execute("SELECT COUNT(*) FROM history_imports").fetchone()[0] == 0
    trace.close()


def test_mapping_cursor_scope_and_complete_response_bound(monkeypatch):
    trace = TraceStore(); imports = HistoryImports(trace)
    receipt, _ = commit(imports, event() + b"\n" + event())
    cursor = imports.records(receipt["id"], limit=1)["nextCursor"]
    other, _ = commit(imports, event(thread="other"), request="other")
    for options in ({"cursor": cursor}, {"cursor": "x" * 2049}, {"cursor": "%%%"}, {"limit": 101}, {"limit": True}):
        with pytest.raises(InvestigationError) as error:
            imports.records(other["id"], **options)
        assert error.value.status == 400
    with pytest.raises(InvestigationError) as error:
        imports.get_request("missing")
    assert error.value.status == 404
    monkeypatch.setattr(importer_module, "MAX_RESPONSE_BYTES", 128)
    for read in (lambda: imports.get_request("request"), lambda: imports.records(receipt["id"]),
                 lambda: imports.commit(event() + b"\n" + event(), request_id="request", preview_fingerprint="old")):
        with pytest.raises(InvestigationError) as error:
            read()
        assert error.value.status == 413
    assert len(trace.records()) == 3 and not trace.db.in_transaction
    trace.close()


def test_api_over_file_size_and_pending_preview_mismatch_do_not_mutate():
    trace = TraceStore(); api = EidosAPI(trace)
    supplied = body(event(), requestId="stale", previewFingerprint="0" * 64)
    assert call(api, value=supplied)[0] == 409
    oversized = body(b"x" * (MAX_FILE_BYTES + 1))
    assert call(api, "/preview", value=oversized)[0] == 413
    assert trace.records() == []
    api.close(); trace.close()
