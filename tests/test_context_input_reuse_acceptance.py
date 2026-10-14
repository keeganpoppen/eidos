"""Independent stored-history acceptance; all source/result data is authored.

These cases exercise SQLite and the public store operations. They never launch
native work, and source deletion below is an explicit trusted fixture mutation.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack, closing
import json
import sqlite3
from threading import Barrier

import pytest

from eidos.investigation import InvestigationError, InvestigationStore
from eidos.trace import TraceStore


def seed(trace):
    store = InvestigationStore(trace)
    for number in range(1, 4):
        trace.append_line(source="synthetic/context-reuse", direction="internal",
            raw_text=json.dumps({"method": "$history/item", "params": {
                "threadId": "reuse-source", "item": {"id": str(number),
                "type": "agentMessage", "text": f"Authored record {number}",
                "futureField": {"authority": "copied description only"}}}}, indent=1))
    selection = lambda seq: {"threadId": "reuse-source", "startSeq": seq,
                            "endSeq": seq, "rationale": f"Retain exact record {seq}"}
    artifact_owner = store.create({"requestId": "source-artifact", "title": "Original result",
        "question": "What is recorded?", "selections": [selection(1)]})
    claimed, _ = store.claim(artifact_owner["id"], artifact_owner["currentContextId"])
    store.update_attempt(claimed["id"], source="synthetic/completion", threadId="authored-worker",
                         turnId="authored-turn", status="running")
    text = "Authored result preserves uncertainty [evidence:1]."
    output = trace.append(source="synthetic/completion", direction="appserver_to_client", message={
        "method": "item/completed", "params": {"threadId": "authored-worker", "turnId": "authored-turn",
        "item": {"id": "answer", "type": "agentMessage", "text": text}}})
    completed = store.complete(claimed["id"], {"text": text, "outputSeqs": [output.seq],
                                              "executionEvidence": "synthetic"})
    reviewed = store.adopt(completed["id"], {"artifactId": completed["artifact"]["id"],
                                             "decision": "reject", "note": "Frozen historical review"})
    source = store.create({"requestId": "frozen-source", "title": "Frozen packet",
        "question": "Old question", "selections": [selection(1), selection(3)],
        "artifactInputs": [{"investigationId": reviewed["id"], "artifactId": reviewed["artifact"]["id"],
                            "rationale": "Inspect the attributed result"}]})
    return store, source, reviewed, selection


def reuse(source, **changes):
    return {"requestId": "reuse-request", "title": "Independent new work", "question": "New bounded question",
            "inputSource": {"investigationId": source["id"], "contextId": source["contexts"][0]["id"]},
            **changes}


def counts(trace):
    return {name: trace.db.execute(f"SELECT count(*) FROM {name}").fetchone()[0]
            for name in ("investigations", "investigation_requests", "cm_objects", "cm_events", "cm_requests")}


def remove_owner(trace, identifier):
    trace.db.execute("DELETE FROM investigation_requests WHERE investigation_id=?", (identifier,))
    trace.db.execute("DELETE FROM investigations WHERE id=?", (identifier,))


def test_frozen_context_suffices_after_underlying_rows_and_artifact_owner_disappear(tmp_path):
    with closing(TraceStore(tmp_path / "history.db")) as trace:
        store, source, reviewed, _ = seed(trace)
        original = source["contexts"][0]
        remove_owner(trace, reviewed["id"])
        trace.db.execute("DELETE FROM trace_records")
        source_before = store.get(source["id"])

        def no_current_raw_read(action, table, *_):
            return sqlite3.SQLITE_DENY if action == sqlite3.SQLITE_READ and table == "trace_records" else sqlite3.SQLITE_OK

        trace.db.set_authorizer(no_current_raw_read)
        try:
            created = store.create(reuse(source))
        finally:
            trace.db.set_authorizer(None)
        packet = created["contexts"][0]
        for field in ("selections", "records", "artifactInputs"):
            assert packet[field] == original[field]
        assert packet["artifactInputs"][0]["sourceAdoption"] == reviewed["adoption"]
        assert packet["question"] == "New bounded question" and packet["parentContextId"] is None
        assert packet["inputOrigin"]["contextId"] == original["id"]
        assert created["attempt"] is None and created["artifact"] is None
        assert store.get(source["id"]) == source_before
        assert trace.records() == []


def test_exact_concurrent_retry_serializes_across_database_connections(tmp_path):
    path = tmp_path / "concurrent.db"
    with ExitStack() as stack:
        traces = [stack.enter_context(closing(TraceStore(path))) for _ in range(6)]
        first, source, _, _ = seed(traces[0])
        stores = [first, *(InvestigationStore(trace) for trace in traces[1:])]
        before = counts(traces[0])
        barrier = Barrier(len(stores))

        def create(store):
            barrier.wait(timeout=5)
            return store.create(reuse(source))

        with ThreadPoolExecutor(max_workers=len(stores)) as pool:
            results = list(pool.map(create, stores))
        assert all(result == results[0] for result in results)
        after = counts(traces[0])
        assert after["investigations"] == before["investigations"] + 1
        assert after["investigation_requests"] == before["investigation_requests"] + 1
        assert after["cm_events"] == before["cm_events"] + 1
        assert after["cm_requests"] == before["cm_requests"]
        assert stores[-1].create(reuse(source)) == results[0]
        assert counts(traces[0]) == after
        with pytest.raises(InvestigationError) as failure:
            stores[-1].create(reuse(source, question="Conflicting question"))
        assert failure.value.status == 409 and counts(traces[0]) == after


def test_lost_create_reply_can_return_progressed_target_without_rebinding_original(tmp_path):
    path = tmp_path / "replay.db"
    with closing(TraceStore(path)) as trace:
        store, source, _, selection = seed(trace)
        body = reuse(source)
        created = store.create(body)
        exact_created_context = created["contexts"][0]
        revised = store.revise(created["id"], {"requestId": "other-host-revision",
            "parentContextId": created["currentContextId"], "question": "Later unrelated question",
            "selections": [selection(2)]})
        remove_owner(trace, source["id"])
        before = counts(trace)
        assert store.create(body) == revised
        assert counts(trace) == before
    with closing(TraceStore(path)) as reopened:
        replay = InvestigationStore(reopened).create(body)
        assert replay == revised
        assert replay["currentContextId"] != exact_created_context["id"]
        assert replay["contexts"][0] == exact_created_context
        assert replay["contexts"][0]["inputOrigin"] == {
            "version": 1, "kind": "historical-context-inputs", "investigationId": source["id"],
            "contextId": source["contexts"][0]["id"], "manifestId": source["contexts"][0]["manifestId"]}
        assert replay["attempt"] is None
