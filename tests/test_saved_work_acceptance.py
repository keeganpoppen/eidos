"""Independent saved-work acceptance over persisted synthetic source histories.

Real HTTP byte checks use serve.py. Canonical parse instrumentation observes the
actual stored JSON, not a freshly serialized copy of a response. No native or
model process is permitted in this suite.
"""
from __future__ import annotations

import base64
import copy
import importlib.util
import json
from pathlib import Path
import shutil
from unittest.mock import patch

import pytest

from eidos.api import EidosAPI
from eidos.codex import AppServerClient
from eidos.investigation import InvestigationStore
from eidos.trace import TraceStore

spec = importlib.util.spec_from_file_location("saved_work_scale_demo", Path(__file__).parents[1] / "scripts/saved_work_scale_demo.py")
assert spec and spec.loader
demo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(demo)


@pytest.fixture(autouse=True)
def no_native(monkeypatch):
    monkeypatch.setattr(AppServerClient, "start", lambda *_a, **_k: pytest.fail("saved-work acceptance attempted native startup"))


@pytest.fixture(scope="module")
def scale_database(tmp_path_factory):
    path = tmp_path_factory.mktemp("saved-work-scale") / "fixture.db"
    trace = TraceStore(path)
    api = EidosAPI(trace)
    try:
        with patch.object(AppServerClient, "start", side_effect=AssertionError("synthetic seeding attempted native startup")):
            marker = demo.seed(api)
    finally:
        api.close()
        trace.close()
    return path, marker


@pytest.fixture
def small(tmp_path):
    path = tmp_path / "saved-work.db"
    trace = TraceStore(path)
    api = EidosAPI(trace)
    marker = demo.seed(api, owners=7, revisions=5)
    try:
        yield path, trace, api, marker
    finally:
        api.close()
        trace.close()


def get(api, path, **params):
    return api.dispatch(None, "GET", "/api/investigations" + path,
                        {name: value if isinstance(value, list) else [str(value)] for name, value in params.items()})


def source_path(marker, name):
    return f"/{marker['investigations'][name]}/artifacts/{marker['artifacts'][name]}/source"


def test_thousand_owner_real_http_discovery_and_bounded_source_recovery(scale_database, tmp_path):
    original, marker = scale_database
    path = tmp_path / "http-copy.db"
    shutil.copy2(original, path)
    result = demo.measure(path, marker)
    assert result["owners"] == 1000 and result["outOfFirstPageResultFound"]
    assert result["firstCatalogRead"]["canonicalParseCount"] == 1000
    assert result["firstCatalogRead"]["distinctCanonicalOwners"] == 1000
    assert result["hotCatalogAndSearch"]["canonicalParses"] == []
    assert result["unchangedSelectedView"]["canonicalParses"] == []
    assert result["reopenedHotCatalog"]["canonicalParses"] == []
    assert result["reopenedHotCatalog"]["bodyBytes"] < 150
    assert result["hotCatalogAndSearch"]["catalogBytes"] < 16_000
    assert result["hotCatalogAndSearch"]["searchBytes"] < 2_000
    assert result["hotCatalogAndSearch"]["unchangedBytes"] < 150
    assert result["unchangedSelectedView"]["bodyBytes"] < 150
    assert [hop["canonicalParses"] for hop in result["sourceHops"]] == [[marker["investigations"][name]] for name in ("C", "B", "A")]
    assert result["sourceHops"][-1]["bodyBytes"] * 10 < result["fullSourceOwnerViewBytes"]
    assert result["originalSupportRecovered"] and result["nativeOrModelCalls"] == 0


def test_keyset_pages_find_every_owner_and_result_once_after_reopen(scale_database, tmp_path):
    original, marker = scale_database
    path = tmp_path / "pages-copy.db"
    shutil.copy2(original, path)
    trace = TraceStore(path)
    api = EidosAPI(trace)
    try:
        for route, key, identity in (("/catalog", "investigations", "id"), ("/artifacts", "artifacts", "investigationId")):
            seen, cursor = [], None
            while True:
                status, page = get(api, route, **({"limit": 40, "cursor": cursor} if cursor else {"limit": 40}))
                assert status == 200 and 1 <= len(page[key]) <= 40
                seen.extend(item[identity] for item in page[key])
                assert not any(token in json.dumps(page) for token in ("projectedPrompt", "outputSeqs", "rawText", "contexts", "artifactHistory"))
                cursor = page["nextCursor"]
                if not cursor:
                    break
            assert len(seen) == len(set(seen)) == marker["owners"]
            assert set(marker["investigations"].values()) <= set(seen[-40:])
    finally:
        api.close()
        trace.close()


