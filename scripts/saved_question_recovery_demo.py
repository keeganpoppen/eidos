"""Saved-question recovery fixture over the existing labelled synthetic history."""
from __future__ import annotations

import argparse
import copy
import importlib.util
import json
from pathlib import Path
import sqlite3

from eidos.api import EidosAPI
from eidos.serve import serve
from eidos.trace import TraceStore

spec = importlib.util.spec_from_file_location("recorded_demo", Path(__file__).with_name("recorded_experiment_demo.py"))
assert spec and spec.loader
recorded = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recorded)
MARKER = "synthetic-saved-question-recovery/v1"
RATIONALE = "Recover why automatic retry was rejected: the first operation may already have completed despite its lost reply. Compare the original packet with the saved rejection evidence."
REVIEW = "Current synthetic review rejects adopting this comparison as a retry policy. The historical question and original evidence stay unchanged."


def seed(api: EidosAPI) -> dict:
    base = recorded.seed(api)
    owner = base["owner"]
    experiment = recorded.chain.call(api, f"/{owner}/experiments", {
        "requestId": MARKER + "/experiment", "baselineContextId": base["contexts"]["C0"],
        "baselineArtifactId": base["artifacts"]["A1"], "alternativeContextId": base["contexts"]["C1"],
        "rationale": RATIONALE})
    c1 = next(value for value in base["frozenContexts"] if value["id"] == base["contexts"]["C1"])
    rejection = next(value for value in c1["records"] if "Rejected: an automatic retry" in value["rawText"])
    target_focus = {"investigationId": owner, "contextId": c1["id"], "seq": rejection["seq"], "threadId": rejection["threadId"]}
    saved = {}
    def snapshot(name, title, arrangement, focus, *, renderer=recorded.snapshots.RENDERER):
        value = recorded.snapshots.call(api, body={"requestId": MARKER + "/" + name, "title": title,
            "rendererVersion": renderer, "arrangement": arrangement, "focus": focus})["composition"]
        saved[name] = value
        return value
    snapshot("target", "Unknown reply · retry review", recorded.arrangement(experiment), target_focus)
    snapshot("broader", "Unknown reply · retry review (broader inputs)", recorded.arrangement(base["experiments"]["E2"]), None)
    snapshot("current", "Unknown reply · retry review (current result)", {
        "left": {"investigationId": owner, "contextId": base["contexts"]["C2"], "artifactId": base["artifacts"]["A2"]},
        "right": {"investigationId": owner, "contextId": base["contexts"]["C1"]}, "lens": "result", "layout": "beside"}, None)
    snapshot("oldRenderer", "Unknown reply · retry review (older renderer)", recorded.arrangement(experiment),
             copy.deepcopy(base["snapshot"]["focus"]), renderer="nema-content-blocks/v0;authored-unknown-parser")
    missing = recorded.chain.call(api, body={"requestId": MARKER + "/missing-source", "title": "Synthetic later unavailable source",
        "question": "Was a transport retry ever explicitly authorized?", "selections": [{"threadId": rejection["threadId"],
        "startSeq": rejection["seq"], "endSeq": rejection["seq"], "rationale": "Saved rejection evidence"}]})
    missing = recorded.chain.authored_completion(api, missing, f"Authored source later removed from this fixture. [evidence:{rejection['seq']}]")
    snapshot("missing", "Unknown reply · retry review (unavailable source)", {
        "left": {"investigationId": missing["id"], "contextId": missing["currentContextId"], "artifactId": missing["artifact"]["id"]},
        "right": {"investigationId": owner, "contextId": base["contexts"]["C1"]}, "lens": "context", "layout": "beside"}, None)
    # Explicit trusted fixture import/removal, not a production deletion action.
    # The immutable saved snapshot must remain inspectable without rebinding.
    with api.investigations._transaction():
        api.store.db.execute("DELETE FROM investigation_requests WHERE investigation_id=?", (missing["id"],))
        api.store.db.execute("DELETE FROM investigations WHERE id=?", (missing["id"],))
    current_review = recorded.chain.call(api, f"/{owner}/experiments/{experiment['id']}/review", {
        "requestId": MARKER + "/current-review", "decision": "reject", "rationale": REVIEW})
    marker = {**base, "schemaVersion": MARKER, "baseFixtureSchema": base["schemaVersion"],
        "recoverySnapshots": saved, "recoveryExperiment": experiment, "currentRecoveryReview": current_review,
        "rejectionRecord": rejection, "missingOwner": missing["id"], "search": "Unknown reply",
        "expectedRationale": RATIONALE, "expectedCurrentReview": REVIEW,
        "missingSourceConstruction": "Trusted synthetic fixture removes one owner only after saving its exact ordinary snapshot."}
    api.store.append(source=MARKER, direction="internal", message={"method": "$saved-question-recovery/demo", "params": marker})
    return marker


def resume(path: Path) -> dict:
    if not path.is_file():
        raise ValueError("--resume requires this script's marked fixture")
    with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as db:
        rows = db.execute("SELECT raw_text FROM trace_records WHERE source=? AND method='$saved-question-recovery/demo'", (MARKER,)).fetchall()
    if len(rows) != 1:
        raise ValueError("not a unique saved-question synthetic fixture")
    return json.loads(rows[0][0])["params"]


def inspect(api: EidosAPI, marker: dict) -> dict:
    original = {**marker, "schemaVersion": marker["baseFixtureSchema"]}
    recorded.inspect(api, original)
    for value in marker["recoverySnapshots"].values():
        assert recorded.snapshots.call(api, "/" + value["id"], method="GET")["composition"] == value
    assert recorded.experiment(api, marker["owner"], marker["recoveryExperiment"]["id"]) == marker["currentRecoveryReview"]
    status, _ = api.dispatch(recorded.chain.Request(), "GET", f"/api/investigations/{marker['missingOwner']}/view", {})
    assert status == 404
    assert not any(record.method == "turn/start" for record in api.store.records())
    return {**marker, "reopenedSavedQuestionsExact": True,
        "humanBenefitMeasured": False, "nativeOrModelCalls": 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    marker = resume(args.db) if args.resume else None
    if marker is None and args.db.exists():
        raise ValueError("fixture construction requires a new database")
    trace = TraceStore(args.db)
    api = EidosAPI(trace)
    try:
        marker = marker or seed(api)
    finally:
        api.close(); trace.close()
    trace = TraceStore(args.db)
    api = EidosAPI(trace)
    try:
        result = json.dumps(inspect(api, marker), indent=2) + "\n"
    finally:
        api.close(); trace.close()
    if args.output:
        args.output.write_text(result)
    print(result, end="")
    if args.serve:
        fake = Path(__import__("eidos.api", fromlist=["__file__"]).__file__).resolve().parents[2] / "tests/fixtures/investigation_appserver.py"
        serve(args.db, codex=str(fake), port=args.port)


if __name__ == "__main__":
    main()
