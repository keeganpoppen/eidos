"""Literal public-result discovery must retain exact historical identities."""
import importlib.util
import json
from pathlib import Path

import pytest

from eidos.api import EidosAPI
from eidos.investigation import InvestigationError
from eidos.investigation_reads import InvestigationReads
from eidos.trace import TraceStore

spec = importlib.util.spec_from_file_location("result_discovery_fixture", Path(__file__).resolve().parents[1] / "scripts/result_discovery_demo.py")
assert spec and spec.loader
demo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(demo)


@pytest.fixture
def history(tmp_path):
    trace = TraceStore(tmp_path / "discovery.db")
    api = EidosAPI(trace)
    marker = demo.seed(api)
    try:
        yield trace, api, marker
    finally:
        api.close()
        trace.close()


def search(api, term, **params):
    return api.investigation_reads.catalog({"q": [term], **{k: [str(v)] for k, v in params.items()}}, artifacts=True)


def canonical(trace):
    return [tuple(row) for row in trace.db.execute("SELECT * FROM investigations ORDER BY id")]


def test_historical_question_and_result_resolve_exact_old_context_before_reuse(history):
    trace, api, marker = history
    before = canonical(trace)
    hits = search(api, marker["questionQuery"])["artifacts"]
    old = next(hit for hit in hits if hit["investigationId"] == marker["owner"])
    assert (old["artifactId"], old["contextId"], old["attemptId"]) == tuple(marker[key] for key in ("artifactId", "contextId", "attemptId"))
    assert old["match"] == {"field": "question", "excerpt": marker["question"]}
    assert {hit["artifactId"] for hit in hits} == {marker["artifactId"], marker["decoyArtifactId"]}
    assert next(hit for hit in hits if hit["artifactId"] == marker["decoyArtifactId"])["match"]["field"] == "title"
    result_hit = search(api, marker["resultQuery"])["artifacts"]
    assert len(result_hit) == 1 and result_hit[0]["artifactId"] == marker["artifactId"]
    assert result_hit[0]["match"] == {"field": "result", "excerpt": marker["text"]}
    source = api.investigation_reads.source(marker["owner"], marker["artifactId"], {"contextId": [old["contextId"]]})
    assert source["context"]["question"] == marker["question"]
    assert marker["support"] in source["context"]["records"][0]["rawText"]
    assert canonical(trace) == before
    new = api.investigations.create({"requestId": "reuse-discovered", "title": "Next question", "question": "What should be retained?",
        "selections": [], "artifactInputs": [{"investigationId": old["investigationId"], "artifactId": old["artifactId"], "rationale": "Inspected original support"}]})
    frozen = new["contexts"][0]["artifactInputs"][0]
    assert frozen["sourceContextId"] == marker["contextId"]
    assert frozen["artifact"] == source["artifact"]
    assert not [row for row in trace.records() if row.method == "turn/start"]


def test_search_excludes_source_records_prompts_inputs_unknown_fields_and_private_store(history):
    trace, api, marker = history
    work = api.investigations.get(marker["owner"])
    with api.investigations._transaction():
        work["contexts"][0]["projectedPrompt"] += " PROMPT_ONLY_CANARY"
        work["contexts"][0]["artifactInputs"] = [{"ignoredFixture": "INPUT_ONLY_CANARY"}]
        work["artifactHistory"][0]["futureField"] = "UNKNOWN_ONLY_CANARY"
        api.investigations._save(work)
    private = TraceStore(Path(trace.path).with_name("private-canary.db"), role="private-control")
    private.append(source="private", direction="internal", message={"method": "$fixture/private", "secret": "PRIVATE_ONLY_CANARY"})
    private.close()
    for term in [marker["excludedCanary"], marker["support"], "PROMPT_ONLY_CANARY", "INPUT_ONLY_CANARY", "UNKNOWN_ONLY_CANARY", "PRIVATE_ONLY_CANARY"]:
        assert search(api, term)["artifacts"] == []


def test_missing_historical_context_does_not_borrow_latest_question(history):
    _, api, marker = history
    search(api, marker["questionQuery"])
    with api.investigations._transaction():
        work = api.investigations.get(marker["owner"])
        work["contexts"] = [ctx for ctx in work["contexts"] if ctx["id"] != marker["contextId"]]
        api.investigations._save(work)
    assert [hit for hit in search(api, marker["questionQuery"])["artifacts"] if hit["investigationId"] == marker["owner"]] == []
    assert search(api, marker["resultQuery"])["artifacts"][0]["artifactId"] == marker["artifactId"]
    with pytest.raises(InvestigationError, match="context|provenance|missing"):
        api.investigation_reads.source(marker["owner"], marker["artifactId"], {"contextId": [marker["contextId"]]})


@pytest.mark.parametrize("text,query", [
    ("x " * 2000 + "Straße %_ <script>retained</script>" + " y" * 2000, "STRASSE %_"),
    ("ß" * 500 + "remember this tail", "remember this tail"),
    ("İ" * 500 + "Nema", "NEMA"),
])
def test_excerpt_bound_and_unicode_casefold_offsets(text, query):
    excerpt = InvestigationReads._excerpt(text, query.casefold())
    assert len(excerpt) <= 240
    assert query.casefold() in excerpt.casefold()
    assert excerpt.startswith("…")