def test_exact_out_of_page_result_composition_and_source_reads_preserve_all_pins(small):
    _, trace, api, marker = small
    a = api.investigations.get(marker["investigations"]["A"])
    contexts_before = [tuple(row) for row in trace.db.execute("SELECT * FROM cm_requests ORDER BY name")]
    history_before = [tuple(row) for row in trace.db.execute("SELECT * FROM investigations ORDER BY id")]
    trace_count = trace.db.execute("SELECT COUNT(*) FROM trace_records").fetchone()[0]
    status, found = get(api, "/artifacts", q="STRASSE", limit=1)
    assert status == 200 and found["artifacts"][0]["artifactId"] == a["artifact"]["id"]
    body = {"requestId": "saved-work-acceptance/compose", "title": "Exact historical source", "question": "Which decision controls recovery?",
        "selections": [], "artifactInputs": [{"investigationId": a["id"], "artifactId": a["artifact"]["id"], "rationale": "Found by title search outside the loaded page."}]}
    composed = demo.composition.call(api, body=body)
    frozen = composed["contexts"][0]["artifactInputs"][0]
    assert frozen["artifact"] == a["artifact"]
    assert frozen["sourceContextId"] == marker["contexts"]["A"]
    assert frozen["sourceAttemptManifestId"] == a["attempt"]["manifestId"]
    assert composed["attempt"] is None
    # Retrying the same save must retain the same owner and exact frozen packet.
    assert demo.composition.call(api, body=body) == composed
    for name in ("C", "B", "A"):
        status, source = get(api, source_path(marker, name), contextId=marker["contexts"][name])
        assert status == 200 and source["artifact"]["id"] == marker["artifacts"][name]
        assert "contexts" not in source and "artifactHistory" not in source
    assert [tuple(row) for row in trace.db.execute("SELECT * FROM cm_requests ORDER BY name")] == contexts_before
    assert [tuple(row) for row in trace.db.execute("SELECT * FROM investigations WHERE id!=? ORDER BY id", (composed["id"],))] == history_before
    assert trace.db.execute("SELECT COUNT(*) FROM trace_records").fetchone()[0] == trace_count


def test_source_returns_historical_artifact_context_and_attempt_not_current_fields(small):
    _, trace, api, marker = small
    old = api.investigations.get(marker["investigations"]["A"])
    imported = copy.deepcopy(old)
    # Explicit trusted canonical-import fixture: retain a real historical result
    # while installing distinguishable later fields. It admits no executable work.
    imported["artifactHistory"] = [copy.deepcopy(old["artifact"])]
    imported["attemptHistory"] = [copy.deepcopy(old["attempt"])]
    imported["currentContextId"] = old["contexts"][0]["id"]
    imported["attempt"] = {**old["attempt"], "id": "attempt_synthetic_later", "contextId": imported["currentContextId"]}
    imported["artifact"] = {**old["artifact"], "id": "artifact_synthetic_later", "attemptId": imported["attempt"]["id"],
        "contextId": imported["currentContextId"], "text": "Later synthetic result must never substitute for the referenced one."}
    imported["adoption"] = {**old["adoption"], "artifactId": imported["artifact"]["id"]}
    trace.db.execute("UPDATE investigations SET state_json=? WHERE id=?", (json.dumps(imported, sort_keys=True, separators=(",", ":")), old["id"]))
    status, source = get(api, source_path(marker, "A"), contextId=marker["contexts"]["A"])
    assert status == 200
    assert source["artifact"] == old["artifact"] and source["attempt"] == old["attempt"]
    assert source["context"]["id"] == old["currentContextId"] and source["adoption"] is None
    assert get(api, source_path(marker, "A"), contextId=imported["currentContextId"])[0] == 409
    wrong_owner = source_path(marker, "A").replace(old["id"], marker["investigations"]["B"])
    assert get(api, wrong_owner)[0] == 404


