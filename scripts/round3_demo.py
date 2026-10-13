"""Synthetic inquiry → disclosure → new attempt → evaluated alternative.

uv run python scripts/round3_demo.py --db /tmp/nema-round3.db
uv run python scripts/round3_demo.py --db /tmp/nema-round3.db --resume

The executable fixture is local Python. No native account, provider or model is
used. Reopening verifies the saved result and never dispatches work.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3
import time

from eidos.api import EidosAPI
from eidos.trace import TraceStore
from investigation_continuation_demo import call
from investigation_demo import seed


SOURCE = "synthetic-round3-demo/v1"
FIXTURE = Path(__file__).resolve().parents[1] / "tests/fixtures/investigation_appserver.py"


def wait(api, identifier, predicate):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        value = api.investigations.get(identifier)
        if predicate(value):
            return value
        time.sleep(.01)
    raise RuntimeError("synthetic investigation did not settle")


def marker(path):
    if not path.is_file():
        raise ValueError("resume requires this script's completed synthetic database")
    with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as db:
        row = db.execute("SELECT raw_text FROM trace_records WHERE source=? ORDER BY seq DESC LIMIT 1", (SOURCE,)).fetchone()
        if row is None:
            raise ValueError("synthetic Round 3 completion marker missing; partial work requires inspection")
        return json.loads(row[0])["params"]


def report(api, trace, ids):
    work = api.investigations.get(ids["investigationId"])
    inquiry = work["continuation"]["inquiry"]
    attempts = work.get("attemptHistory", []) + [work["attempt"]]
    experiment = api.investigation_experiments.get(work["id"], ids["experimentId"])
    rejected = api.investigation_experiments.get(work["id"], ids["rejectedExperimentId"])
    return {
        "schemaVersion": 1, "evidenceClass": "synthetic", "nativeModelCalls": 0,
        "investigationId": work["id"], "attemptIds": [a["id"] for a in attempts],
        "requestPins": [a["contextRequestName"] for a in attempts],
        "fixtureTurns": len([r for r in trace.records() if r.method == "turn/start"]),
        "inquiryId": inquiry["id"], "responseIds": [r["id"] for r in inquiry["responses"]],
        "sourceDecisionOccurrence": inquiry["responses"][-1]["occurrenceId"],
        "incorporationOutcome": work["continuation"]["outcomeId"],
        "originalContextId": work["nativeArtifact"]["contextId"],
        "expandedContextId": work["attempt"]["contextId"],
        "baselineArtifactId": work["nativeArtifact"]["id"],
        "receiptArtifactId": work["artifactHistory"][0]["id"],
        "returnedArtifactId": work["artifact"]["id"],
        "executionEvidence": work["artifact"]["executionEvidence"],
        "experiment": experiment, "rejectedExperiment": rejected,
        "limitation": "Fixture inquiry and answers; measured packet changes do not establish improved model reasoning.",
    }


def run(path: Path, resume=False):
    ids = marker(path) if resume else None
    trace = TraceStore(path)
    if not resume:
        packet = seed(trace)
    api = EidosAPI(trace, codex=str(FIXTURE))
    try:
        if resume:
            before = len(trace.records())
            result = report(api, trace, ids)
            assert result["fixtureTurns"] == 2 and len(trace.records()) == before
            return result
        selections = packet["selections"]
        # Keep one support record from each thread and explicitly request the
        # omitted acknowledgement/completion evidence in the fixture scenario.
        initial = [selections[0], selections[-1]]
        work = call(api, "", {**packet, "requestId": "round3-create",
            "question": packet["question"] + " [synthetic-needs-evidence]", "selections": initial})
        identifier = work["id"]
        call(api, f"/{identifier}/dispatch", {"contextId": work["currentContextId"]})
        pending = wait(api, identifier, lambda v: (v.get("continuation") or {}).get("inquiry") is not None)
        inquiry_path = f"/{identifier}/inquiries/{pending['continuation']['inquiry']['id']}"
        call(api, inquiry_path + "/responses", {"requestId": "round3-defer", "decision": "defer", "note": "Inspect original support first."})
        api.close()
        trace.close()
        trace = TraceStore(path)
        api = EidosAPI(trace, codex=str(FIXTURE))
        offered = call(api, inquiry_path + "/responses", {"requestId": "round3-offer", "decision": "offer",
            "note": "The acknowledgement/completion record is additional attributed fixture evidence.",
            "selections": [{"threadId": "fixture-design", "startSeq": 14, "endSeq": 14,
                            "rationale": "Requested acknowledgement and recorded completion."}]})
        continuation = offered["continuation"]
        body = {"requestId": "round3-followup", "continuationId": continuation["id"],
                "contextId": continuation["nativeNext"]["contextId"]}
        call(api, f"/{identifier}/continue", body)
        completed = wait(api, identifier, lambda v: v["attempt"].get("continuedFrom") and v["status"] == "completed")
        call(api, f"/{identifier}/continue", body)
        comparison = {"requestId": "round3-compare", "baselineContextId": completed["nativeArtifact"]["contextId"],
            "baselineArtifactId": completed["nativeArtifact"]["id"], "alternativeContextId": completed["attempt"]["contextId"],
            "rationale": "Retain the requested completion source beside the original evidence; inspect the increased packet cost."}
        experiment = call(api, f"/{identifier}/experiments", comparison)
        # Automated demonstration decisions explicitly identify their actor.
        # The public owner route is exercised in tests/Chromium; this report must
        # not claim that its script's decision came from the human owner.
        ledger = api.investigation_experiments.ledger
        review = ledger.review("round3-demo-review", proposal=experiment["proposalId"],
            evaluations=[experiment["evaluation"]["id"]], decision="adopt", actor="synthetic-demo",
            rationale="Exercise durable decision storage only.", review_kind="synthetic")
        adoption = ledger.adopt("round3-demo-adoption", review=review.name)
        ledger.rollback("round3-demo-rollback", adoption=adoption.name, actor="synthetic-demo", rationale="Restore the original candidate in this synthetic demonstration.")
        rejected = call(api, f"/{identifier}/experiments", {**comparison, "requestId": "round3-rejected"})
        ledger.review("round3-demo-rejection", proposal=rejected["proposalId"],
            evaluations=[rejected["evaluation"]["id"]], decision="reject", actor="synthetic-demo",
            rationale="No measured answer-quality improvement; preserve the counterexample.", review_kind="synthetic")
        ids = {"investigationId": identifier, "experimentId": experiment["id"], "rejectedExperimentId": rejected["id"]}
        trace.append(source=SOURCE, direction="internal", message={"method": "$round3/completed", "params": ids})
        result = report(api, trace, ids)
        assert result["fixtureTurns"] == 2 and result["executionEvidence"] == "synthetic"
        return result
    finally:
        api.close()
        trace.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    print(json.dumps(run(args.db, args.resume), indent=2))
