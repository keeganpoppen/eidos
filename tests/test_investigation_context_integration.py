"""The combined packet → pin → native evidence → local review provenance seam."""
from __future__ import annotations

import json
import sys

import pytest

from eidos.api import EidosAPI
from eidos.investigation_worker import NativeInvestigationWorker
from eidos.trace import TraceStore
from test_investigation_api import FAKE, call, sources, wait_result


def test_revisions_project_frozen_packets_and_share_unchanged_ingredients(tmp_path):
    trace = TraceStore(tmp_path / "context.db")
    api = EidosAPI(trace)
    body = sources(trace)
    work = api.investigations.create(body)
    first = work["contexts"][0]
    work = api.investigations.revise(work["id"], {
        "requestId": "revise", "parentContextId": first["id"],
        "question": "Compare a narrower recovery policy", "selections": body["selections"],
    })
    second = work["contexts"][1]
    manifests = api.investigations.contexts.store
    assert first["id"] != second["id"] and first["manifestId"] != second["manifestId"]
    diff = manifests.diff(first["manifestId"], second["manifestId"])
    assert {change.path for change in diff} == {"builder/selection", "input/user"}
    for record in first["records"]:
        path = f"evidence/{record['seq']}"
        assert manifests.at(first["manifestId"], path) == manifests.at(second["manifestId"], path)
    before = api.investigations.context_manifest(work["id"], first["id"])
    trace.db.execute("UPDATE trace_records SET thread_id='later-index' WHERE seq=?", (first["records"][0]["seq"],))
    assert api.investigations.context_manifest(work["id"], first["id"]) == before
    record_slots = [s for s in before["slots"] if s["path"].startswith("evidence/")]
    assert "future" in record_slots[0]["claims"][0]["content"]["data"]["rawText"]
    assert all(c["state"] != "OBSERVED" for slot in before["slots"] for c in slot["claims"])
    assert {g["boundary"] for slot in before["slots"] for g in slot["gaps"]} == {"app_server", "provider"}
    changes = trace.db.total_changes
    assert call(api, f"/{work['id']}/context-lineage", method="GET")[0] == 200
    assert call(api, f"/{work['id']}/contexts/{first['id']}/manifest", method="GET")[0] == 200
    assert call(api, f"/{work['id']}/contexts/guessed-name/manifest", method="GET")[0] == 404
    assert trace.db.total_changes == changes
    api.close()
    trace.close()


def test_pin_and_claim_rollback_together_before_any_launch(tmp_path, monkeypatch):
    trace = TraceStore(tmp_path / "rollback.db")
    api = EidosAPI(trace)
    work = api.investigations.create(sources(trace))
    before = trace.db.execute("SELECT COUNT(*) FROM cm_objects").fetchone()[0]
    original = api.investigations._save
    def crash(value):
        assert value["attempt"]["contextRequestName"]
        raise RuntimeError("before claim commit")
    monkeypatch.setattr(api.investigations, "_save", crash)
    with pytest.raises(RuntimeError, match="before claim commit"):
        api.start_investigation(work["id"], work["currentContextId"])
    assert api.investigations.get(work["id"])["attempt"] is None
    assert trace.db.execute("SELECT COUNT(*) FROM cm_requests").fetchone()[0] == 0
    assert trace.db.execute("SELECT COUNT(*) FROM cm_objects").fetchone()[0] == before
    assert not [r for r in trace.records() if r.method == "turn/start"]
    monkeypatch.setattr(api.investigations, "_save", original)
    api.close()
    trace.close()


def test_native_pin_committed_before_launch_recovery_and_offer_never_repin(tmp_path, monkeypatch):
    path = tmp_path / "whole-loop.db"
    trace = TraceStore(path)
    api = EidosAPI(trace)
    work = api.investigations.create(sources(trace))
    identifier = work["id"]

    class CheckingWorker(NativeInvestigationWorker):
        def run(self, attempt, context, update):
            # An independent connection must observe the committed pin BEFORE
            # the real fixture worker starts even its subprocess.
            other = TraceStore(path)
            row = other.db.execute("SELECT cid FROM cm_requests WHERE name=?", (attempt["contextRequestName"],)).fetchone()
            assert row is not None
            other.close()
            return super().run(attempt, context, update)

    api.investigation_worker = CheckingWorker(trace, command=[sys.executable, str(FAKE)])
    def fail_projection(_):
        raise RuntimeError("projection interrupted after native completion")
    monkeypatch.setattr(api.investigations.contexts, "correlate", fail_projection)
    api.start_investigation(identifier, work["currentContextId"])
    completed = wait_result(api, identifier)
    api.close()  # joins native completion and the failing derived projection
    completed = api.investigations.get(identifier)
    assert completed["status"] == "completed"
    assert "projection interrupted" in completed["contextLineageError"]
    pinned = api.investigations.context_lineage(identifier)["attempt"]
    assert pinned["pin"]["data"]["state"] == "PROJECTED"
    assert pinned["events"] == []
    trace.close()

    trace = TraceStore(path)
    api = EidosAPI(trace)  # evidence projection repairs with no native send
    repaired = api.investigations.context_lineage(identifier)["attempt"]
    assert repaired["pin"] == pinned["pin"]
    assert len(repaired["events"]) == 2
    manifest_store = api.investigations.contexts.store
    policy_slot = manifest_store.get(manifest_store.at(pinned["manifestId"], "runtime/requested-policy"))
    policy_claim = manifest_store.get(policy_slot.refs[0][1])
    policy = manifest_store.get(policy_claim.ref("content")).data
    thread_request = next(r.message["params"] for r in trace.records() if r.method == "thread/start")
    turn_request = next(r.message["params"] for r in trace.records() if r.method == "turn/start")
    assert policy["threadConfig"] == thread_request["config"]
    assert policy["approvalPolicy"] == thread_request["approvalPolicy"]
    assert policy["environments"] == thread_request["environments"] == turn_request["environments"]
    assert policy["sandboxPolicy"] == turn_request["sandboxPolicy"]
    assert {e["data"]["details"]["observation"] for e in repaired["events"]} == {"recorded-outbound", "native-acknowledgement"}
    assert all(e["data"]["boundary"] == "app_server" for e in repaired["events"])
    for event in repaired["events"]:
        assert event["refs"]["manifest"] == pinned["manifestId"]
        assert event["data"]["identity"]["attempt_id"] == completed["attempt"]["id"]
    context = completed["contexts"][0]
    status, pending = call(api, f"/{identifier}/continuation", {
        "requestId": "review", "attemptId": completed["attempt"]["id"], "question": "What further evidence can be disclosed?",
    })
    assert status == 202
    inquiry = pending["continuation"]["inquiry"]["id"]
    status, reviewed = call(api, f"/{identifier}/inquiries/{inquiry}/responses", {
        "requestId": "offer", "decision": "offer", "selections": context["selections"][:1],
    })
    assert status == 200 and reviewed["status"] == "completed"
    offered = reviewed["continuation"]["inquiry"]["responses"][0]["evidenceContext"]
    assert offered["manifestId"] != context["manifestId"]
    assert api.investigations.context_manifest(identifier, offered["id"])["manifestId"] == offered["manifestId"]
    assert reviewed["nativeArtifact"] == completed["artifact"]
    assert reviewed["artifact"]["kind"] == "eidos-evidence-review"
    assert api.investigations.context_lineage(identifier)["attempt"] == repaired
    assert api.recover_investigation(identifier)["artifact"] == reviewed["artifact"]
    assert len([r for r in trace.records() if r.method == "turn/start"]) == 1
    assert trace.db.execute("SELECT COUNT(*) FROM cm_requests").fetchone()[0] == 1
    api.close()
    trace.close()


