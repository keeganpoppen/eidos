"""Independent immutable-composition acceptance; persisted synthetic sources only."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import copy
import importlib.util
import json
from pathlib import Path
from threading import Barrier

import pytest

from eidos.api import EidosAPI
from eidos.codex import AppServerClient
from eidos.trace import TraceStore

spec = importlib.util.spec_from_file_location("composition_snapshot_demo", Path(__file__).parents[1] / "scripts/composition_snapshot_demo.py")
assert spec and spec.loader
demo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(demo)


@pytest.fixture
def sources(tmp_path, monkeypatch):
    monkeypatch.setattr(AppServerClient, "start", lambda *_a, **_k: pytest.fail("snapshot acceptance attempted native startup"))
    path = tmp_path / "snapshots.db"
    trace = TraceStore(path)
    api = EidosAPI(trace)
    marker = demo.seed_sources(api)
    try:
        yield path, trace, api, marker
    finally:
        api.close()
        trace.close()


def stored(api, body):
    status, value = demo.request(api, body=body)
    assert status == 201, value
    return value["composition"]


def catalog(api, **query):
    return demo.call(api, method="GET", query={key: [str(value)] for key, value in query.items()})


def source_state(trace):
    return {"investigations": [tuple(row) for row in trace.db.execute("SELECT * FROM investigations ORDER BY id")],
        "pins": [tuple(row) for row in trace.db.execute("SELECT * FROM cm_requests ORDER BY name")],
        "authority": [tuple(row) for row in trace.db.execute("SELECT name,kind,domain_name FROM authority_occurrences ORDER BY name")],
        "trace": [tuple(row) for row in trace.db.execute("SELECT seq,raw_text FROM trace_records ORDER BY seq")]}


def test_save_reopen_read_copy_changes_only_snapshot_storage(sources):
    path, trace, api, marker = sources
    before = source_state(trace)
    body = demo.body(marker)
    saved = stored(api, body)
    assert set(saved) == {"schemaVersion", "id", "contentId", "title", "createdAtMs", "rendererVersion", "arrangement", "focus", "copiedFrom"}
    assert saved["schemaVersion"] == 1 and saved["copiedFrom"] is None
    assert saved["arrangement"] == body["arrangement"] and saved["focus"] == body["focus"]
    assert not any(token in json.dumps(saved) for token in ("rawText", "projectedPrompt", "capability", "checkpoint", "pendingRequest"))
    reopened_trace = TraceStore(path)
    reopened = EidosAPI(reopened_trace)
    try:
        assert demo.call(reopened, f"/{saved['id']}", method="GET")["composition"] == saved
        changed = {**body, "requestId": "snapshot-copy", "title": "Alternative placement",
                   "arrangement": {**body["arrangement"], "layout": "stacked"}, "copiedFrom": saved["id"]}
        copied = stored(reopened, changed)
        assert copied["id"] != saved["id"] and copied["copiedFrom"] == saved["id"]
        assert copied["contentId"] != saved["contentId"]
        assert demo.call(reopened, f"/{saved['id']}", method="GET")["composition"] == saved
        assert source_state(reopened_trace) == before
    finally:
        reopened.close()
        reopened_trace.close()


def test_lost_reply_replay_survives_missing_source_but_new_save_does_not(sources, monkeypatch):
    path, trace, api, marker = sources
    body = demo.body(marker)
    saved = stored(api, body)
    # Simulate an incomplete later source restore. There is deliberately no
    # product delete API; snapshot reading must not require live source presence.
    trace.db.execute("PRAGMA foreign_keys=OFF")
    trace.db.execute("DELETE FROM investigations WHERE id=?", (marker["investigations"]["A"],))
    trace.db.execute("PRAGMA foreign_keys=ON")
    assert stored(api, body) == saved
    assert demo.call(api, f"/{saved['id']}", method="GET")["composition"] == saved
    assert demo.request(api, body={**body, "requestId": "new-unresolved"})[0] in {404, 409}
    assert demo.request(api, body={**body, "requestId": "repair-still-unresolved", "copiedFrom": saved["id"]})[0] in {404, 409}
    assert demo.request(api, body={**body, "title": "Changed content under old request"})[0] == 409
    other_trace = TraceStore(path)
    other = EidosAPI(other_trace)
    try:
        assert stored(other, body) == saved
        assert demo.call(other, f"/{saved['id']}", method="GET")["composition"] == saved
    finally:
        other.close()
        other_trace.close()


def test_two_independent_connections_admit_one_snapshot_for_same_request(sources):
    path, trace, api, marker = sources
    second_trace = TraceStore(path)
    second = EidosAPI(second_trace)
    before = source_state(trace)
    barrier = Barrier(2)
    body = demo.body(marker)
    def create(controller):
        barrier.wait(timeout=5)
        return stored(controller, copy.deepcopy(body))
    try:
        with ThreadPoolExecutor(max_workers=2) as workers:
            values = list(workers.map(create, [api, second]))
        assert values[0] == values[1]
        assert len(catalog(api)["compositions"]) == 1
        assert source_state(trace) == before
    finally:
        second.close()
        second_trace.close()


def test_pending_inquiry_snapshot_does_not_acquire_later_response_or_receipt(sources):
    _, trace, api, marker = sources
    body = {**demo.body(marker), "arrangement": marker["pendingArrangement"], "focus": None}
    pending = stored(api, body)
    advanced = demo.advance_inquiry(api, marker)
    assert advanced["artifact"]["kind"] == "eidos-evidence-review"
    assert advanced["continuation"]["inquiry"]["responses"]
    assert demo.call(api, f"/{pending['id']}", method="GET")["composition"] == pending
    assert stored(api, body) == pending
    assert "responseId" not in pending["arrangement"]["inquiry"]
    assert "artifactId" not in pending["arrangement"]["right"]
    # An explicit copy may bind the now available exact terminal response.
    response = advanced["continuation"]["inquiry"]["responses"][-1]
    arrangement = copy.deepcopy(pending["arrangement"])
    arrangement["right"] = {"investigationId": advanced["id"], "contextId": advanced["artifact"]["contextId"], "artifactId": advanced["artifact"]["id"]}
    arrangement["inquiry"].update(responseId=response["id"], evidenceContextId=response["evidenceContext"]["id"])
    copied = stored(api, {**body, "requestId": "terminal-copy", "copiedFrom": pending["id"], "arrangement": arrangement})
    assert copied["arrangement"]["right"]["artifactId"] == advanced["artifact"]["id"]
    assert not [record for record in trace.records() if record.method == "turn/start"]


@pytest.mark.parametrize("field", ["inquiryId", "responseId", "decisionOccurrenceId", "attemptId"])
def test_imported_receipt_cannot_claim_another_response_or_origin_attempt(sources, field):
    _, trace, api, marker = sources
    advanced = demo.advance_inquiry(api, marker)
    response = advanced["continuation"]["inquiry"]["responses"][-1]
    arrangement = copy.deepcopy(marker["pendingArrangement"])
    arrangement["right"] = {"investigationId": advanced["id"], "contextId": advanced["artifact"]["contextId"], "artifactId": advanced["artifact"]["id"]}
    arrangement["inquiry"].update(responseId=response["id"], evidenceContextId=response["evidenceContext"]["id"])
    # Explicit malformed trusted-import fixture, not a public mutation route.
    # Canonical membership alone must not certify a contradictory receipt link.
    imported = copy.deepcopy(advanced)
    imported["artifact"][field] = "foreign_" + field
    trace.db.execute("UPDATE investigations SET state_json=? WHERE id=?", (json.dumps(imported, sort_keys=True, separators=(",", ":")), imported["id"]))
    count = trace.db.execute("SELECT COUNT(*) FROM cm_objects").fetchone()[0]
    assert demo.request(api, body={**demo.body(marker), "arrangement": arrangement, "focus": None})[0] == 409
    assert catalog(api)["compositions"] == []
    assert trace.db.execute("SELECT COUNT(*) FROM cm_objects").fetchone()[0] == count


def test_offered_context_requires_its_exact_owner_response_and_inquiry(sources):
    _, _, api, marker = sources
    advanced = demo.advance_inquiry(api, marker)
    response = advanced["continuation"]["inquiry"]["responses"][-1]
    context = response["evidenceContext"]
    arrangement = {**copy.deepcopy(marker["pendingArrangement"]), "intent": "evidence-chain"}
    arrangement["inquiry"].update(responseId=response["id"], evidenceContextId=context["id"])
    body = {**demo.body(marker), "arrangement": arrangement,
        "focus": {"investigationId": advanced["id"], "contextId": context["id"],
                  "seq": marker["controllingSeq"], "threadId": "fixture-artifact-origin"}}
    stored(api, body)
    invalid = []
    for field in ("inquiryId", "continuationId", "responseId", "evidenceContextId"):
        changed = copy.deepcopy(body)
        changed["arrangement"]["inquiry"][field] = "foreign_" + field
        invalid.append(changed)
    no_response = copy.deepcopy(body)
    del no_response["arrangement"]["inquiry"]["responseId"]
    invalid.append(no_response)
    # A generic context comparison can focus an offered packet when the server
    # resolves it through that owner's actual offer response.
    generic = copy.deepcopy(body)
    generic["requestId"] = "generic-offered-focus"
    generic["arrangement"] = demo.body(marker)["arrangement"]
    stored(api, generic)
    foreign_owner = copy.deepcopy(body)
    foreign_owner["focus"]["investigationId"] = marker["investigations"]["A"]
    invalid.append(foreign_owner)
    for index, changed in enumerate(invalid):
        changed["requestId"] = f"invalid-offered-{index}"
        assert demo.request(api, body=changed)[0] in {400, 404, 409}, changed


@pytest.mark.parametrize("mutation", ["wrong-owner", "wrong-context", "wrong-artifact", "wrong-thread", "outside-record", "inherited-citation"])
def test_context_artifact_and_source_addresses_cannot_launder_provenance(sources, mutation):
    _, _, api, marker = sources
    body = copy.deepcopy(demo.body(marker))
    if mutation == "wrong-owner":
        body["arrangement"]["left"]["investigationId"] = marker["investigations"]["B"]
    elif mutation == "wrong-context":
        body["arrangement"]["left"]["contextId"] = marker["contexts"]["C"]
    elif mutation == "wrong-artifact":
        body["arrangement"]["left"]["artifactId"] = marker["artifacts"]["C"]
    elif mutation == "wrong-thread":
        body["focus"]["threadId"] = "foreign-thread"
    elif mutation == "outside-record":
        body["focus"]["seq"] = marker["controllingSeq"] + 1  # recorded detour, omitted from A's packet
    else:
        body["focus"] = {**marker["targets"]["C"], "seq": marker["controllingSeq"], "threadId": "fixture-artifact-origin"}
    assert demo.request(api, body=body)[0] in {400, 404, 409}
    assert catalog(api)["compositions"] == []


@pytest.mark.parametrize("location,field", [("root", "holder"), ("root", "outputGrants"), ("root", "draft"), ("root", "open"),
    ("arrangement", "perform"), ("arrangement", "executor"), ("left", "nativeHandle"), ("focus", "sourceRecords")])
def test_copied_authority_or_source_fields_are_rejected_without_effect(sources, location, field):
    _, trace, api, marker = sources
    before = source_state(trace)
    body = copy.deepcopy(demo.body(marker))
    target = body if location == "root" else body["arrangement"]["left"] if location == "left" else body[location]
    target[field] = {"instruction": "perform native execution", "holder": "local-owner", "live": True}
    assert demo.request(api, body=body)[0] == 400
    assert catalog(api)["compositions"] == [] and source_state(trace) == before


@pytest.mark.parametrize("field,value", [("seq", True), ("seq", float("nan")), ("seq", float("inf")), ("seq", 0), ("blockId", "block-0<script>")])
def test_focus_numbers_and_block_selector_syntax_fail_closed(sources, field, value):
    _, _, api, marker = sources
    body = copy.deepcopy(demo.body(marker))
    body["focus"][field] = value
    assert demo.request(api, body=body)[0] == 400


def test_unknown_renderer_remains_exact_inspectable_data(sources):
    _, trace, api, marker = sources
    before = source_state(trace)
    body = {**demo.body(marker), "rendererVersion": "unknown-parser/v999", "focus": {
        **marker["targets"]["A"], "blockId": "block-0", "seq": marker["controllingSeq"], "threadId": "fixture-artifact-origin"}}
    saved = stored(api, body)
    assert demo.call(api, f"/{saved['id']}", method="GET")["composition"] == saved
    assert saved["rendererVersion"] == body["rendererVersion"] and saved["focus"] == body["focus"]
    assert source_state(trace) == before  # parser equivalence belongs to explicit UI resolution, never backend claims


def test_metadata_catalog_is_bounded_literal_casefolded_and_does_not_read_sources(sources):
    _, _, api, marker = sources
    for index in range(43):
        stored(api, {**demo.body(marker, request_id=f"catalog-{index}"), "title": f"Straße %_ comparison {index:02d}"})
    with demo.scale.source_reads(api) as reads:
        first = catalog(api, q="STRASSE %_", limit=40)
        second = catalog(api, q="strasse %_", limit=40, cursor=first["nextCursor"])
        detail = demo.call(api, f"/{first['compositions'][0]['id']}", method="GET")
    assert reads["canonicalParses"] == [] and reads["canonicalReadStatements"] == []
    assert len(first["compositions"]) == 40 and len(second["compositions"]) == 3
    assert len({item["id"] for item in first["compositions"] + second["compositions"]}) == 43
    assert not any(key in json.dumps(first) for key in ("arrangement", "focus", "rawText", "projectedPrompt"))
    assert detail["composition"]["id"] == first["compositions"][0]["id"]
    assert demo.request(api, method="GET", query={"q": ["different"], "cursor": [first["nextCursor"]]})[0] == 400
    for query in ({"limit": ["0"]}, {"limit": ["41"]}, {"limit": ["", "1"]}, {"unknown": [""]}):
        assert demo.request(api, method="GET", query=query)[0] == 400


def test_copy_ancestry_and_create_only_routes_do_not_turn_names_into_authority(sources):
    _, trace, api, marker = sources
    body = demo.body(marker)
    assert demo.request(api, body={**body, "copiedFrom": marker["investigations"]["A"]})[0] in {404, 409}
    saved = stored(api, body)
    before = source_state(trace)
    for action in ("apply", "dispatch", "delete", "update", "continue"):
        assert demo.request(api, f"/{saved['id']}/{action}", {})[0] == 404
    assert demo.request(api, f"/{saved['id']}", body, method="PUT")[0] == 404
    assert demo.request(api, f"/{saved['id']}", method="DELETE")[0] == 404
    assert source_state(trace) == before


def test_real_http_body_limit_exact_retry_and_metadata_response(sources):
    path, trace, _, marker = sources
    before = source_state(trace)
    body = demo.body(marker)
    with demo.scale.http_server(path) as (origin, api):
        assert demo.http(origin, body=body)["status"] == 201
        saved = demo.http(origin, body=body)
        assert saved["status"] == 201
        assert demo.http(origin, body={**body, "title": "Changed"})["status"] == 409
        assert demo.http(origin, raw=json.dumps({**body, "requestId": "too-large"}).encode() + b" " * 16384)["status"] == 400
        assert demo.http(origin, "?limit=&limit=1")["status"] == 400
        with demo.scale.source_reads(api) as observed:
            catalog = demo.http(origin, "?limit=1")
            detail = demo.http(origin, "/" + saved["body"]["composition"]["id"])
        assert catalog["status"] == detail["status"] == 200
        assert catalog["bodyBytes"] < 600 and detail["bodyBytes"] < 2500
        assert len(catalog["body"]["compositions"]) == 1
        assert not observed["canonicalParses"] and not observed["canonicalReadStatements"]
    assert source_state(trace) == before


def test_named_experiment_requires_its_exact_compiled_targets(sources):
    _, _, api, marker = sources
    a = api.investigations.get(marker["investigations"]["A"])
    initial = demo.chain.call(api, body={"requestId": "experiment-owner", "title": "Synthetic comparison candidate",
        "question": "Which observation controls recovery?", "selections": a["contexts"][0]["selections"]})
    changed = demo.chain.call(api, f"/{initial['id']}/contexts", {"requestId": "experiment-revise",
        "parentContextId": initial["currentContextId"], "question": initial["contexts"][0]["question"],
        "selections": [{**item, "rationale": "Revised selection rationale"} for item in initial["contexts"][0]["selections"]]})
    completed = demo.chain.authored_completion(api, changed, f"Synthetic authored result [evidence:{marker['controllingSeq']}]")
    experiment = demo.chain.call(api, f"/{completed['id']}/experiments", {"requestId": "snapshot-experiment",
        "baselineContextId": completed["currentContextId"], "baselineArtifactId": completed["artifact"]["id"],
        "alternativeContextId": initial["currentContextId"], "rationale": "Synthetic saved context comparison; no execution."})
    arrangement = {"left": demo.target(completed), "right": {"investigationId": completed["id"], "contextId": initial["currentContextId"]},
        "lens": "context", "layout": "stacked", "intent": "alternative-review", "experimentId": experiment["id"]}
    body = {**demo.body(marker), "arrangement": arrangement, "focus": None}
    saved = stored(api, body)
    assert saved["arrangement"] == arrangement
    foreign = copy.deepcopy(body)
    foreign["requestId"] = "experiment-wrong-target"
    foreign["arrangement"]["right"] = marker["targets"]["C"]
    assert demo.request(api, body=foreign)[0] in {404, 409}
    bad_name = copy.deepcopy(body)
    bad_name["requestId"] = "experiment-wrong-name"
    bad_name["arrangement"]["experimentId"] = "experiment_foreign"
    assert demo.request(api, body=bad_name)[0] in {404, 409}
