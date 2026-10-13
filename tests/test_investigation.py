from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path

import pytest

from eidos.investigation import InvestigationError, InvestigationStore
from eidos.trace import TraceStore


def seed(trace: TraceStore) -> dict:
    trace.append_line(
        source="native/source-a",
        direction="client_to_appserver",
        raw_text='{"id":7, "method":"turn/start", "params":{"threadId":"a","input":[]}, "futureField":{"keep":"exact bytes"}}',
    )
    trace.append(source="native/source-b", direction="appserver_to_client", message={
        "method": "item/completed", "params": {"threadId": "b", "turnId": "b-turn", "item": {
            "id": "b-distractor", "type": "agentMessage", "text": "exclude this interleaved record",
        }},
    })
    trace.append(source="native/source-a", direction="appserver_to_client", message={
        "method": "item/completed", "params": {"threadId": "a", "turnId": "a-turn", "item": {
            "id": "a-decision", "type": "agentMessage", "text": "retain uncertain outcomes",
        }},
    })
    trace.append(source="history/import", direction="internal", message={
        "method": "$history/item", "params": {"threadId": "b", "turnId": "b-turn", "item": {
            "id": "b-alternative", "type": "agentMessage", "text": "rejected: silently retry external work",
        }},
    })
    return {
        "requestId": "create-1",
        "title": "Compare recovery choices",
        "question": "Which approach preserves uncertainty?",
        "selections": [
            {"threadId": "a", "startSeq": 1, "endSeq": 3, "rationale": "current decision"},
            {"threadId": "b", "startSeq": 4, "endSeq": 4, "rationale": "rejected alternative"},
        ],
    }


def revision(investigation: dict, *, request_id: str = "revise-1") -> dict:
    return {
        "requestId": request_id,
        "parentContextId": investigation["currentContextId"],
        "question": "What is still unknown?",
        "selections": investigation["contexts"][-1]["selections"],
    }


def complete(store: InvestigationStore, investigation: dict, *, text: str = "Supported [evidence:3]; unavailable [evidence:2].") -> dict:
    investigation, _ = store.claim(investigation["id"], investigation["currentContextId"])
    store.update_attempt(investigation["id"], source="native/worker", threadId="worker", turnId="worker-turn", status="running")
    output = store.trace.append(source="native/worker", direction="appserver_to_client", message={
        "method": "item/completed", "params": {"threadId": "worker", "turnId": "worker-turn", "item": {
            "id": "answer", "type": "agentMessage", "text": text, "phase": "final",
        }},
    })
    return store.complete(investigation["id"], {
        "text": text, "outputSeqs": [output.seq],
        "citations": [2], "unsupportedCitations": [3],  # Store derives these; caller claims are not authoritative.
    })


def test_packet_retains_exact_raw_unknown_fields_and_excludes_interleaved_thread():
    trace = TraceStore()
    body = seed(trace)
    store = InvestigationStore(trace)
    investigation = store.create(body)
    context = investigation["contexts"][0]

    assert [record["seq"] for record in context["records"]] == [1, 3, 4]
    raw = context["records"][0]["rawText"]
    assert raw == trace.get(1).raw_text
    assert json.loads(raw)["futureField"] == {"keep": "exact bytes"}
    assert context["records"][0]["sha256"] == hashlib.sha256(raw.encode()).hexdigest()
    assert "exclude this interleaved record" not in context["projectedPrompt"]
    assert "provider context are unknown" in context["coverage"]
    assert "[evidence:1]" in context["projectedPrompt"]
    assert "[evidence:4]" in context["projectedPrompt"]
    assert context["parentContextId"] is None


def test_context_remains_frozen_after_enrichment_reimport_mutable_reads_and_restart(tmp_path: Path):
    path = tmp_path / "trace.db"
    trace = TraceStore(path)
    store = InvestigationStore(trace)
    investigation = store.create(seed(trace))
    original = json.loads(json.dumps(investigation))
    trace.append(source="native/source-a", direction="appserver_to_client", message={"id": 7, "result": {"turn": {"id": "late-turn"}}})
    assert trace.get(1).turn_id == "late-turn"
    trace.append_line(source="history/reimport", direction="internal", raw_text=trace.get(4).raw_text)
    investigation["contexts"][0]["records"][0]["rawText"] = "caller mutation"
    investigation["contexts"][0]["projectedPrompt"] = "caller mutation"
    trace.close()

    reopened = TraceStore(path)
    try:
        restored = InvestigationStore(reopened).get(original["id"])
        assert restored == original
    finally:
        reopened.close()


def test_overlapping_ranges_retain_rationales_but_deduplicate_records():
    trace = TraceStore()
    body = seed(trace)
    body["selections"].append({"threadId": "a", "startSeq": 3, "endSeq": 3, "rationale": "specific point"})
    context = InvestigationStore(trace).create(body)["contexts"][0]
    assert len(context["selections"]) == 3
    assert [record["seq"] for record in context["records"]] == [1, 3, 4]
    assert context["selections"][-1]["rationale"] == "specific point"


