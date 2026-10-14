"""Authored public-repository fixture for exact direct-result-use inspection."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sqlite3

from authored_finding_demo import FINDING, seed as seed_source
from eidos.api import EidosAPI
from eidos.serve import serve
from eidos.trace import TraceStore

SCHEMA = "authored-public-repository-result-uses/v1"
BASE = "25d6350b104c2543060fe76a9447502c81f56caa"


def seed(api: EidosAPI) -> dict:
    original = seed_source(api)
    a = api.investigations.get(original["ownerId"])
    a0 = a["contexts"][0]

    def finding(owner: dict, text: str, key: str) -> dict:
        return api.investigations.create_finding(owner["id"], {
            "requestId": SCHEMA + key, "contextId": owner["currentContextId"], "text": text})[0]

    def create(key: str, question: str, **inputs) -> dict:
        return api.investigations.create({"requestId": SCHEMA + key,
            "title": key, "question": question, **inputs})

    f0 = finding(a, FINDING, "/f0")
    f1 = finding(a, "Hypothesis: a merge preview needs source-specific identity evidence. "
                 "No general rule is established.", "/f1")
    b = create("B: merge review", "Which checks should a future merge preview expose?",
        artifactInputs=[{"investigationId": a["id"], "artifactId": f0["id"],
                         "rationale": "Inspect the preserved overlap boundary before proposing a merge."}])
    b0 = b["contexts"][0]
    bf = finding(b, "A candidate merge preview should expose overlap and distinguish retry "
                 "identity from event identity [artifact:" + f0["id"] + "].", "/bf")
    b = api.investigations.revise(b["id"], {"requestId": SCHEMA + "/b1",
        "parentContextId": b0["id"], "question": "Which implementation inputs should be inspected separately?",
        "selections": a0["selections"]})
    c = create("C: derived follow-up", "How should we evaluate a proposed review?",
        artifactInputs=[{"investigationId": b["id"], "artifactId": bf["id"],
                         "rationale": "Inspect the candidate review proposal."}])
    d = create("D: copied review inputs", "Which repeated events could be mistaken for retransmission?",
               inputSource={"investigationId": b["id"], "contextId": b0["id"]})
    e = create("E: shared evidence", "Which implementation check runs before appending?", selections=a0["selections"])
    f = create("F: unsupported mention", "Does a named result alone establish source membership?", selections=a0["selections"])
    finding(f, "This prose merely mentions " + f0["id"] + " and does not supply it.", "/ff")
    owners = api.investigations.list()
    raw = [{"seq": r.seq, "rawText": r.raw_text,
            "sha256": hashlib.sha256(r.raw_text.encode()).hexdigest()} for r in api.store.records()]
    marker = {"schemaVersion": SCHEMA, "classification": "authored-public-repository-direct-result-uses",
        "base": BASE, "nativeOrModelCalls": 0, "source": {"investigationId": a["id"], "artifactId": f0["id"], "contextId": a0["id"]},
        "f0": f0, "f1": f1, "bf": bf, "originalContext": a0,
        "b": b["id"], "b0": b0, "b1": b["currentContextId"], "c": c["id"],
        "d": d["id"], "d0": d["contexts"][0], "e": e["id"], "f": f["id"],
        "originalOwners": owners, "originalRaw": raw,
        "expectedUses": [{"investigationId": b["id"], "contextId": b0["id"], "isCurrent": False},
                         {"investigationId": d["id"], "contextId": d["currentContextId"], "isCurrent": True}]}
    api.store.db.execute("CREATE TABLE result_uses_demo_marker(marker_json TEXT NOT NULL)")
    api.store.db.execute("INSERT INTO result_uses_demo_marker VALUES(?)", (json.dumps(marker),))
    return marker


def resume(path: Path) -> dict:
    if not path.is_file():
        raise ValueError("--resume requires this script's marked fixture")
    with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as db:
        rows = db.execute("SELECT marker_json FROM result_uses_demo_marker").fetchall()
    if len(rows) != 1:
        raise ValueError("not a unique result-uses fixture")
    marker = json.loads(rows[0][0])
    if marker.get("schemaVersion") != SCHEMA or marker.get("base") != BASE:
        raise ValueError("fixture marker does not match this script")
    return marker


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--delete-source", action="store_true", help="trusted fixture-only upstream deletion injection")
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--port", type=int, default=8767)
    args = parser.parse_args()
    if args.delete_source and not args.resume:
        parser.error("--delete-source requires --resume")
    path = args.db.expanduser().resolve()
    marker = resume(path) if args.resume else None
    if marker is None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if any(Path(str(path) + suffix).exists() for suffix in ("-wal", "-shm", "-journal")):
            raise ValueError("fixture requires a fresh database without sidecars")
        with path.open("xb"):
            pass
    trace = TraceStore(path)
    api = EidosAPI(trace)
    try:
        marker = marker or seed(api)
        if args.delete_source:
            # Deliberate trusted-store failure injection, never a product action.
            trace.db.execute("BEGIN IMMEDIATE")
            try:
                # Creation/revision receipts have an owner foreign key. Finding
                # receipts deliberately survive source loss and remain untouched.
                trace.db.execute("DELETE FROM investigation_requests WHERE investigation_id=?", (marker["source"]["investigationId"],))
                trace.db.execute("DELETE FROM investigations WHERE id=?", (marker["source"]["investigationId"],))
                trace.db.execute("DELETE FROM trace_records")
                trace.db.execute("COMMIT")
            except BaseException:
                trace.db.execute("ROLLBACK")
                raise
        assert all(w["attempt"] is None and w["artifact"] is None for w in api.investigations.list())
        marker = {**marker, "sourceDeleted": not bool(trace.db.execute("SELECT 1 FROM investigations WHERE id=?",
                                  (marker["source"]["investigationId"],)).fetchone())}
        args.output.write_text(json.dumps(marker, indent=2) + "\n")
        print(json.dumps({"database": str(path), "marker": str(args.output), "source": marker["source"],
                          "sourceDeleted": marker["sourceDeleted"], "nativeOrModelCalls": 0}), flush=True)
    finally:
        api.close()
        trace.close()
    if args.serve:
        serve(path, port=args.port)


if __name__ == "__main__":
    main()
