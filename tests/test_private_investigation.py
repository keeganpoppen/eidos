from __future__ import annotations

import base64
import json
from pathlib import Path
import sys
import subprocess
import threading
import time

import pytest

from eidos.investigation_inquiries import parse_terminal_inquiry
from eidos.investigation_worker import NativeInvestigationWorker
from eidos.private_investigation import (
    PrivateEvidenceError, PrivateEvidenceLimits, PrivateInvestigationWorker, _PrivateTrace, validate_publication,
)
from eidos.trace import TraceStore


FIXTURE = Path(__file__).parent / "fixtures" / "private_investigation_server.py"


def setup(tmp_path, mode="conclusion", *, limits=None):
    trace = TraceStore(tmp_path / "main.sqlite")
    marker = tmp_path / "launches"
    command = [sys.executable, str(FIXTURE), mode, str(marker)]
    worker = PrivateInvestigationWorker(trace, command, execution_evidence="synthetic", limits=limits)
    context = {"id": "context-public", "question": "A bounded fixture question", "projectedPrompt": "Selected public record [evidence:7].",
               "records": [{"seq": 7, "rawText": "public input"}]}
    attempt = {"id": "attempt-public", "contextId": context["id"], "timeoutSeconds": 3,
               "source": None, "threadId": None, "turnId": None}
    return trace, worker, attempt, context, marker


def main_dump(trace):
    return "\n".join(trace.db.iterdump())


def evidence(worker, attempt, context, result):
    return worker.resolve_result_evidence(attempt, context, result)


def test_private_bytes_and_late_unknown_fields_never_enter_publication(tmp_path):
    trace, worker, attempt, context, marker = setup(tmp_path)
    trace.append(source="ordinary", direction="internal", message={"method": "fixture/public"})
    progress = []
    result = worker.run(attempt, context, lambda **fields: attempt.update(fields), on_event=progress.append)
    proof = evidence(worker, attempt, context, result)
    private = proof["trace"]
    assert marker.read_text() == "started\n"
    assert progress == []
    assert result["outputSeqs"] == [2]
    assert proof["artifact"]["outputSeqs"] != result["outputSeqs"]
    assert result["citations"] == [7] and result["unsupportedCitations"] == [999]
    assert result["executionEvidence"] == "synthetic"
    assert "PRIVATE_" not in main_dump(trace)
    login = next(r for r in private.records() if r.method == "account/login/completed")
    assert login.raw_text == ' { "method" : "account/login/completed", "params": {"loginId":"PRIVATE_LOGIN_CANARY", "future": [1, {"code":"PRIVATE_CODE_CANARY"}]}} '
    stderr = next(r.message["params"] for r in private.records() if r.method == "$transport/stderr")
    assert base64.b64decode(stderr["capturedBase64"]) == b"PRIVATE_STDERR_CANARY  unknown bytes\t\n"
    assert "PRIVATE_LATE_CANARY" in "".join(r.raw_text for r in private.records())
    assert "PRIVATE_OUTPUT_UNKNOWN_CANARY" in "".join(r.raw_text for r in private.records())
    public = trace.get(2)
    assert public.direction == "internal" and public.method == "$capsule/result"
    assert public.source == attempt["source"] and public.thread_id == attempt["threadId"]
    assert public.message["params"]["provenance"] == {"kind": "private-capsule", "capsuleId": proof["capsuleId"]}
    for path in worker.root.rglob("*"):
        assert path.stat().st_mode & 0o077 == 0
    with pytest.raises(ValueError):
        TraceStore(private.path)
    worker.close()
    worker.close_evidence()
    trace.close()


@pytest.mark.parametrize("when", ["before", "after"])
def test_publication_crash_then_reopen_recovers_without_resend(tmp_path, monkeypatch, when):
    trace, worker, attempt, context, marker = setup(tmp_path)
    original = worker._publish

    def interrupted(binding, artifact):
        if when == "after":
            original(binding, artifact)
        raise RuntimeError("PRIVATE_CALLBACK_CANARY")

    monkeypatch.setattr(worker, "_publish", interrupted)
    with pytest.raises(PrivateEvidenceError) as caught:
        worker.run(attempt, context, lambda **fields: attempt.update(fields))
    assert "PRIVATE_" not in str(caught.value)
    assert "PRIVATE_" not in main_dump(trace)
    command = worker.command
    worker.close()
    worker.close_evidence()
    trace.close()
    reopened = TraceStore(tmp_path / "main.sqlite")
    recovered = PrivateInvestigationWorker(reopened, command, execution_evidence="synthetic")
    first = recovered.recover(attempt, context)
    assert first is not None
    assert recovered.run(attempt, context, lambda **fields: pytest.fail("retry callback")) == first
    assert recovered.recover(attempt, context) == first
    assert len(reopened.records()) == 1
    assert marker.read_text() == "started\n"
    assert validate_publication(reopened, attempt, context, first) == first
    recovered.close()
    recovered.close_evidence()
    reopened.close()


