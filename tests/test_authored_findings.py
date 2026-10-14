"""Local prose is reusable evidence data, never a fabricated native completion."""
import io
import json

import pytest

from eidos.api import EidosAPI
from eidos.investigation import InvestigationError, _json
from eidos.investigation_artifacts import finding_id
from eidos.trace import TraceStore


def call(api, method, path, body=None, query=None):
    raw = json.dumps(body, ensure_ascii=False).encode() if body is not None else b""
    class Handler:
        headers = {"Content-Length": str(len(raw))}
        rfile = io.BytesIO(raw)
    return api.dispatch(Handler(), method, path, query or {})


@pytest.fixture
def setup(tmp_path):
    trace = TraceStore(tmp_path / "findings.db")
    api = EidosAPI(trace)
    record = trace.append(source="authored-public-fixture", direction="internal", message={
        "method": "$history/item", "params": {"threadId": "source", "turnId": "t", "item": {
            "id": "choice", "type": "agentMessage", "text": "Atomic import preserves original bytes.",
            "unknown": {"retained": True}}}})
    body = {"requestId": "owner", "title": "Import policy", "question": "Why refuse colliding history?",
            "selections": [{"threadId": "source", "startSeq": record.seq, "endSeq": record.seq, "rationale": "source"}]}
    work = api.investigations.create(body)
    try:
        yield trace, api, work, body
    finally:
        api.close()
        trace.close()


def request(work, text="Keep explicit refusals [evidence:1].", request_id="finding"):
    return {"requestId": request_id, "contextId": work["currentContextId"], "text": text}


def save(api, work, body=None):
    return call(api, "POST", f"/api/investigations/{work['id']}/findings", body or request(work))


def reuse(work, finding, request_id="derived"):
    return {"requestId": request_id, "title": "Review the finding", "question": "What remains uncertain?",
            "selections": [], "artifactInputs": [{"investigationId": work["id"], "artifactId": finding["id"],
                                                   "rationale": "An attributed claim, not original observation."}]}


def test_save_only_adds_finding_and_receipt_with_no_native_or_context_mutation(setup):
    trace, api, work, _ = setup
    before_records = [tuple(r) for r in trace.db.execute("SELECT * FROM trace_records")]
    before_manifests = [tuple(r) for r in trace.db.execute("SELECT * FROM cm_objects ORDER BY cid")]
    status, receipt = save(api, work)
    finding = receipt["finding"]
    assert status == 201
    assert finding["kind"] == "owner-authored-finding"
    assert finding["citations"] == [1] and finding["unsupportedCitations"] == []
    assert finding["artifactCitations"] == finding["unsupportedArtifactCitations"] == []
    assert finding["authorship"]["kind"] == "local-owner"
    stored = api.investigations.get(work["id"])
    assert stored.pop("findings") == [finding]
    assert stored == work
    assert [tuple(r) for r in trace.db.execute("SELECT * FROM trace_records")] == before_records
    assert [tuple(r) for r in trace.db.execute("SELECT * FROM cm_objects ORDER BY cid")] == before_manifests
    with pytest.raises(InvestigationError, match="no attempt"):
        api.investigations.complete(work["id"], {"text": "Not a completion", "outputSeqs": [1]})
    assert save(api, work) == (200, receipt)
    # New request gets a receipt but reuses the exact original immutable value.
    assert save(api, work, request(work, request_id="second")) == (201, receipt)
    assert api.investigations.get(work["id"])["findings"] == [finding]


def test_receipt_reopen_after_native_progress_is_exact_and_replay_precedes_resolution(setup, monkeypatch):
    trace, api, work, body = setup
    _, receipt = save(api, work)
    c0 = work["currentContextId"]
    advanced = api.investigations.revise(work["id"], {"selections": body["selections"], "requestId": "revise", "parentContextId": c0,
        "question": "A later question"})
    advanced, _ = api.investigations.claim(work["id"], advanced["currentContextId"])
    output = trace.append(source="authored-native-fixture", direction="internal", message={"method": "$fixture/output"})
    finished = api.investigations.complete(work["id"], {"text": "Separate synthetic result", "outputSeqs": [output.seq],
                                                      "executionEvidence": "synthetic"})
    other = TraceStore(trace.path)
    reopened = EidosAPI(other)
    try:
        def no_resolution(_):
            pytest.fail("receipt recovery must not load current source")
        monkeypatch.setattr(reopened.investigations, "_load", no_resolution)
        assert save(reopened, work) == (200, receipt)
        path = f"/api/investigations/{work['id']}/findings/requests/finding"
        assert call(reopened, "GET", path) == (200, receipt)
        assert call(reopened, "GET", path.replace(work["id"], "wrong-owner"))[0] == 404
        assert save(reopened, work, request(work, text="changed"))[0] == 409
    finally:
        reopened.close()
        other.close()
    assert api.investigations.get(work["id"]) == finished


