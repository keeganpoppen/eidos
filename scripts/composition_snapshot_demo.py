"""Persist synthetic named comparison snapshots without native/model execution.

The fixture uses authored A→B→C results, then a real local Eidos inquiry and
decision receipt. A saved pending inquiry remains pinned after that decision.
Snapshots contain references only; no source packets or live authority are copied.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import sqlite3
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from eidos.api import EidosAPI
from eidos.trace import TraceStore
from eidos.serve import serve


def script(name: str):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(name + ".py"))
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


chain = script("artifact_composition_demo")
scale = script("saved_work_scale_demo")
MARKER = "synthetic-composition-snapshots/v1"
RENDERER = "nema-content-blocks/v1;marked@18.1.0"


def request(api: EidosAPI, path: str = "", body: Any = None, *, method: str = "POST", query=None):
    return api.dispatch(chain.Request(body), method, "/api/compositions" + path, query or {})


def call(api: EidosAPI, path: str = "", body: Any = None, *, method: str = "POST", query=None):
    status, value = request(api, path, body, method=method, query=query)
    if not 200 <= status < 300:
        raise RuntimeError(f"synthetic snapshot request {path!r} failed: {status} {value}")
    return value


def http(origin: str, path: str = "", *, body: Any = None, raw: bytes | None = None):
    data = raw if raw is not None else None if body is None else json.dumps(body).encode()
    request = Request(origin + "/api/compositions" + path, data=data,
                      headers={} if data is None else {"Content-Type": "application/json"})
    try:
        response = urlopen(request, timeout=15)
    except HTTPError as error:
        response = error
    with response:
        content = response.read()
        return {"status": response.status, "bodyBytes": len(content), "body": json.loads(content)}


def target(work: dict[str, Any], *, artifact: bool = True) -> dict[str, str]:
    value = work.get("nativeArtifact") or work["artifact"]
    return {"investigationId": work["id"], "contextId": value["contextId"],
            **({"artifactId": value["id"]} if artifact else {})}


def body(marker: dict[str, Any], *, request_id: str = "snapshot-acceptance/base") -> dict[str, Any]:
    return {"requestId": request_id, "title": "Original recovery comparison", "rendererVersion": RENDERER,
        "arrangement": {"left": marker["targets"]["A"], "right": marker["targets"]["C"], "lens": "result", "layout": "beside"},
        "focus": {"investigationId": marker["investigations"]["A"], "contextId": marker["contexts"]["A"],
                  "seq": marker["controllingSeq"], "threadId": "fixture-artifact-origin"}}


def seed_sources(api: EidosAPI) -> dict[str, Any]:
    marker = chain.seed(api)
    works = {name: api.investigations.get(identifier) for name, identifier in marker["investigations"].items()}
    a = works["A"]
    pending = chain.call(api, f"/{works['B']['id']}/continuation", {
        "requestId": MARKER + "/inquiry", "attemptId": works["B"]["attempt"]["id"],
        "question": "Which original observation resolves the missing-reply question?"})
    inquiry = pending["continuation"]["inquiry"]
    return {**marker, "schemaVersion": MARKER, "classification": "SYNTHETIC_AUTHORED_RESULTS_AND_LOCAL_INQUIRY",
        "nativeOrModelCalls": 0, "targets": {name: target(work) for name, work in works.items()},
        "contexts": {name: work["currentContextId"] for name, work in works.items()},
        "artifacts": {name: work["artifact"]["id"] for name, work in works.items()},
        "controllingRawRecord": next(r for r in a["contexts"][0]["records"] if r["seq"] == marker["controllingSeq"]),
        "pendingArrangement": {"left": target(pending), "right": target(pending, artifact=False),
            "lens": "result", "layout": "beside", "intent": "evidence-chain",
            "inquiry": {"continuationId": pending["continuation"]["id"], "inquiryId": inquiry["id"]}}}


def advance_inquiry(api: EidosAPI, marker: dict[str, Any]) -> dict[str, Any]:
    identifier = marker["investigations"]["B"]
    inquiry_id = marker["pendingArrangement"]["inquiry"]["inquiryId"]
    a = api.investigations.get(marker["investigations"]["A"])
    chain.call(api, f"/{identifier}/inquiries/{inquiry_id}/responses", {
        "requestId": MARKER + "/offer", "decision": "offer", "note": "Synthetic explicit local disclosure; no new native execution.",
        "selections": a["contexts"][0]["selections"]})
    return chain.call(api, f"/{identifier}/resume", {})


def seed(api: EidosAPI) -> dict[str, Any]:
    marker = seed_sources(api)
    base = call(api, body=body(marker, request_id=MARKER + "/baseline"))["composition"]
    pending_body = {**body(marker, request_id=MARKER + "/pending"), "title": "Pending inquiry before decision",
                    "arrangement": marker["pendingArrangement"], "focus": None}
    pending = call(api, body=pending_body)["composition"]
    future = call(api, body={**body(marker, request_id=MARKER + "/future"), "title": "Unknown renderer keeps exact source",
        "rendererVersion": "unknown-future-parser/999", "focus": {**marker["targets"]["A"], "blockId": "block-0",
            "seq": marker["controllingSeq"], "threadId": "fixture-artifact-origin"}})["composition"]
    artifact_focus = call(api, body={**body(marker, request_id=MARKER + "/artifact-focus"),
        "title": "Saved artifact citation without a passage", "focus": {**marker["targets"]["A"],
            "seq": marker["controllingSeq"], "threadId": "fixture-artifact-origin"}})["composition"]
    advanced = advance_inquiry(api, marker)
    assert call(api, f"/{pending['id']}", method="GET")["composition"] == pending
    marker.update(snapshots={"baseline": base, "pending": pending, "unknownRenderer": future, "artifactFocus": artifact_focus},
                  advancedArtifactId=advanced["artifact"]["id"], advancedInquiry=advanced["continuation"]["inquiry"])
    api.store.append(source=MARKER, direction="internal", message={"method": "$composition/demo", "params": marker})
    return marker


def resume(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError("--resume requires an existing marked synthetic snapshot fixture")
    with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as db:
        rows = db.execute("SELECT raw_text FROM trace_records WHERE source=? AND method='$composition/demo'", (MARKER,)).fetchall()
    if len(rows) != 1:
        raise ValueError("database is not this script's unique synthetic fixture")
    value = json.loads(rows[0][0])["params"]
    if value.get("schemaVersion") != MARKER or value.get("nativeOrModelCalls") != 0:
        raise ValueError("invalid synthetic snapshot fixture marker")
    return value


def inspect(api: EidosAPI, marker: dict[str, Any]) -> dict[str, Any]:
    with scale.source_reads(api) as reads:
        catalog = call(api, method="GET")
        observed = {name: call(api, f"/{value['id']}", method="GET")["composition"] for name, value in marker["snapshots"].items()}
    assert observed == marker["snapshots"] and not reads["canonicalParses"]
    b = api.investigations.get(marker["investigations"]["B"])
    assert b["artifact"]["id"] == marker["advancedArtifactId"]
    assert "artifactId" not in observed["pending"]["arrangement"]["right"]
    assert "responseId" not in observed["pending"]["arrangement"]["inquiry"]
    assert not any(record.method == "turn/start" for record in api.store.records())
    return {**marker, "reopenedSnapshotsExact": True, "newInquiryDecisionDidNotRebind": True,
        "catalogRows": len(catalog["compositions"]), "catalogAndSnapshotSourceReads": reads,
        "snapshotEnvelopeBytes": {name: len(json.dumps(value, separators=(",", ":")).encode()) for name, value in observed.items()},
        "limits": "Same-database synthetic recovery; no native/model work, caller authentication, cross-database import, or human-speed claim."}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    marker = resume(args.db) if args.resume else None
    if not args.resume and args.db.exists():
        raise ValueError("--db must be new; use --resume for this marked synthetic fixture")
    trace = TraceStore(args.db)
    api = EidosAPI(trace)
    try:
        marker = marker or seed(api)
    finally:
        api.close()
        trace.close()
    reopened_trace = TraceStore(args.db)
    reopened_api = EidosAPI(reopened_trace)
    try:
        result = inspect(reopened_api, marker)
    finally:
        reopened_api.close()
        reopened_trace.close()
    text = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.write_text(text)
    print(text, end="")
    if args.serve:
        fake = Path(__import__("eidos.api", fromlist=["__file__"]).__file__).resolve().parents[2] / "tests/fixtures/investigation_appserver.py"
        serve(args.db, codex=str(fake), port=args.port)


if __name__ == "__main__":
    main()
