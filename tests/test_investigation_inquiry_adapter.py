"""Terminal inquiry attribution using synthetic recorded native evidence only."""
from __future__ import annotations

import hashlib
import json

import pytest

from eidos.investigation import InvestigationStore
from eidos.investigation_inquiries import NativeInquiryError, terminal_inquiry
from eidos.investigation_worker import NativeInvestigationWorker
from eidos.trace import TraceStore


PAYLOAD = {
    "schemaVersion": 1, "kind": "nema-needs-evidence",
    "question": "Which source records show the recovery boundary?",
    "cause": "The selected records describe intent without the actual acknowledgement.",
}


def recorded_inquiry(text=None, *, phase="final", terminal_item=False):
    trace = TraceStore()
    source = trace.append(source="synthetic-source", direction="internal", message={
        "method": "$history/item", "params": {"threadId": "source-thread", "item": {
            "id": "source-item", "type": "agentMessage", "text": "Evidence is incomplete.",
        }},
    })
    store = InvestigationStore(trace)
    investigation = store.create({
        "requestId": "create", "title": "Review missing evidence", "question": "Can we recover?",
        "selections": [{"threadId": "source-thread", "startSeq": source.seq, "endSeq": source.seq}],
    })
    identifier = investigation["id"]
    store.claim(identifier, investigation["currentContextId"])
    store.update_attempt(identifier, source="synthetic-native", threadId="native-thread",
                         turnId="native-turn", status="running")
    context = investigation["contexts"][0]
    request = trace.append(source="synthetic-native", direction="client_to_appserver", message={
        "id": 9, "method": "turn/start", "params": {
            "threadId": "native-thread", "input": [{"type": "text", "text": context["projectedPrompt"]}],
        },
    })
    trace.append(source="synthetic-native", direction="appserver_to_client", message={
        "id": 9, "result": {"turn": {"id": "native-turn", "status": "inProgress"}},
    })
    text = json.dumps(PAYLOAD) if text is None else text
    item = {"id": "native-answer", "type": "agentMessage", "phase": phase, "text": text,
            "futureItemField": {"preserve": True}}
    if not terminal_item:
        event = trace.append(source="synthetic-native", direction="appserver_to_client", message={
            "method": "item/completed", "params": {
                "threadId": "native-thread", "turnId": "native-turn", "item": item,
            }, "futureEventField": [1, 2, 3],
        })
    terminal = trace.append(source="synthetic-native", direction="appserver_to_client", message={
        "method": "turn/completed", "params": {"threadId": "native-thread", "turn": {
            "id": "native-turn", "status": "completed", "error": None,
            "items": [item] if terminal_item else [],
        }},
    })
    if terminal_item:
        event = terminal
    store.complete(identifier, {"text": text, "outputSeqs": [event.seq],
                                "citations": [], "unsupportedCitations": []})
    # Construction creates no subprocess. Only recover() is used by this suite.
    worker = NativeInvestigationWorker(trace, command=["must-never-run"])
    return store, worker, identifier, request, event


@pytest.mark.parametrize("terminal_item", [False, True])
def test_binds_question_to_exact_terminal_evidence_without_mutation(terminal_item):
    store, worker, identifier, request, event = recorded_inquiry(terminal_item=terminal_item)
    original = store.get(identifier)
    records = store.trace.records()
    observation = terminal_inquiry(store, identifier, worker)
    assert observation == {
        "schemaVersion": 1, "origin": "native-specialist", "mode": "terminal-needs-evidence",
        "investigationId": identifier, "attemptId": original["attempt"]["id"],
        "contextId": original["currentContextId"], "nativeArtifactId": original["artifact"]["id"],
        "question": PAYLOAD["question"], "cause": PAYLOAD["cause"], "requestSeq": request.seq,
        "nativeEvent": {"seq": event.seq, "source": event.source, "threadId": "native-thread",
                        "turnId": "native-turn", "method": event.method,
                        "sha256": hashlib.sha256(event.raw_text.encode()).hexdigest()},
    }
    assert terminal_inquiry(store, identifier, worker) == observation
    assert store.get(identifier) == original
    assert store.trace.records() == records


@pytest.mark.parametrize("text", ["An ordinary conclusion.", '{"kind":"other-result"}',
                                "```json\n" + json.dumps(PAYLOAD) + "\n```"])
def test_ordinary_or_quoted_output_never_admits_an_inquiry(text):
    store, worker, identifier, _, _ = recorded_inquiry(text)
    assert terminal_inquiry(store, identifier, worker) is None


