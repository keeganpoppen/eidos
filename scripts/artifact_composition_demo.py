"""Persist a synthetic A → B → C artifact chain and recover its original support.

uv run python scripts/artifact_composition_demo.py --db /tmp/new-artifact-chain.db
uv run python scripts/artifact_composition_demo.py --db /tmp/new-artifact-chain.db --resume --serve

Completions are authored through the trusted host interface, explicitly labelled
synthetic. No app-server subprocess, native account or model is used to seed it.
The optional server uses the repository's synthetic worker if dispatch is invoked.
"""
from __future__ import annotations

import argparse
import io
import json
from pathlib import Path
import sqlite3
from typing import Any

import eidos.api
from eidos.api import EidosAPI
from eidos.serve import serve
from eidos.trace import TraceStore


MARKER = "synthetic-artifact-composition-demo/v1"
CONTROL = "Persist the dispatch identity before sending; recover recorded completion and retain unknown delivery."
OMITTED = "OMITTED_TRANSCRIPT_CANARY: an irrelevant fixture detour must not enter descendant prompts."


class Request:
    def __init__(self, body: Any = None) -> None:
        raw = json.dumps({} if body is None else body).encode()
        self.headers = {"Content-Length": str(len(raw)), "Content-Type": "application/json"}
        self.rfile = io.BytesIO(raw)


def call(api: EidosAPI, path: str = "", body: Any = None, *, method: str = "POST") -> dict[str, Any]:
    status, result = api.dispatch(Request(body), method, "/api/investigations" + path, {})
    if not 200 <= status < 300:
        raise RuntimeError(f"synthetic fixture request {path!r} failed: {status} {result}")
    return result


def authored_completion(api: EidosAPI, work: dict[str, Any], text: str) -> dict[str, Any]:
    """Author a synthetic result; a claim/pin is not evidence of native execution."""
    claimed, admitted = api.investigations.claim(work["id"], work["currentContextId"])
    if not admitted:
        raise ValueError("fixture completion requires a fresh synthetic attempt")
    source = MARKER + "/" + claimed["attempt"]["id"]
    thread, turn = "fixture-artifact-" + work["id"], "fixture-authored-result"
    api.investigations.update_attempt(work["id"], source=source, threadId=thread, turnId=turn)
    result = api.store.append(source=source, direction="internal", message={
        "method": "$history/item", "params": {"threadId": thread, "turnId": turn, "item": {
            "id": "authored-result", "type": "agentMessage", "text": text,
            "futureField": {"synthetic": True, "capturedFromNative": False},
        }},
    })
    return api.investigations.complete(work["id"], {
        "text": text, "outputSeqs": [result.seq], "executionEvidence": "synthetic",
    }, expected_attempt_id=claimed["attempt"]["id"])


def seed(api: EidosAPI) -> dict[str, Any]:
    if api.store.records() or api.investigations.list():
        raise ValueError("artifact composition demo needs an empty database")
    support = []
    for ordinal, text in enumerate((CONTROL, OMITTED, "Rejected: retry automatically after a missing reply; the first operation may already have happened.")):
        record = api.store.append(source=MARKER, direction="internal", message={
            "method": "$history/item", "params": {"threadId": "fixture-artifact-origin", "turnId": f"origin-{ordinal}", "item": {
                "id": f"origin-answer-{ordinal}", "type": "agentMessage", "text": text,
                "futureField": {"preserve": True, "fixture": "artifact-composition"},
            }},
        })
        if ordinal != 1:
            support.append({"threadId": record.thread_id, "startSeq": record.seq, "endSeq": record.seq,
                            "rationale": "Controlling decision" if ordinal == 0 else "Rejected retry counterexample"})
    api.store.register_semantic_observer(name="synthetic-artifact-fixture", lens="thread")
    api.store.put_semantic_revision(thread_id="fixture-artifact-origin", lens="thread", observer="synthetic-artifact-fixture",
        horizon_seq=record.seq, nodes=[{"id": "dispatch-decision", "title": "Dispatch decision and rejected retry",
            "summary": "Synthetic controlling evidence for the artifact chain.",
            "support": [{"start": item["startSeq"], "end": item["endSeq"], "weight": 1.0} for item in support]}])
    a = call(api, body={"requestId": MARKER + "/A", "title": "A · Recover the controlling decision",
        "question": "Which decision controls uncertain dispatch recovery?", "selections": support})
    a = authored_completion(api, a, "Synthetic authored analysis A; no model was called. " + CONTROL
        + " " + " ".join(f"[evidence:{item['startSeq']}]" for item in support))
    a = call(api, f"/{a['id']}/adoption", {"artifactId": a["artifact"]["id"], "decision": "adopt",
        "note": "Synthetic review records a decision; it does not prove the analysis."})
    b = call(api, body={"requestId": MARKER + "/B", "title": "B · Build on the retained result",
        "question": "What recovery practice follows from analysis A?", "selections": [],
        "artifactInputs": [{"investigationId": a["id"], "artifactId": a["artifact"]["id"],
                            "rationale": "Use the attributed result and retain its original source link."}]})
    b = authored_completion(api, b, "Synthetic authored analysis B; no model was called. Preserve uncertainty and inspect the original decision before resending. "
        + f"[artifact:{a['artifact']['id']}]")
    c = call(api, body={"requestId": MARKER + "/C", "title": "C · Inspect the result chain",
        "question": "Recover the controlling evidence behind B without copying A and B transcripts.", "selections": [],
        "artifactInputs": [{"investigationId": b["id"], "artifactId": b["artifact"]["id"],
                            "rationale": "Continue from B; inspect its original context when checking support."}]})
    c = authored_completion(api, c, "Synthetic authored analysis C; no model was called. B attributes the recovery practice to A; follow the source context to inspect the controlling decision. "
        + f"[artifact:{b['artifact']['id']}]")
    marker = {"demoVersion": 1, "investigations": {"A": a["id"], "B": b["id"], "C": c["id"]},
              "controllingSeq": support[0]["startSeq"], "counterexampleSeq": support[1]["startSeq"]}
    api.store.append(source=MARKER, direction="internal", message={"method": "$artifact/demo", "params": marker})
    return marker


