"""Persisted recorded-experiment acceptance; synthetic host history, no native."""
from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest

from eidos.api import EidosAPI
from eidos.codex import AppServerClient
from eidos.trace import TraceStore

spec = importlib.util.spec_from_file_location("recorded_experiment_demo", Path(__file__).parents[1] / "scripts/recorded_experiment_demo.py")
assert spec and spec.loader
demo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(demo)


@pytest.fixture
def persisted(tmp_path, monkeypatch):
    monkeypatch.setattr(AppServerClient, "start", lambda *_a, **_k: pytest.fail("recorded experiment acceptance attempted native startup"))
    path = tmp_path / "recorded-experiment.db"
    trace = TraceStore(path)
    api = EidosAPI(trace)
    marker = demo.seed(api)
    try:
        yield path, trace, api, marker
    finally:
        api.close()
        trace.close()


def canonical_source_state(trace):
    return {"owners": [tuple(row) for row in trace.db.execute("SELECT * FROM investigations ORDER BY id")],
            "trace": [tuple(row) for row in trace.db.execute("SELECT seq,raw_text FROM trace_records ORDER BY seq")],
            "pins": [tuple(row) for row in trace.db.execute("SELECT * FROM cm_requests ORDER BY name")],
            "authority": [tuple(row) for row in trace.db.execute("SELECT name,kind,domain_name FROM authority_occurrences ORDER BY name")]}


def snapshot_body(marker, request_id="acceptance/snapshot"):
    return {"requestId": request_id, "title": "Exact recorded experiment snapshot",
            "rendererVersion": demo.snapshots.RENDERER,
            "arrangement": demo.arrangement(marker["experiments"]["E1"]), "focus": None}


def exact_source(api, owner, artifact, context):
    return api.dispatch(demo.chain.Request(), "GET", f"/api/investigations/{owner}/artifacts/{artifact}/source",
                        {"contextId": [context]})


def test_reopen_preserves_historical_experiment_and_exact_original_support(persisted):
    path, trace, api, marker = persisted
    before = canonical_source_state(trace)
    observed = demo.inspect(api, marker)
    assert observed["sameArtifactDifferentFrozenReview"]
    e1 = demo.experiment(api, marker["owner"], marker["experiments"]["E1"]["id"])
    assert e1["baseline"] == {"investigationId": marker["owner"], "contextId": marker["contexts"]["C0"],
        "artifactId": marker["artifacts"]["A1"], "attemptId": marker["baselineAttemptId"]}
    assert e1["alternative"] == {"investigationId": marker["owner"], "contextId": marker["contexts"]["C1"]}
    status, source = exact_source(api, marker["owner"], marker["artifacts"]["A1"], marker["contexts"]["C0"])
    assert status == 200
    assert source["attempt"]["id"] == marker["baselineAttemptId"]
    assert source["attempt"]["manifestId"] == marker["baselineAttemptManifestId"]
    assert source["context"]["records"][0] == marker["originalRecord"]
    assert "unknownFixtureField" in source["context"]["records"][0]["rawText"]
    assert "artifactHistory" not in source and "contexts" not in source
    assert canonical_source_state(trace) == before
    api.close()
    reopened = EidosAPI(trace)
    try:
        assert demo.inspect(reopened, marker) == observed
        assert demo.experiment(reopened, marker["owner"], e1["id"]) == e1
    finally:
        reopened.close()


def test_review_refresh_is_separate_from_frozen_experiment_and_snapshot(persisted):
    _, trace, api, marker = persisted
    before = canonical_source_state(trace)
    original = marker["experiments"]["E1"]
    reviewed = demo.chain.call(api, f"/{marker['owner']}/experiments/{original['id']}/review", {
        "requestId": "acceptance/reject", "decision": "reject", "rationale": "Synthetic review: changed frozen input is not retention."})
    assert reviewed["status"] == "rejected" and reviewed["review"]["decision"] == "reject"
    assert demo.immutable_experiment(reviewed) == demo.immutable_experiment(original)
    assert demo.snapshots.call(api, "/" + marker["snapshot"]["id"], method="GET")["composition"] == marker["snapshot"]
    assert canonical_source_state(trace) == before
    api.close()
    reopened = EidosAPI(trace)
    try:
        assert demo.experiment(reopened, marker["owner"], original["id"]) == reviewed
        assert demo.inspect(reopened, marker)["currentReviews"]["E1"]["status"] == "rejected"
    finally:
        reopened.close()


