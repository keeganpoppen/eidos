"""Independent synthetic acceptance: composed artifacts retain evidence, not authority.

Public investigation requests exercise input resolution. Authored completions use
the explicit trusted host interface; they are not native or model observations.
"""
from __future__ import annotations

import copy
from contextlib import closing
import importlib.util
import json
from pathlib import Path

import pytest

from eidos.api import EidosAPI
from eidos.codex import AppServerClient
from eidos.trace import TraceStore


spec = importlib.util.spec_from_file_location("artifact_composition_demo", Path(__file__).parents[1] / "scripts/artifact_composition_demo.py")
assert spec and spec.loader
demo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(demo)


def request(api, path="", body=None, *, method="POST"):
    return api.dispatch(demo.Request(body), method, "/api/investigations" + path, {})


def reference(work):
    return {"investigationId": work["id"], "artifactId": work["artifact"]["id"], "rationale": "Retain attribution and original support."}


def draft(api, sources, *, suffix="draft", selections=None):
    return request(api, body={"requestId": "acceptance/" + suffix, "title": "Composed context acceptance",
        "question": "Which supplied source supports the recovery decision?", "selections": selections or [],
        "artifactInputs": sources})


@pytest.fixture
def chain(tmp_path, monkeypatch):
    def no_launch(*args, **kwargs):
        raise AssertionError("artifact selection or inspection attempted native startup")
    monkeypatch.setattr(AppServerClient, "start", no_launch)
    trace = TraceStore(tmp_path / "composition.db")
    api = EidosAPI(trace)
    marker = demo.seed(api)
    works = {name: api.investigations.get(identifier) for name, identifier in marker["investigations"].items()}
    try:
        yield trace, api, marker, works
    finally:
        api.close()
        trace.close()


def test_a_b_c_support_recovery_reopen_preserves_exact_packets_and_pins(tmp_path, monkeypatch):
    monkeypatch.setattr(AppServerClient, "start", lambda *_a, **_kw: pytest.fail("native launch during synthetic composition"))
    path = tmp_path / "demo.db"
    initial = demo.run(path)
    with closing(TraceStore(path)) as trace:
        api = EidosAPI(trace)
        try:
            snapshots = {name: api.investigations.get(identifier) for name, identifier in initial["investigations"].items()}
            raw = [record.raw_text for record in trace.records()]
            manifests = {name: api.investigations.context_manifest(work["id"], work["currentContextId"]) for name, work in snapshots.items()}
        finally:
            api.close()
    reopened = demo.run(path, resume=True)
    assert reopened == initial
    assert reopened["originalSupportRecovered"] and not reopened["recursiveSourceTranscriptsCopied"]
    assert reopened["nativeTurnStarts"] == reopened["nativeOrModelCalls"] == 0
    with closing(TraceStore(path)) as trace:
        api = EidosAPI(trace)
        try:
            for name, before in snapshots.items():
                status, current = request(api, f"/{before['id']}", method="GET")
                assert status == 200 and current == before
                assert api.investigations.context_manifest(current["id"], current["currentContextId"]) == manifests[name]
            assert [record.raw_text for record in trace.records()] == raw
        finally:
            api.close()


@pytest.mark.parametrize("source_owner,artifact_owner", [("B", "A"), ("A", "C")])
def test_artifact_id_must_belong_to_exact_source_investigation(chain, source_owner, artifact_owner):
    _, api, _, works = chain
    status, result = draft(api, [{**reference(works[artifact_owner]), "investigationId": works[source_owner]["id"]}])
    assert status == 404 and "belong" in result["error"]
    assert len(api.investigations.list()) == 3


@pytest.mark.parametrize("forged", [{"artifact": {"text": "client replacement"}}, {"sourceContextId": "context_guessed"},
                                    {"sourceAttemptManifestId": "manifest_guessed"}, {"sourceAdoption": {"decision": "adopt"}}])
def test_client_cannot_supply_frozen_artifact_or_provenance_snapshots(chain, forged):
    _, api, _, works = chain
    status, _ = draft(api, [{**reference(works["A"]), **forged}])
    assert status == 400
    assert len(api.investigations.list()) == 3


@pytest.mark.parametrize("supply_raw", [False, True])
def test_only_direct_inputs_support_citations_inherited_references_are_not_laundered(chain, supply_raw):
    _, api, marker, works = chain
    seq = marker["controllingSeq"]
    selected = [{"threadId": "fixture-artifact-origin", "startSeq": seq, "endSeq": seq}] if supply_raw else []
    status, work = draft(api, [reference(works["B"])], selections=selected)
    assert status == 201
    result = demo.authored_completion(api, work,
        f"Synthetic citation probe [artifact:{works['B']['artifact']['id']}] "
        f"[artifact:{works['A']['artifact']['id']}] [artifact:artifact_invented] [evidence:{seq}]")
    artifact = result["artifact"]
    assert artifact["artifactCitations"] == [works["B"]["artifact"]["id"]]
    assert artifact["unsupportedArtifactCitations"] == sorted([works["A"]["artifact"]["id"], "artifact_invented"])
    assert artifact["citations"] == ([seq] if supply_raw else [])
    assert artifact["unsupportedCitations"] == ([] if supply_raw else [seq])