@pytest.mark.parametrize("payload", [
    {**PAYLOAD, "schemaVersion": True}, {**PAYLOAD, "schemaVersion": 2},
    {**PAYLOAD, "question": ""}, {**PAYLOAD, "question": "q" * 16001},
    {**PAYLOAD, "cause": None}, {**PAYLOAD, "authority": "copied-holder"},
    {key: value for key, value in PAYLOAD.items() if key != "cause"},
])
def test_unsupported_protocol_cannot_be_silently_admitted(payload):
    store, worker, identifier, _, _ = recorded_inquiry(json.dumps(payload))
    original = store.get(identifier)
    with pytest.raises(NativeInquiryError):
        terminal_inquiry(store, identifier, worker)
    assert store.get(identifier) == original


def test_duplicate_fields_do_not_select_a_different_interpretation():
    text = json.dumps(PAYLOAD)[:-1] + ', "question":"replacement question"}'
    store, worker, identifier, _, _ = recorded_inquiry(text)
    with pytest.raises(NativeInquiryError, match="duplicate"):
        terminal_inquiry(store, identifier, worker)


@pytest.mark.parametrize("field,value", [
    ("source", "copied-source"), ("threadId", "copied-thread"), ("turnId", "copied-turn"),
    ("contextId", "copied-context"),
])
def test_copied_attribution_fails_closed(field, value):
    store, worker, identifier, _, _ = recorded_inquiry()
    with store._transaction():
        state = store._load(identifier)
        state["attempt"][field] = value
        store._save(state)
    with pytest.raises(NativeInquiryError):
        terminal_inquiry(store, identifier, worker)


def test_changed_saved_text_cannot_replace_the_recorded_specialist_question():
    store, worker, identifier, _, _ = recorded_inquiry()
    with store._transaction():
        state = store._load(identifier)
        state["artifact"]["text"] = json.dumps({**PAYLOAD, "question": "Forged replacement?"})
        store._save(state)
    with pytest.raises(NativeInquiryError, match="recovered native result"):
        terminal_inquiry(store, identifier, worker)


def test_legacy_unphased_output_is_readable_but_not_a_specialist_protocol_event():
    store, worker, identifier, _, _ = recorded_inquiry(phase=None)
    with pytest.raises(NativeInquiryError, match="explicit final"):
        terminal_inquiry(store, identifier, worker)


def test_completed_artifact_survives_new_contradictory_terminal_evidence():
    store, worker, identifier, _, _ = recorded_inquiry()
    original = store.get(identifier)
    store.trace.append(source="synthetic-native", direction="appserver_to_client", message={
        "method": "turn/completed", "params": {"threadId": "native-thread", "turn": {
            "id": "native-turn", "status": "failed", "error": {"message": "later contradiction"},
        }},
    })
    with pytest.raises(NativeInquiryError, match="evidence recovery failed"):
        terminal_inquiry(store, identifier, worker)
    assert store.get(identifier) == original


def test_original_native_artifact_remains_the_inquiry_cause_during_review():
    store, worker, identifier, _, _ = recorded_inquiry()
    original = store.get(identifier)
    with store._transaction():
        state = store._load(identifier)
        state["nativeArtifact"] = state["artifact"]
        state["artifact"] = {**state["artifact"], "kind": "eidos-evidence-review", "text": "receipt"}
        store._save(state)
    observation = terminal_inquiry(store, identifier, worker)
    assert observation["nativeArtifactId"] == original["artifact"]["id"]


def test_copied_completed_description_cannot_admit_on_startup():
    from eidos.api import EidosAPI
    store, worker, identifier, _, _ = recorded_inquiry()
    copied = store.get(identifier)
    copied['id'] = 'copied-native-result'
    with store._transaction():
        store.trace.db.execute(
            'INSERT INTO investigations VALUES (?,?,?)',
            (copied['id'], copied['createdAtMs'], json.dumps(copied)),
        )
    with pytest.raises(NativeInquiryError, match='another investigation'):
        terminal_inquiry(store, copied['id'], worker)
    api = EidosAPI(store.trace)
    try:
        assert api.investigations.get(identifier)['continuation']['origin'] == 'native-specialist'
        rejected = api.investigations.get(copied['id'])
        assert rejected.get('continuation') is None
        assert 'another investigation' in rejected['inquiryAdmissionError']
    finally:
        api.close()
        store.trace.close()
