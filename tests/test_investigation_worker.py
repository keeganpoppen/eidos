from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

import pytest

from eidos.investigation_worker import NativeInvestigationError, NativeInvestigationWorker
from eidos.trace import TraceStore


FAKE_SERVER = r'''
import json, os, sys, time
mode = sys.argv[1]
waiting = None
def send(message):
    print(json.dumps(message), flush=True)
def finish(ident):
    turn = {"id": "worker-turn", "status": "inProgress", "items": []}
    if mode != "missing-ack":
        send({"id": ident, "result": {"turn": turn}, "futureAck": {"x": 1}})
    if mode == "timeout":
        return
    text = "Conclusion [evidence:7] [evidence:7] [evidence:999]."
    if mode == "output-limit":
        text = "x" * 10000
    item = {"id": "answer", "type": "agentMessage", "phase": "final", "text": text, "futureItem": ["kept"]}
    if mode == "final-answer":
        send({"method": "item/completed", "params": {"threadId": "worker-thread", "turnId": "worker-turn", "item": {"id": "progress", "type": "agentMessage", "phase": "commentary", "text": "I am investigating."}}})
        item["phase"] = "final_answer"
    send({"method": "item/completed", "params": {"threadId": "worker-thread", "turnId": "worker-turn", "item": item}})
    turn["status"] = "failed" if mode == "failed" else "completed"
    turn["error"] = {"message": "synthetic native failure"} if mode == "failed" else None
    send({"method": "turn/completed", "params": {"threadId": "worker-thread", "turn": turn}, "futureTerminal": True})
for line in sys.stdin:
    msg = json.loads(line)
    ident = msg.get("id")
    method = msg.get("method")
    if method == "initialize":
        send({"id": ident, "result": {"userAgent": "synthetic-investigation-worker"}})
    elif method == "thread/start":
        assert msg["params"]["cwd"] == os.getcwd()
        send({"id": ident, "result": {"thread": {"id": "worker-thread"}}})
    elif method == "mcpServerStatus/list":
        if mode == "mcp-tools":
            if msg["params"].get("cursor") is None:
                send({"id": ident, "result": {"data": [], "nextCursor": "second-page"}})
            else:
                send({"id": ident, "result": {"data": [{"tools": {"send_email": {}}, "runtimeStatus": "connected"}], "nextCursor": None}})
        elif mode == "mcp-pending":
            send({"id": ident, "result": {"data": [{"tools": {}, "runtimeStatus": "starting"}], "nextCursor": None}})
        else:
            send({"id": ident, "result": {"data": [], "nextCursor": None}})
            if mode == "stalled-reader":
                time.sleep(30)
    elif method == "turn/start":
        if mode == "interactive":
            waiting = ident
            send({"id": 900, "method": "item/tool/requestUserInput", "params": {"question": "authorize?"}})
        else:
            finish(ident)
    elif ident == 900 and waiting is not None:
        assert "error" in msg
        finish(waiting)
'''


@pytest.fixture
def context():
    return {
        "id": "context-test",
        "projectedPrompt": "Compare these two recorded decisions. Preserve citations.",
        "records": [{"seq": 7}, {"seq": 11}],
    }


def worker_at(tmp_path: Path, store: TraceStore, mode: str = "normal") -> NativeInvestigationWorker:
    script = tmp_path / "native_fake.py"
    script.write_text(FAKE_SERVER)
    return NativeInvestigationWorker(store, [sys.executable, str(script), mode])


def attempt(timeout: float = 3) -> dict:
    return {"id": "attempt-test", "contextId": "context-test", "timeoutSeconds": timeout}


def run_worker(worker, state, context):
    updates = []
    def update(**fields):
        if "source" in fields:
            assert worker.trace.records() == []
        updates.append(fields)
        state.update(fields)
    return worker.run(state, context, update), updates


def test_worker_sends_exact_frozen_prompt_and_retains_raw_unknown_fields(tmp_path, context):
    store = TraceStore(tmp_path / "trace.db")
    worker = worker_at(tmp_path, store)
    state = attempt()
    artifact, updates = run_worker(worker, state, context)

    assert updates[0] == {"source": state["source"]}
    assert state["threadId"] == "worker-thread"
    assert state["turnId"] == "worker-turn"
    assert state["status"] == "running"
    requests = [record for record in store.records() if record.direction == "client_to_appserver"]
    thread = next(record.message["params"] for record in requests if record.method == "thread/start")
    assert thread["sandbox"] == "read-only"
    assert thread["approvalPolicy"] == "never"
    assert thread["ephemeral"] is False
    assert thread["environments"] == []
    assert thread["config"] == {
        "features.apps": False, "features.shell_tool": False,
        "features.multi_agent": False, "features.hooks": False,
        "features.memories": False, "web_search": "disabled",
    }
    assert not Path(thread["cwd"]).exists()
    turn = next(record.message["params"] for record in requests if record.method == "turn/start")
    assert turn["input"] == [{"type": "text", "text": context["projectedPrompt"]}]
    assert turn["sandboxPolicy"] == {"type": "readOnly", "networkAccess": False}
    assert turn["environments"] == []
    output = store.get(artifact["outputSeqs"][0])
    assert output.message["params"]["item"]["futureItem"] == ["kept"]
    assert output.message["params"]["item"]["text"] == artifact["text"]
    assert artifact["citations"] == [7]
    assert artifact["unsupportedCitations"] == [999]
    assert any(record.message.get("futureTerminal") is True for record in store.records())