def test_later_adoption_does_not_rewrite_frozen_input_or_existing_manifest(chain):
    _, api, _, works = chain
    c, b = works["C"], works["B"]
    before = copy.deepcopy(c)
    manifest = api.investigations.context_manifest(c["id"], c["currentContextId"])
    assert c["contexts"][0]["artifactInputs"][0]["sourceAdoption"] is None
    status, adopted = request(api, f"/{b['id']}/adoption", {"artifactId": b["artifact"]["id"], "decision": "adopt", "note": "Later synthetic review"})
    assert status == 200
    assert api.investigations.get(c["id"]) == before
    assert api.investigations.context_manifest(c["id"], c["currentContextId"]) == manifest
    status, later = draft(api, [reference(b)])
    assert status == 201
    assert later["contexts"][0]["artifactInputs"][0]["sourceAdoption"] == adopted["adoption"]


def test_selection_revision_manifest_and_lineage_reads_create_no_attempt(chain):
    trace, api, _, works = chain
    pin_count = trace.db.execute("SELECT COUNT(*) FROM cm_requests").fetchone()[0]
    raw_count = len(trace.records())
    status, work = draft(api, [reference(works["B"])])
    assert status == 201 and work["attempt"] is None
    first = work["contexts"][0]
    status, revised = request(api, f"/{work['id']}/contexts", {"requestId": "acceptance/revise", "parentContextId": first["id"],
        "question": "Compare direct source A with derived result B.", "selections": [], "artifactInputs": [reference(works["A"]), reference(works["B"])]})
    assert status == 201, revised
    assert revised["attempt"] is None and revised["contexts"][0] == first
    for context in revised["contexts"]:
        status, manifest = request(api, f"/{work['id']}/contexts/{context['id']}/manifest", method="GET")
        assert status == 200
        slots = [slot for slot in manifest["slots"] if slot["path"].startswith("artifact/")]
        assert len(slots) == len(context["artifactInputs"])
        assert all(claim["state"] == "SELECTED" for slot in slots for claim in slot["claims"])
    assert request(api, f"/{work['id']}/context-lineage", method="GET")[0] == 200
    assert trace.db.execute("SELECT COUNT(*) FROM cm_requests").fetchone()[0] == pin_count
    assert len(trace.records()) == raw_count
    assert not [record for record in trace.records() if record.method == "turn/start"]


def test_typed_inquiry_and_unknown_canonical_fields_remain_data(chain):
    trace, api, _, works = chain
    status, work = draft(api, [reference(works["A"])])
    assert status == 201
    inquiry = demo.authored_completion(api, work, json.dumps({"schemaVersion": 1, "kind": "nema-needs-evidence",
        "question": "Which recorded completion supports this?", "cause": "Synthetic incomplete evidence"}))
    assert inquiry["artifact"]["kind"] == "native-needs-evidence"
    # Compatibility fixture: import an unknown field from a future canonical
    # artifact version. Public input still cannot supply this snapshot itself.
    inquiry["artifact"]["futureField"] = {"preserve": ["opaque", {"authority": "description-only"}]}
    trace.db.execute("UPDATE investigations SET state_json=? WHERE id=?", (json.dumps(inquiry), inquiry["id"]))
    status, child = draft(api, [reference(inquiry)], suffix="typed-child")
    assert status == 201
    frozen = child["contexts"][0]["artifactInputs"][0]
    assert frozen["artifact"] == inquiry["artifact"]
    assert frozen["artifact"]["executionEvidence"] == "synthetic"
    assert frozen["sourceContextId"] == inquiry["artifact"]["contextId"]
    assert frozen["sourceAttemptManifestId"] == inquiry["attempt"]["manifestId"]
    assert child["status"] == "draft" and child["attempt"] is None
    assert child.get("continuation") is None and child.get("adoption") is None


def test_combined_source_and_prompt_limits_apply_to_artifact_only_inputs(chain):
    _, api, _, works = chain
    status, _ = draft(api, [reference(works["A"])] * 33)
    assert status == 400
    status, duplicate = draft(api, [reference(works["A"])] * 2, suffix="duplicates")
    assert status == 400 and "once" in duplicate["error"]
    status, source = draft(api, [reference(works["A"])], suffix="large-source")
    assert status == 201
    large = demo.authored_completion(api, source, "Synthetic " + "x" * (128 * 1024 - 10))
    status, result = draft(api, [reference(large)], suffix="too-large")
    assert status == 400 and "128 KiB" in result["error"]