def test_validator_works_inside_completion_transaction_and_rejects_spoofs(tmp_path):
    trace, worker, attempt, context, marker = setup(tmp_path)
    result = worker.run(attempt, context, lambda **fields: attempt.update(fields))
    trace.db.execute("BEGIN IMMEDIATE")
    assert validate_publication(trace, attempt, context, result) == result
    trace.db.rollback()
    for changed in ({**result, "text": "different"}, {**result, "executionEvidence": "native-observed"},
                    {**result, "outputEvidence": {**result["outputEvidence"], "capsuleId": "capsule_wrong"}},
                    {**result, "citations": [999]}):
        with pytest.raises(PrivateEvidenceError):
            validate_publication(trace, attempt, context, changed)
    publication = trace.get(result["outputSeqs"][0])
    copied = trace.append(source=publication.source, direction="appserver_to_client", message=publication.message)
    with pytest.raises(PrivateEvidenceError):
        validate_publication(trace, attempt, context, {**result, "outputSeqs": [copied.seq]})
    for changed in ({**context, "projectedPrompt": "changed"}, {**context, "id": "different"}):
        with pytest.raises(PrivateEvidenceError):
            worker.recover(attempt, changed)
    with pytest.raises(PrivateEvidenceError):
        worker.resolve_result_evidence({**attempt, "source": "other-incarnation"}, context, result)
    worker.close()
    worker.close_evidence()
    trace.close()


@pytest.mark.parametrize("mode,needle", [("rpc-error", "PRIVATE_ERROR_CANARY"), ("malformed", "PRIVATE_MALFORMED_CANARY")])
def test_failures_are_private_and_never_publish(tmp_path, mode, needle):
    trace, worker, attempt, context, marker = setup(tmp_path, mode)
    with pytest.raises(PrivateEvidenceError) as caught:
        worker.run(attempt, context, lambda **fields: attempt.update(fields))
    assert "PRIVATE_" not in str(caught.value)
    assert trace.records() == [] and "PRIVATE_" not in main_dump(trace)
    private = next(iter(worker._stores.values()))
    records = private.records()
    if mode == "malformed":
        gap = next(r.message["params"] for r in records if r.method == "$transport/captureGap")
        assert needle.encode() in base64.b64decode(gap["capturedBase64"])
    else:
        assert needle in "".join(r.raw_text for r in records)
    assert worker.recover(attempt, context) is None
    worker.close()
    worker.close_evidence()
    trace.close()


def test_retention_and_outbound_limits_stop_without_relaunch(tmp_path):
    limits = PrivateEvidenceLimits(max_capsules=1, max_outbound_records=1)
    trace, worker, attempt, context, marker = setup(tmp_path, limits=limits)
    with pytest.raises(PrivateEvidenceError):
        worker.run(attempt, context, lambda **fields: attempt.update(fields))
    private = next(iter(worker._stores.values()))
    assert len([r for r in private.records() if r.direction == "client_to_appserver"]) == 1
    with pytest.raises(PrivateEvidenceError, match="retention-limit"):
        worker.run({**attempt, "id": "another", "source": None}, context, lambda **fields: None)
    with pytest.raises(PrivateEvidenceError, match="outcome-unknown"):
        worker.run(attempt, context, lambda **fields: None)
    assert marker.read_text() == "started\n"
    worker.close()
    worker.close_evidence()
    trace.close()


def test_record_limit_preserves_rejected_frame_in_private_gap(tmp_path):
    trace, worker, attempt, context, marker = setup(tmp_path, limits=PrivateEvidenceLimits(max_records=4))
    with pytest.raises(PrivateEvidenceError):
        worker.run(attempt, context, lambda **fields: attempt.update(fields))
    private = next(iter(worker._stores.values()))
    gaps = [r.message["params"] for r in private.records() if r.method == "$transport/captureGap"]
    assert len(gaps) == 1
    assert gaps[0]["captureComplete"] is False
    assert gaps[0]["capturedBytes"] > 0
    assert "PRIVATE_" not in main_dump(trace)
    assert private._counts["records"] <= 4
    worker.close()
    worker.close_evidence()
    trace.close()