def test_recovery_after_completion_before_local_mapping_or_artifact_commit_never_sends(tmp_path, context):
    path = tmp_path / "trace.db"
    store = TraceStore(path)
    state = attempt()
    artifact, _ = run_worker(worker_at(tmp_path, store), state, context)
    store.close()
    reopened = TraceStore(path)
    count = len(reopened.records())
    # No executable is available to this recovery instance.
    recovering = NativeInvestigationWorker(reopened, ["/definitely/not/an/executable"])
    recovered_attempt = {**attempt(), "source": state["source"]}
    assert recovering.recover(recovered_attempt, context) == artifact
    assert recovering.recover(recovered_attempt, context) == artifact
    assert len(reopened.records()) == count


def test_missing_turn_ack_can_recover_recorded_terminal_output_without_resend(tmp_path, context):
    store = TraceStore()
    worker = worker_at(tmp_path, store, "missing-ack")
    state = attempt(0.4)
    with pytest.raises(NativeInvestigationError):
        worker.run(state, context, lambda **fields: state.update(fields))
    assert "turnId" not in state
    artifact = worker.recover(state, context)
    assert artifact is not None
    assert artifact["citations"] == [7]
    assert len([record for record in store.records() if record.method == "turn/start"]) == 1


def test_failed_native_terminal_with_text_never_becomes_success(tmp_path, context):
    store = TraceStore()
    worker = worker_at(tmp_path, store, "failed")
    state = attempt()
    with pytest.raises(NativeInvestigationError, match="synthetic native failure") as failed:
        worker.run(state, context, lambda **fields: state.update(fields))
    assert failed.value.status == "failed"
    with pytest.raises(NativeInvestigationError) as recovered:
        worker.recover(state, context)
    assert recovered.value.status == "failed"
    assert any(record.method == "item/completed" for record in store.records())


def test_interactive_request_is_explicitly_rejected_while_turn_rpc_is_pending(tmp_path, context):
    store = TraceStore()
    state = attempt()
    artifact, _ = run_worker(worker_at(tmp_path, store, "interactive"), state, context)
    assert artifact["text"]
    rejected = next(record for record in store.records() if record.direction == "client_to_appserver" and record.message.get("id") == 900)
    assert rejected.message["error"]["code"] == -32000


def test_timeout_closes_owned_process_and_retains_uncertain_attempt(tmp_path, context):
    store = TraceStore()
    state = attempt(0.3)
    worker = worker_at(tmp_path, store, "timeout")
    with pytest.raises(NativeInvestigationError, match="deadline") as failure:
        worker.run(state, context, lambda **fields: state.update(fields))
    assert failure.value.status == "unknown"
    assert state["turnId"] == "worker-turn"
    assert worker.recover(state, context) is None
    params = next(record.message["params"] for record in store.records() if record.method == "thread/start")
    assert not Path(params["cwd"]).exists()


def test_output_limit_preserves_received_evidence_without_admitting_artifact(tmp_path, context):
    store = TraceStore()
    state = attempt()
    worker = worker_at(tmp_path, store, "output-limit")
    worker.MAX_OUTPUT_CHARS = 2000
    with pytest.raises(NativeInvestigationError, match="output limit"):
        worker.run(state, context, lambda **fields: state.update(fields))
    assert any(record.method == "item/completed" for record in store.records())
    with pytest.raises(NativeInvestigationError, match="output limit"):
        worker.recover(state, context)


def test_recovery_rejects_wrong_context_thread_and_incarnation(tmp_path, context):
    store = TraceStore()
    worker = worker_at(tmp_path, store)
    state = attempt()
    run_worker(worker, state, context)
    with pytest.raises(ValueError, match="different context"):
        worker.recover({**state, "contextId": "other-context"}, context)
    with pytest.raises(NativeInvestigationError, match="frozen context"):
        worker.recover(state, {**context, "projectedPrompt": "substituted prompt"})
    with pytest.raises(NativeInvestigationError, match="thread"):
        worker.recover({**state, "threadId": "other-thread"}, context)
    assert worker.recover({**state, "source": "other-incarnation"}, context) is None


