"""Crash-boundary integration evidence. All native turns use the local fixture."""
from __future__ import annotations

import json
import sys

import pytest

from eidos.api import EidosAPI
from eidos.investigation_worker import NativeInvestigationWorker
from eidos.process_runtime import ProcessRuntime
from eidos.trace import TraceStore

from test_investigation_continuations_api import (
    FAKE, begin, call, continuation_body, create_body, inquiry_path, native,
    occurrences, successful,
)


class Crash(BaseException):
    """Simulated process death: bypass normal error reporting, retain commits."""


def die(*args, **kwargs):
    raise Crash("injected interruption")


def reopened(tmp_path):
    trace = TraceStore(tmp_path / "investigation.db")
    return trace, EidosAPI(trace)


def assert_one_native(trace):
    assert len([record for record in trace.records() if record.method == "turn/start"]) == 1


def test_native_claim_must_commit_before_worker_launch(tmp_path, monkeypatch):
    trace = TraceStore(tmp_path / "investigation.db")
    api = EidosAPI(trace)
    investigation = api.investigations.create(create_body(trace))
    launched = []
    monkeypatch.setattr(api.investigation_worker, "run", lambda *args: launched.append(args))
    with monkeypatch.context() as fault:
        fault.setattr(api.investigations, "_save", die)
        with pytest.raises(Crash):
            api.start_investigation(investigation["id"], investigation["currentContextId"])
    assert api.investigations.get(investigation["id"])["attempt"] is None
    assert not launched and not trace.records()[-1].method == "turn/start"
    api.close()
    trace.close()


def test_claim_committed_then_thread_launch_failure_never_reexecutes(tmp_path, monkeypatch):
    trace = TraceStore(tmp_path / "investigation.db")
    api = EidosAPI(trace)
    investigation = api.investigations.create(create_body(trace))
    launched = []
    monkeypatch.setattr(api.investigation_worker, "run", lambda *args: launched.append(args))
    import threading
    with monkeypatch.context() as fault:
        def failed_start(self):
            raise RuntimeError("thread launch failed")
        fault.setattr(threading.Thread, "start", failed_start)
        with pytest.raises(RuntimeError, match="launch failed"):
            api.start_investigation(investigation["id"], investigation["currentContextId"])
    value = api.investigations.get(investigation["id"])
    assert value["attempt"]["status"] == "unknown"
    assert api.start_investigation(value["id"], value["currentContextId"])["attempt"] == value["attempt"]
    assert not launched
    api.close()
    trace.close()


def test_source_mapping_failure_precedes_any_external_launch(tmp_path, monkeypatch):
    trace = TraceStore(tmp_path / "investigation.db")
    api = EidosAPI(trace)
    investigation = api.investigations.create(create_body(trace))
    value, _ = api.investigations.claim(investigation["id"], investigation["currentContextId"])
    worker = NativeInvestigationWorker(trace, command=[sys.executable, str(FAKE)])
    with pytest.raises(Crash):
        worker.run(value["attempt"], value["contexts"][0], die)
    assert not [r for r in trace.records() if r.method == "initialize"]
    assert api.recover_investigation(value["id"])["attempt"]["status"] == "unknown"
    worker.close()
    api.close()
    trace.close()


@pytest.mark.parametrize("boundary", ["genesis", "prepared", "commit", "checkpoint", "outer_pointer"])
def test_request_preparation_and_committed_discover_recover_same_investigation(native, tmp_path, monkeypatch, boundary):
    api, trace, native_result, _ = native
    tm = api.investigation_runtime.trusted
    with monkeypatch.context() as fault:
        if boundary == "genesis":
            original = tm.admit_authority_domain
            def failed_genesis(**kwargs):
                result = original(**kwargs)
                if kwargs["description"].get("$kind") == "ModelProcess":
                    die()
                return result
            fault.setattr(tm, "admit_authority_domain", failed_genesis)
        elif boundary == "prepared":
            original = tm.bind_eidos_value
            def failed_preparation(**kwargs):
                if kwargs["value"].get("$kind") == "ModelPreparedStep":
                    die()
                return original(**kwargs)
            fault.setattr(tm, "bind_eidos_value", failed_preparation)
        elif boundary == "commit":
            original = tm.commit_projection_occurrence
            def failed_commit(**kwargs):
                result = original(**kwargs)
                if kwargs["kind"] == "ModelInteraction":
                    die()
                return result
            fault.setattr(tm, "commit_projection_occurrence", failed_commit)
        elif boundary == "checkpoint":
            original = ProcessRuntime.checkpoint
            def failed_checkpoint(self, **kwargs):
                if kwargs["step"] == 1:
                    die()
                return original(self, **kwargs)
            fault.setattr(ProcessRuntime, "checkpoint", failed_checkpoint)
        else:
            original = api.investigation_continuations._save_link
            def failed_pointer(identifier, link):
                if link["runtime"].get("inquiryId"):
                    die()
                return original(identifier, link)
            fault.setattr(api.investigation_continuations, "_save_link", failed_pointer)
        with pytest.raises(Crash):
            begin(api, native_result)
    interrupted = api.investigations.get(native_result["id"])
    assert interrupted["continuation"]["id"]
    assert interrupted["attempt"] == native_result["attempt"]
    process_before = interrupted["continuation"]["processId"]
    api.close()
    restored_trace, restored = reopened(tmp_path)
    try:
        pending = restored.investigations.get(native_result["id"])
        assert pending["status"] == "pending", pending["continuation"]["error"]
        assert pending["id"] == interrupted["id"]
        assert pending["continuation"]["id"] == interrupted["continuation"]["id"]
        if process_before is not None:
            assert pending["continuation"]["processId"] == process_before
        assert len(occurrences(restored, domain=pending["continuation"]["processId"])) == 1
        assert successful(call(restored, f"/{pending['id']}/continuation", continuation_body(native_result))) == pending
        assert_one_native(restored_trace)
    finally:
        restored.close()
        restored_trace.close()


