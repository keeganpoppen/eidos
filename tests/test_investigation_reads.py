"""Replaceable read-index contracts; fixtures never dispatch native work."""
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest

from eidos.api import EidosAPI
from eidos.investigation import InvestigationError, InvestigationStore
from eidos.investigation_reads import InvestigationReads
from eidos.trace import TraceStore
from test_artifact_context_compatibility import legacy_body, result, using


def get(api, path, **query):
    return api.dispatch(None, "GET", "/api/investigations" + path,
                        {key: [str(value)] for key, value in query.items()})


@pytest.fixture
def setup(tmp_path):
    trace = TraceStore(tmp_path / "reads.db")
    store = InvestigationStore(trace)
    work = result(store, store.create(legacy_body(trace)))
    derived = result(store, store.create(using(work)))
    # Index initialization after source rows already exist exercises migration.
    api = EidosAPI(trace)
    try:
        yield trace, api, work, derived
    finally:
        api.close()
        trace.close()


def test_legacy_reads_stay_exact_and_new_catalogs_exclude_source_payloads(setup):
    trace, api, work, derived = setup
    canonical = [tuple(row) for row in trace.db.execute("SELECT * FROM investigations ORDER BY id")]
    assert get(api, "/" + work["id"])[1] == api.investigations.get(work["id"])
    assert get(api, "")[1] == {"investigations": api.investigations.list()}
    for path, key in (("/catalog", "investigations"), ("/artifacts", "artifacts")):
        status, body = get(api, path, limit=1)
        assert status == 200 and len(body[key]) == 1 and body["nextCursor"]
        assert "projectedPrompt" not in json.dumps(body) and "records" not in json.dumps(body)
        assert "Retain uncertain delivery." not in json.dumps(body)
        assert get(api, path, limit=1, knownVersion=body["version"])[1] == {
            "unchanged": True, "version": body["version"]}
    assert [tuple(row) for row in trace.db.execute("SELECT * FROM investigations ORDER BY id")] == canonical


def test_hot_catalog_and_unchanged_view_parse_only_small_metadata(setup, monkeypatch):
    _, api, work, _ = setup
    api.investigation_reads.catalog({})
    first = api.investigation_reads.view(work["id"], {})
    load = json.loads
    parsed = []
    def small_only(value, *args, **kwargs):
        parsed.append(len(value))
        assert len(value) < 1500, "hot read parsed canonical source history"
        return load(value, *args, **kwargs)
    monkeypatch.setattr("eidos.investigation_reads.json.loads", small_only)
    for _ in range(3):
        api.investigation_reads.catalog({})
        api.investigation_reads.catalog({}, artifacts=True)
        assert api.investigation_reads.view(work["id"], {"knownVersion": [first["version"]]}) == {
            "version": first["version"], "unchanged": True}
    assert parsed


def test_independent_writer_invalidates_catalog_and_conditional_view(setup, tmp_path):
    trace, api, work, _ = setup
    before = api.investigation_reads.view(work["id"], {})
    catalog = api.investigation_reads.catalog({})
    writer = TraceStore(tmp_path / "reads.db")
    other = InvestigationStore(writer)
    try:
        current = other.adopt(work["id"], {"artifactId": work["artifact"]["id"], "decision": "reject", "note": "Later review"})
    finally:
        writer.close()
    observed = api.investigation_reads.view(work["id"], {"knownVersion": [before["version"]]})
    assert not observed["unchanged"] and observed["investigation"] == current
    assert observed["version"] != before["version"]
    assert api.investigation_reads.catalog({"knownVersion": [catalog["version"]]})["unchanged"] is False
    assert get(api, f"/{work['id']}/artifacts/{work['artifact']['id']}/source")[1]["adoption"] == current["adoption"]


def test_identical_recovery_write_keeps_warm_projection_after_controller_reopen(setup, tmp_path, monkeypatch):
    trace, api, work, _ = setup
    catalog = api.investigation_reads.catalog({})
    view = api.investigation_reads.view(work["id"], {})
    # Startup recovery may persist an unchanged terminal state. Such writes
    # must not force every saved owner through projection again after restart.
    trace.db.execute("UPDATE investigations SET state_json=state_json")
    reopened_trace = TraceStore(tmp_path / "reads.db")
    reopened = EidosAPI(reopened_trace)
    try:
        assert reopened_trace.db.execute("SELECT COUNT(*) FROM investigation_read_dirty").fetchone()[0] == 0
        monkeypatch.setattr(reopened.investigations, "_load", lambda *_: pytest.fail("unchanged view loaded source"))
        assert reopened.investigation_reads.catalog({}) == catalog
        assert reopened.investigation_reads.view(work["id"], {"knownVersion": [view["version"]]})["unchanged"]
    finally:
        reopened.close()
        reopened_trace.close()