@pytest.mark.parametrize("selection", [
    {"threadId": "a", "startSeq": 1, "endSeq": 2},
    {"threadId": "b", "startSeq": 1, "endSeq": 3},
    {"threadId": "a", "startSeq": 3, "endSeq": 1},
    {"threadId": "a", "startSeq": True, "endSeq": 3},
    {"threadId": "a", "startSeq": 1, "endSeq": 2**100},
    {"threadId": "absent", "startSeq": 1, "endSeq": 1},
])
def test_invalid_source_ranges_fail_without_saving(selection):
    trace = TraceStore()
    body = seed(trace)
    body["selections"] = [selection]
    store = InvestigationStore(trace)
    with pytest.raises(InvestigationError) as failure:
        store.create(body)
    assert failure.value.status == 400
    assert store.list() == []


@pytest.mark.parametrize("field,value", [
    ("title", "t" * 201),
    ("question", "q" * 16001),
    ("question", "invalid unicode \ud800"),
    ("selections", []),
    ("selections", [{"threadId": "a", "startSeq": 1, "endSeq": 1}] * 33),
])
def test_context_input_limits(field, value):
    trace = TraceStore()
    body = seed(trace)
    body[field] = value
    with pytest.raises(InvestigationError) as failure:
        InvestigationStore(trace).create(body)
    assert failure.value.status == 400


def test_context_record_and_utf8_prompt_limits():
    trace = TraceStore()
    store = InvestigationStore(trace)
    body = seed(trace)
    for _ in range(257):
        trace.append(source="test", direction="internal", message={"method": "event", "params": {"threadId": "many"}})
    body["selections"] = [{"threadId": "many", "startSeq": 5, "endSeq": 261}]
    with pytest.raises(InvestigationError, match="256 records"):
        store.create(body)
    large = trace.append(source="test", direction="internal", message={"method": "event", "params": {"threadId": "large", "text": "é" * 70000}})
    body["selections"] = [{"threadId": "large", "startSeq": large.seq, "endSeq": large.seq}]
    with pytest.raises(InvestigationError, match="128 KiB"):
        store.create(body)
    assert store.list() == []


def test_create_and_revision_request_ids_bind_exact_body_and_operation():
    trace = TraceStore()
    store = InvestigationStore(trace)
    body = seed(trace)
    investigation = store.create(body)
    assert store.create(body) == investigation
    with pytest.raises(InvestigationError) as failure:
        store.create({**body, "question": "different"})
    assert failure.value.status == 409
    update = revision(investigation)
    revised = store.revise(investigation["id"], update)
    assert revised["contexts"][0] == investigation["contexts"][0]
    assert revised["contexts"][1]["parentContextId"] == investigation["currentContextId"]
    assert store.revise(investigation["id"], update) == revised
    for changed in ({**update, "question": "altered"}, {**update, "requestId": body["requestId"]}):
        with pytest.raises(InvestigationError) as failure:
            store.revise(investigation["id"], changed)
        assert failure.value.status == 409


def test_stale_revision_and_claim_conflict_then_context_freezes_after_dispatch():
    trace = TraceStore()
    store = InvestigationStore(trace)
    investigation = store.create(seed(trace))
    revised = store.revise(investigation["id"], revision(investigation))
    with pytest.raises(InvestigationError) as failure:
        store.revise(investigation["id"], revision(investigation, request_id="stale"))
    assert failure.value.status == 409
    with pytest.raises(InvestigationError) as failure:
        store.claim(investigation["id"], investigation["currentContextId"])
    assert failure.value.status == 409
    dispatched, claimed = store.claim(revised["id"], revised["currentContextId"])
    assert claimed is True
    assert dispatched["attempt"]["timeoutSeconds"] == 120
    with pytest.raises(InvestigationError) as failure:
        store.revise(investigation["id"], revision(revised, request_id="too-late"))
    assert failure.value.status == 409
    repeated, claimed = store.claim(revised["id"], revised["currentContextId"])
    assert claimed is False
    assert repeated == dispatched


def test_concurrent_create_and_dispatch_claims_use_sqlite_not_instance_locks(tmp_path: Path):
    path = tmp_path / "trace.db"
    traces = [TraceStore(path) for _ in range(6)]
    stores = [InvestigationStore(trace) for trace in traces]
    body = seed(traces[0])
    try:
        with ThreadPoolExecutor(max_workers=6) as pool:
            created = list(pool.map(lambda store: store.create(body), stores))
            investigation = created[0]
            claimed = list(pool.map(lambda store: store.claim(investigation["id"], investigation["currentContextId"]), stores))
        assert len({value["id"] for value in created}) == 1
        assert sum(won for _, won in claimed) == 1
        assert len({value["attempt"]["id"] for value, _ in claimed}) == 1
    finally:
        for trace in traces:
            trace.close()


