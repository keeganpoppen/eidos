"""Persist real experiment records over explicitly synthetic canonical histories.

The public draft API creates all frozen packets before any result exists. A
labelled trusted-host fixture import then positions synthetic attempts at those
saved contexts, preserving every prior attempt/result and using canonical pins
and completion. This is not an executable historical-context dispatch feature.
Experiment, review, snapshot and exact-source reads use their actual APIs.
"""
from __future__ import annotations

import argparse
import copy
import importlib.util
import json
from pathlib import Path
import sqlite3
from typing import Any

from eidos.api import EidosAPI
from eidos.trace import TraceStore
from eidos.serve import serve

spec = importlib.util.spec_from_file_location("snapshot_demo", Path(__file__).with_name("composition_snapshot_demo.py"))
assert spec and spec.loader
snapshots = importlib.util.module_from_spec(spec)
spec.loader.exec_module(snapshots)
chain = snapshots.chain
MARKER = "synthetic-recorded-experiment/v1"
QUESTION = "Which original decision controls retrying an operation with an unknown acknowledgement?"


def experiment(api: EidosAPI, owner: str, identifier: str) -> dict[str, Any]:
    return chain.call(api, f"/{owner}/experiments/{identifier}", method="GET")


def arrangement(value: dict[str, Any]) -> dict[str, Any]:
    fields = ("investigationId", "contextId", "artifactId")
    return {"left": {key: value["baseline"][key] for key in fields if key in value["baseline"]},
            "right": {key: value["alternative"][key] for key in fields if key in value["alternative"]},
            "lens": "context", "layout": "beside", "intent": "alternative-review", "experimentId": value["id"]}


def immutable_experiment(value: dict[str, Any]) -> dict[str, Any]:
    return {key: content for key, content in value.items() if key not in {"status", "review", "adoption", "rollback"}}


def import_authored_result(api: EidosAPI, owner_id: str, context_id: str, text: str) -> dict[str, Any]:
    """Trusted fixture-only history construction; no production admission claim.

    Actual frozen contexts, manifest pins, output records and canonical artifact
    citation/classification logic are retained. No native process can be launched.
    """
    with api.investigations._transaction():
        work = api.investigations.get(owner_id)
        if context_id not in {context["id"] for context in work["contexts"]}:
            raise ValueError("fixture cannot invent an unowned context")
        if work["attempt"]:
            work.setdefault("attemptHistory", []).append(work["attempt"])
        if work["artifact"]:
            work.setdefault("artifactHistory", []).append(work["artifact"])
        work.update(currentContextId=context_id, attempt=None, artifact=None, adoption=None, status="draft")
        api.investigations._save(work)
    claimed, fresh = api.investigations.claim(owner_id, context_id)
    if not fresh:
        raise ValueError("synthetic history requires a fresh pinned attempt")
    attempt_id = claimed["attempt"]["id"]
    source, thread, turn = MARKER + "/" + attempt_id, "fixture-result-" + owner_id, attempt_id
    api.investigations.update_attempt(owner_id, source=source, threadId=thread, turnId=turn,
                                      expected_attempt_id=attempt_id)
    record = api.store.append(source=source, direction="internal", message={
        "method": "$history/item", "params": {"threadId": thread, "turnId": turn,
        "item": {"id": "authored-" + attempt_id, "type": "agentMessage", "text": text,
                 "futureFixtureField": {"authored": True, "capturedFromNative": False}}}})
    return api.investigations.complete(owner_id, {"text": text, "outputSeqs": [record.seq],
        "executionEvidence": "synthetic"}, expected_attempt_id=attempt_id)


