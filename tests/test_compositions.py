"""Saved presentations retain references without copying evidence or authority."""
import copy
from concurrent.futures import ThreadPoolExecutor
import io
import json
from threading import Barrier

import pytest

from eidos.api import EidosAPI
from eidos.trace import TraceStore
from test_artifact_context_compatibility import legacy_body, result, using


def call(api, method="POST", path="", body=None, **query):
    raw = json.dumps(body).encode() if body is not None else b""
    class Handler:
        headers = {"Content-Length": str(len(raw))}
        rfile = io.BytesIO(raw)
    return api.dispatch(Handler(), method, "/api/compositions" + path, {k: [str(v)] for k, v in query.items()})


def target(work):
    return {"investigationId": work["id"], "contextId": work["currentContextId"], "artifactId": work["artifact"]["id"]}


@pytest.fixture
def setup(tmp_path):
    path = tmp_path / "compositions.db"
    trace = TraceStore(path)
    api = EidosAPI(trace)
    a = result(api.investigations, api.investigations.create(legacy_body(trace)))
    b = result(api.investigations, api.investigations.create(using(a)))
    body = {"requestId": "snapshot-first", "title": "Decision comparison", "rendererVersion": "test-renderer/1",
            "arrangement": {"left": target(a), "right": target(b), "lens": "result", "layout": "beside"},
            "focus": {**target(a), "blockId": "block-0", "seq": 1, "threadId": "source"}}
    try:
        yield path, trace, api, a, b, body
    finally:
        api.close()
        trace.close()


def test_save_reopen_and_copy_preserve_immutable_content_without_canonical_writes(setup):
    path, trace, api, a, _, body = setup
    canonical = [tuple(r) for r in trace.db.execute("SELECT * FROM investigations ORDER BY id")]
    trace_rows = [tuple(r) for r in trace.db.execute("SELECT * FROM trace_records")]
    status, value = call(api, body=body)
    saved = value["composition"]
    assert status == 201
    assert saved["arrangement"] == body["arrangement"] and saved["focus"] == body["focus"]
    assert saved["copiedFrom"] is None
    obj = api.compositions.objects.get(saved["contentId"])
    assert obj.kind == "workbench.composition.v1" and obj.data == {k:v for k,v in saved.items() if k != "contentId"}
    assert "projectedPrompt" not in obj.data_json and "rawText" not in obj.data_json
    assert call(api, body=body) == (status, value)
    assert call(api, "GET", "/" + saved["id"])[1] == value
    changed = copy.deepcopy(body)
    changed.update(requestId="snapshot-copy", copiedFrom=saved["id"])
    changed["arrangement"]["layout"] = "stacked"
    copied = call(api, body=changed)[1]["composition"]
    assert copied["id"] != saved["id"] and copied["copiedFrom"] == saved["id"]
    assert api.compositions.objects.get(copied["contentId"]).ref("copiedFrom") == saved["contentId"]
    assert api.compositions.get(saved["id"]) == saved
    assert [tuple(r) for r in trace.db.execute("SELECT * FROM investigations ORDER BY id")] == canonical
    assert [tuple(r) for r in trace.db.execute("SELECT * FROM trace_records")] == trace_rows
    reopened_trace = TraceStore(path)
    reopened = EidosAPI(reopened_trace)
    try:
        assert reopened.compositions.get(saved["id"]) == saved
        assert reopened.compositions.get(copied["id"]) == copied
    finally:
        reopened.close()
        reopened_trace.close()


def test_missing_source_does_not_rewrite_read_or_block_exact_retry_but_new_save_fails(setup):
    _, trace, api, a, _, body = setup
    status, value = call(api, body=body)
    # Simulate trusted source unavailability after the snapshot was committed.
    trace.db.execute("DELETE FROM investigation_requests WHERE investigation_id=?", (a["id"],))
    trace.db.execute("DELETE FROM investigations WHERE id=?", (a["id"],))
    assert call(api, body=body) == (status, value)
    assert call(api, "GET", "/" + value["composition"]["id"]) == (200, value)
    assert call(api, body={**body, "requestId": "new-missing"})[0] == 404
    assert call(api, body={**body, "title": "Changed retry"})[0] == 409


@pytest.mark.parametrize("mutation", [
    lambda b: b.update(perform="launch"),
    lambda b: b["arrangement"].update(outputGrants=["copied"]),
    lambda b: b["arrangement"]["left"].update(holder="owner"),
    lambda b: b["focus"].update(rawText="copied source"),
    lambda b: b.update(rendererVersion=""),
    lambda b: b.update(title="x" * 161),
    lambda b: b["focus"].update(seq=True),
    lambda b: b["focus"].update(seq=2**53),
    lambda b: b["focus"].pop("threadId"),
    lambda b: b["focus"].update(blockId="latest"),
    lambda b: b["focus"].pop("artifactId"),
    lambda b: b["arrangement"].update(intent="execute"),
    lambda b: b["arrangement"].update(intent="evidence-chain"),
    lambda b: b["arrangement"].update(intent="alternative-review"),
])
def test_copied_authority_unknown_fields_and_invalid_selectors_are_rejected(setup, mutation):
    _, trace, api, _, _, body = setup
    mutation(body)
    assert call(api, body=body)[0] == 400
    assert trace.db.execute("SELECT COUNT(*) FROM workbench_compositions").fetchone()[0] == 0