def test_keyset_pages_survive_new_owner_and_casefold_search_is_literal(setup, monkeypatch):
    _, api, work, _ = setup
    store = api.investigations
    monkeypatch.setattr("eidos.investigation.time.time", lambda: 2000)
    for index in range(5):
        store.create({**using(work, f"page-{index}"), "title": f"Straße %_{index}"})
    first = api.investigation_reads.catalog({"limit": ["2"], "q": ["STRASSE %_"]})
    first_ids = [item["id"] for item in first["investigations"]]
    monkeypatch.setattr("eidos.investigation.time.time", lambda: 2001)
    store.create({**using(work, "append"), "title": "Straße %_new"})
    found = list(first_ids)
    page = first
    while page["nextCursor"]:
        page = api.investigation_reads.catalog({"limit": ["2"], "q": ["STRASSE %_"], "cursor": [page["nextCursor"]]})
        found.extend(item["id"] for item in page["investigations"])
    assert len(found) == len(set(found)) == 5
    for args, artifact in (({"q": ["different"]}, False), ({"q": ["STRASSE %_"]}, True)):
        with pytest.raises(InvestigationError, match="cursor"):
            api.investigation_reads.catalog({**args, "cursor": [first["nextCursor"]]}, artifacts=artifact)


@pytest.mark.parametrize("query", [
    {"limit": ["0"]}, {"limit": ["41"]}, {"limit": ["x"]}, {"q": ["x" * 201]},
    {"limit": ["1", "2"]}, {"cursor": ["not-a-cursor"]}, {"authority": ["copied"]},
])
def test_read_parameters_fail_closed_without_changing_canonical_state(setup, query):
    trace, api, _, _ = setup
    before = [tuple(row) for row in trace.db.execute("SELECT * FROM investigations ORDER BY id")]
    assert api.dispatch(None, "GET", "/api/investigations/catalog", query)[0] == 400
    assert [tuple(row) for row in trace.db.execute("SELECT * FROM investigations ORDER BY id")] == before


def test_source_reads_one_exact_context_and_rejects_owner_and_context_mismatch(setup):
    _, api, work, derived = setup
    artifact = work["artifact"]
    status, source = get(api, f"/{work['id']}/artifacts/{artifact['id']}/source", contextId=artifact["contextId"])
    assert status == 200
    assert source["artifact"] == artifact
    assert source["context"] == work["contexts"][0]
    assert source["attempt"] == work["attempt"]
    assert "contexts" not in source and "artifactHistory" not in source
    assert get(api, f"/{derived['id']}/artifacts/{artifact['id']}/source")[0] == 404
    assert get(api, f"/{work['id']}/artifacts/{artifact['id']}/source", contextId="wrong")[0] == 409


def test_rebuild_is_replaceable_and_preserves_version_and_source_bytes(setup):
    trace, api, work, _ = setup
    reads = api.investigation_reads
    catalog = reads.catalog({})
    artifacts = reads.catalog({}, artifacts=True)
    view = reads.view(work["id"], {})
    before = [tuple(row) for row in trace.db.execute("SELECT * FROM investigations ORDER BY id")]
    reads.rebuild()
    assert reads.catalog({}) == catalog
    assert reads.catalog({}, artifacts=True) == artifacts
    assert reads.view(work["id"], {}) == view
    assert [tuple(row) for row in trace.db.execute("SELECT * FROM investigations ORDER BY id")] == before


def test_view_version_and_data_share_snapshot_while_another_writer_waits(setup, tmp_path, monkeypatch):
    _, api, work, _ = setup
    before = api.investigation_reads.view(work["id"], {})
    writer = TraceStore(tmp_path / "reads.db")
    other = InvestigationStore(writer)
    begin, attempted, finished = Event(), Event(), Event()
    writer.db.set_trace_callback(lambda statement: attempted.set() if statement == "BEGIN IMMEDIATE" else None)
    original = api.investigations._load
    def interleaved_load(identifier):
        begin.set()
        assert attempted.wait(3)
        assert not finished.wait(0.04), "writer changed source between version and detail"
        return original(identifier)
    def mutate():
        assert begin.wait(3)
        updated = other.adopt(work["id"], {"artifactId": work["artifact"]["id"], "decision": "reject", "note": "Concurrent review"})
        finished.set()
        return updated
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(mutate)
            with monkeypatch.context() as patch:
                patch.setattr(api.investigations, "_load", interleaved_load)
                observed = api.investigation_reads.view(work["id"], {})
            updated = pending.result(timeout=3)
        assert observed == before
        after = api.investigation_reads.view(work["id"], {"knownVersion": [before["version"]]})
        assert not after["unchanged"] and after["investigation"] == updated
        assert after["version"] != before["version"]
    finally:
        writer.close()
