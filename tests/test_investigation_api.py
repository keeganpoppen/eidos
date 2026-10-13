"""Integrated local native-boundary evidence; no provider or personal history."""
from __future__ import annotations

import io
import json
from pathlib import Path
import sys
import time

from eidos.api import EidosAPI
from eidos.investigation_worker import NativeInvestigationWorker
from eidos.serve import local_request_error
from eidos.trace import TraceStore


FAKE = Path(__file__).parent / "fixtures/investigation_appserver.py"


class Handler:
    def __init__(self, body=None):
        raw = json.dumps(body or {}).encode()
        self.headers = {"Content-Length": str(len(raw)), "Content-Type": "application/json"}
        self.rfile = io.BytesIO(raw)


def call(api, path="", body=None, method="POST"):
    return api.dispatch(Handler(body), method, "/api/investigations" + path, {})


def sources(store):
    selections = []
    for thread, text in [("decision", "Persist attempt identity before send."), ("experiment", "A missing reply did not prove no native turn existed.")]:
        record = store.append(source="synthetic", direction="internal", message={
            "method": "$history/item", "params": {"threadId": thread, "turnId": thread + "-turn", "item": {
                "id": thread + "-answer", "type": "agentMessage", "text": text, "future": {"keep": True},
            }},
        })
        selections.append({"threadId": thread, "startSeq": record.seq, "endSeq": record.seq, "rationale": "compare recovery evidence"})
    return {"requestId": "request-1", "title": "Two-thread recovery", "question": "What should happen after a missing native reply?", "selections": selections}


def wait_result(api, identifier):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        value = api.investigations.get(identifier)
        if value["status"] in {"completed", "failed", "unknown"}:
            return value
        time.sleep(0.01)
    raise AssertionError("synthetic worker did not finish")


def test_two_thread_preview_native_artifact_adoption_and_restart(tmp_path):
    path = tmp_path / "trace.db"
    store = TraceStore(path)
    body = sources(store)
    raw_sources = [record.raw_text for record in store.records()]
    api = EidosAPI(store)
    api.investigation_worker = NativeInvestigationWorker(store, command=[sys.executable, str(FAKE)])
    status, investigation = call(api, body=body)
    assert status == 201
    identifier = investigation["id"]
    context = investigation["contexts"][0]
    assert {r["threadId"] for r in context["records"]} == {"decision", "experiment"}
    status, duplicate = call(api, body=body)
    assert status == 201 and duplicate["id"] == identifier
    assert call(api, body={**body, "question": "altered"})[0] == 409
    assert call(api, f"/{identifier}/dispatch", {"contextId": context["id"], "executor": "guessed-name"})[0] == 400
    status, dispatched = call(api, f"/{identifier}/dispatch", {"contextId": context["id"]})
    assert status == 202
    assert call(api, f"/{identifier}/dispatch", {"contextId": context["id"]})[1]["attempt"]["id"] == dispatched["attempt"]["id"]
    completed = wait_result(api, identifier)
    assert completed["status"] == "completed", completed["attempt"]
    outgoing = [r for r in store.records() if r.method == "turn/start"]
    assert len(outgoing) == 1
    assert outgoing[0].message["params"]["input"][0]["text"] == context["projectedPrompt"]
    assert completed["artifact"]["contextId"] == context["id"]
    assert completed["artifact"]["attemptId"] == completed["attempt"]["id"]
    assert completed["artifact"]["unsupportedCitations"] == []
    adoption = {"artifactId": completed["artifact"]["id"], "decision": "adopt", "note": "Keep uncertainty explicit."}
    status, accepted = call(api, f"/{identifier}/adoption", adoption)
    assert status == 200
    assert call(api, f"/{identifier}/adoption", adoption)[1]["adoption"] == accepted["adoption"]
    assert call(api, f"/{identifier}/adoption", {**adoption, "decision": "reject"})[0] == 409
    assert [record.raw_text for record in store.records()[:2]] == raw_sources
    api.close()
    store.close()

    reopened = TraceStore(path)
    restarted = EidosAPI(reopened)
    status, recovered = call(restarted, f"/{identifier}", method="GET")
    assert status == 200 and recovered["artifact"] == completed["artifact"]
    assert recovered["adoption"] == accepted["adoption"]
    assert call(restarted, f"/{identifier}/dispatch", {"contextId": context["id"]})[1]["attempt"] == completed["attempt"]
    assert len([r for r in reopened.records() if r.method == "turn/start"]) == 1
    restarted.close()
    reopened.close()


def test_restart_recovers_native_completion_before_outer_artifact_commit(tmp_path):
    path = tmp_path / "trace.db"
    store = TraceStore(path)
    api = EidosAPI(store)
    investigation = api.investigations.create(sources(store))
    identifier = investigation["id"]
    claimed, _ = api.investigations.claim(identifier, investigation["currentContextId"])
    worker = NativeInvestigationWorker(store, command=[sys.executable, str(FAKE)])
    def save_only_incarnation(**fields):
        if "source" in fields:
            api.investigations.update_attempt(identifier, source=fields["source"])
    worker.run(claimed["attempt"], claimed["contexts"][0], save_only_incarnation)
    # Inject crash after native completion persisted, before complete().
    assert api.investigations.get(identifier)["artifact"] is None
    api.close()
    store.close()
    reopened = TraceStore(path)
    restarted = EidosAPI(reopened)
    recovered = restarted.investigations.get(identifier)
    assert recovered["status"] == "completed"
    assert recovered["attempt"]["threadId"].startswith("fixture-worker-")
    assert recovered["attempt"]["turnId"].startswith("fixture-turn-")
    artifact = recovered["artifact"]
    assert restarted.recover_investigation(identifier)["artifact"] == artifact
    assert len([r for r in reopened.records() if r.method == "turn/start"]) == 1
    restarted.close()
    reopened.close()


def test_interrupted_dispatch_stays_unknown_and_never_replays(tmp_path):
    path = tmp_path / "trace.db"
    store = TraceStore(path)
    api = EidosAPI(store)
    investigation = api.investigations.create(sources(store))
    identifier, context_id = investigation["id"], investigation["currentContextId"]
    claimed, _ = api.investigations.claim(identifier, context_id)
    api.close()
    store.close()
    reopened = TraceStore(path)
    restarted = EidosAPI(reopened)
    unknown = restarted.investigations.get(identifier)
    assert unknown["status"] == "unknown"
    assert restarted.start_investigation(identifier, context_id)["attempt"]["id"] == claimed["attempt"]["id"]
    assert not [r for r in reopened.records() if r.method == "turn/start"]
    restarted.close()
    reopened.close()


def test_local_http_admission_rejects_cross_site_and_rebinding():
    base = {"Host": "127.0.0.1:8765", "Content-Type": "application/json"}
    assert local_request_error("POST", base) is None
    assert local_request_error("POST", {**base, "Origin": "http://127.0.0.1:5173"}) is None
    assert local_request_error("POST", {**base, "Origin": "https://attacker.invalid"})
    assert local_request_error("POST", {**base, "Origin": "null"})
    assert local_request_error("POST", {**base, "Content-Type": "text/plain"})
    assert local_request_error("GET", {**base, "Host": "attacker.invalid:8765"})
    assert local_request_error("POST", {**base, "Origin": "http://localhost:9999"})