def test_wrong_owner_context_artifact_and_record_cannot_form_valid_bindings(setup):
    _, _, api, a, b, body = setup
    for patch in ({"investigationId": b["id"]}, {"contextId": b["currentContextId"]},
                  {"artifactId": b["artifact"]["id"]}, {"seq": 2}, {"threadId": "unrelated"}):
        candidate = copy.deepcopy(body)
        candidate["focus"].update(patch)
        assert call(api, body=candidate)[0] == 409
    assert call(api, body={**body, "copiedFrom": "unknown"})[0] == 404
    # A version label is descriptive. Unsupported selectors remain inspectable;
    # it is the renderer's job to decline interpreting them under another parser.
    saved = call(api, body={**body, "rendererVersion": "future-parser/99"})
    assert saved[0] == 201 and saved[1]["composition"]["rendererVersion"] == "future-parser/99"


def test_http_boundary_rejects_oversized_raw_body_before_parsing_and_nonfinite_content(setup):
    _, trace, api, _, _, body = setup
    raw = json.dumps(body).encode() + b" " * 16384
    class Handler:
        headers = {"Content-Length": str(len(raw))}
        rfile = io.BytesIO(raw)
    assert api.dispatch(Handler(), "POST", "/api/compositions", {})[0] == 400
    assert Handler.rfile.tell() == 0
    assert call(api, body={**body, "focus": float("nan")})[0] == 400
    assert trace.db.execute("SELECT COUNT(*) FROM workbench_compositions").fetchone()[0] == 0


@pytest.mark.parametrize("mismatch", ["missing-attempt", "wrong-attempt-context"])
def test_new_save_requires_artifact_attempt_consistency_without_rewriting_prior_receipt(setup, mismatch):
    _, trace, api, a, b, body = setup
    original = call(api, body=body)
    assert original[0] == 201
    # A malformed trusted import is evidence to inspect, never permission to
    # create another apparently resolved snapshot over inconsistent provenance.
    changed = copy.deepcopy(a)
    if mismatch == "missing-attempt":
        changed["attempt"] = None
    else:
        changed["attempt"]["contextId"] = b["currentContextId"]
    with trace.db:
        api.investigations._save(changed)
    assert call(api, body=body) == original
    assert call(api, "GET", "/" + original[1]["composition"]["id"]) == (200, original[1])
    assert call(api, body={**body, "requestId": "inconsistent-new-save"})[0] == 409
    assert trace.db.execute("SELECT COUNT(*) FROM workbench_compositions").fetchone()[0] == 1


def test_search_pages_metadata_and_query_scope_without_source_reads(setup, monkeypatch):
    _, _, api, _, _, body = setup
    for index in range(5):
        api.compositions.create({**body, "requestId": f"page-{index}", "title": f"Straße %_ {index}"})
    monkeypatch.setattr(api.investigations, "_load", lambda *_: pytest.fail("catalog read canonical source"))
    monkeypatch.setattr(api.compositions.objects, "get", lambda *_: pytest.fail("catalog read full composition"))
    status, first = call(api, "GET", q="STRASSE %_", limit=2)
    assert status == 200 and len(first["compositions"]) == 2 and first["nextCursor"]
    seen, page = [], first
    while True:
        seen.extend(item["id"] for item in page["compositions"])
        assert "arrangement" not in json.dumps(page) and "focus" not in json.dumps(page)
        if not page["nextCursor"]:
            break
        status, page = call(api, "GET", q="STRASSE %_", limit=2, cursor=page["nextCursor"])
        assert status == 200
    assert len(seen) == len(set(seen)) == 5
    assert call(api, "GET", q="other", cursor=first["nextCursor"])[0] == 400
    assert call(api, "GET", limit=41)[0] == 400
    assert call(api, "GET", limit="")[0] == 400
    assert call(api, "GET", unexpected="")[0] == 400


def test_simultaneous_same_request_on_independent_connections_has_one_immutable_receipt(setup):
    path, trace, api, _, _, body = setup
    other_trace = TraceStore(path)
    other = EidosAPI(other_trace)
    barrier = Barrier(2)
    def save(controller):
        barrier.wait(timeout=3)
        return call(controller, body=body)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            one = pool.submit(save, api)
            two = pool.submit(save, other)
            assert one.result(timeout=3) == two.result(timeout=3)
        assert trace.db.execute("SELECT COUNT(*) FROM workbench_compositions").fetchone()[0] == 1
    finally:
        other.close()
        other_trace.close()
