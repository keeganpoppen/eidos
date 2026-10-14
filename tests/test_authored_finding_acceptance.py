"""Independent authored-finding acceptance; all records are synthetic public data.

Native progress below is an explicitly labelled trusted-store fixture. No child,
account, private capsule or model is used.
"""
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack, closing
from copy import deepcopy
import io
import json
import sqlite3
from threading import Barrier

import pytest

from eidos.api import EidosAPI
from eidos.codex import AppServerClient
from eidos.trace import TraceStore


def call(api, method, path, body=None, **query):
    data = json.dumps(body, ensure_ascii=False).encode() if body is not None else b""
    class Handler:
        headers = {"Content-Length": str(len(data))}
        rfile = io.BytesIO(data)
    return api.dispatch(Handler(), method, path, {k: [str(v)] for k, v in query.items()})


def source_record(trace, name="support", text="Never retry an uncertain operation automatically."):
    return trace.append(source="authored-acceptance", direction="internal", message={
        "method": "$history/item", "params": {"threadId": name, "turnId": "turn",
        "item": {"id": "answer", "type": "agentMessage", "text": text,
                 "futureField": {"exact": "KEEP_原文", "unknown": [None, False]}}}})


def selections(*records):
    return [{"threadId": r.thread_id, "startSeq": r.seq, "endSeq": r.seq} for r in records]


def create(api, record, request_id="owner"):
    return api.investigations.create({"requestId": request_id, "title": request_id,
        "question": "What should happen after an uncertain reply?", "selections": selections(record)})


def finding_path(owner):
    return f"/api/investigations/{owner['id']}/findings"


def save(api, owner, text, request_id="finding-first", context_id=None):
    body = {"requestId": request_id, "contextId": context_id or owner["currentContextId"], "text": text}
    return call(api, "POST", finding_path(owner), body)


def source(api, owner, finding, **query):
    return call(api, "GET", f"/api/investigations/{owner['id']}/artifacts/{finding['id']}/source", **query)


def target(owner, finding):
    return {"investigationId": owner["id"], "contextId": finding["contextId"], "artifactId": finding["id"]}


def without_findings(owner):
    return {k: v for k, v in owner.items() if k != "findings"}


