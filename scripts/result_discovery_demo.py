"""Authored exact-result discovery, without native/account/model calls.

Seed a fresh --db with --output marker.json. --resume --serve uses the same
ordinary API with native admission closed; browser acceptance only reads/saves.
Historical result import is the existing explicitly trusted fixture helper.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import sqlite3

from eidos.api import EidosAPI
from eidos.serve import serve
from eidos.trace import TraceStore

spec = importlib.util.spec_from_file_location("recorded_discovery_fixture", Path(__file__).with_name("recorded_experiment_demo.py"))
assert spec and spec.loader
recorded = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recorded)
MARKER = "synthetic-result-discovery/v1"
QUESTION = "Why did cancelled preparation resume after restart?"
RESULT = "The stopped claim must survive restart; retain the original cancellation evidence."
SUPPORT = "A cancellation before launch must commit a stopped attempt claim, so reopening cannot start it."
EXCLUDED = "RAW_ONLY_DISCOVERY_CANARY"


def seed(api: EidosAPI) -> dict:
    if api.store.records() or api.investigations.list():
        raise ValueError("Use an empty authored fixture database.")
    row = api.store.append(source=MARKER, direction="internal", message={"method": "$history/item", "params": {
        "threadId": "discovery-source", "turnId": "original-decision", "item": {
            "id": "controlling-decision", "type": "agentMessage", "text": SUPPORT, "unknownFixtureField": EXCLUDED}}})
    selections = [{"threadId": row.thread_id, "startSeq": row.seq, "endSeq": row.seq,
                   "rationale": "Original controlling decision"}]
    work = api.investigations.create({"requestId": MARKER + "/owner", "title": "Release review",
                                      "question": QUESTION, "selections": selections})
    c0 = work["currentContextId"]
    work = api.investigations.revise(work["id"], {"requestId": MARKER + "/newer-context", "parentContextId": c0,
                                               "question": "What did the later display check establish?", "selections": selections})
    c1 = work["currentContextId"]
    old = recorded.import_authored_result(api, work["id"], c0, RESULT + f" [evidence:{row.seq}]")
    latest = recorded.import_authored_result(api, work["id"], c1, f"The later display check found no overflow. [evidence:{row.seq}]")
    decoy = api.investigations.create({"requestId": MARKER + "/decoy", "title": "Cancelled preparation checklist",
                                      "question": "Did the checklist retain a title?", "selections": selections})
    decoy = recorded.chain.authored_completion(api, decoy, f"This authored title match is not the controlling decision. [evidence:{row.seq}]")
    marker = {"schemaVersion": MARKER, "classification": "authored-host-history", "nativeOrModelCalls": 0,
              "owner": work["id"], "contextId": c0, "artifactId": old["artifact"]["id"],
              "attemptId": old["attempt"]["id"], "currentContextId": c1, "currentArtifactId": latest["artifact"]["id"],
              "decoyOwner": decoy["id"], "decoyArtifactId": decoy["artifact"]["id"],
              "questionQuery": "cancelled preparation", "resultQuery": "stopped claim", "question": QUESTION,
              "text": old["artifact"]["text"], "support": SUPPORT, "supportSeq": row.seq,
              "excludedCanary": EXCLUDED, "humanBenefitMeasured": False}
    api.store.append(source=MARKER, direction="internal", message={"method": "$result-discovery/demo", "params": marker})
    return marker


def marker_at(path: Path) -> dict:
    if not path.is_file():
        raise ValueError("Resume needs this authored fixture database.")
    with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as db:
        rows = db.execute("SELECT raw_text FROM trace_records WHERE source=? AND method='$result-discovery/demo'", (MARKER,)).fetchall()
    if len(rows) != 1:
        raise ValueError("Not a unique result-discovery fixture.")
    return json.loads(rows[0][0])["params"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--port", type=int, default=8767)
    args = parser.parse_args()
    if args.resume:
        marker = marker_at(args.db)
    else:
        if args.db.exists():
            raise ValueError("Use a fresh fixture database.")
        trace = TraceStore(args.db)
        api = EidosAPI(trace)
        try:
            marker = seed(api)
        finally:
            api.close()
            trace.close()
    if args.output:
        args.output.write_text(json.dumps(marker, indent=2) + "\n")
    print(json.dumps(marker, indent=2), flush=True)
    if args.serve:
        serve(args.db, port=args.port)


if __name__ == "__main__":
    main()
