"""Independent controllers sharing SQLite; native evidence uses the local fixture."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event

import pytest

from eidos.api import EidosAPI
from eidos.trace import TraceStore

from test_investigation_continuations_api import (
    begin, call, continuation_body, inquiry_path, native, occurrences, successful,
)


@pytest.fixture
def controllers(native, tmp_path):
    api, trace, completed, body = native
    peer_trace = TraceStore(tmp_path / "investigation.db")
    peer = EidosAPI(peer_trace)
    try:
        yield api, peer, completed, body
    finally:
        peer.close()
        peer_trace.close()


@pytest.mark.parametrize("stale_result", ["failure", "pending"])
def test_stale_controller_cannot_change_peer_completion(controllers, monkeypatch, stale_result):
    api, peer, completed, _ = controllers
    pending = begin(api, completed)
    reached, release = Event(), Event()
    original = api.investigation_runtime.advance

    def delayed_advance(state):
        old_result = original(state)
        assert old_result["pending"] is True
        reached.set()
        assert release.wait(5), "peer did not finish before stale controller resumed"
        if stale_result == "failure":
            raise RuntimeError("stale controller failed after peer completed")
        return old_result

    monkeypatch.setattr(api.investigation_runtime, "advance", delayed_advance)
    with ThreadPoolExecutor(max_workers=1) as pool:
        delayed = pool.submit(call, api, f"/{pending['id']}/resume", {})
        try:
            assert reached.wait(5)
            final = successful(call(peer, inquiry_path(pending) + "/responses", {
                "requestId": "peer-refusal", "decision": "refuse",
            }))
            assert final["status"] == "completed"
            assert final["continuation"]["error"] is None
            committed = occurrences(peer)
        finally:
            release.set()
        assert successful(delayed.result(timeout=5)) == final
    assert successful(call(peer, f"/{pending['id']}/resume", {})) == final
    assert occurrences(peer) == committed


def test_stale_pending_merge_preserves_peer_defer_authority_and_response(controllers, monkeypatch):
    api, peer, completed, body = controllers
    pending = begin(api, completed)
    reached, release = Event(), Event()
    original = api.investigation_runtime.advance

    def delayed_pending(state):
        old_result = original(state)
        assert old_result["pending"] is True
        reached.set()
        assert release.wait(5), "peer did not defer before stale controller resumed"
        return old_result

    with monkeypatch.context() as fault:
        fault.setattr(api.investigation_runtime, "advance", delayed_pending)
        with ThreadPoolExecutor(max_workers=1) as pool:
            delayed = pool.submit(call, api, f"/{pending['id']}/resume", {})
            try:
                assert reached.wait(5)
                deferred = successful(call(peer, inquiry_path(pending) + "/responses", {
                    "requestId": "peer-deferral", "decision": "defer",
                }))
                assert deferred["continuation"]["inquiry"]["status"] == "deferred"
                committed = occurrences(peer)
            finally:
                release.set()
            assert successful(delayed.result(timeout=5)) == deferred
    assert occurrences(peer) == committed
    # A subsequent offer must consume the successor responder created by the
    # peer's deferral, not the stale pre-response source authority.
    final = successful(call(api, inquiry_path(pending) + "/responses", {
        "requestId": "subsequent-offer", "decision": "offer", "selections": body["selections"],
    }))
    assert final["status"] == "completed", final["continuation"]["error"]
    responses = final["continuation"]["inquiry"]["responses"]
    assert [response["decision"] for response in responses] == ["defer", "offer"]
    assert all(response["status"] == "committed" for response in responses)
    tm = api.investigation_runtime.trusted
    source_defer = tm.authority_occurrence(responses[0]["occurrenceId"])
    source_offer = tm.authority_occurrence(responses[1]["occurrenceId"])
    assert set(source_offer["inputs"]) <= set(source_defer["outputs"].values())


def test_independent_connections_serialize_duplicate_open_and_competing_responses(controllers):
    api, peer, completed, body = controllers
    opening = Barrier(2)

    def open_once(controller):
        opening.wait(timeout=5)
        return successful(call(controller, f"/{completed['id']}/continuation", continuation_body(completed)))

    with ThreadPoolExecutor(max_workers=2) as pool:
        pending, duplicate = list(pool.map(open_once, (api, peer)))
    assert pending == duplicate
    responding = Barrier(2)

    def respond(pair):
        controller, request = pair
        responding.wait(timeout=5)
        return call(controller, inquiry_path(pending) + "/responses", request)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(respond, (
            (api, {"requestId": "competing-offer", "decision": "offer", "selections": body["selections"]}),
            (peer, {"requestId": "competing-refusal", "decision": "refuse"}),
        )))
    assert sorted(status for status, _ in results) == [200, 409]
    final = successful(call(peer, f"/{pending['id']}/resume", {}))
    assert final["status"] == "completed"
    responses = final["continuation"]["inquiry"]["responses"]
    assert len(responses) == 1
    assert final["artifact"]["responseId"] == responses[0]["id"]
    assert len([event for event in occurrences(peer) if event[1] in {"DiscoveryOffer", "DiscoveryRefuse"}]) == 1
    assert len([event for event in occurrences(peer) if event[1] == "ModelProcessFinish"]) == 1