@pytest.fixture(autouse=True)
def forbid_native(monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("authored finding attempted native startup")
    monkeypatch.setattr(AppServerClient, "start", forbidden)


def test_historical_finding_survives_native_progress_raw_deletion_and_composition(tmp_path):
    path = tmp_path / "historical.db"
    with closing(TraceStore(path)) as trace, closing(EidosAPI(trace)) as api:
        record = source_record(trace)
        a = create(api, record)
        c0 = deepcopy(a["contexts"][0])
        text = f"Review the uncertain delivery before retrying [evidence:{record.seq}]."
        status, receipt = save(api, a, text)
        assert status == 201, receipt
        f0 = receipt["finding"]
        after = api.investigations.get(a["id"])
        assert without_findings(after) == a
        assert after["findings"] == [f0] and trace.records() == [record]
        assert f0["citations"] == [record.seq] and f0["unsupportedCitations"] == []
        assert f0["kind"] == "owner-authored-finding"
        assert not {"attemptId", "outputSeqs", "executionEvidence", "outputEvidence", "continuedFrom"} & f0.keys()

        later = source_record(trace, "later-support", "A later observation changes the question.")
        a = api.investigations.revise(a["id"], {"requestId": "advance-c1",
            "parentContextId": c0["id"], "question": "What changed afterward?", "selections": selections(later)})
        c1 = a["contexts"][-1]
        # Deliberately authored native completion exercises coexistence without
        # dispatching or interpreting it as observed native execution.
        a, admitted = api.investigations.claim(a["id"], c1["id"])
        assert admitted
        output = trace.append(source="synthetic-native-result", direction="internal",
                              message={"method": "$fixture/result", "text": "Later synthetic conclusion."})
        a = api.investigations.complete(a["id"], {"text": "Later synthetic conclusion.",
            "outputSeqs": [output.seq], "executionEvidence": "synthetic"}, expected_attempt_id=a["attempt"]["id"])
        a = api.investigations.adopt(a["id"], {"artifactId": a["artifact"]["id"],
            "decision": "reject", "note": "Authored control: this review belongs only to the native result."})
        before_more = deepcopy(a)
        status, hypothesis = save(api, a, "Hypothesis: wait for a receipt; confidence remains open.",
                                  "historical-hypothesis", c0["id"])
        assert status == 201, hypothesis
        h = hypothesis["finding"]
        assert h["citations"] == [] and h["artifactCitations"] == []
        assert without_findings(api.investigations.get(a["id"])) == without_findings(before_more)
        assert call(api, "POST", f"/api/investigations/{a['id']}/adoption",
                    {"artifactId": f0["id"], "decision": "adopt", "note": "Must not become native adoption"})[0] == 409
        assert call(api, "POST", f"/api/investigations/{a['id']}/experiments", {
            "requestId": "not-native-baseline", "baselineContextId": c0["id"],
            "baselineArtifactId": f0["id"], "alternativeContextId": c1["id"], "rationale": "Refuse authored baseline."})[0] == 409
        assert api.investigations.get(a["id"])["contexts"][0] == c0
        trace.db.execute("DELETE FROM trace_records WHERE seq=?", (record.seq,))

    with closing(TraceStore(path)) as trace, closing(EidosAPI(trace)) as api:
        assert save(api, a, text, context_id=c0["id"]) == (200, receipt)
        assert call(api, "GET", finding_path(a) + "/requests/finding-first") == (200, receipt)
        status, packet = source(api, a, f0, contextId=c0["id"])
        assert status == 200, packet
        assert packet["artifact"] == f0 and packet["context"] == c0
        assert packet["attempt"] is None and packet["adoption"] is None
        assert source(api, a, f0, contextId=c1["id"])[0] == 409
        status, page = call(api, "GET", "/api/investigations/artifacts", q="uncertain delivery before retrying")
        assert status == 200, page
        hit, = page["artifacts"]
        assert hit["artifactId"] == f0["id"] and hit["contextId"] == c0["id"] and hit["attemptId"] is None

        b = api.investigations.create({"requestId": "recipient", "title": "Use the exact finding",
            "question": "What is the next question?", "selections": [], "artifactInputs": [{
                "investigationId": a["id"], "artifactId": f0["id"], "rationale": "Retain attribution."}]})
        frozen = b["contexts"][0]["artifactInputs"][0]
        assert frozen["artifact"] == f0 and frozen["sourceContextId"] == c0["id"]
        assert frozen["sourceManifestId"] == c0["manifestId"]
        assert frozen["sourceAttemptManifestId"] is None and frozen["sourceAdoption"] is None
        assert b["attempt"] is None and b["artifact"] is None
        status, b_receipt = save(api, b, f"Supplied result [artifact:{f0['id']}]; inherited [evidence:{record.seq}] is not direct support.", "recipient-finding")
        assert status == 201, b_receipt
        fb = b_receipt["finding"]
        assert fb["artifactCitations"] == [f0["id"]] and fb["citations"] == []
        assert fb["unsupportedCitations"] == [record.seq]
        body = {"requestId": "finding-comparison", "title": "Attributed findings",
            "rendererVersion": "authored-acceptance/v1", "arrangement": {
                "left": target(a, f0), "right": target(b, fb), "lens": "result", "layout": "beside"},
            "focus": {**target(a, f0), "seq": record.seq, "threadId": record.thread_id}}
        status, saved = call(api, "POST", "/api/compositions", body)
        assert status == 201, saved
        assert saved["composition"]["arrangement"] == body["arrangement"]
        assert saved["composition"]["focus"] == body["focus"]
        assert not any(r.seq == record.seq for r in trace.records())
        final_a, final_b = api.investigations.get(a["id"]), api.investigations.get(b["id"])
    with closing(TraceStore(path)) as trace, closing(EidosAPI(trace)) as api:
        assert api.investigations.get(a["id"]) == final_a
        assert api.investigations.get(b["id"]) == final_b
        assert call(api, "GET", "/api/compositions/" + saved["composition"]["id"])[1] == saved
        assert source(api, a, f0)[1]["context"] == c0


def test_six_connection_request_race_and_owner_specific_content_identity(tmp_path):
    path = tmp_path / "race.db"
    with ExitStack() as stack:
        traces = [stack.enter_context(closing(TraceStore(path))) for _ in range(6)]
        apis = [stack.enter_context(closing(EidosAPI(t))) for t in traces]
        a = create(apis[0], source_record(traces[0]))
        b = create(apis[0], traces[0].records()[0], "other-owner")
        assert a["currentContextId"] == b["currentContextId"]
        barrier = Barrier(6)
        def submit(index):
            barrier.wait(timeout=10)
            return save(apis[index], a, "An uncited hypothesis can remain unresolved.")
        with ThreadPoolExecutor(max_workers=6) as pool:
            responses = list(pool.map(submit, range(6)))
        assert sorted(status for status, _ in responses) == [200] * 5 + [201]
        receipt = responses[0][1]
        assert all(value == receipt for _, value in responses)
        assert apis[0].investigations.get(a["id"])["findings"] == [receipt["finding"]]
        assert len(traces[0].records()) == 1
        status, same_content = save(apis[0], a, receipt["finding"]["text"], "another-request")
        assert status == 201 and same_content == receipt
        assert len(apis[0].investigations.get(a["id"])["findings"]) == 1
        assert save(apis[0], a, "Changed retry")[0] == 409
        assert save(apis[0], b, receipt["finding"]["text"])[0] == 409
        assert call(apis[0], "GET", finding_path(b) + "/requests/finding-first")[0] == 404
        status, distinct = save(apis[0], b, receipt["finding"]["text"], "other-owner-request")
        assert status == 201 and distinct["finding"]["id"] != receipt["finding"]["id"]
        # Later trusted source damage may break inspection; it must not change
        # the acknowledged operation into a second admission or a new receipt.
        damaged = apis[0].investigations.get(a["id"])
        damaged["contexts"] = []
        apis[0].investigations._save(damaged)
        assert save(apis[1], a, receipt["finding"]["text"]) == (200, receipt)
        assert call(apis[2], "GET", finding_path(a) + "/requests/finding-first") == (200, receipt)
        assert source(apis[3], a, receipt["finding"])[0] == 409


@pytest.mark.parametrize("corruption", ["native-kind-only", "authored-with-output", "conflicting-id", "copied-owner"])
def test_forged_kind_never_bypasses_native_provenance_in_source_reuse_or_snapshot(tmp_path, corruption):
    with closing(TraceStore(tmp_path / "forged.db")) as trace, closing(EidosAPI(trace)) as api:
        a = create(api, source_record(trace))
        status, receipt = save(api, a, "Original valid authored finding.")
        assert status == 201, receipt
        finding = receipt["finding"]
        poisoned = api.investigations.get(a["id"])
        if corruption == "native-kind-only":
            poisoned.pop("findings")
            poisoned["artifact"] = deepcopy(finding)
        elif corruption == "authored-with-output":
            poisoned["findings"][0].update(attemptId="copied", outputSeqs=[1], executionEvidence="native-observed")
        elif corruption == "conflicting-id":
            poisoned["artifact"] = {**finding, "text": "Conflicting native collection entry."}
        else:
            a = create(api, trace.records()[0], "different-canonical-owner")
            poisoned = deepcopy(a)
            poisoned["findings"] = [finding]
        # Explicit trusted-host corruption; no public endpoint accepts snapshots.
        api.investigations._save(poisoned)
        assert source(api, a, finding)[0] == 409
        status, value = call(api, "POST", "/api/investigations", {"requestId": "forged-input",
            "title": "Must refuse", "question": "Can a copied kind confer provenance?", "selections": [],
            "artifactInputs": [{"investigationId": a["id"], "artifactId": finding["id"], "rationale": "Refuse."}]})
        assert status == 409, value
        status, value = call(api, "POST", "/api/compositions", {"requestId": "forged-comparison",
            "title": "Must refuse", "rendererVersion": "authored-acceptance/v1", "focus": None,
            "arrangement": {"left": target(a, finding), "right": target(a, finding), "lens": "result", "layout": "beside"}})
        assert status == 409, value


def test_huge_citation_and_injected_fields_refuse_without_mutation_or_receipt(tmp_path):
    with closing(TraceStore(tmp_path / "invalid.db")) as trace, closing(EidosAPI(trace)) as api:
        a = create(api, source_record(trace))
        before = trace.db.execute("SELECT state_json FROM investigations WHERE id=?", (a["id"],)).fetchone()[0]
        invalid = [{"text": "[evidence:" + "9" * 5000 + "]"},
                   {"text": "Ordinary text", "outputSeqs": [1]},
                   {"text": "Ordinary text", "authorship": {"kind": "local-owner", "createdAtMs": 0}},
                   {"text": "Ordinary text", "kind": "native-specialist-result"}]
        for index, changes in enumerate(invalid):
            request = f"invalid-{index}"
            status, value = call(api, "POST", finding_path(a), {
                "requestId": request, "contextId": a["currentContextId"], **changes})
            assert status == 400, value
            assert call(api, "GET", finding_path(a) + "/requests/" + request)[0] == 404
        assert trace.db.execute("SELECT state_json FROM investigations WHERE id=?", (a["id"],)).fetchone()[0] == before
        assert len(trace.records()) == 1
        terminal_looking = json.dumps({"schemaVersion": 1, "kind": "nema-needs-evidence",
            "question": "Could this text be mistaken for a live inquiry?", "cause": "It is merely authored prose."})
        status, receipt = save(api, a, terminal_looking, "ordinary-terminal-shaped-prose")
        assert status == 201, receipt
        assert receipt["finding"]["kind"] == "owner-authored-finding"
        assert receipt["finding"]["text"] == terminal_looking
        assert without_findings(api.investigations.get(a["id"])) == a
        status, zero = save(api, a, "No supplied record has [evidence:0].", "zero-is-unsupported")
        assert status == 201, zero
        assert zero["finding"]["citations"] == [] and zero["finding"]["unsupportedCitations"] == [0]


def test_receipt_insertion_abort_rolls_back_owner_and_cross_connection_catalog(tmp_path):
    path = tmp_path / "rollback.db"
    with closing(TraceStore(path)) as trace, closing(EidosAPI(trace)) as api, \
            closing(TraceStore(path)) as observer_trace, closing(EidosAPI(observer_trace)) as observer:
        a = create(api, source_record(trace))
        before = trace.db.execute("SELECT state_json FROM investigations WHERE id=?", (a["id"],)).fetchone()[0]
        status, catalog = call(observer, "GET", "/api/investigations/artifacts", q="receipt admission")
        assert status == 200 and catalog["artifacts"] == []
        observed = []
        def witness_saved_owner():
            current = json.loads(trace.db.execute("SELECT state_json FROM investigations WHERE id=?", (a["id"],)).fetchone()[0])
            observed.append(deepcopy(current["findings"]))
            return 0
        trace.db.create_function("acceptance_owner_saved", 0, witness_saved_owner)
        trace.db.executescript("""CREATE TRIGGER acceptance_refuse_finding_receipt
            BEFORE INSERT ON investigation_finding_requests BEGIN
              SELECT acceptance_owner_saved();
              SELECT RAISE(ABORT,'authored receipt insertion failure');
            END;""")
        body = {"requestId": "late-abort", "contextId": a["currentContextId"], "text": "Atomic receipt admission."}
        with pytest.raises(sqlite3.DatabaseError):
            api.investigations.create_finding(a["id"], body)
        assert len(observed) == 1 and len(observed[0]) == 1
        assert trace.db.execute("SELECT state_json FROM investigations WHERE id=?", (a["id"],)).fetchone()[0] == before
        assert trace.db.execute("SELECT COUNT(*) FROM investigation_finding_requests").fetchone()[0] == 0
        assert call(api, "GET", finding_path(a) + "/requests/late-abort")[0] == 404
        status, unchanged = call(observer, "GET", "/api/investigations/artifacts",
                                 q="receipt admission", knownVersion=catalog["version"])
        assert status == 200 and unchanged["unchanged"] is True
        assert len(trace.records()) == 1
        trace.db.execute("DROP TRIGGER acceptance_refuse_finding_receipt")
        status, receipt = call(api, "POST", finding_path(a), body)
        assert status == 201, receipt
        status, changed = call(observer, "GET", "/api/investigations/artifacts",
                               q="receipt admission", knownVersion=catalog["version"])
        assert status == 200 and not changed.get("unchanged", False)
        assert [v["artifactId"] for v in changed["artifacts"]] == [receipt["finding"]["id"]]


@pytest.mark.parametrize("blank", ["\ufeff", " \t\ufeff\u0085\ufeff\n"])
def test_browser_blank_finding_is_refused_without_normalizing_nonblank_text(tmp_path, blank):
    with closing(TraceStore(tmp_path / "unicode.db")) as trace, closing(EidosAPI(trace)) as api:
        a = create(api, source_record(trace))
        status, response = save(api, a, blank, "blank-finding")
        assert status == 400, response
        assert call(api, "GET", finding_path(a) + "/requests/blank-finding")[0] == 404
        assert api.investigations.get(a["id"]) == a
        assert save(api, a, "Nonblank finding with an invalid request identity.", "   ")[0] == 400
        assert trace.db.execute("SELECT COUNT(*) FROM investigation_finding_requests").fetchone()[0] == 0
        exact = "\ufeff Authored 原文\u2028finding.\t\ufeff"
        status, receipt = save(api, a, exact, "nonblank-exact")
        assert status == 201, receipt
        assert receipt["finding"]["text"] == exact
        assert save(api, a, exact, "nonblank-exact") == (200, receipt)