def test_inquiry_resolver_returns_original_final_event_and_request(tmp_path):
    trace, worker, attempt, context, marker = setup(tmp_path, "inquiry")
    result = worker.run(attempt, context, lambda **fields: attempt.update(fields))
    assert parse_terminal_inquiry(result["text"]) is not None
    proof = evidence(worker, attempt, context, result)
    event = proof["trace"].get(proof["artifact"]["outputSeqs"][0])
    assert event.method == "item/completed" and event.direction == "appserver_to_client"
    assert event.message["params"]["item"]["phase"] == "final"
    assert event.message["params"]["item"]["text"] == result["text"]
    requests = [r for r in proof["trace"].records() if r.method == "turn/start"]
    assert len(requests) == 1 and requests[0].seq < event.seq
    assert requests[0].message["params"]["input"] == [{"type": "text", "text": context["projectedPrompt"]}]
    assert proof["attempt"]["source"] == attempt["source"]
    assert "PRIVATE_" not in main_dump(trace)
    worker.close()
    worker.close_evidence()
    trace.close()


def test_memory_host_retains_private_root_across_adapters():
    trace = TraceStore(":memory:")
    one = PrivateInvestigationWorker(trace, [sys.executable, str(FIXTURE), "conclusion"])
    two = PrivateInvestigationWorker(trace, [sys.executable, str(FIXTURE), "conclusion"])
    assert one.root == two.root
    one.close()
    one.close_evidence()
    assert two.root.is_dir()
    two.close()
    two.close_evidence()
    trace.close()


def test_limits_reject_nonfinite_or_boolean_values():
    for value in (0, -1, True, 1.5, float("inf")):
        with pytest.raises(ValueError):
            PrivateEvidenceLimits(max_capsules=value)


def test_recovery_hydrates_binding_after_lost_mapping_and_preserves_publication(tmp_path):
    trace, worker, attempt, context, marker = setup(tmp_path)
    result = worker.run(attempt, context, lambda **fields: attempt.update(fields))
    row = trace.db.execute("SELECT state_json FROM private_investigation_bindings").fetchone()
    state = json.loads(row[0])
    del state["attempt"]["turnId"]
    trace.db.execute("DELETE FROM private_investigation_publications")
    trace.db.execute("DELETE FROM trace_records")
    trace.db.execute("UPDATE private_investigation_bindings SET state_json=?", (json.dumps(state),))
    attempt["turnId"] = None
    recovered = worker.recover(attempt, context)
    assert recovered is not None and recovered["text"] == result["text"]
    assert trace.get(recovered["outputSeqs"][0]).turn_id == "private-fixture-turn"
    assert marker.read_text() == "started\n"
    worker.close()
    worker.close_evidence()
    trace.close()


def test_private_conflict_after_publication_is_not_silently_reused(tmp_path):
    trace, worker, attempt, context, marker = setup(tmp_path)
    result = worker.run(attempt, context, lambda **fields: attempt.update(fields))
    proof = evidence(worker, attempt, context, result)
    original = proof["trace"].get(proof["artifact"]["outputSeqs"][0])
    altered = original.message
    altered["params"]["item"]["text"] = "different conclusion"
    proof["trace"].append(source=attempt["source"], direction="appserver_to_client", message=altered)
    proof["trace"].append(source=attempt["source"], direction="appserver_to_client", message={
        "method": "turn/completed", "params": {"threadId": attempt["threadId"], "turn": {"id": attempt["turnId"], "status": "completed"}},
    })
    with pytest.raises(PrivateEvidenceError):
        worker.recover(attempt, context)
    assert len(trace.records()) == 1
    assert marker.read_text() == "started\n"
    worker.close()
    worker.close_evidence()
    trace.close()


def test_missing_private_proof_keeps_public_receipt_but_cannot_resolve(tmp_path):
    trace, worker, attempt, context, marker = setup(tmp_path)
    result = worker.run(attempt, context, lambda **fields: attempt.update(fields))
    path = Path(evidence(worker, attempt, context, result)["trace"].path)
    worker.close_evidence()
    path.unlink()
    assert worker.recover(attempt, context) == result
    with pytest.raises(PrivateEvidenceError, match="unavailable"):
        worker.resolve_result_evidence(attempt, context, result)
    assert marker.read_text() == "started\n"
    worker.close()
    worker.close_evidence()
    trace.close()