def seed(api: EidosAPI) -> dict[str, Any]:
    if api.store.records() or api.investigations.list():
        raise ValueError("recorded experiment fixture requires an empty database")
    records = []
    for ordinal, text in enumerate((chain.CONTROL, chain.OMITTED,
            "Rejected: an automatic retry can duplicate an operation whose first reply was lost.")):
        records.append(api.store.append(source=MARKER, direction="internal", message={
            "method": "$history/item", "params": {"threadId": "recorded-experiment-origin", "turnId": f"support-{ordinal}",
            "item": {"id": f"synthetic-support-{ordinal}", "type": "agentMessage", "text": text,
                     "unknownFixtureField": {"retain": True, "ordinal": ordinal}}}}))
    def selections(indices):
        return [{"threadId": records[n].thread_id, "startSeq": records[n].seq, "endSeq": records[n].seq,
                 "rationale": "Original decision support" if n == 0 else "Additional saved observation"} for n in indices]
    source = chain.call(api, body={"requestId": MARKER + "/source", "title": "Source result · recorded experiment",
        "question": QUESTION, "selections": selections([0, 2])})
    source = chain.authored_completion(api, source, "Synthetic source result; no model called. " + chain.CONTROL
        + f" [evidence:{records[0].seq}] [evidence:{records[2].seq}]")
    source_artifact = source["artifact"]["id"]
    inputs = [{"investigationId": source["id"], "artifactId": source_artifact,
               "rationale": "Retain the same exact source result; inspect its separate frozen review."}]
    work = chain.call(api, body={"requestId": MARKER + "/owner", "title": "Recorded experiment · retained C0 and context-only C1",
        "question": QUESTION, "selections": selections([0]), "artifactInputs": inputs})
    c0 = work["currentContextId"]
    source = chain.call(api, f"/{source['id']}/adoption", {"artifactId": source_artifact, "decision": "reject",
        "note": "Synthetic source review: rejection is attributable history, not deletion or proof."})
    work = chain.call(api, f"/{work['id']}/contexts", {"requestId": MARKER + "/C1", "parentContextId": c0,
        "question": QUESTION, "selections": selections([0, 2]), "artifactInputs": inputs})
    c1 = work["currentContextId"]
    work = chain.call(api, f"/{work['id']}/contexts", {"requestId": MARKER + "/C2", "parentContextId": c1,
        "question": QUESTION, "selections": selections([0, 1, 2]), "artifactInputs": inputs})
    c2 = work["currentContextId"]
    work = import_authored_result(api, work["id"], c0,
        f"Synthetic retained A1 baseline; no model called. {chain.CONTROL} [evidence:{records[0].seq}] [artifact:{source_artifact}]")
    a1, attempt1 = copy.deepcopy(work["artifact"]), copy.deepcopy(work["attempt"])
    experiments = {}
    for name, context in (("E1", c1), ("E2", c2)):
        experiments[name] = chain.call(api, f"/{work['id']}/experiments", {"requestId": MARKER + "/" + name,
            "baselineContextId": c0, "baselineArtifactId": a1["id"], "alternativeContextId": context,
            "rationale": f"Recorded {name}: compare saved inputs, including a changed frozen review of the same result."})
    saved = snapshots.call(api, body={"requestId": MARKER + "/snapshot", "title": "Recorded E1 before later results",
        "rendererVersion": snapshots.RENDERER, "arrangement": arrangement(experiments["E1"]),
        "focus": {"investigationId": work["id"], "contextId": c0, "artifactId": a1["id"],
                  "blockId": "block-0", "seq": records[0].seq, "threadId": records[0].thread_id}})["composition"]
    work = import_authored_result(api, work["id"], c1,
        f"LATER_C1_RESULT_NOT_PINNED: synthetic later output must not fill the saved alternative. [evidence:{records[0].seq}]")
    later_c1 = copy.deepcopy(work["artifact"])
    work = import_authored_result(api, work["id"], c2,
        f"LATEST_C2_A2_NOT_PINNED: synthetic current output must not replace the retained baseline. [evidence:{records[0].seq}]")
    marker = {"schemaVersion": MARKER, "classification": "SYNTHETIC_TRUSTED_HOST_HISTORY_WITH_REAL_RECORDED_EXPERIMENTS",
        "fixtureHistoryImport": "Frozen packets created via API; labelled synthetic historical attempts installed through trusted fixture helper.",
        "nativeOrModelCalls": 0, "owner": work["id"], "sourceOwner": source["id"], "sourceArtifact": source_artifact,
        "contexts": {"C0": c0, "C1": c1, "C2": c2}, "artifacts": {"A1": a1["id"], "laterC1": later_c1["id"], "A2": work["artifact"]["id"]},
        "baselineAttemptId": attempt1["id"], "baselineAttemptManifestId": attempt1["manifestId"],
        "experiments": experiments, "snapshot": saved, "frozenContexts": work["contexts"],
        "originalRecord": next(item for item in work["contexts"][0]["records"] if item["seq"] == records[0].seq)}
    api.store.append(source=MARKER, direction="internal", message={"method": "$recorded-experiment/demo", "params": marker})
    return marker