def test_same_artifact_id_does_not_hide_changed_frozen_review(persisted):
    _, _, api, marker = persisted
    e1 = marker["experiments"]["E1"]
    left, right = marker["frozenContexts"][:2]
    before, after = left["artifactInputs"][0], right["artifactInputs"][0]
    assert before["artifact"] == after["artifact"]
    assert before["artifactId"] == after["artifactId"] == marker["sourceArtifact"]
    assert before["sourceAdoption"] is None and after["sourceAdoption"]["decision"] == "reject"
    assert e1["evaluation"]["changedArtifactIds"] == [marker["sourceArtifact"]]
    assert e1["evaluation"]["addedArtifactIds"] == e1["evaluation"]["removedArtifactIds"] == []
    assert e1["evaluation"]["checks"]["baselineEvidenceRetained"] is True
    assert e1["evaluation"]["checks"]["baselineArtifactsRetained"] is False
    assert e1["evaluation"]["passes"] is False
    assert e1["evaluation"]["modelCalls"] == 0 and not e1["evaluation"]["measuredModelReasoningImprovement"]


@pytest.mark.parametrize("change", ["latest_baseline", "new_alternative_artifact", "different_experiment"])
def test_new_snapshot_cannot_rebind_named_experiment_to_later_work(persisted, change):
    _, trace, api, marker = persisted
    body = snapshot_body(marker)
    changed = body["arrangement"]
    if change == "latest_baseline":
        changed["left"].update(contextId=marker["contexts"]["C2"], artifactId=marker["artifacts"]["A2"])
    elif change == "new_alternative_artifact":
        changed["right"]["artifactId"] = marker["artifacts"]["laterC1"]
    else:
        changed["experimentId"] = marker["experiments"]["E2"]["id"]
    before = trace.db.execute("SELECT count(*) FROM workbench_compositions").fetchone()[0]
    assert demo.snapshots.request(api, body=body)[0] == 409
    assert trace.db.execute("SELECT count(*) FROM workbench_compositions").fetchone()[0] == before


def test_explicit_lens_change_keeps_context_only_alternative(persisted):
    _, trace, api, marker = persisted
    before = canonical_source_state(trace)
    for lens in ("context", "result"):
        body = snapshot_body(marker, "acceptance/lens/" + lens)
        body["arrangement"]["lens"] = lens
        saved = demo.snapshots.call(api, body=body)["composition"]
        assert saved["arrangement"]["right"] == marker["experiments"]["E1"]["alternative"]
        assert "artifactId" not in saved["arrangement"]["right"]
    assert canonical_source_state(trace) == before


@pytest.mark.parametrize("owner,identifier", [("source", "E1"), ("owner", "missing"), ("missing", "E1")])
def test_owner_scoped_experiment_names_do_not_fall_back_to_latest(persisted, owner, identifier):
    _, _, api, marker = persisted
    selected_owner = "investigation_missing" if owner == "missing" else marker["sourceOwner"] if owner == "source" else marker["owner"]
    selected_id = "comparison_missing" if identifier == "missing" else marker["experiments"][identifier]["id"]
    status, _ = api.dispatch(demo.chain.Request(), "GET", f"/api/investigations/{selected_owner}/experiments/{selected_id}", {})
    assert status == 404