def test_failed_terminal_classification_survives_private_recovery(tmp_path):
    trace, worker, attempt, context, marker = setup(tmp_path, "failed")
    with pytest.raises(PrivateEvidenceError) as first:
        worker.run(attempt, context, lambda **fields: attempt.update(fields))
    assert first.value.status == "failed"
    with pytest.raises(PrivateEvidenceError) as second:
        worker.recover(attempt, context)
    assert second.value.status == "failed"
    assert "PRIVATE_" not in str(second.value) and "PRIVATE_" not in main_dump(trace)
    assert "PRIVATE_" not in worker.public_error(RuntimeError("PRIVATE_OTHER_CANARY"))
    worker.close()
    worker.close_evidence()
    trace.close()


def test_close_cancels_owned_process_and_keeps_sink_until_callbacks_join(tmp_path):
    trace, worker, attempt, context, marker = setup(tmp_path, "waiting")
    running = threading.Event()
    outcomes = []

    def update(**fields):
        attempt.update(fields)
        if fields.get("status") == "running":
            running.set()

    def run():
        try:
            worker.run(attempt, context, update)
        except PrivateEvidenceError as exc:
            outcomes.append(exc)

    thread = threading.Thread(target=run)
    thread.start()
    assert running.wait(2)
    with pytest.raises(PrivateEvidenceError, match="worker-still-closing"):
        worker.close_evidence()
    worker.close()
    thread.join(3)
    assert not thread.is_alive() and len(outcomes) == 1
    assert worker.recover(attempt, context) is None
    assert marker.read_text() == "started\n" and trace.records() == []
    worker.close_evidence()
    trace.close()


def test_concurrent_adapter_claim_does_not_relaunch_owned_attempt(tmp_path):
    trace, worker, attempt, context, marker = setup(tmp_path, "waiting")
    other_trace = TraceStore(tmp_path / "main.sqlite")
    other = PrivateInvestigationWorker(other_trace, worker.command, execution_evidence="synthetic")
    running = threading.Event()
    errors = []

    def update(**fields):
        attempt.update(fields)
        if fields.get("status") == "running":
            running.set()

    def first():
        try:
            worker.run(attempt, context, update)
        except PrivateEvidenceError as exc:
            errors.append(exc)

    thread = threading.Thread(target=first)
    thread.start()
    assert running.wait(2)
    with pytest.raises(PrivateEvidenceError, match="outcome-unknown"):
        other.run(dict(attempt), context, lambda **fields: pytest.fail("duplicate callback"))
    assert marker.read_text() == "started\n"
    worker.close()
    thread.join(3)
    assert not thread.is_alive() and len(errors) == 1
    worker.close_evidence()
    other.close()
    other.close_evidence()
    other_trace.close()
    trace.close()


def test_existing_public_native_recording_recovers_unchanged(tmp_path):
    trace, private, attempt, context, marker = setup(tmp_path)
    legacy = NativeInvestigationWorker(trace, private.command, execution_evidence="synthetic")
    original = legacy.run(attempt, context, lambda **fields: attempt.update(fields))
    assert private.recover(attempt, context) == original
    assert "outputEvidence" not in original
    assert trace.db.execute("SELECT COUNT(*) FROM private_investigation_bindings").fetchone()[0] == 0
    assert marker.read_text() == "started\n"
    legacy.close()
    private.close()
    private.close_evidence()
    trace.close()


def test_equal_numeric_sequences_keep_private_and_public_namespaces_distinct(tmp_path, monkeypatch):
    trace, worker, attempt, context, marker = setup(tmp_path)
    original = worker._publish

    def collide(binding, artifact):
        target = artifact["outputSeqs"][0]
        for _ in range(target - 1):
            trace.append(source="public-padding", direction="internal", message={"method": "fixture/padding"})
        return original(binding, artifact)

    monkeypatch.setattr(worker, "_publish", collide)
    result = worker.run(attempt, context, lambda **fields: attempt.update(fields))
    proof = evidence(worker, attempt, context, result)
    assert result["outputSeqs"] == proof["artifact"]["outputSeqs"]
    seq = result["outputSeqs"][0]
    assert trace.get(seq).method == "$capsule/result"
    assert proof["trace"].get(seq).method == "item/completed"
    assert "PRIVATE_" not in main_dump(trace)
    worker.close()
    worker.close_evidence()
    trace.close()


