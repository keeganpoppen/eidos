"""Independent integration attacks; subprocesses use synthetic SQLite history only.

These tests establish local admission/recovery boundaries, not exactly-once native
effects or security against arbitrary callers of the privileged Python machinery.
"""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import time

import pytest

from eidos.api import EidosAPI
from eidos.authority import ProjectionGrant
from eidos.investigation import InvestigationError, InvestigationStore
from eidos.semantic_values import projection_value
from eidos.trace import TraceStore
from eidos.trusted import TrustedMachinery
from test_investigation_continuations_api import call, inquiry_path, occurrences
from test_specialist_inquiries import answer, native_turns, next_body, pending_specialist


def _seed(path: Path, *, answered: bool = True):
    trace = TraceStore(path)
    api = EidosAPI(trace)
    try:
        pending, body = pending_specialist(api, trace, key="round3-crash")
        value = answer(api, pending, body) if answered else pending
        return value, body, [(r.seq, r.raw_text) for r in trace.records()]
    finally:
        api.close()
        trace.close()


def _pins(trace):
    return [tuple(row) for row in trace.db.execute("SELECT * FROM cm_requests ORDER BY name")]


@pytest.mark.parametrize("phase", ["before_commit", "after_commit"])
def test_abrupt_exit_during_a2_admission_retains_atomic_pin_and_never_resends(tmp_path, monkeypatch, phase):
    path = tmp_path / "abrupt-a2.db"
    before, _, raw = _seed(path)
    request = next_body(before, "abrupt-a2-admission")
    child = subprocess.run([
        sys.executable, "-c", """
import json, os, sys
from eidos.investigation import InvestigationStore
from eidos.trace import TraceStore
trace = TraceStore(sys.argv[1])
store = InvestigationStore(trace)
request = json.loads(sys.argv[3])
if sys.argv[4] == 'before_commit':
    remember = store._remember
    def crash_before_commit(*args):
        remember(*args)
        assert trace.db.in_transaction
        assert trace.db.execute('SELECT COUNT(*) FROM cm_requests').fetchone()[0] == 2
        assert store.get(sys.argv[2])['attempt']['contextId'] == request['contextId']
        os._exit(73)
    store._remember = crash_before_commit
value, claimed = store.claim_followup(sys.argv[2], request)
assert claimed and not trace.db.in_transaction
os._exit(73)
""", str(path), before["id"], json.dumps(request), phase,
    ], capture_output=True, text=True, timeout=20)
    assert child.returncode == 73, child.stderr

    trace = TraceStore(path)
    api = None
    try:
        store = InvestigationStore(trace)
        saved = store.get(before["id"])
        assert [(r.seq, r.raw_text) for r in trace.records()] == raw
        ledger = trace.db.execute("SELECT * FROM investigation_native_continuations").fetchone()
        if phase == "before_commit":
            assert saved == before
            assert len(_pins(trace)) == 1
            assert ledger["attempt_id"] is None
            assert trace.db.execute(
                "SELECT 1 FROM investigation_requests WHERE request_id=?", (request["requestId"],),
            ).fetchone() is None
            # The rolled-back operation is available for a fresh, explicit claim.
            saved, admitted = store.claim_followup(before["id"], request)
            assert admitted
        else:
            assert saved["attempt"]["status"] == "dispatching"
            assert ledger["attempt_id"] == saved["attempt"]["id"]
        assert len(_pins(trace)) == 2
        assert saved["attemptHistory"] == [before["attempt"]]
        assert saved["nativeArtifact"] == before["nativeArtifact"]
        assert saved["artifactHistory"] == [before["artifact"]]
        pin = store.contexts.store.get_request(saved["attempt"]["contextRequestName"])
        assert pin.data["identity"]["attempt_id"] == saved["attempt"]["id"]
        assert pin.ref("manifest") == saved["attempt"]["manifestId"]

        def forbidden_native(*args, **kwargs):
            raise AssertionError("recovery or a retry tried to launch native work")

        monkeypatch.setattr("eidos.investigation_worker.NativeInvestigationWorker.run", forbidden_native)
        api = EidosAPI(trace)  # Startup recovery must leave the admitted send unknown.
        recovered = api.recover_investigation(before["id"])
        assert recovered["attempt"]["id"] == saved["attempt"]["id"]
        assert recovered["attempt"]["status"] == "unknown"
        assert api.continue_investigation(before["id"], request) == recovered
        with pytest.raises(InvestigationError, match="already admitted"):
            api.continue_investigation(before["id"], {**request, "requestId": "try-again"})
        assert len(native_turns(trace)) == 1
        assert [(r.seq, r.raw_text) for r in trace.records()] == raw
        assert len(_pins(trace)) == 2
    finally:
        if api is not None:
            api.close()
        trace.close()