def test_expanded_match_larger_than_excerpt_is_honestly_truncated():
    value = "prefix " + "s" * 400 + " suffix"
    excerpt = InvestigationReads._excerpt(value, ("ß" * 200).casefold())
    assert len(excerpt) <= 240 and excerpt.endswith("…")


def test_migrate_old_warm_projection_then_reopen_and_rebuild_without_canonical_change(history, monkeypatch):
    trace, api, marker = history
    api.investigation_reads.catalog({})
    before = canonical(trace)
    trace.db.execute("DROP TABLE investigation_read_result_search")
    trace.db.execute("DROP TRIGGER investigation_read_result_search_delete")
    assert trace.db.execute("SELECT count(*) FROM investigation_read_dirty").fetchone()[0] == 0
    reads = InvestigationReads(api.investigations)
    assert trace.db.execute("SELECT count(*) FROM investigation_read_dirty").fetchone()[0] > 0
    page = reads.catalog({"q": [marker["resultQuery"]]}, artifacts=True)
    assert page["artifacts"][0]["artifactId"] == marker["artifactId"]
    assert canonical(trace) == before
    reads.rebuild()
    assert reads.catalog({"q": [marker["resultQuery"]]}, artifacts=True) == page
    reopened = InvestigationReads(api.investigations)
    assert trace.db.execute("SELECT count(*) FROM investigation_read_dirty").fetchone()[0] == 0
    loads = json.loads
    def metadata_only(value, *args, **kwargs):
        assert len(value) < 1500, "hot search decoded canonical history"
        return loads(value, *args, **kwargs)
    monkeypatch.setattr("eidos.investigation_reads.json.loads", metadata_only)
    assert reopened.catalog({"q": [marker["resultQuery"]], "knownVersion": [page["version"]]}, artifacts=True) == {"version": page["version"], "unchanged": True}


def test_search_cursor_is_query_bound_and_does_not_reuse_old_title_only_membership(history):
    _, api, marker = history
    first = search(api, marker["questionQuery"], limit=1)
    second = search(api, marker["questionQuery"], limit=1, cursor=first["nextCursor"])
    assert len(first["artifacts"]) == len(second["artifacts"]) == 1
    assert first["artifacts"][0]["artifactId"] != second["artifacts"][0]["artifactId"]
    old = api.investigation_reads._cursor("artifacts", marker["questionQuery"], [0, "owner", "artifact"])
    with pytest.raises(InvestigationError, match="cursor"):
        search(api, marker["questionQuery"], cursor=old)
    with pytest.raises(InvestigationError, match="cursor"):
        search(api, marker["resultQuery"], cursor=first["nextCursor"])
    assert all("match" not in hit for hit in search(api, "")["artifacts"])
    assert api.investigation_reads.catalog({"q": [marker["resultQuery"]]})["investigations"] == []


def test_independent_writer_new_result_and_actual_reopen_update_only_matching_pages(history):
    trace, api, marker = history
    before = search(api, marker["resultQuery"])
    writer_trace = TraceStore(trace.path)
    writer = EidosAPI(writer_trace)
    try:
        new = demo.recorded.import_authored_result(writer, marker["owner"], marker["currentContextId"],
            "Newly reviewed stopped claim: inspect both results. [evidence:1]")
    finally:
        writer.close()
        writer_trace.close()
    after = search(api, marker["resultQuery"], knownVersion=before["version"])
    assert not after["unchanged"] and after["version"] != before["version"]
    assert {hit["artifactId"] for hit in after["artifacts"]} == {marker["artifactId"], new["artifact"]["id"]}
    assert [hit["artifactId"] for hit in search(api, marker["questionQuery"])["artifacts"] if hit["investigationId"] == marker["owner"]] == [marker["artifactId"]]
    reopened_trace = TraceStore(trace.path)
    reopened = EidosAPI(reopened_trace)
    try:
        assert reopened_trace.db.execute("SELECT count(*) FROM investigation_read_dirty").fetchone()[0] == 0
        assert search(reopened, marker["resultQuery"]) == after
        source = reopened.investigation_reads.source(marker["owner"], marker["artifactId"], {"contextId": [marker["contextId"]]})
        assert source["context"]["question"] == marker["question"]
    finally:
        reopened.close()
        reopened_trace.close()


def test_literal_unicode_result_match_has_bounded_plain_excerpt_and_deletion_clears_projection(history):
    trace, api, marker = history
    exact = "Straße %_ <script>literal fixture text</script>"
    work = demo.recorded.import_authored_result(api, marker["owner"], marker["currentContextId"], "ß " * 1000 + exact + " tail" * 1000)
    before = canonical(trace)
    hit = search(api, "STRASSE %_")["artifacts"]
    assert len(hit) == 1 and hit[0]["artifactId"] == work["artifact"]["id"]
    assert hit[0]["match"]["field"] == "result" and exact in hit[0]["match"]["excerpt"]
    assert len(hit[0]["match"]["excerpt"]) <= 240
    assert len(search(api, "%_")["artifacts"]) == 1
    assert canonical(trace) == before
    with api.investigations._transaction():
        trace.db.execute("DELETE FROM investigation_requests WHERE investigation_id=?", (marker["owner"],))
        trace.db.execute("DELETE FROM investigations WHERE id=?", (marker["owner"],))
    assert search(api, "STRASSE %_")["artifacts"] == []
    assert trace.db.execute("SELECT count(*) FROM investigation_read_result_search WHERE investigation_id=?", (marker["owner"],)).fetchone()[0] == 0