def inspect(api: EidosAPI, marker: dict[str, Any]) -> dict[str, Any]:
    works = {name: call(api, f"/{identifier}", method="GET") for name, identifier in marker["investigations"].items()}
    c = works["C"]["contexts"][0]
    b_input = c["artifactInputs"][0]
    b = next(ctx for ctx in works["B"]["contexts"] if ctx["id"] == b_input["sourceContextId"])
    a_input = b["artifactInputs"][0]
    a = next(ctx for ctx in works["A"]["contexts"] if ctx["id"] == a_input["sourceContextId"])
    controlling = next(record for record in a["records"] if record["seq"] == marker["controllingSeq"])
    assert CONTROL in controlling["rawText"]
    assert not c["records"] and not b["records"]
    assert len(c["artifactInputs"]) == len(b["artifactInputs"]) == 1
    assert works["A"]["artifact"]["text"] not in c["projectedPrompt"]
    assert all(OMITTED not in ctx["projectedPrompt"] for ctx in (a, b, c))
    turn_starts = [record for record in api.store.records() if record.method == "turn/start"]
    assert not turn_starts
    return {"schemaVersion": "nema-artifact-composition-demo/1", "classification": "SYNTHETIC_AUTHORED_HOST_COMPLETIONS",
        "nativeOrModelCalls": 0, "nativeTurnStarts": len(turn_starts), "investigations": marker["investigations"],
        "contexts": {key: value["currentContextId"] for key, value in works.items()},
        "artifacts": {key: value["artifact"]["id"] for key, value in works.items()},
        "promptBytes": {"A": len(a["projectedPrompt"].encode()), "B": len(b["projectedPrompt"].encode()), "C": len(c["projectedPrompt"].encode())},
        "recoveryPath": [works["C"]["id"], works["B"]["id"], works["A"]["id"], marker["controllingSeq"]],
        "controllingSeq": marker["controllingSeq"], "counterexampleSeq": marker["counterexampleSeq"],
        "controllingRawRecord": controlling, "originalSupportRecovered": True,
        "recursiveSourceTranscriptsCopied": False, "providerContext": "unknown"}


def validate_resume(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError("--resume requires an existing marked synthetic demo")
    with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as db:
        rows = db.execute("SELECT raw_text FROM trace_records WHERE source=? AND method='$artifact/demo'", (MARKER,)).fetchall()
        if len(rows) != 1:
            raise ValueError("--resume requires this script's unique synthetic marker")
        marker = json.loads(rows[0][0])["params"]
        if marker.get("demoVersion") != 1 or set(marker.get("investigations", {})) != {"A", "B", "C"}:
            raise ValueError("synthetic marker is invalid")
        for identifier in marker["investigations"].values():
            row = db.execute("SELECT state_json FROM investigations WHERE id=?", (identifier,)).fetchone()
            if row is None or json.loads(row[0]).get("artifact", {}).get("executionEvidence") != "synthetic":
                raise ValueError("demo does not contain the expected synthetic results")
        return marker


def run(path: Path, *, resume: bool = False) -> dict[str, Any]:
    marker = validate_resume(path) if resume else None
    if not resume and path.exists():
        raise ValueError("--db must be a new path; use --resume for a marked synthetic demo")
    store = TraceStore(path)
    api = EidosAPI(store)
    try:
        return inspect(api, marker if marker is not None else seed(api))
    finally:
        api.close()
        store.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = json.dumps(run(args.db, resume=args.resume), indent=2) + "\n"
    if args.output:
        args.output.write_text(result)
    print(result, end="")
    if args.serve:
        fake = Path(eidos.api.__file__).resolve().parents[2] / "tests/fixtures/investigation_appserver.py"
        serve(args.db, codex=str(fake), port=args.port)


if __name__ == "__main__":
    main()