def resume(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError("--resume requires a marked fixture database")
    with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as db:
        rows = db.execute("SELECT raw_text FROM trace_records WHERE source=? AND method='$recorded-experiment/demo'", (MARKER,)).fetchall()
    if len(rows) != 1:
        raise ValueError("database is not this script's synthetic fixture")
    marker = json.loads(rows[0][0])["params"]
    if marker.get("schemaVersion") != MARKER or marker.get("nativeOrModelCalls") != 0:
        raise ValueError("invalid fixture marker")
    return marker


def inspect(api: EidosAPI, marker: dict[str, Any]) -> dict[str, Any]:
    work = api.investigations.get(marker["owner"])
    assert work["currentContextId"] == marker["contexts"]["C2"] and work["artifact"]["id"] == marker["artifacts"]["A2"]
    assert work["contexts"] == marker["frozenContexts"]
    reviews = {}
    for name, frozen in marker["experiments"].items():
        value = experiment(api, marker["owner"], frozen["id"])
        assert immutable_experiment(value) == immutable_experiment(frozen)
        assert "artifactId" not in value["alternative"]
        assert value["evaluation"]["changedArtifactIds"] == [marker["sourceArtifact"]]
        assert value["evaluation"]["checks"]["baselineArtifactsRetained"] is False
        reviews[name] = {key: value[key] for key in ("status", "review", "adoption", "rollback")}
    saved = snapshots.call(api, "/" + marker["snapshot"]["id"], method="GET")["composition"]
    assert saved == marker["snapshot"]
    before, after = work["contexts"][:2]
    assert before["artifactInputs"][0]["artifactId"] == after["artifactInputs"][0]["artifactId"]
    assert before["artifactInputs"][0]["sourceAdoption"] is None
    assert after["artifactInputs"][0]["sourceAdoption"]["decision"] == "reject"
    assert not any(record.method == "turn/start" for record in api.store.records())
    return {**marker, "reopenedOriginalPinsExact": True, "contextOnlyAlternativeDespiteLaterResult": True,
        "sameArtifactDifferentFrozenReview": True, "currentReviews": reviews,
        "limits": "Synthetic trusted-host history construction; real saved API records, no native/model execution or measured reasoning/human benefit."}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    marker = resume(args.db) if args.resume else None
    if not args.resume and args.db.exists():
        raise ValueError("--db must be new; use --resume for a marked synthetic fixture")
    trace = TraceStore(args.db)
    api = EidosAPI(trace)
    try:
        marker = marker or seed(api)
    finally:
        api.close()
        trace.close()
    trace = TraceStore(args.db)
    api = EidosAPI(trace)
    try:
        result = json.dumps(inspect(api, marker), indent=2) + "\n"
    finally:
        api.close()
        trace.close()
    if args.output:
        args.output.write_text(result)
    print(result, end="")
    if args.serve:
        fake = Path(__import__("eidos.api", fromlist=["__file__"]).__file__).resolve().parents[2] / "tests/fixtures/investigation_appserver.py"
        serve(args.db, codex=str(fake), port=args.port)


if __name__ == "__main__":
    main()