@pytest.mark.parametrize("same_request", [True, False])
def test_independent_process_a2_claim_race_has_one_admission(tmp_path, same_request):
    path = tmp_path / "race-a2.db"
    before, _, raw = _seed(path)
    gate = tmp_path / "release"
    children = []
    requests = [next_body(before, "race" if same_request else f"race-{index}") for index in range(2)]
    program = """
import json, pathlib, sys, time
from eidos.investigation import InvestigationError, InvestigationStore
from eidos.trace import TraceStore
trace = TraceStore(sys.argv[1])
store = InvestigationStore(trace)
pathlib.Path(sys.argv[5]).touch()
deadline = time.monotonic() + 10
while not pathlib.Path(sys.argv[4]).exists():
    assert time.monotonic() < deadline, 'parent did not release race'
    time.sleep(.01)
try:
    result, claimed = store.claim_followup(sys.argv[2], json.loads(sys.argv[3]))
    print(json.dumps({'status': 200, 'claimed': claimed, 'attemptId': result['attempt']['id']}))
except InvestigationError as failure:
    print(json.dumps({'status': failure.status, 'error': failure.message}))
finally:
    trace.close()
"""
    try:
        for index, request in enumerate(requests):
            children.append(subprocess.Popen([
                sys.executable, "-c", program, str(path), before["id"], json.dumps(request),
                str(gate), str(tmp_path / f"ready-{index}"),
            ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True))
        deadline = time.monotonic() + 10
        while not all((tmp_path / f"ready-{index}").exists() for index in range(2)):
            assert time.monotonic() < deadline, "subprocesses did not initialize"
            assert all(child.poll() is None for child in children)
            time.sleep(.01)
        gate.touch()
        results = []
        for child in children:
            output, error = child.communicate(timeout=15)
            assert child.returncode == 0, error
            results.append(json.loads(output))
        assert sum(result.get("claimed", False) for result in results) == 1
        assert sorted(result["status"] for result in results) == ([200, 200] if same_request else [200, 409])
        if same_request:
            assert results[0]["attemptId"] == results[1]["attemptId"]
        trace = TraceStore(path)
        try:
            saved = InvestigationStore(trace).get(before["id"])
            assert len(saved["attemptHistory"]) == 1
            assert len(_pins(trace)) == 2
            assert [(r.seq, r.raw_text) for r in trace.records()] == raw
            assert trace.db.execute(
                "SELECT attempt_id FROM investigation_native_continuations",
            ).fetchone()[0] == saved["attempt"]["id"]
        finally:
            trace.close()
    finally:
        for child in children:
            if child.poll() is None:
                child.kill()
            child.communicate(timeout=5)


def test_abrupt_exit_after_source_offer_does_not_claim_recipient_incorporation(tmp_path):
    path = tmp_path / "source-commit.db"
    pending, body, raw = _seed(path, answered=False)
    child = subprocess.run([
        sys.executable, "-c", """
import json, os, sys
from eidos.api import EidosAPI
from eidos.trace import TraceStore
trace = TraceStore(sys.argv[1])
api = EidosAPI(trace)
advance = api.investigation_runtime.advance
def crash_after_source(state):
    if trace.db.execute("SELECT 1 FROM authority_occurrences WHERE kind='DiscoveryOffer'").fetchone():
        assert not trace.db.in_transaction
        os._exit(73)
    return advance(state)
api.investigation_runtime.advance = crash_after_source
api.investigation_continuations.respond(sys.argv[2], sys.argv[3], json.loads(sys.argv[4]))
raise AssertionError('source commit crash point was not reached')
""", str(path), pending["id"], pending["continuation"]["inquiry"]["id"], json.dumps({
        "requestId": "abrupt-offer", "decision": "offer", "selections": body["selections"],
    }),
    ], capture_output=True, text=True, timeout=20)
    assert child.returncode == 73, child.stderr
    trace = TraceStore(path)
    api = None
    try:
        saved = InvestigationStore(trace).get(pending["id"])
        continuation = saved["continuation"]
        response = continuation["inquiry"]["responses"][0]
        assert response["status"] == "committed" and response["occurrenceId"]
        assert continuation["outcomeId"] is None
        assert continuation["contextName"] == pending["continuation"]["contextName"]
        assert saved["currentContextId"] == pending["currentContextId"]
        assert saved["contexts"] == pending["contexts"]
        assert saved["nativeArtifact"] == pending["nativeArtifact"]
        assert [(r.seq, r.raw_text) for r in trace.records()] == raw
        api = EidosAPI(trace)
        recovered = api.recover_investigation(pending["id"])
        assert recovered["continuation"]["outcomeId"]
        assert recovered["continuation"]["contextName"] != continuation["contextName"]
        assert recovered["continuation"]["inquiry"]["responses"][0] == response
        assert len([row for row in occurrences(api) if row[1] == "DiscoveryOffer"]) == 1
        assert len(native_turns(trace)) == len(_pins(trace)) == 1
        assert recovered["currentContextId"] == pending["currentContextId"]
        assert recovered["continuation"]["nativeNext"]["status"] == "awaiting-admission"
    finally:
        if api is not None:
            api.close()
        trace.close()


@pytest.mark.parametrize("field", ["holder", "establishes", "consumes", "originMetadata", "checkpointId"])
def test_http_inquiry_cannot_supply_authority_successors(tmp_path, field):
    path = tmp_path / "authority.db"
    pending, _, _ = _seed(path, answered=False)
    trace = TraceStore(path)
    api = EidosAPI(trace)
    try:
        before = api.investigations.get(pending["id"])
        history = occurrences(api)
        authority = [tuple(row) for row in trace.db.execute("SELECT * FROM projections ORDER BY name")]
        status, _ = call(api, inquiry_path(pending) + "/responses", {
            "requestId": "arbitrary-successor", "decision": "refuse", field: "copied-authority",
        })
        assert status == 400
        assert api.investigations.get(pending["id"]) == before
        assert occurrences(api) == history
        assert [tuple(row) for row in trace.db.execute("SELECT * FROM projections ORDER BY name")] == authority
        assert len(native_turns(trace)) == 1
    finally:
        api.close()
        trace.close()


def test_generic_tm_successors_are_privileged_host_policy_not_inferred_from_consumption():
    # This executable counterexample documents why generic TM may not be exposed
    # to the inquiry caller. Its mechanism checks linearity, not semantic rights.
    tm = TrustedMachinery()
    try:
        domain = tm.admit_authority_domain(description={"scope": "synthetic review"}, establishes=(
            ProjectionGrant(key="read", holder="owner", description=projection_value(
                key="read", role="Reader", state="bounded",
            )),
        ), request_id="genesis")
        committed = tm.commit_projection_occurrence(kind="privileged-host-counterexample",
            consumes=(domain["projections"]["read"],), establishes=(
                ProjectionGrant(key="write", holder="different-holder", description=projection_value(
                    key="write", role="ArbitrarySuccessor", state="not-implied-by-reader",
                )),
            ), fact={}, request_id="privileged-transition")
        successor = tm.projection(committed["established"]["write"])
        assert successor["holder"] == "different-holder"
        assert successor["disposition"] == "live"
        assert successor["role"] == "ArbitrarySuccessor"
    finally:
        tm.close()
