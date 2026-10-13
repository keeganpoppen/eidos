"""Authored pending preparation for real API/browser cancellation checks.

Seed with --db /tmp/owned-demo.db --output /tmp/owned-demo.json.
Serve with the same --db and --resume --serve --port 8767. No native/model calls.
After dispatch, touch the reported fixtureDirectory/release-login to release
authored login events. Stopping the attempt first must prevent thread/turn work.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from unittest.mock import patch

from eidos.api import EidosAPI
from eidos.private_investigation import PrivateInvestigationWorker
import eidos.serve as server_module
from eidos.trace import TraceStore


MARKER = "synthetic-owned-attempt-demo/v1"
FIXTURE = Path(__file__).resolve().parents[1] / "tests/fixtures/owned_attempt_server.py"


def preparation(session):
    """Authored protocol checks, not a production native account admission."""
    login = session.request("account/login/start", {"type": "chatgptDeviceCode"})
    if login.get("loginId") != "authored-login":
        raise ValueError("Unexpected authored login identity")
    session.phase("awaiting-sign-in")
    event = session.recv_event()
    if (event.get("method") != "account/login/completed"
            or event.get("params", {}).get("loginId") != login["loginId"]
            or event["params"].get("success") is not True):
        raise ValueError("Unexpected authored login completion")
    updated = session.recv_event()
    if updated.get("method") != "account/updated" or updated.get("params", {}).get("planType") != "plus":
        raise ValueError("Unexpected authored account update")
    session.phase("checking")
    account = session.request("account/read", {"refreshToken": False})
    if account.get("account", {}).get("planType") != "plus":
        raise ValueError("Unexpected authored account read")
    session.request("config/read", {"includeLayers": False})


def fixture_directory(path: Path) -> Path:
    return Path(str(path.resolve()) + ".fixture")


def make_api(trace, *, codex=None):
    api = EidosAPI(trace, codex=str(FIXTURE))
    api.investigation_worker.close()
    api.investigation_worker.close_evidence()
    api.investigation_worker = PrivateInvestigationWorker(
        trace, [sys.executable, str(FIXTURE), "complete", str(fixture_directory(Path(trace.path)))],
        execution_evidence="synthetic", preparation=preparation, preparation_timeout=120,
    )
    return api


def seed(path: Path):
    if path.exists() or fixture_directory(path).exists() or Path(str(path) + ".private").exists():
        raise ValueError("Use a fresh authored fixture database.")
    fixture_directory(path).mkdir(mode=0o700)
    trace = TraceStore(path)
    api = make_api(trace)
    try:
        for i in range(6):
            trace.append(source=MARKER, direction="internal", message={"method": "$fixture/setup", "params": {"index": i}})
        record = trace.append(source=MARKER, direction="internal", message={"method": "$history/item", "params": {
            "threadId": "owned-source", "turnId": "owned-source-turn", "item": {
                "id": "owned-source-item", "type": "agentMessage", "text": "A stop request must target only the owned attempt."}}})
        values = {}
        for mode in ("cancel", "release"):
            value = api.investigations.create({"requestId": MARKER + "/" + mode,
                "title": "Owned preparation · " + mode, "question": "What does the retained source establish about " + mode + "?",
                "selections": [{"threadId": record.thread_id, "startSeq": record.seq, "endSeq": record.seq}]})
            values[mode] = {"investigationId": value["id"], "contextId": value["currentContextId"]}
        marker = {"schemaVersion": MARKER, "investigations": values}
        trace.append(source=MARKER, direction="internal", message={"method": "$owned-attempt/demo", "params": marker})
        return {**marker, "fixtureDirectory": str(fixture_directory(path)), "classification": "authored-subprocess-fixture",
                "nativeOrModelCalls": 0}
    finally:
        api.close()
        trace.close()


def inspect(path: Path):
    trace = TraceStore(path)
    api = None
    try:
        markers = [r for r in trace.records() if r.source == MARKER and r.method == "$owned-attempt/demo"]
        if len(markers) != 1:
            raise ValueError("Not a unique owned-attempt authored fixture.")
        marker = markers[0].message["params"]
        api = make_api(trace)
        for entry in marker["investigations"].values():
            value = api.investigations.get(entry["investigationId"])
            assert value["currentContextId"] == entry["contextId"]
            assert "PRIVATE_" not in json.dumps(value)
        return {**marker, "fixtureDirectory": str(fixture_directory(path)), "classification": "authored-subprocess-fixture",
                "nativeOrModelCalls": 0}
    finally:
        if api is not None:
            api.close()
        trace.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--port", type=int, default=8767)
    args = parser.parse_args()
    value = inspect(args.db) if args.resume else seed(args.db)
    if args.output:
        args.output.write_text(json.dumps(value, indent=2) + "\n")
    print(json.dumps(value, indent=2), flush=True)
    if args.serve:
        # The existing server/loopback guards are used intact with a local fixture
        # factory. No command/provider is accepted from an HTTP request.
        with patch.object(server_module, "EidosAPI", make_api):
            server_module.serve(args.db, port=args.port, codex=str(FIXTURE))


if __name__ == "__main__":
    main()