def test_prepared_attempt_and_outbound_only_trace_remain_pending(context):
    store = TraceStore()
    worker = NativeInvestigationWorker(store)
    assert worker.recover(attempt(), context) is None
    state = {**attempt(), "source": "test-worker"}
    store.append(source=state["source"], direction="client_to_appserver", message={
        "id": 1, "method": "turn/start", "params": {
            "threadId": "worker-thread",
            "input": [{"type": "text", "text": context["projectedPrompt"]}],
        },
    })
    assert worker.recover(state, context) is None


@pytest.mark.parametrize("mode", ["mcp-tools", "mcp-pending"])
def test_configured_or_unresolved_mcp_tools_block_native_turn(tmp_path, context, mode):
    store = TraceStore()
    worker = worker_at(tmp_path, store, mode)
    state = attempt()
    with pytest.raises(NativeInvestigationError, match="MCP") as failure:
        worker.run(state, context, lambda **fields: state.update(fields))
    assert failure.value.status == "failed"
    assert not any(record.method == "turn/start" for record in store.records())
    assert worker.recover(state, context) is None


def test_closed_worker_cannot_launch_new_owned_process(tmp_path, context):
    store = TraceStore()
    worker = worker_at(tmp_path, store)
    worker.close()
    with pytest.raises(NativeInvestigationError, match="closed"):
        worker.run(attempt(), context, lambda **fields: None)
    assert store.records() == []


def test_close_interrupts_an_active_owned_worker(tmp_path, context):
    store = TraceStore()
    worker = worker_at(tmp_path, store, "timeout")
    state = attempt()
    running = threading.Event()
    failures = []
    def update(**fields):
        state.update(fields)
        if fields.get("status") == "running":
            running.set()
    def run():
        try:
            worker.run(state, context, update)
        except NativeInvestigationError as exc:
            failures.append(exc)
    thread = threading.Thread(target=run)
    thread.start()
    assert running.wait(timeout=2)
    worker.close()
    thread.join(timeout=3)
    assert not thread.is_alive()
    assert len(failures) == 1
    assert failures[0].status == "unknown"
    assert worker.recover(state, context) is None


def test_recovery_can_attribute_text_in_terminal_payload_without_item_event(context):
    store = TraceStore()
    state = {**attempt(), "source": "native-incarnation"}
    store.append(source=state["source"], direction="client_to_appserver", message={
        "id": 1, "method": "turn/start", "params": {
            "threadId": "thread", "input": [{"type": "text", "text": context["projectedPrompt"]}],
        },
    })
    terminal = store.append(source=state["source"], direction="appserver_to_client", message={
        "method": "turn/completed", "params": {
            "threadId": "thread", "turn": {"id": "turn", "status": "completed", "items": [
                {"id": "final", "type": "agentMessage", "phase": "final", "text": "Result [evidence:11]."},
            ]},
        },
    })
    artifact = NativeInvestigationWorker(store).recover(state, context)
    assert artifact == {
        "text": "Result [evidence:11].", "outputSeqs": [terminal.seq],
        "citations": [11], "unsupportedCitations": [],
    }


def test_native_final_answer_phase_excludes_completed_commentary(tmp_path, context):
    store = TraceStore()
    artifact, _ = run_worker(worker_at(tmp_path, store, "final-answer"), attempt(), context)
    assert artifact["text"].startswith("Conclusion")
    assert "I am investigating" not in artifact["text"]
    assert len(artifact["outputSeqs"]) == 1


def test_close_between_native_rpcs_cannot_restart_same_incarnation(tmp_path, context):
    store = TraceStore()
    worker = worker_at(tmp_path, store)
    def update(**fields):
        if fields.get("threadId"):
            worker.close()
    with pytest.raises(NativeInvestigationError):
        worker.run(attempt(), context, update)
    assert len([r for r in store.records() if r.method == "initialize"]) == 1
    assert not [r for r in store.records() if r.method == "turn/start"]


def test_deadline_interrupts_large_prompt_when_native_stops_reading(tmp_path, context):
    store = TraceStore()
    worker = worker_at(tmp_path, store, "stalled-reader")
    context = {**context, "projectedPrompt": "x" * 120_000}
    started = time.monotonic()
    with pytest.raises(NativeInvestigationError, match="deadline"):
        worker.run(attempt(0.3), context, lambda **fields: None)
    assert time.monotonic() - started < 3
    assert len([r for r in store.records() if r.method == "turn/start"]) == 1