def test_identical_contexts_on_different_owners_have_distinct_finding_ids(setup):
    _, api, work, body = setup
    other = api.investigations.create({**body, "requestId": "another-owner"})
    assert other["currentContextId"] == work["currentContextId"]
    first = save(api, work)[1]["finding"]
    second = save(api, other, request(other, request_id="other-finding"))[1]["finding"]
    assert first["id"] != second["id"]
    assert {k: v for k, v in first.items() if k not in {"id", "authorship"}} == {
        k: v for k, v in second.items() if k not in {"id", "authorship"}}


def test_frozen_result_input_does_not_inherit_raw_citation_membership(setup):
    trace, api, work, _ = setup
    first = save(api, work)[1]["finding"]
    derived = api.investigations.create(reuse(work, first))
    context = derived["contexts"][0]
    frozen = context["artifactInputs"][0]
    assert context["records"] == []
    assert frozen["artifact"] == first and frozen["sourceContextId"] == work["currentContextId"]
    assert frozen["sourceAttemptManifestId"] is frozen["sourceAdoption"] is None
    text = f"Review [artifact:{first['id']}] [artifact:unknown] [evidence:1] [evidence:0]."
    second = save(api, derived, request(derived, text, "derived-finding"))[1]["finding"]
    assert second["citations"] == [] and second["unsupportedCitations"] == [0, 1]
    assert second["artifactCitations"] == [first["id"]] and second["unsupportedArtifactCitations"] == ["unknown"]
    trace.db.execute("DELETE FROM trace_records")
    source = api.investigation_reads.source(work["id"], first["id"], {})
    assert source["context"] == work["contexts"][0]
    assert source["attempt"] is source["adoption"] is None
    third = api.investigations.create(reuse(derived, second, "third"))
    assert third["contexts"][0]["artifactInputs"][0]["artifact"] == second
    assert third["attempt"] is None and third["status"] == "draft"


def test_plain_composition_result_search_and_historical_focus(setup):
    _, api, work, body = setup
    finding = save(api, work)[1]["finding"]
    found = api.investigation_reads.catalog({"q": ["explicit refusals"]}, artifacts=True)["artifacts"]
    assert [a["artifactId"] for a in found] == [finding["id"]]
    assert found[0]["attemptId"] is None and found[0]["kind"] == finding["kind"]
    revised = api.investigations.revise(work["id"], {"selections": body["selections"], "requestId": "later", "parentContextId": work["currentContextId"],
        "question": "Later question"})
    target = {"investigationId": work["id"], "contextId": finding["contextId"], "artifactId": finding["id"]}
    snapshot = api.compositions.create({"requestId": "snapshot", "title": "Authored result", "rendererVersion": "test/1",
        "arrangement": {"left": target, "right": {"investigationId": work["id"], "contextId": revised["currentContextId"]},
                        "lens": "result", "layout": "beside"},
        "focus": {**target, "seq": 1, "threadId": "source"}})
    assert api.compositions.get(snapshot["id"]) == snapshot
    assert snapshot["arrangement"]["left"] == target
    assert call(api, "POST", f"/api/investigations/{work['id']}/adoption",
                {"artifactId": finding["id"], "decision": "adopt", "note": "No native authority"})[0] == 409
    assert call(api, "POST", f"/api/investigations/{work['id']}/experiments", {
        "requestId": "forbidden", "baselineContextId": finding["contextId"], "baselineArtifactId": finding["id"],
        "alternativeContextId": revised["currentContextId"], "rationale": "Not a native baseline"})[0] in {400, 409}