def test_missing_baseline_keeps_saved_descriptions_but_prevents_new_binding(persisted):
    _, trace, api, marker = persisted
    # Labelled malformed/partial trusted import; this is not a product mutation API.
    with api.investigations._transaction():
        work = api.investigations.get(marker["owner"])
        work["artifactHistory"] = [item for item in work["artifactHistory"] if item["id"] != marker["artifacts"]["A1"]]
        api.investigations._save(work)
    assert demo.snapshots.call(api, "/" + marker["snapshot"]["id"], method="GET")["composition"] == marker["snapshot"]
    assert exact_source(api, marker["owner"], marker["artifacts"]["A1"], marker["contexts"]["C0"])[0] == 404
    assert demo.snapshots.request(api, body=snapshot_body(marker))[0] == 409


def test_imported_baseline_attempt_disagreement_cannot_be_saved_as_exact_experiment(persisted):
    _, trace, api, marker = persisted
    # Adversarial trusted import: same descriptive artifact ID, altered attempt.
    # Neither that name nor the frozen experiment makes this source relation true.
    with api.investigations._transaction():
        work = api.investigations.get(marker["owner"])
        next(item for item in work["artifactHistory"] if item["id"] == marker["artifacts"]["A1"])["attemptId"] = work["attempt"]["id"]
        api.investigations._save(work)
    assert exact_source(api, marker["owner"], marker["artifacts"]["A1"], marker["contexts"]["C0"])[0] == 409
    count = trace.db.execute("SELECT count(*) FROM workbench_compositions").fetchone()[0]
    assert demo.snapshots.request(api, body=snapshot_body(marker))[0] == 409
    assert trace.db.execute("SELECT count(*) FROM workbench_compositions").fetchone()[0] == count


def test_named_experiment_rejects_another_valid_attempt_in_same_context(persisted):
    _, trace, api, marker = persisted
    # A valid additional synthetic attempt exists at C0. A malformed trusted
    # import then rewires old A1 to it while retaining A1's descriptive ID.
    another = demo.import_authored_result(api, marker["owner"], marker["contexts"]["C0"],
        f"Synthetic alternate C0 attempt [evidence:{marker['originalRecord']['seq']}]")
    with api.investigations._transaction():
        work = api.investigations.get(marker["owner"])
        next(item for item in work["artifactHistory"] if item["id"] == marker["artifacts"]["A1"])["attemptId"] = another["attempt"]["id"]
        api.investigations._save(work)
    assert exact_source(api, marker["owner"], marker["artifacts"]["A1"], marker["contexts"]["C0"])[0] == 200
    generic = snapshot_body(marker, "acceptance/generic-same-context-attempt")
    generic["arrangement"].pop("experimentId")
    generic["arrangement"].pop("intent")
    assert demo.snapshots.request(api, body=generic)[0] == 201
    count = trace.db.execute("SELECT count(*) FROM workbench_compositions").fetchone()[0]
    assert demo.snapshots.request(api, body=snapshot_body(marker))[0] == 409
    assert trace.db.execute("SELECT count(*) FROM workbench_compositions").fetchone()[0] == count
    assert demo.snapshots.call(api, "/" + marker["snapshot"]["id"], method="GET")["composition"] == marker["snapshot"]


def test_real_http_exact_experiment_and_source_do_not_dispatch_or_mutate(persisted):
    path, trace, api, marker = persisted
    before = canonical_source_state(trace)
    with demo.snapshots.scale.http_server(path) as (origin, _controller):
        e1 = demo.snapshots.scale.http(origin, f"/{marker['owner']}/experiments/{marker['experiments']['E1']['id']}")
        source = demo.snapshots.scale.http(origin, f"/{marker['owner']}/artifacts/{marker['artifacts']['A1']}/source",
                                             {"contextId": marker["contexts"]["C0"]})
        foreign = demo.snapshots.scale.http(origin, f"/{marker['sourceOwner']}/experiments/{marker['experiments']['E1']['id']}")
    assert e1["status"] == source["status"] == 200 and foreign["status"] == 404
    assert e1["body"] == marker["experiments"]["E1"]
    assert len(json.dumps(e1["body"])) < 6000 and "projectedPrompt" not in e1["body"]
    assert source["body"]["context"]["records"][0] == marker["originalRecord"]
    assert source["body"]["attempt"]["id"] == marker["baselineAttemptId"]
    assert canonical_source_state(trace) == before