def test_publication_and_ledger_insert_rollback_together(tmp_path):
    trace, worker, attempt, context, marker = setup(tmp_path)
    trace.db.execute("CREATE TRIGGER fail_publication BEFORE INSERT ON private_investigation_publications BEGIN SELECT RAISE(ABORT, 'PRIVATE_SQL_CANARY'); END")
    with pytest.raises(PrivateEvidenceError) as caught:
        worker.run(attempt, context, lambda **fields: attempt.update(fields))
    assert "PRIVATE_" not in str(caught.value)
    assert trace.records() == []
    assert trace.db.execute("SELECT COUNT(*) FROM private_investigation_publications").fetchone()[0] == 0
    trace.db.execute("DROP TRIGGER fail_publication")
    result = worker.recover(attempt, context)
    assert result is not None and len(trace.records()) == 1
    assert marker.read_text() == "started\n"
    worker.close()
    worker.close_evidence()
    trace.close()


def test_private_record_budget_is_shared_across_connections(tmp_path):
    limits = PrivateEvidenceLimits(max_records=1)
    one = _PrivateTrace(tmp_path / "private.sqlite", limits)
    two = _PrivateTrace(tmp_path / "private.sqlite", limits)
    one.append(source="fixture", direction="internal", message={"method": "first"})
    with pytest.raises(PrivateEvidenceError, match="record-limit"):
        two.append(source="fixture", direction="internal", message={"method": "second"})
    assert len(two.records()) == 1
    one.close()
    two.close()


@pytest.mark.parametrize("concurrent_recovery", [False, True])
def test_no_publication_before_closed_source_revalidation(tmp_path, monkeypatch, concurrent_recovery):
    trace, worker, attempt, context, marker = setup(tmp_path, "late-failed")
    release = tmp_path / "release-late-terminal"
    worker.command = (*worker.command, str(release))
    other_trace = TraceStore(tmp_path / "main.sqlite")
    other = PrivateInvestigationWorker(other_trace, worker.command, execution_evidence="synthetic")
    original = NativeInvestigationWorker.recover
    challenged = []

    def delayed_return(inner, bound, packet):
        result = original(inner, bound, packet)
        if result is not None and not release.exists():
            if concurrent_recovery:
                assert other.recover(dict(attempt), context) is None
                assert trace.records() == []
            challenged.append(True)
            release.touch()
            deadline = time.monotonic() + 2
            while not any("PRIVATE_LATE_FAILURE_CANARY" in record.raw_text for record in inner.trace.records()):
                assert time.monotonic() < deadline, "authored late native frame was not recorded"
                time.sleep(0.005)
        return result

    monkeypatch.setattr(NativeInvestigationWorker, "recover", delayed_return)
    with pytest.raises(PrivateEvidenceError) as caught:
        worker.run(attempt, context, lambda **fields: attempt.update(fields))
    assert challenged == [True]
    assert "PRIVATE_" not in str(caught.value)
    assert trace.records() == []
    assert trace.db.execute("SELECT COUNT(*) FROM private_investigation_publications").fetchone()[0] == 0
    assert marker.read_text() == "started\n"
    with pytest.raises(PrivateEvidenceError):
        worker.recover(attempt, context)
    worker.close()
    worker.close_evidence()
    other.close()
    other.close_evidence()
    other_trace.close()
    trace.close()


def test_recorder_host_crash_releases_writer_exclusion_for_evidence_recovery(tmp_path):
    trace, worker, attempt, context, marker = setup(tmp_path)
    host = '''
import json,os,sys
from eidos.trace import TraceStore
from eidos.private_investigation import PrivateInvestigationWorker
trace=TraceStore(sys.argv[1])
worker=PrivateInvestigationWorker(trace,json.loads(sys.argv[2]),execution_evidence='synthetic')
worker._publish=lambda binding,artifact: os._exit(0)
attempt=json.loads(sys.argv[3]); context=json.loads(sys.argv[4])
worker.run(attempt,context,lambda **fields: attempt.update(fields))
raise RuntimeError('fixture host did not exit at publication boundary')
'''
    subprocess.run([sys.executable, "-c", host, trace.path, json.dumps(worker.command), json.dumps(attempt), json.dumps(context)],
                   check=True, timeout=10, capture_output=True)
    assert trace.records() == []
    result = worker.recover(attempt, context)
    assert result is not None and result["text"].startswith("Authored conclusion")
    assert worker.recover(attempt, context) == result
    assert marker.read_text() == "started\n"
    worker.close()
    worker.close_evidence()
    trace.close()
