"""Extend a marked public reproduction fixture with later and same-owner findings.

The input database is copied before any mutation. All added results are explicitly
authored navigation counterexamples; they are not new command observations.
"""
from __future__ import annotations

import argparse
from contextlib import closing
import io
import json
from pathlib import Path
import sqlite3

from eidos.api import EidosAPI
from eidos.trace import TraceStore

SCHEMA = "supplied-result-comparison/v1"


def call(api: EidosAPI, path: str, body: dict | None = None) -> dict:
    raw = b"" if body is None else json.dumps(body).encode()
    class Handler:
        headers = {"Content-Length": str(len(raw))}
        rfile = io.BytesIO(raw)
    status, value = api.dispatch(Handler(), "GET" if body is None else "POST", path, {})
    if status not in {200, 201}:
        raise ValueError((path, status, value))
    return value


def build(source_dir: Path, output: Path) -> dict:
    source_dir, output = source_dir.resolve(), output.resolve()
    if not source_dir.is_relative_to(Path("/tmp")) or not output.is_relative_to(Path("/tmp")):
        raise ValueError("Only explicit /tmp fixtures are accepted")
    bundle = json.loads((source_dir / "saved-reproduction-bundle.json").read_text())
    if bundle.get("schemaVersion") != "saved-local-reproduction/v1":
        raise ValueError("Expected the explicitly saved public reproduction packet")
    with closing(sqlite3.connect((source_dir / "workbench.db").as_uri() + "?mode=ro", uri=True)) as source:
        rows = source.execute("SELECT marker_json FROM supplied_text_episode_marker").fetchall()
        if len(rows) != 1 or json.loads(rows[0][0]).get("schemaVersion") != "public-code-supplied-text-episode/v1":
            raise ValueError("Public-code fixture marker required")
        output.mkdir(exist_ok=False)
        with closing(sqlite3.connect(output / "workbench.db")) as target:
            source.backup(target)
    with closing(TraceStore(output / "workbench.db")) as trace, closing(EidosAPI(trace)) as api:
        original = {key: call(api, "/api/investigations/" + bundle[key]["id"])
                    for key in ("observation", "review", "reproduction")}
        if any(original[key] != bundle[key] for key in original):
            raise ValueError("Source owners do not match the saved reproduction packet")
        def finding(owner: dict, request: str, text: str) -> dict:
            return call(api, "/api/investigations/" + owner["id"] + "/findings", {
                "requestId": request, "contextId": owner["currentContextId"], "text": text})["finding"]
        def result_input(owner: dict, artifact: dict) -> dict:
            return {"investigationId": owner["id"], "artifactId": artifact["id"],
                    "rationale": "Exact retained supplied result for this authored navigation counterexample."}
        def revise(owner: dict, request: str, question: str, inputs: list[dict]) -> dict:
            return call(api, "/api/investigations/" + owner["id"] + "/contexts", {
                "requestId": request, "parentContextId": owner["currentContextId"],
                "question": question, "artifactInputs": inputs})

        source0, consumer0 = original["review"], original["reproduction"]
        f0, r0 = source0["findings"][0], consumer0["findings"][0]
        source1 = revise(source0, "comparison-source-C1", "Authored later review; retain the prior reviewed result as historical.",
                         [result_input(original["observation"], original["observation"]["findings"][0])])
        f1 = finding(source1, "comparison-source-F1", "NEWER_F1_NOT_SUPPLIED: authored navigation counterexample; no new execution claim.")
        consumer1 = revise(consumer0, "comparison-consumer-C1", "Authored later consumer; the original reproduction finding keeps its exact older input.",
                           [result_input(source1, f1)])
        r1 = finding(consumer1, "comparison-consumer-R1", "NEWER_R1_NOT_SELECTED: authored later finding uses the later source " + f"[artifact:{f1['id']}].")
        single = call(api, "/api/investigations", {
            "requestId": "comparison-same-owner", "title": "Same owner: retain the earlier finding",
            "question": "Authored navigation counterexample with two linked results in one owner.",
            "artifactInputs": [result_input(source0, f0)]})
        a0 = finding(single, "comparison-same-owner-A0", "The earlier result is preserved as data " + f"[artifact:{f0['id']}].")
        single1 = revise(single, "comparison-same-owner-C1", "Compare this later finding with its exact earlier result in the same owner.",
                         [result_input(single, a0)])
        a1 = finding(single1, "comparison-same-owner-A1", "This later finding supplies the exact earlier one " + f"[artifact:{a0['id']}].")
        marker = {"schemaVersion": SCHEMA, "classification": "public reproduction plus authored navigation counterexamples",
                  "nativeOrModelCalls": 0, "database": str(output / "workbench.db"),
                  "sourceOwner": source0["id"], "consumerOwner": consumer0["id"],
                  "F0": f0, "F1": f1, "R0": r0, "R1": r1,
                  "sameOwner": single["id"], "A0": a0, "A1": a1,
                  "originalOwners": original}
        trace.db.execute("CREATE TABLE supplied_result_comparison_marker(marker_json TEXT NOT NULL)")
        trace.db.execute("INSERT INTO supplied_result_comparison_marker VALUES(?)", (json.dumps(marker),))
        marker["owners"] = {identifier: call(api, "/api/investigations/" + identifier)
                            for identifier in (source0["id"], consumer0["id"], single["id"])}
        assert all(owner["attempt"] is None and owner["artifact"] is None for owner in marker["owners"].values())
    (output / "marker.json").write_text(json.dumps(marker, indent=2) + "\n")
    return marker


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reproduction-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    marker = build(args.reproduction_dir, args.output_dir)
    print(json.dumps({key: marker[key] for key in ("schemaVersion", "database", "sourceOwner", "consumerOwner", "sameOwner")}))