def test_external_writer_refreshes_only_changed_owner_and_preserves_prior_frozen_input(small):
    path, _, api, marker = small
    b = api.investigations.get(marker["investigations"]["B"])
    c = api.investigations.get(marker["investigations"]["C"])
    _, before = get(api, f"/{b['id']}/view")
    get(api, "/catalog")
    writer = TraceStore(path)
    try:
        InvestigationStore(writer).adopt(b["id"], {"artifactId": b["artifact"]["id"], "decision": "reject", "note": "Later independent review."})
    finally:
        writer.close()
    with demo.source_reads(api) as observed:
        status, changed = get(api, f"/{b['id']}/view", knownVersion=before["version"])
    assert status == 200 and not changed["unchanged"] and changed["investigation"]["adoption"]["decision"] == "reject"
    assert observed["canonicalParses"] == [b["id"], b["id"]]  # dirty projection + requested full view
    with demo.source_reads(api) as idle:
        assert get(api, f"/{b['id']}/view", knownVersion=changed["version"])[1]["unchanged"]
        get(api, "/artifacts")
    assert idle["canonicalParses"] == []
    assert api.investigations.get(c["id"]) == c


def test_http_rejects_invalid_limits_and_cursor_query_kind_reuse(small):
    path, _, _, _ = small
    with demo.http_server(path) as (origin, _api):
        for limit in (0, 41, "abc"):
            assert demo.http(origin, "/catalog", {"limit": limit})["status"] == 400
        page = demo.http(origin, "/catalog", {"limit": 1})["body"]
        cursor = page["nextCursor"]
        assert demo.http(origin, "/catalog", {"cursor": cursor, "q": "different"})["status"] == 400
        assert demo.http(origin, "/artifacts", {"cursor": cursor})["status"] == 400
        assert demo.http(origin, "/catalog", {"limit": [1, 2]})["status"] == 400
        assert demo.http(origin, "/catalog", {"unexpected": "value"})["status"] == 400


@pytest.mark.parametrize("query", [{"limit": ["", "1"]}, {"unexpected": ""}, {"knownVersion": ""}])
def test_http_does_not_discard_blank_parameters_before_validation(small, query):
    path, _, _, _ = small
    with demo.http_server(path) as (origin, _api):
        assert demo.http(origin, "/catalog", query)["status"] == 400


def test_cursor_version_is_an_integer_not_boolean(small):
    _, _, api, _ = small
    first = get(api, "/catalog", limit=1)[1]
    cursor = first["nextCursor"]
    decoded = json.loads(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)))
    decoded["v"] = True
    altered = base64.urlsafe_b64encode(json.dumps(decoded).encode()).decode().rstrip("=")
    assert get(api, "/catalog", limit=1, cursor=altered)[0] == 400


def test_rebuild_and_reopen_preserve_versions_exact_sources_and_canonical_bytes(small):
    path, trace, api, marker = small
    catalog = get(api, "/catalog")[1]
    detail = get(api, source_path(marker, "A"), contextId=marker["contexts"]["A"])[1]
    before = [tuple(row) for row in trace.db.execute("SELECT * FROM investigations ORDER BY id")]
    api.investigation_reads.rebuild()
    assert get(api, "/catalog", knownVersion=catalog["version"])[1]["unchanged"]
    assert get(api, source_path(marker, "A"), contextId=marker["contexts"]["A"])[1] == detail
    reopened_trace = TraceStore(path)
    reopened = EidosAPI(reopened_trace)
    try:
        assert get(reopened, "/catalog", knownVersion=catalog["version"])[1]["unchanged"]
        assert get(reopened, source_path(marker, "A"), contextId=marker["contexts"]["A"])[1] == detail
        assert [tuple(row) for row in reopened_trace.db.execute("SELECT * FROM investigations ORDER BY id")] == before
    finally:
        reopened.close()
        reopened_trace.close()