def test_legacy_attempt_is_inspectable_without_inventing_a_presend_pin(tmp_path):
    trace = TraceStore(tmp_path / "legacy.db")
    api = EidosAPI(trace)
    work = api.investigations.create(sources(trace))
    claimed, _ = api.investigations.claim(work["id"], work["currentContextId"])
    for context in claimed["contexts"]:
        context.pop("manifestId")
    claimed["attempt"].pop("manifestId")
    claimed["attempt"].pop("contextRequestName")
    trace.db.execute("UPDATE investigations SET state_json=? WHERE id=?", (json.dumps(claimed), claimed["id"]))
    api.recover_investigation(claimed["id"])
    assert api.investigations.context_lineage(claimed["id"])["attempt"]["pin"] is None
    assert api.investigations.context_manifest(claimed["id"], claimed["currentContextId"])["manifestId"] is None
    assert api.start_investigation(claimed["id"], claimed["currentContextId"])["attempt"]["id"] == claimed["attempt"]["id"]
    assert not [r for r in trace.records() if r.method == "turn/start"]
    api.close()
    trace.close()


def test_borrowed_pin_cannot_create_cross_attempt_correlation(tmp_path):
    trace = TraceStore(tmp_path / "cross.db")
    api = EidosAPI(trace)
    body = sources(trace)
    first = api.investigations.create(body)
    second = api.investigations.create({**body, "requestId": "second"})
    first, _ = api.investigations.claim(first["id"], first["currentContextId"])
    second, _ = api.investigations.claim(second["id"], second["currentContextId"])
    assert first["attempt"]["manifestId"] == second["attempt"]["manifestId"]
    second["attempt"].update(contextRequestName=first["attempt"]["contextRequestName"], source="borrowed")
    with pytest.raises(ValueError, match="does not belong"):
        api.investigations.contexts.correlate(second)
    assert api.investigations.context_lineage(second["id"])["attempt"]["events"] == []
    api.close()
    trace.close()


def test_unsolicited_reply_before_send_is_not_a_native_acknowledgement(tmp_path):
    trace = TraceStore(tmp_path / "unsolicited.db")
    api = EidosAPI(trace)
    work = api.investigations.create(sources(trace))
    work, _ = api.investigations.claim(work["id"], work["currentContextId"])
    api.investigations.update_attempt(work["id"], source="synthetic-incarnation")
    trace.append(source="synthetic-incarnation", direction="appserver_to_client",
                 message={"id": 1, "result": {"turn": {"id": "unsolicited"}}})
    trace.append(source="synthetic-incarnation", direction="client_to_appserver", message={
        "id": 1, "method": "turn/start", "params": {"threadId": "thread",
            "input": [{"type": "text", "text": work["contexts"][0]["projectedPrompt"]}]},
    })
    # Python equality must not conflate malformed boolean RPC IDs with ints.
    trace.append(source="synthetic-incarnation", direction="appserver_to_client",
                 message={"id": True, "result": {"turn": {"id": "boolean-id"}}})
    api.investigations.reconcile_context(work["id"])
    events = api.investigations.context_lineage(work["id"])["attempt"]["events"]
    assert [e["data"]["details"]["observation"] for e in events] == ["recorded-outbound"]
    trace.append(source="synthetic-incarnation", direction="client_to_appserver", message={
        "id": 2, "method": "turn/start", "params": {"threadId": "thread", "input": [{"type": "text", "text": "different task"}]},
    })
    api.investigations.reconcile_context(work["id"])
    lineage = api.investigations.context_lineage(work["id"])
    assert "multiple turn requests" in lineage["error"]
    assert lineage["attempt"]["events"] == events  # preserve earlier observation, flag new ambiguity
    api.close()
    trace.close()