def test_concurrent_revisions_admit_one_parent_successor(tmp_path: Path):
    path = tmp_path / "trace.db"
    first, second = TraceStore(path), TraceStore(path)
    stores = [InvestigationStore(first), InvestigationStore(second)]
    investigation = stores[0].create(seed(first))

    def revise(index):
        try:
            return stores[index].revise(investigation["id"], revision(investigation, request_id=f"revision-{index}"))
        except InvestigationError as error:
            return error.status

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(revise, range(2)))
        assert sum(result == 409 for result in results) == 1
        assert len(stores[0].get(investigation["id"])["contexts"]) == 2
    finally:
        first.close()
        second.close()


def test_unknown_dispatch_survives_restart_without_becoming_dispatchable(tmp_path: Path):
    path = tmp_path / "trace.db"
    trace = TraceStore(path)
    store = InvestigationStore(trace)
    investigation = store.create(seed(trace))
    claimed, _ = store.claim(investigation["id"], investigation["currentContextId"])
    store.update_attempt(investigation["id"], source="native/incarnation", status="unknown", error="lost acknowledgement")
    trace.close()
    reopened = TraceStore(path)
    try:
        restored, won = InvestigationStore(reopened).claim(investigation["id"], investigation["currentContextId"])
        assert won is False
        assert restored["attempt"]["id"] == claimed["attempt"]["id"]
        assert restored["status"] == "unknown"
        assert restored["attempt"]["source"] == "native/incarnation"
    finally:
        reopened.close()


def test_attempt_mapping_cannot_be_substituted_and_output_must_match():
    trace = TraceStore()
    store = InvestigationStore(trace)
    investigation = store.create(seed(trace))
    store.claim(investigation["id"], investigation["currentContextId"])
    store.update_attempt(investigation["id"], source="worker/incarnation")
    with pytest.raises(InvestigationError) as failure:
        store.update_attempt(investigation["id"], source="unrelated/incarnation")
    assert failure.value.status == 409
    with pytest.raises(InvestigationError, match="does not match"):
        store.complete(investigation["id"], {"text": "an answer", "outputSeqs": [1]})
    with pytest.raises(InvestigationError, match="does not exist"):
        store.complete(investigation["id"], {"text": "an answer", "outputSeqs": [9999]})


def test_result_citations_derive_from_selected_packet_and_completion_is_idempotent():
    trace = TraceStore()
    store = InvestigationStore(trace)
    investigation = complete(store, store.create(seed(trace)))
    artifact = investigation["artifact"]
    assert artifact["citations"] == [3]
    assert artifact["unsupportedCitations"] == [2]
    assert artifact["contextId"] == investigation["currentContextId"]
    assert artifact["attemptId"] == investigation["attempt"]["id"]
    repeat = {key: artifact[key] for key in ("text", "outputSeqs")}
    assert store.complete(investigation["id"], repeat) == investigation
    with pytest.raises(InvestigationError) as failure:
        store.complete(investigation["id"], {**repeat, "text": "different answer"})
    assert failure.value.status == 409
    assert store.update_attempt(investigation["id"], status="unknown", error="late timeout") == investigation


def test_adoption_is_explicit_durable_and_does_not_change_source_evidence(tmp_path: Path):
    path = tmp_path / "trace.db"
    trace = TraceStore(path)
    store = InvestigationStore(trace)
    investigation = complete(store, store.create(seed(trace)))
    before = [(record.seq, record.raw_text) for record in trace.records()]
    body = {"artifactId": investigation["artifact"]["id"], "decision": "adopt", "note": "Keep uncertain outcomes explicit."}
    adopted = store.adopt(investigation["id"], body)
    assert store.adopt(investigation["id"], body) == adopted
    with pytest.raises(InvestigationError) as failure:
        store.adopt(investigation["id"], {**body, "decision": "reject"})
    assert failure.value.status == 409
    assert [(record.seq, record.raw_text) for record in trace.records()] == before
    trace.close()
    reopened = TraceStore(path)
    try:
        assert InvestigationStore(reopened).get(investigation["id"]) == adopted
    finally:
        reopened.close()


def test_unknown_investigation_does_not_resolve_by_another_name():
    store = InvestigationStore(TraceStore())
    with pytest.raises(InvestigationError) as failure:
        store.get("guessed-investigation")
    assert failure.value.status == 404


def test_concurrent_adoption_preserves_one_reviewed_decision(tmp_path: Path):
    path = tmp_path / "trace.db"
    traces = [TraceStore(path), TraceStore(path)]
    stores = [InvestigationStore(trace) for trace in traces]
    investigation = complete(stores[0], stores[0].create(seed(traces[0])))

    def adopt(index):
        try:
            return stores[index].adopt(investigation["id"], {
                "artifactId": investigation["artifact"]["id"],
                "decision": ["adopt", "reject"][index],
                "note": "reviewed",
            })
        except InvestigationError as error:
            return error.status

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(adopt, range(2)))
        assert sum(result == 409 for result in results) == 1
        assert stores[0].get(investigation["id"]) == stores[1].get(investigation["id"])
        with pytest.raises(InvestigationError) as failure:
            stores[0].adopt(investigation["id"], {
                "artifactId": investigation["artifact"]["id"], "decision": [],
            })
        assert failure.value.status == 400
    finally:
        for trace in traces:
            trace.close()
