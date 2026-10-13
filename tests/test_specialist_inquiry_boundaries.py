"""Adversarial admission boundaries using synthetic native records only."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
from threading import Barrier, Event

import pytest

from eidos.api import EidosAPI
from eidos.investigation import InvestigationError
from eidos.investigation_continuations import InvestigationContinuations
from eidos.investigation_inquiries import terminal_inquiry
from eidos.trace import TraceStore

from test_investigation_continuations_api import occurrences
from test_investigation_inquiry_adapter import PAYLOAD, recorded_inquiry
from test_specialist_inquiries import answer, native_turns, next_body, specialist


def rejected(operation):
    with pytest.raises(InvestigationError) as failure:
        operation()
    assert failure.value.status == 409


@pytest.mark.parametrize("invalid", [False, True])
def test_terminal_result_cannot_be_adopted_or_seized_before_inquiry_admission(invalid):
    # This is the durable crash gap after complete(), before open_specialist().
    payload = {**PAYLOAD, "schemaVersion": 2} if invalid else PAYLOAD
    store, worker, identifier, _, _ = recorded_inquiry(json.dumps(payload))
    try:
        continuations = InvestigationContinuations(store)
        completed = store.get(identifier)
        assert completed["attempt"]["status"] == "completed"
        assert completed["status"] == "needs-evidence"
        assert completed["artifact"]["kind"] == (
            "native-inquiry-invalid" if invalid else "native-needs-evidence"
        )
        assert completed.get("continuation") is None
        before = [(record.seq, record.raw_text) for record in store.trace.records()]
        for decision in ("adopt", "reject"):
            rejected(lambda: store.adopt(identifier, {
                "artifactId": completed["artifact"]["id"], "decision": decision,
            }))
        rejected(lambda: continuations.open(identifier, {
            "requestId": "competing-owner-review", "attemptId": completed["attempt"]["id"],
            "question": "Replace the specialist question with this owner review?",
        }))
        assert store.get(identifier) == completed
        assert [(record.seq, record.raw_text) for record in store.trace.records()] == before
        assert store.trace.db.execute("SELECT COUNT(*) FROM investigation_runtime_links").fetchone()[0] == 0
        if not invalid:
            observation = terminal_inquiry(store, identifier, worker)
            pending = continuations.open_specialist(identifier, observation)
            assert pending["continuation"]["inquiry"]["question"] == PAYLOAD["question"]
            assert pending["nativeArtifact"] == completed["artifact"]
    finally:
        worker.close()
        store.trace.close()


def test_forged_native_fields_on_completed_cycle_b_review_cannot_admit_native_work():
    store, worker, identifier, _, event = recorded_inquiry("An ordinary native conclusion.")
    try:
        continuations = InvestigationContinuations(store)
        original = store.get(identifier)
        pending = continuations.open(identifier, {
            "requestId": "owner-review", "attemptId": original["attempt"]["id"],
            "question": "Can the owner disclose further evidence?",
        })
        completed = continuations.respond(identifier, pending["continuation"]["inquiry"]["id"], {
            "requestId": "owner-refusal", "decision": "refuse",
        })
        assert completed["continuation"]["origin"] == "synthetic-eidos"
        # Public provenance and names may be copied or edited during historical
        # import. Keep their outer IDs self-consistent to exercise the host ledger.
        forged = deepcopy(completed)
        continuation = forged["continuation"]
        continuation["origin"] = "native-specialist"
        continuation["cause"] = {
            "schemaVersion": 1, "origin": "native-specialist", "mode": "terminal-needs-evidence",
            "investigationId": identifier, "attemptId": original["attempt"]["id"],
            "contextId": original["currentContextId"], "nativeArtifactId": original["artifact"]["id"],
            "question": continuation["question"], "cause": "Copied specialist-origin description.",
            "requestSeq": 1, "nativeEvent": {"seq": event.seq},
        }
        continuation["nativeNext"] = {
            "status": "awaiting-admission", "contextId": original["currentContextId"], "attemptId": None,
        }
        with store._transaction():
            store._save(forged)
        rejected(lambda: store.prepare_followup(identifier))
        rejected(lambda: store.claim_followup(identifier, next_body(forged)))
        assert store.get(identifier) == forged
        assert store.trace.db.execute("SELECT COUNT(*) FROM investigation_native_continuations").fetchone()[0] == 0
        assert len(native_turns(store.trace)) == 1
    finally:
        worker.close()
        store.trace.close()


@pytest.mark.parametrize("decision", ["offer", "refuse"])
def test_cancellation_and_terminal_response_have_one_winner_across_controllers(specialist, tmp_path, decision):
    api, trace, pending, body = specialist
    peer_trace = TraceStore(tmp_path / "specialist.db")
    peer = EidosAPI(peer_trace)
    gate = Barrier(2)
    identifier = pending["id"]
    inquiry_id = pending["continuation"]["inquiry"]["id"]
    response = {"requestId": "race-response", "decision": decision}
    if decision == "offer":
        response["selections"] = body["selections"]

    def compete(operation):
        gate.wait(timeout=5)
        try:
            return 200, operation()
        except InvestigationError as failure:
            return failure.status, failure.message

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            cancellation = pool.submit(compete, lambda: api.investigation_continuations.cancel(
                identifier, inquiry_id, {"requestId": "race-cancel"},
            ))
            answer_result = pool.submit(compete, lambda: peer.investigation_continuations.respond(
                identifier, inquiry_id, response,
            ))
            results = [cancellation.result(timeout=5), answer_result.result(timeout=5)]
        assert sorted(status for status, _ in results) == [200, 409]
        final = api.investigations.get(identifier)
        link = json.loads(trace.db.execute(
            "SELECT state_json FROM investigation_runtime_links WHERE investigation_id=?", (identifier,),
        ).fetchone()[0])
        terminal = [row for row in final["continuation"]["inquiry"]["responses"]
                    if row["decision"] in {"offer", "refuse"}]
        source_decisions = [event for event in occurrences(api) if event[1] in {"DiscoveryOffer", "DiscoveryRefuse"}]
        if results[0][0] == 200:
            assert final["continuation"]["inquiry"]["status"] == "cancelled"
            assert link["cancelled"] is True
            assert terminal == source_decisions == []
            rejected(lambda: peer.investigation_continuations.respond(identifier, inquiry_id, response))
        else:
            assert final["continuation"]["inquiry"]["status"] == ("answered" if decision == "offer" else "refused")
            assert not link.get("cancelled")
            assert len(terminal) == len(source_decisions) == 1
            rejected(lambda: api.investigation_continuations.cancel(
                identifier, inquiry_id, {"requestId": "race-cancel"},
            ))
        assert len(native_turns(trace)) == 1
    finally:
        peer.close()
        peer_trace.close()


def test_cancellation_cannot_overtake_an_admitted_terminal_response(specialist, tmp_path, monkeypatch):
    api, trace, pending, _ = specialist
    peer_trace = TraceStore(tmp_path / "specialist.db")
    peer = EidosAPI(peer_trace)
    admitted, release = Event(), Event()
    original = api.investigation_continuations.resume
    identifier = pending["id"]
    inquiry_id = pending["continuation"]["inquiry"]["id"]

    def pause_after_admission(current_id):
        admitted.set()
        assert release.wait(5), "test did not release terminal response realization"
        return original(current_id)

    monkeypatch.setattr(api.investigation_continuations, "resume", pause_after_admission)
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            responding = pool.submit(api.investigation_continuations.respond, identifier, inquiry_id, {
                "requestId": "admitted-refusal", "decision": "refuse",
            })
            try:
                assert admitted.wait(5)
                assert api.investigations.get(identifier)["continuation"]["inquiry"]["responses"][-1]["status"] == "admitted"
                assert not [event for event in occurrences(peer) if event[1] == "DiscoveryRefuse"]
                rejected(lambda: peer.investigation_continuations.cancel(
                    identifier, inquiry_id, {"requestId": "too-late-cancel"},
                ))
            finally:
                release.set()
            final = responding.result(timeout=5)
        assert final["continuation"]["inquiry"]["status"] == "refused"
        assert len([event for event in occurrences(api) if event[1] == "DiscoveryRefuse"]) == 1
        assert len(native_turns(trace)) == 1
    finally:
        peer.close()
        peer_trace.close()


@pytest.mark.parametrize("field", ["cause", "question", "contextId", "nativeEvent"])
def test_changed_public_native_cause_cannot_prepare_or_claim_after_answer(specialist, field):
    api, trace, pending, body = specialist
    answered = answer(api, pending, body)
    forged = deepcopy(answered)
    cause = forged["continuation"]["cause"]
    if field == "nativeEvent":
        cause[field]["seq"] += 1
    else:
        cause[field] = "altered-public-" + field
    with api.investigations._transaction():
        api.investigations._save(forged)
    before_occurrences = occurrences(api)
    rejected(lambda: api.investigations.prepare_followup(pending["id"]))
    rejected(lambda: api.investigations.claim_followup(pending["id"], next_body(forged)))
    assert api.investigations.get(pending["id"]) == forged
    assert occurrences(api) == before_occurrences
    assert len(native_turns(trace)) == 1
