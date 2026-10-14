"""Public repository excerpts for offline authored-finding acceptance; no native calls."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess

from eidos.api import EidosAPI
from eidos.serve import serve
from eidos.trace import TraceStore

SCHEMA = "authored-public-repository-finding/v1"
BASE = "2aae982806de5386d0e42dc22f499bdb6d5e77f4"
ROOT = Path(__file__).resolve().parents[1]
QUESTION = "Why does v1 refuse same-thread imports, and what evidence would justify a later merge operation?"
LATER_QUESTION = "Which overlap counterexample should a future merge operation distinguish?"
FINDING = (
    "Native coordinate overlap is a review boundary. D34 preserves original coordinates "
    "and refuses new imports of existing threads until an explicit merge contract exists "
    "[evidence:1]. The implementation checks raw records, annotations and semantic "
    "revisions before appending, but resolves an exact committed request before collision "
    "checks [evidence:2].\n\nMy inference: retry identity and incremental-history identity "
    "are separate obligations.\n\nOpen question: what overlap evidence could distinguish "
    "repeated delivery from two real identical events without rewriting source coordinates? "
    "No general merge rule is established by these excerpts."
)


def seed(api: EidosAPI) -> dict:
    paths = ("docs/roadmap/DECISIONS.md", "src/eidos/history_imports.py")
    excerpts = []
    selections = []
    for index, path in enumerate(paths):
        raw = subprocess.check_output(["git", "show", BASE + ":" + path], cwd=ROOT)
        full = raw.decode("utf-8")
        if index == 0:
            text = "### D34 — " + full.split("### D34 — ", 1)[1].split("\n## Deferred", 1)[0]
            thread = "fixture-finding-import-decision"
        else:
            text = "    def commit(" + full.split("    def commit(", 1)[1].split("\n    def get_request", 1)[0]
            thread = "fixture-finding-import-implementation"
        provenance = {"commit": BASE, "path": path, "fileSha256": hashlib.sha256(raw).hexdigest(),
                      "excerptSha256": hashlib.sha256(text.encode()).hexdigest()}
        record = api.store.append(source="authored-public-repository", direction="internal", message={
            "method": "$history/item", "params": {"threadId": thread, "turnId": "public-excerpt",
                "item": {"id": "excerpt", "type": "userMessage", "content": [{"type": "text",
                    "text": "Public repository excerpt, authored fixture (not native output): " + path + " at " + BASE + "\n" + text}]}},
            "repositoryEvidence": provenance})
        assert record.seq == index + 1, "fixture must start with an empty trace"
        excerpts.append({**provenance, "seq": record.seq, "threadId": thread})
        selections.append({"threadId": thread, "startSeq": record.seq, "endSeq": record.seq,
                           "rationale": FINDING if index == 0 else "Inspect exact replay and collision ordering."})
    owner = api.investigations.create({"requestId": SCHEMA + "/create", "title": "Import overlap: rationale and open question",
                                      "question": QUESTION, "selections": selections})
    marker = {"schemaVersion": SCHEMA, "classification": "authored-public-repository-excerpts", "base": BASE,
              "nativeOrModelCalls": 0, "excerpts": excerpts, "ownerId": owner["id"], "contextId": owner["currentContextId"],
              "originalOwner": owner, "question": QUESTION, "laterQuestion": LATER_QUESTION, "findingText": FINDING,
              "search": "Native coordinate overlap", "uncitedText": "Hypothesis: a merge preview could distinguish retransmission from repeated events. No supporting source is cited for this proposal."}
    api.store.db.execute("CREATE TABLE authored_finding_demo_marker(marker_json TEXT NOT NULL)")
    api.store.db.execute("INSERT INTO authored_finding_demo_marker VALUES(?)", (json.dumps(marker),))
    return marker


def resume(path: Path) -> dict:
    if not path.is_file():
        raise ValueError("--resume requires this script's marked fixture")
    with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as db:
        rows = db.execute("SELECT marker_json FROM authored_finding_demo_marker").fetchall()
    if len(rows) != 1:
        raise ValueError("not a unique authored-finding fixture")
    marker = json.loads(rows[0][0])
    if marker.get("schemaVersion") != SCHEMA or marker.get("base") != BASE:
        raise ValueError("fixture marker does not match this script")
    return marker


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--advance", action="store_true", help="explicitly advance this marked fixture's context, without an attempt")
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--port", type=int, default=8767)
    args = parser.parse_args()
    if args.advance and not args.resume:
        parser.error("--advance requires --resume")
    database = args.db.expanduser().resolve()
    marker = resume(database) if args.resume else None
    if marker is None:
        database.parent.mkdir(parents=True, exist_ok=True)
        if any(Path(str(database) + suffix).exists() for suffix in ("-wal", "-shm", "-journal")):
            raise ValueError("fixture creation requires a fresh database without sidecars")
        with database.open("xb"):
            pass
    trace = TraceStore(database)
    api = EidosAPI(trace)
    try:
        marker = marker or seed(api)
        if args.advance:
            api.investigations.revise(marker["ownerId"], {"requestId": SCHEMA + "/advance",
                "parentContextId": marker["contextId"], "question": LATER_QUESTION,
                "selections": marker["originalOwner"]["contexts"][0]["selections"]})
        current = api.investigations.get(marker["ownerId"])
        assert current["attempt"] is None and current["artifact"] is None
        assert not trace.db.execute("SELECT 1 FROM trace_records WHERE method='turn/start'").fetchone()
        marker = {**marker, "currentOwner": current, "currentContextId": current["currentContextId"]}
        args.output.write_text(json.dumps(marker, indent=2) + "\n")
        print(json.dumps({"marker": str(args.output), "database": str(database), "ownerId": marker["ownerId"],
                          "contextId": marker["contextId"], "currentContextId": marker["currentContextId"], "nativeOrModelCalls": 0}), flush=True)
    finally:
        api.close()
        trace.close()
    if args.serve:
        serve(database, port=args.port)


if __name__ == "__main__":
    main()
