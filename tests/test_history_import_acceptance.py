"""Independent ingestion acceptance over authored public bytes only.

These tests neither launch native work nor open existing private evidence. The
private-role checks use empty, newly created in-memory stores.
"""
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack, closing
import base64
import hashlib
import io
import json
import sqlite3
import threading

import pytest

from eidos.api import EidosAPI
from eidos.codex import AppServerClient
from eidos.history_imports import HistoryImports
from eidos.investigation import InvestigationError
from eidos.trace import PrivateTraceAccessError, TraceStore


FORMAT = "appserver-jsonl/v1"
SOURCE = "codex-live"  # An origin label must not borrow this recorder's source.
DIRECTION = "appserver_to_client"


def raw(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()


def item(thread, text, item_id="answer"):
    return {"method": "$history/item", "params": {"threadId": thread, "turnId": "turn",
        "item": {"id": item_id, "type": "agentMessage", "text": text}}}


def archive():
    delta = raw({"method": "item/agentMessage/delta", "params": {
        "threadId": "import-a", "turnId": "turn", "itemId": "split", "delta": "quartz "},
        "future": {"preserve": "privateResultPublication is ordinary text"}})
    rows = [
        (raw({"id": 77, "result": {"turn": {"id": "borrowed-turn"}}}), b"\r\n"),
        (b"", b"\n"),
        (delta, b"\n"),
        (raw(item("import-a", "UNWANTED_NEIGHBOR", "neighbor")), b"\r"),
        (delta, b"\r\n"),
        (raw({"method": "item/agentMessage/delta", "params": {"threadId": "import-a",
            "turnId": "turn", "itemId": "split", "delta": "bridge retains uncertainty."}}), b"\n"),
        (b" \t", b"\r\n"),
        (raw(item("import-b", "Other support: do not retry automatically.\u2028Still one physical line.")), b"\n"),
        (raw({"method": "future/descriptive", "params": {"note": "$capsule/result",
            "future": {"item": {"type": "privateResultPublication"}}}}), b"\r"),
        (raw(item("import-b", "An unterminated final line.", "last")), b""),
    ]
    data = b"".join(content + ending for content, ending in rows)
    expected, offset = [], 0
    for line, (content, ending) in enumerate(rows, 1):
        if content.strip():
            expected.append({"line": line, "byteStart": offset,
                "contentByteEnd": offset + len(content), "byteEnd": offset + len(content) + len(ending),
                "rawSha256": hashlib.sha256(content).hexdigest(), "rawText": content.decode()})
        offset += len(content) + len(ending)
    return data, expected


def metadata(**changes):
    return {"source": SOURCE, "direction": DIRECTION, "file_name": "authored.jsonl", **changes}


def commit(imports, data, preview, request_id="acceptance-operation", **changes):
    return imports.commit(data, request_id=request_id,
                          preview_fingerprint=preview["previewFingerprint"], **metadata(**changes))


def mappings(imports, import_id, limit=3):
    result, cursor = [], None
    while True:
        page = imports.records(import_id, limit=limit, cursor=cursor)
        assert page["importId"] == import_id
        assert len(json.dumps(page, ensure_ascii=False, separators=(",", ":")).encode()) <= 128 * 1024
        result.extend(page["records"])
        cursor = page["nextCursor"]
        if cursor is None:
            return result


class Request:
    def __init__(self, body):
        encoded = json.dumps(body).encode()
        self.headers = {"Content-Length": str(len(encoded))}
        self.rfile = io.BytesIO(encoded)


def api_call(api, path, body=None, **query):
    return api.dispatch(Request(body), "GET" if body is None else "POST", path,
                        {key: [str(value)] for key, value in query.items()})


@pytest.fixture(autouse=True)
def no_native(monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("history import attempted native startup")
    monkeypatch.setattr(AppServerClient, "start", forbidden)


def test_original_bytes_rpc_isolation_discovery_and_canonical_save(tmp_path):
    path = tmp_path / "composed.db"
    data, expected = archive()
    with closing(TraceStore(path)) as trace, closing(EidosAPI(trace)) as api:
        pending = trace.append(source=SOURCE, direction="client_to_appserver", message={
            "id": 77, "method": "turn/start", "params": {"threadId": "existing-live-thread",
            "input": [{"type": "text", "text": "Existing independent request"}]}})
        body = {"format": FORMAT, "source": SOURCE, "direction": DIRECTION,
                "fileName": "authored.jsonl", "contentBase64": base64.b64encode(data).decode()}
        status, review = api_call(api, "/api/history/imports/preview", body)
        assert status == 200, review
        preview = review["preview"]
        assert preview["physicalLineCount"] == 10 and preview["blankLineCount"] == 2
        assert preview["recordCount"] == 8 and preview["summary"]["threadCount"] == 2
        assert preview["byteLength"] == len(data)
        assert preview["fileSha256"] == hashlib.sha256(data).hexdigest()
        assert [r.seq for r in trace.records()] == [pending.seq]
        status, result = api_call(api, "/api/history/imports", {**body,
            "requestId": "composed-import", "previewFingerprint": preview["previewFingerprint"]})
        assert status == 201, result
        receipt = result["receipt"]
        assert receipt["source"] == SOURCE and receipt["captureSource"] != SOURCE
        assert trace.get(pending.seq) == pending
        importer = HistoryImports(trace)
        lines = mappings(importer, receipt["id"])
        assert len(lines) == len(expected)
        for row, wanted in zip(lines, expected):
            assert row == {**{k: v for k, v in wanted.items() if k != "rawText"}, "seq": row["seq"]}
            record = trace.get(row["seq"])
            assert record.raw_text == wanted["rawText"] and record.source == receipt["captureSource"]
        first = trace.get(lines[0]["seq"])
        assert first.response_to is None and first.thread_id is None
        assert lines[1]["rawSha256"] == lines[3]["rawSha256"]  # Repeated physical records survive.
        assert lines[1]["seq"] != lines[3]["seq"]
        original = trace.db.execute("SELECT original_bytes FROM history_imports WHERE id=?", (receipt["id"],)).fetchone()[0]
        assert bytes(original) == data

        inspected = []
        for query in ("quartz bridge", "do not retry automatically"):
            status, page = api_call(api, "/api/evidence/search", q=query)
            assert status == 200, page
            hit, = page["hits"]
            status, detail = api_call(api, "/api/evidence/hits/" + hit["id"], q=query, version=hit["version"])
            assert status == 200, detail
            inspected.extend(detail["records"])
        selected = sorted(inspected, key=lambda record: record["seq"])
        assert [r["seq"] for r in selected] == [lines[n]["seq"] for n in (1, 3, 4, 5)]
        assert not any("UNWANTED_NEIGHBOR" in r["rawText"] for r in selected)
        status, work = api_call(api, "/api/investigations", {"requestId": "composed-question",
            "title": "Question from explicit imported evidence", "question": "Why retain uncertain delivery?",
            "selections": [{"threadId": r["threadId"], "startSeq": r["seq"], "endSeq": r["seq"]} for r in selected]})
        assert status == 201, work
        assert work["contexts"][0]["records"] == selected
        assert work["artifact"] is None and work["attempt"] is None
    with closing(TraceStore(path)) as trace, closing(EidosAPI(trace)) as api:
        assert HistoryImports(trace).get_request("composed-import") == receipt
        assert api.investigations.get(work["id"]) == work


def test_six_connection_same_operation_and_deleted_source_replay(tmp_path, monkeypatch):
    path = tmp_path / "six.db"
    data, _ = archive()
    with ExitStack() as stack:
        traces = [stack.enter_context(closing(TraceStore(path))) for _ in range(6)]
        imports = [HistoryImports(trace) for trace in traces]
        preview = imports[0].preview(data, **metadata())
        barrier = threading.Barrier(6)

        def submit(index):
            barrier.wait(timeout=10)
            return commit(imports[index], data, preview, file_name=f"renamed-{index}.jsonl")

        with ThreadPoolExecutor(max_workers=6) as pool:
            outcomes = list(pool.map(submit, range(6)))
        receipt = outcomes[0][0]
        assert sum(created for _, created in outcomes) == 1
        assert all(value == receipt for value, _ in outcomes)
        assert len(traces[0].records()) == 8
        frozen_map = mappings(imports[0], receipt["id"])
        traces[0].db.execute("DELETE FROM trace_records WHERE source=?", (receipt["captureSource"],))
        assert traces[0].records() == []
    with closing(TraceStore(path)) as reopened:
        importer = HistoryImports(reopened)
        assert importer.get_request(receipt["requestId"]) == receipt
        def later_parser(*_args, **_kwargs):
            pytest.fail("durable operation replay consulted a later parser/admission policy")
        monkeypatch.setattr(importer, "_prepare", later_parser)
        replay, created = commit(importer, data, preview, file_name="another-name.jsonl")
        assert created is False and replay == receipt and reopened.records() == []
        assert mappings(importer, receipt["id"]) == frozen_map
        for changes in ({"source": "different-origin"}, {"direction": "client_to_appserver"}):
            with pytest.raises(InvestigationError) as error:
                commit(importer, data, preview, **changes)
            assert error.value.status == 409
        with pytest.raises(InvestigationError) as error:
            commit(importer, data + b"\n", preview)
        assert error.value.status == 409


def test_distinct_operations_recheck_thread_collision_after_preview(tmp_path):
    path = tmp_path / "collision.db"
    with closing(TraceStore(path)) as left, closing(TraceStore(path)) as right:
        imports = [HistoryImports(left), HistoryImports(right)]
        data = [raw(item("shared-import-thread", f"candidate {i}")) for i in range(2)]
        reviews = [imports[i].preview(data[i], **metadata()) for i in range(2)]
        barrier = threading.Barrier(2)

        def submit(index):
            barrier.wait(timeout=10)
            try:
                receipt, created = commit(imports[index], data[index], reviews[index], f"distinct-{index}")
                return (201 if created else 200), receipt
            except InvestigationError as error:
                return error.status, None

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(submit, range(2)))
        assert sorted(status for status, _ in results) == [201, 409]
        assert len(left.records()) == 1
        assert left.db.execute("SELECT COUNT(*) FROM history_imports").fetchone()[0] == 1


@pytest.mark.parametrize("remaining", ["annotation", "semantic-map"])
def test_no_rows_does_not_allow_attachment_to_stale_thread_state(tmp_path, remaining):
    with closing(TraceStore(tmp_path / f"{remaining}.db")) as trace:
        if remaining == "annotation":
            trace.annotate_thread("stale-thread", kind="authored-internal")
        else:
            trace.put_semantic_revision(thread_id="stale-thread", lens="thread", observer="authored",
                                        horizon_seq=0, nodes=[])
        data = raw(item("stale-thread", "new archive must remain independent"))
        importer = HistoryImports(trace)
        review = importer.preview(data, **metadata())
        with pytest.raises(InvestigationError) as error:
            commit(importer, data, review)
        assert error.value.status == 409 and trace.records() == []


def test_abort_at_receipt_insert_rolls_back_all_appends_and_discovery_generation(tmp_path):
    with closing(TraceStore(tmp_path / "rollback.db")) as trace, closing(EidosAPI(trace)) as api:
        old = trace.append_line(source="authored-existing", direction=DIRECTION,
                               raw_text=raw(item("old-thread", "existing needle")).decode())
        _, before = api_call(api, "/api/evidence/search", q="existing needle")
        importer = HistoryImports(trace)
        data, _ = archive()
        preview = importer.preview(data, **metadata())
        seen = []

        def observe_all_appends():
            seen.append(trace.db.execute("SELECT COUNT(*) FROM trace_records WHERE seq>?", (old.seq,)).fetchone()[0])
            return 0

        trace.db.create_function("acceptance_before_receipt", 0, observe_all_appends)
        trace.db.executescript("""CREATE TRIGGER acceptance_refuse_receipt BEFORE INSERT ON history_imports
            BEGIN SELECT acceptance_before_receipt(); SELECT RAISE(ABORT,'authored receipt refusal'); END;""")
        with pytest.raises((sqlite3.DatabaseError, InvestigationError)):
            commit(importer, data, preview)
        assert seen == [8]  # The failure is after every native description was inserted.
        assert trace.records() == [old]
        assert trace.db.execute("SELECT COUNT(*) FROM history_imports").fetchone()[0] == 0
        assert trace.db.execute("SELECT COUNT(*) FROM history_import_lines").fetchone()[0] == 0
        status, unchanged = api_call(api, "/api/evidence/search", q="existing needle", knownVersion=before["version"])
        assert status == 200 and unchanged["unchanged"] is True
        with pytest.raises(InvestigationError) as missing:
            importer.get_request("acceptance-operation")
        assert missing.value.status == 404
        trace.db.execute("DROP TRIGGER acceptance_refuse_receipt")
        receipt, created = commit(importer, data, preview)
        assert created is True and receipt["recordCount"] == 8 and len(trace.records()) == 9


@pytest.mark.parametrize("reserved", [
    {"method": "$capsule/result", "params": {"text": "claimed publication"}},
    {"method": "$capsule/unknown", "params": {}},
    {"method": "$history/item", "params": {"threadId": "new", "turnId": "turn",
        "item": {"id": "claimed", "type": "privateResultPublication", "text": "claimed publication",
                 "provenance": {"kind": "private-capsule", "capsuleId": "copied-description"}}}},
])
def test_reserved_publication_shape_refusal_is_atomic_but_words_remain_data(tmp_path, reserved):
    with closing(TraceStore(tmp_path / "reserved.db")) as trace:
        importer = HistoryImports(trace)
        ordinary = raw(item("ordinary", "$capsule/result and privateResultPublication are inert words."))
        candidate = ordinary + b"\n" + raw(reserved)
        with pytest.raises(InvestigationError) as error:
            importer.preview(candidate, **metadata())
        assert error.value.status == 400 and trace.records() == []
        preview = importer.preview(ordinary, **metadata())
        receipt, created = commit(importer, ordinary, preview)
        assert created and receipt["recordCount"] == 1
        assert trace.records()[0].raw_text == ordinary.decode()


def test_private_role_refuses_constructor_and_every_public_operation():
    data, _ = archive()
    with closing(TraceStore()) as trace:
        importer = HistoryImports(trace)
        preview = importer.preview(data, **metadata())
        trace.role = "private-control"
        try:
            for operation in (lambda: importer.preview(data, **metadata()),
                              lambda: commit(importer, data, preview),
                              lambda: importer.get_request("acceptance-operation"),
                              lambda: importer.records("missing-import")):
                with pytest.raises(PrivateTraceAccessError):
                    operation()
        finally:
            trace.role = "workbench"
    with closing(TraceStore(role="private-control")) as empty_private:
        with pytest.raises(PrivateTraceAccessError):
            HistoryImports(empty_private)


def test_legacy_batch_failure_preserves_outer_transaction_without_partial_prefix():
    delta = raw({"method": "item/agentMessage/delta", "params": {
        "threadId": "legacy", "turnId": "turn", "itemId": "answer", "delta": "needle "}}).decode()
    with closing(TraceStore()) as trace:
        with pytest.raises(InvestigationError):
            trace.import_jsonl([delta, "{malformed tail"], source="legacy-capture")
        assert trace.records() == []
        trace.db.executescript("""CREATE TRIGGER acceptance_legacy_refusal BEFORE INSERT ON trace_records
            WHEN NEW.method='authored/refuse' BEGIN SELECT RAISE(ABORT,'authored batch refusal'); END;""")
        trace.db.execute("BEGIN IMMEDIATE")
        outer = trace.append_line(source="unrelated-outer-write", direction="internal",
                                  raw_text=raw(item("outer", "Keep this surrounding transaction")).decode())
        with pytest.raises(sqlite3.DatabaseError):
            trace.import_jsonl([delta, '{"method":"authored/refuse"}'], source="legacy-capture")
        assert trace.db.in_transaction and trace.records() == [outer]
        trace.db.execute("COMMIT")
        # Separate successful legacy calls intentionally remain distinct, with
        # their original caller-selected correlation source and count contract.
        assert trace.import_jsonl([delta], source="legacy-capture") == 1
        assert trace.import_jsonl([delta], source="legacy-capture") == 1
        records = trace.records()[1:]
        assert [r.source for r in records] == ["legacy-capture", "legacy-capture"]
        assert [r.raw_text for r in records] == [delta, delta]