@pytest.mark.parametrize("text", ["An uncited hypothesis.", '{"type":"needs-evidence","question":"More?"}',
    "[evidence:9007199254740991]", "[evidence:0]", "[evidence:١]"])
def test_hypothesis_and_protocol_shaped_prose_are_plain_data(setup, text):
    _, api, work, _ = setup
    status, value = save(api, work, request(work, text))
    assert status == 201 and value["finding"]["text"] == text
    assert value["finding"]["citations"] == []
    after = api.investigations.get(work["id"])
    assert after["status"] == "draft" and after["attempt"] is None and "continuation" not in after


@pytest.mark.parametrize("update", [
    {"kind": "native-specialist-result"}, {"authorship": {"kind": "local-owner", "createdAtMs": 1}},
    {"outputSeqs": [1]}, {"executionEvidence": "native-observed"}, {"contextId": "foreign-context"},
    {"requestId": "bad\n"}, {"requestId": "x" * 129}, {"requestId": ""}, {"requestId": "   "},
    {"text": "[evidence:" + "9" * 5000 + "]"}, {"text": "[evidence:9007199254740992]"},
    {"text": "🧭" * (32 * 1024 + 1)}, {"text": ""}, {"text": "\ufeff"}, {"text": " \ufeff\t\n"},
])
def test_controlled_refusals_leave_owner_and_receipts_unchanged(setup, update):
    trace, api, work, _ = setup
    before = trace.db.execute("SELECT state_json FROM investigations WHERE id=?", (work["id"],)).fetchone()[0]
    status, value = save(api, work, {**request(work), **update})
    assert status in {400, 409} and "error" in value
    assert trace.db.execute("SELECT state_json FROM investigations WHERE id=?", (work["id"],)).fetchone()[0] == before
    assert trace.db.execute("SELECT count(*) FROM investigation_finding_requests").fetchone()[0] == 0


def test_byte_bounded_receipt_refuses_before_mutation(setup):
    trace, api, work, _ = setup
    # Short UTF8 characters can expand sixfold in JSON, beyond the receipt cap.
    with pytest.raises(InvestigationError) as error:
        api.investigations.create_finding(work["id"], request(work, "x" + "\x00" * (128 * 1024 - 1)))
    assert error.value.status == 413
    assert api.investigations.get(work["id"]) == work
    assert trace.db.execute("SELECT count(*) FROM investigation_finding_requests").fetchone()[0] == 0


@pytest.mark.parametrize("mutation", [
    lambda w, f: w.update(artifact=f),
    lambda w, f: f.update(attemptId="invented"),
    lambda w, f: f.update(text="Rewritten under old identity"),
    lambda w, f: f.update(citations=[True]),
])
def test_malformed_or_cross_collection_findings_cannot_be_reused(setup, mutation):
    trace, api, work, _ = setup
    finding = save(api, work)[1]["finding"]
    mutated = api.investigations.get(work["id"])
    mutation(mutated, mutated["findings"][0])
    trace.db.execute("UPDATE investigations SET state_json=? WHERE id=?", (_json(mutated), work["id"]))
    with pytest.raises(InvestigationError) as error:
        api.investigations.create(reuse(work, finding))
    assert error.value.status == 409
    # The exact admission receipt remains inspectable even if trusted data is later malformed.
    assert api.investigations.get_finding_request(work["id"], "finding") == finding


def test_unpaired_surrogate_is_controlled_for_direct_host_caller(setup):
    _, api, work, _ = setup
    with pytest.raises(InvestigationError) as error:
        api.investigations.create_finding(work["id"], request(work, "bad\ud800"))
    assert error.value.status == 400


def test_finding_hash_domain_is_owner_and_version_bound(setup):
    _, api, work, _ = setup
    finding = save(api, work)[1]["finding"]
    content = {k: v for k, v in finding.items() if k not in {"id", "authorship"}}
    assert finding_id(work["id"], content) == finding["id"]
    assert finding_id("another-owner", content) != finding["id"]


def test_valid_bom_bearing_prose_keeps_exact_bytes_and_hash(setup):
    _, api, work, _ = setup
    prose = " \ufeffKeep these exact bytes.\ufeff "
    status, receipt = save(api, work, request(work, prose))
    assert status == 201 and receipt["finding"]["text"] == prose
    assert save(api, work, request(work, prose)) == (200, receipt)
