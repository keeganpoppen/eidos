"""Private inquiry references never masquerade as main-store sequence numbers."""
from copy import deepcopy
import hashlib
import json

import pytest

from eidos.investigation import InvestigationError
from eidos.investigation_continuations import InvestigationContinuations
from eidos.investigation_inquiries import NativeInquiryError, terminal_inquiry
from eidos.investigation_worker import NativeInvestigationWorker
from eidos.trace import TraceStore
from test_investigation_inquiry_adapter import recorded_inquiry


@pytest.fixture
def private_inquiry():
    store, _, identifier, request, event = recorded_inquiry()
    private = TraceStore(role="private-control")
    # A trusted test resolver binds a distinct sequence space. The production
    # adapter separately proves publication/ledger admission in its tests.
    private.append(source="private-control", direction="internal", message={"unknown": "PRIVATE_CANARY"})
    mapping = {}
    for record in store.trace.records():
        if record.source == "synthetic-native":
            mapping[record.seq] = private.append_line(
                source=record.source, direction=record.direction, raw_text=record.raw_text,
            ).seq
    investigation = store.get(identifier)
    artifact = investigation["artifact"]
    artifact["executionEvidence"] = "unverified"
    artifact["outputEvidence"] = {"kind": "private-capsule-publication", "version": 1, "capsuleId": "capsule-fixture"}
    # Establish only the public description; the fake resolver is the explicit
    # trusted-host seam under test, not a way to mint a real publication ledger.
    with store._transaction():
        store._save(investigation)

    class Resolver:
        def recover(self, attempt, context):
            return deepcopy(artifact)

        def resolve_result_evidence(self, attempt, context, published):
            recovered = NativeInvestigationWorker(private, command=["never-launch"]).recover(attempt, context)
            return {"kind": "private-capsule", "capsuleId": "capsule-fixture", "trace": private,
                    "artifact": recovered, "attempt": dict(attempt)}

    try:
        yield store, Resolver(), private, identifier, mapping[request.seq], mapping[event.seq]
    finally:
        private.close()
        store.trace.close()


def test_private_inquiry_validates_original_evidence_and_scopes_references(private_inquiry):
    store, worker, private, identifier, request_seq, event_seq = private_inquiry
    observation = terminal_inquiry(store, identifier, worker)
    assert observation["schemaVersion"] == 2
    assert "requestSeq" not in observation and "seq" not in observation["nativeEvent"]
    for actual, seq in ((observation["request"], request_seq), (observation["nativeEvent"]["evidence"], event_seq)):
        assert actual == {"kind": "private-capsule-record", "capsuleId": "capsule-fixture", "seq": seq,
                          "sha256": hashlib.sha256(private.get(seq).raw_text.encode()).hexdigest()}
    assert "PRIVATE_CANARY" not in json.dumps(observation)
    controller = InvestigationContinuations(store)
    opened = controller.open_specialist(identifier, observation)
    assert opened["continuation"]["origin"] == "native-specialist"
    assert opened["continuation"]["cause"] == observation
    assert controller.open_specialist(identifier, observation) == opened


@pytest.mark.parametrize("mutation", ["capsule", "context", "source", "thread", "turn", "text", "role", "error"])
def test_resolver_mismatch_or_private_error_cannot_create_inquiry(private_inquiry, mutation):
    store, worker, _, identifier, _, _ = private_inquiry
    original = worker.resolve_result_evidence
    def bad(attempt, context, artifact):
        if mutation == "error":
            raise ValueError("PRIVATE_CONTROL_ERROR_CANARY")
        result = original(attempt, context, artifact)
        if mutation == "capsule": result["capsuleId"] = "different"
        elif mutation in {"context", "source", "thread", "turn"}:
            field = {"context": "contextId", "source": "source", "thread": "threadId", "turn": "turnId"}[mutation]
            result["attempt"][field] = "different"
        elif mutation == "text": result["artifact"]["text"] = "different"
        else: result["trace"] = store.trace
        return result
    worker.resolve_result_evidence = bad
    with pytest.raises(NativeInquiryError) as error:
        terminal_inquiry(store, identifier, worker)
    assert "PRIVATE_CONTROL_ERROR_CANARY" not in str(error.value)
    assert store.get(identifier).get("continuation") is None


@pytest.mark.parametrize("mutation", ["terminal", "phase", "prompt"])
def test_private_raw_counterexamples_still_rejected(private_inquiry, mutation):
    store, worker, private, identifier, request_seq, event_seq = private_inquiry
    seq = request_seq if mutation == "prompt" else event_seq
    record = private.get(seq)
    message = record.message
    if mutation == "prompt": message["params"]["input"][0]["text"] += "different"
    elif mutation == "phase": message["params"]["item"]["phase"] = "commentary"
    else:
        terminal = next(r for r in private.records() if r.method == "turn/completed")
        seq, message = terminal.seq, terminal.message
        message["params"]["threadId"] = "different"
    private.db.execute("UPDATE trace_records SET raw_text=? WHERE seq=?", (json.dumps(message), seq))
    with pytest.raises(NativeInquiryError):
        terminal_inquiry(store, identifier, worker)


@pytest.mark.parametrize("mutation", ["bare-request", "bare-event", "wrong-capsule", "order", "hash", "legacy"])
def test_private_admission_rejects_ambiguous_or_wrong_evidence_scope(private_inquiry, mutation):
    store, worker, _, identifier, _, _ = private_inquiry
    observation = terminal_inquiry(store, identifier, worker)
    if mutation == "bare-request": observation["requestSeq"] = observation["request"]["seq"]
    elif mutation == "bare-event": observation["nativeEvent"]["seq"] = observation["nativeEvent"]["evidence"]["seq"]
    elif mutation == "wrong-capsule": observation["request"]["capsuleId"] = "different"
    elif mutation == "order": observation["request"]["seq"] = observation["nativeEvent"]["evidence"]["seq"]
    elif mutation == "hash": observation["request"]["sha256"] = "not-a-hash"
    else: observation["schemaVersion"] = 1
    with pytest.raises(InvestigationError):
        InvestigationContinuations(store).open_specialist(identifier, observation)
    assert store.get(identifier).get("continuation") is None