@pytest.mark.parametrize("boundary", ["source_prepare", "source_commit", "source_bind", "response_link", "requester_resume", "outcome_commit", "outcome_pointer", "reintegration", "http_reply"])
def test_response_and_outcome_failures_repair_without_new_process_or_native_turn(native, tmp_path, monkeypatch, boundary):
    api, trace, native_result, body = native
    pending = begin(api, native_result)
    before = pending["continuation"]
    tm = api.investigation_runtime.trusted
    response_body = {"requestId": "durable-offer", "decision": "offer", "note": "Review these records.", "selections": body["selections"]}
    with monkeypatch.context() as fault:
        if boundary in {"source_prepare", "source_commit", "outcome_commit"}:
            original = tm.commit_projection_occurrence
            def failed_commit(**kwargs):
                kind = kwargs["kind"]
                if boundary == "source_prepare" and kind == "DiscoveryOffer":
                    die()
                result = original(**kwargs)
                if (boundary == "source_commit" and kind == "DiscoveryOffer") or (boundary == "outcome_commit" and kind == "ModelProcessFinish"):
                    die()
                return result
            fault.setattr(tm, "commit_projection_occurrence", failed_commit)
        elif boundary == "source_bind":
            original = tm.bind_eidos_value
            def failed_bind(**kwargs):
                if kwargs["value"].get("$kind") == "CutDisclosure":
                    die()
                return original(**kwargs)
            fault.setattr(tm, "bind_eidos_value", failed_bind)
        elif boundary == "response_link":
            original = api.investigation_runtime.respond
            def failed_response(*args):
                original(*args)
                die()
            fault.setattr(api.investigation_runtime, "respond", failed_response)
        elif boundary == "requester_resume":
            fault.setattr(api.investigation_runtime, "advance", die)
        elif boundary == "outcome_pointer":
            original = api.investigation_continuations._save_link
            def failed_pointer(identifier, link):
                if link["runtime"].get("outcomeId"):
                    die()
                return original(identifier, link)
            fault.setattr(api.investigation_continuations, "_save_link", failed_pointer)
        elif boundary == "reintegration":
            fault.setattr(api.investigation_continuations, "_complete", die)
        else:
            original = api.investigation_continuations._complete
            def lost_reply(identifier):
                original(identifier)
                die()
            fault.setattr(api.investigation_continuations, "_complete", lost_reply)
        with pytest.raises(Crash):
            successful(call(api, inquiry_path(pending) + "/responses", response_body))
    interrupted = api.investigations.get(pending["id"])
    saved_response = interrupted["continuation"]["inquiry"]["responses"][0]
    assert saved_response["evidenceContext"]["records"]
    if boundary in {"source_prepare", "source_commit", "source_bind", "response_link"}:
        assert saved_response["status"] == "admitted"
        assert not [o for o in occurrences(api) if o[1] == "DiscoveryOffer"]
    else:
        assert saved_response["status"] == "committed"
        assert saved_response["occurrenceId"]
    api.close()
    restored_trace, restored = reopened(tmp_path)
    try:
        result = restored.investigations.get(pending["id"])
        assert result["status"] == "completed", result["continuation"]["error"]
        assert result["continuation"]["processId"] == before["processId"]
        assert result["continuation"]["inquiry"]["id"] == before["inquiry"]["id"]
        assert result["attempt"] == native_result["attempt"]
        repaired_response = result["continuation"]["inquiry"]["responses"][0]
        assert repaired_response["id"] == saved_response["id"]
        assert repaired_response["evidenceContext"] == saved_response["evidenceContext"]
        if saved_response["occurrenceId"]:
            assert repaired_response["occurrenceId"] == saved_response["occurrenceId"]
        causal = occurrences(restored)
        assert len([o for o in causal if o[1] == "DiscoveryOffer"]) == 1
        assert len([o for o in causal if o[1] == "ModelProcessFinish"]) == 1
        assert successful(call(restored, inquiry_path(result) + "/responses", response_body)) == result
        assert successful(call(restored, f"/{result['id']}/resume", {})) == result
        assert occurrences(restored) == causal
        assert_one_native(restored_trace)
    finally:
        restored.close()
        restored_trace.close()


