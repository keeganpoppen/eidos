"""Seed exact historical-input reuse using authored history, never native work.

The ordinary API remains closed to native execution. The only output is installed
by the existing explicitly trusted synthetic history helper before browser use.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sqlite3

from eidos.api import EidosAPI
from eidos.serve import serve
from eidos.trace import TraceStore

spec = importlib.util.spec_from_file_location("reuse_authored_history", Path(__file__).with_name("recorded_experiment_demo.py"))
assert spec and spec.loader
recorded = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recorded)
MARKER = "synthetic-context-input-reuse/v1"
OLD_QUESTION = "OLD_QUESTION_ONLY: Which evidence justified the original retry decision?"
NEW_QUESTION = "What remains unresolved when these exact historical inputs are reconsidered?"


def seed(api: EidosAPI) -> dict:
    if api.store.records() or api.investigations.list():
        raise ValueError("Use an empty authored fixture database.")
    records = []
    for index, (thread, text) in enumerate((
        ("reuse-decisions", "A lost acknowledgement does not establish that an operation failed."),
        ("reuse-counterexamples", "An automatic retry could duplicate the previously accepted operation."),
        ("reuse-decisions", "Later display work checked wrapping, not retry semantics."),
    )):
        records.append(api.store.append(source=MARKER, direction="internal", message={
            "method": "$history/item", "params": {"threadId": thread, "turnId": f"turn-{index}", "item": {
                "id": f"reuse-evidence-{index}", "type": "agentMessage", "text": text,
                "futureFixtureField": {"retain": True, "ordinal": index}}}}))

    def selections(*indices):
        return [{"threadId": records[n].thread_id, "startSeq": records[n].seq, "endSeq": records[n].seq,
                 "rationale": f"Historical rationale for input {n + 1}"} for n in indices]

    source = api.investigations.create({"requestId": MARKER + "/source", "title": "Historical retry result",
        "question": "What is established by the recorded acknowledgement?", "selections": selections(0)})
    source = recorded.import_authored_result(api, source["id"], source["currentContextId"],
        f"AUTHORED_RESULT: preserve uncertainty about the first operation. [evidence:{records[0].seq}]")
    artifact = source["artifact"]["id"]
    source = api.investigations.adopt(source["id"], {"artifactId": artifact, "decision": "adopt",
        "note": "OLD_FROZEN_REVIEW: retained at the time these inputs were assembled."})
    inputs = [{"investigationId": source["id"], "artifactId": artifact,
               "rationale": "Keep this exact result and the review captured with it."}]
    owner = api.investigations.create({"requestId": MARKER + "/owner", "title": "Historical context to reconsider",
        "question": OLD_QUESTION, "selections": selections(0, 1), "artifactInputs": inputs})
    historical = deepcopy(owner["contexts"][0])
    source = recorded.import_authored_result(api, source["id"], source["currentContextId"],
        f"NEW_SOURCE_RESULT: later analysis must not replace the frozen input. [evidence:{records[0].seq}]")
    source = api.investigations.adopt(source["id"], {"artifactId": source["artifact"]["id"], "decision": "reject",
        "note": "NEW_SOURCE_REVIEW: a later result's review must not refresh an old frozen input."})
    owner = api.investigations.revise(owner["id"], {"requestId": MARKER + "/C1",
        "parentContextId": owner["currentContextId"], "question": "What did the later display work find?",
        "selections": selections(2), "artifactInputs": inputs})
    marker = {"schemaVersion": MARKER, "classification": "authored-host-history", "nativeOrModelCalls": 0,
        "owner": owner["id"], "sourceOwner": source["id"], "sourceArtifactId": artifact,
        "newerSourceArtifactId": source["artifact"]["id"],
        "historicalContextId": historical["id"], "currentContextId": owner["currentContextId"],
        "historicalContext": historical, "originalOwner": owner, "originalSource": source,
        "oldQuestion": OLD_QUESTION, "newQuestion": NEW_QUESTION, "humanBenefitMeasured": False}
    api.store.append(source=MARKER, direction="internal", message={"method": "$context-input-reuse/demo", "params": marker})
    return marker


def marker_at(path: Path) -> dict:
    if not path.is_file():
        raise ValueError("Resume needs the existing authored fixture database.")
    with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as db:
        rows = db.execute("SELECT raw_text FROM trace_records WHERE source=? AND method='$context-input-reuse/demo'", (MARKER,)).fetchall()
    if len(rows) != 1:
        raise ValueError("Not a unique context-input-reuse fixture.")
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
