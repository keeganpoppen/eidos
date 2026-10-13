"""Persist and measure synthetic saved-work discovery over 1,000 owners.

All completions are authored through the trusted host API, not native/model
observations. HTTP measurements use the repository's actual loopback server.
Cold projection construction is measured separately from hot reads. Source
detail transfers one packet but still parses its owning canonical history.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import importlib.util
import json
from pathlib import Path
import queue
import sqlite3
import threading
from typing import Any, Iterator
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from eidos.api import EidosAPI
from eidos.trace import TraceStore
import eidos.serve as server_module

spec = importlib.util.spec_from_file_location("artifact_fixture", Path(__file__).with_name("artifact_composition_demo.py"))
assert spec and spec.loader
composition = importlib.util.module_from_spec(spec)
spec.loader.exec_module(composition)

MARKER = "synthetic-saved-work-scale/v1"
TITLE_A = "Old result · Straße dispatch decision"
TITLE_C = "Old chain · C recover original support"


def seed(api: EidosAPI, *, owners: int = 1000, revisions: int = 32) -> dict[str, Any]:
    if owners < 3 or revisions < 2:
        raise ValueError("fixture needs at least three owners and two context revisions")
    if api.store.db.execute("SELECT 1 FROM investigations LIMIT 1").fetchone():
        raise ValueError("saved-work fixture requires an empty database")
    def create(ordinal: int, body: dict[str, Any]) -> dict[str, Any]:
        # Explicit synthetic creation dates make catalog order independent of
        # wall-clock corrections while seeding. Production state is unmodified.
        with patch("eidos.investigation.time.time", return_value=1791900000 + ordinal):
            return composition.call(api, body=body)
    raw = []
    for index, text in enumerate((composition.CONTROL, composition.OMITTED,
            "Rejected: retry automatically after a missing reply; the first operation may already have happened.")):
        record = api.store.append(source=MARKER, direction="internal", message={
            "method": "$history/item", "params": {"threadId": "saved-work-origin", "turnId": f"decision-{index}",
                "item": {"id": f"support-{index}", "type": "agentMessage", "text": text,
                         "futureField": {"preserved": True, "classification": "synthetic"}}}})
        raw.append(record)
    selections = [{"threadId": item.thread_id, "startSeq": item.seq, "endSeq": item.seq,
                   "rationale": "Controlling decision and its rejected alternative"} for item in (raw[0], raw[2])]
    api.store.register_semantic_observer(name=MARKER, lens="thread")
    api.store.put_semantic_revision(thread_id="saved-work-origin", lens="thread", observer=MARKER,
        horizon_seq=raw[-1].seq, nodes=[{"id": "dispatch-rule", "title": "Controlling dispatch decision",
            "summary": composition.CONTROL, "support": [{"start": item["startSeq"], "end": item["endSeq"], "weight": 1.0} for item in selections]}])
    a = create(0, {"requestId": MARKER + "/A", "title": TITLE_A,
        "question": "First synthetic draft: " + "Archived context wording. " * 160, "selections": selections})
    for revision in range(1, revisions):
        question = ("Which decision controls uncertain dispatch recovery?" if revision == revisions - 1
                    else f"Synthetic draft revision {revision}: " + "Archived context wording. " * 160)
        a = composition.call(api, f"/{a['id']}/contexts", {"requestId": MARKER + f"/revision/{revision}",
            "parentContextId": a["currentContextId"], "question": question, "selections": selections})
    a = composition.authored_completion(api, a,
        "Synthetic authored A; no model was called. " + composition.CONTROL + f" [evidence:{raw[0].seq}] [evidence:{raw[2].seq}]")
    a = composition.call(api, f"/{a['id']}/adoption", {"artifactId": a["artifact"]["id"], "decision": "adopt", "note": "Synthetic source review."})
    works = {"A": a}
    for name, title, prior in (("B", "Old chain · B attributed recovery practice", "A"), ("C", TITLE_C, "B")):
        source = works[prior]
        work = create(len(works), {"requestId": MARKER + "/" + name, "title": title,
            "question": "Recover the original controlling decision without copying earlier transcripts.", "selections": [],
            "artifactInputs": [{"investigationId": source["id"], "artifactId": source["artifact"]["id"],
                                "rationale": "Inspect the exact original source before retrying."}]})
        works[name] = composition.authored_completion(api, work,
            f"Synthetic authored {name}; no model was called. Retain uncertainty and original support. [artifact:{source['artifact']['id']}]")
    for number in range(owners - 3):
        work = create(number + 3, {"requestId": MARKER + f"/archive/{number}",
            "title": f"Synthetic archive {number:04d}", "question": "Unrelated saved investigation " + str(number),
            "selections": selections[:1]})
        composition.authored_completion(api, work,
            "Synthetic unrelated result; no model was called. " + "Archive filler. " * 32 + f" [evidence:{raw[0].seq}]")
    a_context = next(ctx for ctx in a["contexts"] if ctx["id"] == a["currentContextId"])
    marker = {"schemaVersion": MARKER, "classification": "SYNTHETIC_AUTHORED_HOST_COMPLETIONS",
        "owners": owners, "sourceContextCount": revisions, "nativeOrModelCalls": 0,
        "investigations": {name: work["id"] for name, work in works.items()},
        "artifacts": {name: work["artifact"]["id"] for name, work in works.items()},
        "contexts": {name: work["currentContextId"] for name, work in works.items()},
        "controllingSeq": raw[0].seq, "controllingRawRecord": next(r for r in a_context["records"] if r["seq"] == raw[0].seq)}
    api.store.append(source=MARKER, direction="internal", message={"method": "$saved-work/demo", "params": marker})
    return marker


def resume(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError("--resume requires an existing marked synthetic database")
    with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as db:
        rows = db.execute("SELECT raw_text FROM trace_records WHERE source=? AND method='$saved-work/demo'", (MARKER,)).fetchall()
    if len(rows) != 1:
        raise ValueError("database is not this script's marked synthetic fixture")
    marker = json.loads(rows[0][0])["params"]
    if marker.get("schemaVersion") != MARKER or marker.get("nativeOrModelCalls") != 0:
        raise ValueError("invalid synthetic fixture marker")
    return marker


@contextmanager
def http_server(path: Path) -> Iterator[tuple[str, EidosAPI]]:
    """Exercise serve.py unchanged; capture its real server for bounded shutdown."""
    ready: queue.Queue[Any] = queue.Queue()
    apis = []
    server_class, api_class = server_module.ThreadingHTTPServer, server_module.EidosAPI
    def make_api(*args: Any, **kwargs: Any) -> EidosAPI:
        api = api_class(*args, **kwargs)
        apis.append(api)
        return api
    def make_server(address: Any, handler: Any) -> Any:
        server = server_class(address, handler)
        ready.put(server)
        return server
    fake = Path(server_module.__file__).resolve().parents[2] / "tests/fixtures/investigation_appserver.py"
    with patch.object(server_module, "EidosAPI", make_api), patch.object(server_module, "ThreadingHTTPServer", make_server):
        thread = threading.Thread(target=server_module.serve, args=(path,), kwargs={"port": 0, "codex": str(fake)}, daemon=True)
        thread.start()
        server = ready.get(timeout=20)
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}", apis[0]
    finally:
        server.shutdown()
        thread.join(timeout=10)
        server.server_close()
        if thread.is_alive():
            raise RuntimeError("synthetic HTTP fixture failed to stop")


def http(origin: str, path: str, params: dict[str, Any] | None = None, *, body: Any = None) -> dict[str, Any]:
    url = origin + "/api/investigations" + path
    if params:
        url += "?" + urlencode(params, doseq=True)
    request = Request(url, data=None if body is None else json.dumps(body).encode(),
                      headers={} if body is None else {"Content-Type": "application/json"})
    try:
        response = urlopen(request, timeout=20)
    except HTTPError as error:
        response = error
    with response:
        raw = response.read()
        return {"status": response.status, "bodyBytes": len(raw), "declaredBytes": int(response.headers["Content-Length"]),
                "body": json.loads(raw)}


@contextmanager
def source_reads(api: EidosAPI) -> Iterator[dict[str, Any]]:
    """Count parsing of actual stored source strings, including reads via _load.

    Exact string membership excludes response parsing and metadata projections.
    SQL traces disclose dirty-index queries even when they yield zero rows.
    """
    source = {row["state_json"]: row["id"] for row in api.store.db.execute("SELECT id,state_json FROM investigations")}
    metrics: dict[str, Any] = {"canonicalParses": [], "canonicalReadStatements": []}
    original = json.loads
    def loads(value: Any, *args: Any, **kwargs: Any) -> Any:
        if isinstance(value, str) and value in source:
            metrics["canonicalParses"].append(source[value])
        return original(value, *args, **kwargs)
    def sql(statement: str) -> None:
        if statement.lstrip().upper().startswith("SELECT") and "state_json" in statement and "investigations" in statement:
            metrics["canonicalReadStatements"].append(statement)
    with patch.object(json, "loads", loads):
        api.store.db.set_trace_callback(sql)
        try:
            yield metrics
        finally:
            api.store.db.set_trace_callback(None)


def measure(path: Path, marker: dict[str, Any]) -> dict[str, Any]:
    with http_server(path) as (origin, api):
        with source_reads(api) as cold:
            first = http(origin, "/catalog", {"limit": 20})
        with source_reads(api) as hot:
            catalog = http(origin, "/catalog", {"limit": 20})
            unchanged = http(origin, "/catalog", {"limit": 20, "knownVersion": catalog["body"]["version"]})
            search = http(origin, "/artifacts", {"q": "STRASSE", "limit": 20})
        a = marker["investigations"]["A"]
        full = http(origin, f"/{a}/view")
        with source_reads(api) as idle:
            idle_view = http(origin, f"/{a}/view", {"knownVersion": full["body"]["version"]})
        hops = []
        for name in ("C", "B", "A"):
            with source_reads(api) as reads:
                detail = http(origin, f"/{marker['investigations'][name]}/artifacts/{marker['artifacts'][name]}/source",
                    {"contextId": marker["contexts"][name]})
            assert detail["status"] == 200
            hops.append({"name": name, "bodyBytes": detail["bodyBytes"], **reads})
            if name == "A":
                recovered = next(record for record in detail["body"]["context"]["records"] if record["seq"] == marker["controllingSeq"])
                assert recovered == marker["controllingRawRecord"]
        assert all(value["status"] == 200 and value["bodyBytes"] == value["declaredBytes"] for value in (first, catalog, unchanged, search, full, idle_view))
        assert not hot["canonicalParses"] and not idle["canonicalParses"]
        assert len(search["body"]["artifacts"]) == 1
        assert search["body"]["artifacts"][0]["artifactId"] == marker["artifacts"]["A"]
        assert a not in {item["id"] for item in catalog["body"]["investigations"]}
        result = {**marker, "measurementScope": "actual loopback HTTP bodies; hot read paths after initial API recovery; no model or dispatch",
            "firstCatalogRead": {"bodyBytes": first["bodyBytes"], "canonicalParseCount": len(cold["canonicalParses"]),
                                 "distinctCanonicalOwners": len(set(cold["canonicalParses"])),
                                 "canonicalReadStatementCount": len(cold["canonicalReadStatements"]),
                                 "canonicalReadStatementExamples": cold["canonicalReadStatements"][:3]},
            "hotCatalogAndSearch": {"catalogBytes": catalog["bodyBytes"], "unchangedBytes": unchanged["bodyBytes"],
                                    "searchBytes": search["bodyBytes"], **hot},
            "unchangedSelectedView": {"bodyBytes": idle_view["bodyBytes"], **idle},
            "sourceHops": hops, "fullSourceOwnerViewBytes": full["bodyBytes"],
            "originalSupportRecovered": True, "outOfFirstPageResultFound": True,
            "limitations": "Cold/dirty projection refresh can parse all changed owners; exact source parses one full owner; no aggregate SQL or single-context byte bound is claimed."}
    with http_server(path) as (origin, api):
        with source_reads(api) as restarted:
            page = http(origin, "/catalog", {"limit": 20, "knownVersion": catalog["body"]["version"]})
        assert page["body"]["unchanged"] and not restarted["canonicalParses"]
        result["reopenedHotCatalog"] = {"bodyBytes": page["bodyBytes"], **restarted}
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--owners", type=int, default=1000)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.resume:
        marker = resume(args.db)
    else:
        if args.db.exists():
            raise ValueError("--db must be new; --resume accepts only this marked synthetic fixture")
        trace = TraceStore(args.db)
        api = EidosAPI(trace)
        try:
            marker = seed(api, owners=args.owners)
        finally:
            api.close()
            trace.close()
    result = measure(args.db, marker)
    text = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.write_text(text)
    print(text, end="")
    if args.serve:
        fake = Path(server_module.__file__).resolve().parents[2] / "tests/fixtures/investigation_appserver.py"
        server_module.serve(args.db, port=args.port, codex=str(fake))


if __name__ == "__main__":
    main()