def test_runtime_error_visible_and_response_remains_addressable(native, monkeypatch):
    api, _, native_result, _ = native
    pending = begin(api, native_result)
    with monkeypatch.context() as fault:
        def unavailable(*args):
            raise RuntimeError("local realization temporarily unavailable")
        fault.setattr(api.investigation_runtime, "advance", unavailable)
        response = successful(call(api, inquiry_path(pending) + "/responses", {"requestId": "refusal", "decision": "refuse"}))
    continuation = response["continuation"]
    assert "temporarily unavailable" in continuation["error"]
    assert continuation["inquiry"]["responses"][0]["status"] == "committed"
    assert successful(call(api, inquiry_path(response), method="GET"))["responses"] == continuation["inquiry"]["responses"]
    assert successful(call(api, f"/{pending['id']}/resume", {}))["status"] == "completed"


def test_copied_public_continuation_cannot_supply_a_live_runtime_link(native, tmp_path):
    api, _, native_result, _ = native
    pending = begin(api, native_result)
    # This simulates a future historical import. No HTTP write/import route can
    # create this row today; even a copied public description is not admission.
    copied = json.loads(json.dumps(pending))
    copied["id"] = "historical-copy"
    api.store.db.execute("INSERT INTO investigations VALUES (?,?,?)", (copied["id"], copied["createdAtMs"], json.dumps(copied)))
    before = occurrences(api)
    assert call(api, "/historical-copy/resume", {})[0] == 409
    assert occurrences(api) == before
    assert successful(call(api, f"/{pending['id']}/resume", {}))["continuation"]["checkpointId"] == pending["continuation"]["checkpointId"]
    api.close()
    trace, restarted = reopened(tmp_path)
    try:
        assert call(restarted, "/historical-copy/resume", {})[0] == 409
        assert restarted.investigations.get("historical-copy")["continuation"]["error"]
        assert restarted.investigations.get(pending["id"])["continuation"]["checkpointId"] == pending["continuation"]["checkpointId"]
        assert occurrences(restarted) == before
    finally:
        restarted.close()
        trace.close()


@pytest.mark.parametrize("operation", ["continuation", "response"])
def test_failed_outer_intent_transaction_admits_no_semantic_work(native, monkeypatch, operation):
    api, _, native_result, _ = native
    if operation == "continuation":
        before = native_result
        path = f"/{native_result['id']}/continuation"
        body = continuation_body(native_result)
    else:
        before = begin(api, native_result)
        path = inquiry_path(before) + "/responses"
        body = {"requestId": "response-intent", "decision": "refuse"}
    causal = occurrences(api)
    original = api.investigations._save
    with monkeypatch.context() as fault:
        def fail_after_write(value):
            original(value)
            die()
        fault.setattr(api.investigations, "_save", fail_after_write)
        with pytest.raises(Crash):
            call(api, path, body)
    assert api.investigations.get(before["id"]) == before
    assert occurrences(api) == causal
    repaired = successful(call(api, path, body))
    assert repaired["status"] == ("pending" if operation == "continuation" else "completed")


@pytest.mark.parametrize("finished", [False, True])
def test_late_native_callbacks_cannot_overwrite_pending_or_finished_review(native, finished):
    api, _, native_result, _ = native
    current = begin(api, native_result)
    if finished:
        current = successful(call(api, inquiry_path(current) + "/responses", {
            "requestId": "finish-before-late-callback", "decision": "refuse",
        }))
    artifact = native_result["artifact"]
    native_payload = {key: artifact[key] for key in ("text", "outputSeqs", "citations", "unsupportedCitations")}
    assert api.investigations.complete(current["id"], native_payload) == current
    assert api.investigations.update_attempt(current["id"], status="failed", error="late callback") == current
    assert api.investigations.update_attempt(current["id"], status="unknown", error="late timeout") == current
