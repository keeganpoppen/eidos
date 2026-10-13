"""Saved-question preview fixtures use real persisted APIs, never native calls."""
import importlib.util
from pathlib import Path

import pytest

from eidos.api import EidosAPI
from eidos.codex import AppServerClient
from eidos.trace import TraceStore

spec = importlib.util.spec_from_file_location("saved_recovery_demo", Path(__file__).parents[1] / "scripts/saved_question_recovery_demo.py")
assert spec and spec.loader
demo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(demo)


@pytest.fixture
def saved(tmp_path, monkeypatch):
    monkeypatch.setattr(AppServerClient, "start", lambda *_a, **_k: pytest.fail("preview acceptance attempted native startup"))
    path = tmp_path / "saved-recovery.db"
    trace = TraceStore(path)
    api = EidosAPI(trace)
    marker = demo.seed(api)
    try:
        yield path, trace, api, marker
    finally:
        api.close(); trace.close()


def get(api, path, query=None):
    return api.dispatch(demo.recorded.chain.Request(), "GET", path, query or {})


def test_similar_named_snapshot_catalog_requires_exact_preview_to_distinguish_inputs(saved):
    _, _, api, marker = saved
    status, page = get(api, "/api/compositions", {"limit": ["20"], "q": [marker["search"]]})
    assert status == 200
    assert {row["id"] for row in page["compositions"]} == {row["id"] for row in marker["recoverySnapshots"].values()}
    assert all(row["title"].startswith("Unknown reply · retry review") for row in page["compositions"])
    assert all("arrangement" not in row and "focus" not in row for row in page["compositions"])
    target, broader, current = (marker["recoverySnapshots"][key] for key in ("target", "broader", "current"))
    assert target["arrangement"]["left"]["artifactId"] == marker["artifacts"]["A1"]
    assert target["arrangement"]["right"]["contextId"] == marker["contexts"]["C1"]
    assert "artifactId" not in target["arrangement"]["right"]
    assert broader["arrangement"]["right"]["contextId"] == marker["contexts"]["C2"]
    assert current["arrangement"]["left"]["artifactId"] == marker["artifacts"]["A2"]


def test_saved_reason_and_raw_support_are_available_separately_from_current_review(saved):
    _, trace, api, marker = saved
    before = [(row.seq, row.raw_text) for row in trace.records()]
    status, source = get(api, f"/api/investigations/{marker['owner']}/artifacts/{marker['artifacts']['A1']}/source",
                         {"contextId": [marker["contexts"]["C0"]]})
    assert status == 200
    assert source["attempt"]["id"] == marker["baselineAttemptId"]
    assert source["context"]["question"] == demo.recorded.QUESTION
    assert source["context"]["records"][0] == marker["originalRecord"]
    current = demo.recorded.experiment(api, marker["owner"], marker["recoveryExperiment"]["id"])
    assert current["rationale"] == marker["expectedRationale"]
    assert current["review"]["rationale"] == marker["expectedCurrentReview"]
    assert current["review"]["decision"] == "reject"
    assert demo.recorded.immutable_experiment(current) == demo.recorded.immutable_experiment(marker["recoveryExperiment"])
    selected = marker["recoverySnapshots"]["target"]["focus"]
    assert selected["contextId"] == marker["contexts"]["C1"] and "artifactId" not in selected
    assert selected["seq"] == marker["rejectionRecord"]["seq"]
    assert "Rejected: an automatic retry" in marker["rejectionRecord"]["rawText"]
    assert [(row.seq, row.raw_text) for row in trace.records()] == before


def test_missing_source_retains_saved_description_without_current_fallback(saved):
    _, _, api, marker = saved
    snapshot = marker["recoverySnapshots"]["missing"]
    status, value = get(api, "/api/compositions/" + snapshot["id"])
    assert status == 200 and value["composition"] == snapshot
    left = snapshot["arrangement"]["left"]
    assert get(api, f"/api/investigations/{left['investigationId']}/view")[0] == 404
    assert get(api, f"/api/investigations/{left['investigationId']}/artifacts/{left['artifactId']}/source",
               {"contextId": [left["contextId"]]})[0] == 404
    assert left["investigationId"] != marker["owner"]


def test_unknown_renderer_preserves_exact_record_and_result_pins(saved):
    _, _, api, marker = saved
    old = marker["recoverySnapshots"]["oldRenderer"]
    assert old["focus"] == marker["snapshot"]["focus"]
    assert old["rendererVersion"] != demo.recorded.snapshots.RENDERER
    assert old["arrangement"] == marker["recoverySnapshots"]["target"]["arrangement"]
    assert get(api, "/api/compositions/" + old["id"])[1]["composition"] == old


def test_reopen_preserves_all_snapshot_pins_and_separate_review(saved):
    path, trace, api, marker = saved
    observed = demo.inspect(api, marker)
    api.close(); trace.close()
    assert demo.resume(path) == marker
    reopened = TraceStore(path)
    app = EidosAPI(reopened)
    try:
        assert demo.inspect(app, marker) == observed
        assert not any(record.method == "turn/start" for record in reopened.records())
    finally:
        app.close(); reopened.close()
