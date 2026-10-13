"""Exercise a durable investigation through a synthetic native worker and Eidos.

uv run python scripts/investigation_continuation_demo.py --db /tmp/new-cycle-b.db
uv run python scripts/investigation_continuation_demo.py --db /tmp/new-cycle-b.db --resume

No model or provider is called. --resume only recovers and inspects the marked
synthetic investigation; it never seeds evidence or dispatches another turn.
"""
from __future__ import annotations

import argparse
import io
import json
from pathlib import Path
import sqlite3
import sys
import time
from typing import Any

from eidos.api import EidosAPI
from eidos.investigation_worker import NativeInvestigationWorker
from eidos.trace import TraceStore
from investigation_demo import seed


DEMO_SOURCE = "synthetic-investigation-continuation-demo"
CREATE_REQUEST = "synthetic-cycle-b-demo-create"
FAKE = Path(__file__).resolve().parents[1] / "tests/fixtures/investigation_appserver.py"


class _Request:
    def __init__(self, body: dict[str, Any]) -> None:
        encoded = json.dumps(body).encode()
        self.headers = {"Content-Length": str(len(encoded)), "Content-Type": "application/json"}
        self.rfile = io.BytesIO(encoded)


def call(api: EidosAPI, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    status, result = api.dispatch(
        _Request({} if body is None else body), "POST", "/api/investigations" + path, {},
    )
    if not 200 <= status < 300:
        raise RuntimeError(f"synthetic demo API request {path!r} returned {status}: {result}")
    return result


def open_api(path: Path) -> tuple[TraceStore, EidosAPI]:
    store = TraceStore(path)
    api = EidosAPI(store, codex=str(FAKE))
    api.investigation_worker.close()
    api.investigation_worker = NativeInvestigationWorker(
        store, command=[sys.executable, str(FAKE)],
    )
    return store, api


def validated_marker(path: Path) -> dict[str, Any]:
    """Check the synthetic identity before opening a mutating API connection."""
    if not path.is_file():
        raise ValueError("--resume requires an existing synthetic continuation demo")
    connection = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        row = connection.execute(
            "SELECT raw_text FROM trace_records WHERE source=? ORDER BY seq DESC LIMIT 1",
            (DEMO_SOURCE,),
        ).fetchone()
        if row is None:
            raise ValueError("--resume requires this script's synthetic demo marker")
        marker = json.loads(row[0])["params"]
        request = connection.execute(
            "SELECT investigation_id FROM investigation_requests WHERE request_id=?",
            (CREATE_REQUEST,),
        ).fetchone()
        investigations = connection.execute("SELECT id,state_json FROM investigations").fetchall()
        if (
            marker.get("demoVersion") != 1
            or request is None
            or len(investigations) != 1
            or request[0] != marker.get("investigationId")
            or investigations[0][0] != request[0]
        ):
            raise ValueError("--resume requires the sole marked synthetic investigation")
        investigation = json.loads(investigations[0][1])
        attempt = investigation.get("attempt") or {}
        if (
            attempt.get("id") != marker.get("attemptId")
            or not str(attempt.get("threadId", "")).startswith("fixture-worker-")
            or not str(attempt.get("turnId", "")).startswith("fixture-turn-")
        ):
            raise ValueError("demo marker does not identify a synthetic native attempt")
        return marker
    except (sqlite3.Error, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("--resume requires a valid synthetic continuation demo") from exc
    finally:
        connection.close()


def wait_native(api: EidosAPI, identifier: str) -> dict[str, Any]:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        investigation = api.investigations.get(identifier)
        status = investigation["attempt"]["status"]
        if status in {"completed", "failed", "unknown"}:
            if status != "completed":
                raise RuntimeError(f"synthetic native attempt ended with status {status!r}")
            return investigation
        time.sleep(0.01)
    raise RuntimeError("synthetic native attempt did not complete within ten seconds")


def summary(
    store: TraceStore, api: EidosAPI, investigation: dict[str, Any],
    marker: dict[str, Any], *, mode: str, checkpoint_after_restart: str,
) -> dict[str, Any]:
    investigations = api.investigations.list()
    attempts = [item["attempt"] for item in investigations if item.get("attempt") is not None]
    native_turns = store.db.execute(
        "SELECT COUNT(*) FROM trace_records WHERE direction='client_to_appserver' AND method='turn/start'",
    ).fetchone()[0]
    counts = {
        "investigations": len(investigations), "attempts": len(attempts),
        "nativeTurnStarts": native_turns,
    }
    if counts != {"investigations": 1, "attempts": 1, "nativeTurnStarts": 1}:
        raise RuntimeError(f"synthetic demo unexpectedly duplicated work: {counts}")
    continuation = investigation["continuation"]
    inquiry = continuation["inquiry"]
    artifact = investigation.get("artifact")
    lineage = api.investigations.context_lineage(investigation["id"])
    pin = lineage["attempt"]["pin"]
    if marker.get("requestPinId") and pin["id"] != marker["requestPinId"]:
        raise RuntimeError("native request was repinned during local review/restart")
    offered = next((r["evidenceContext"] for r in inquiry["responses"] if r["decision"] == "offer"), None)
    occurrences = []
    for response in inquiry["responses"]:
        name = response.get("occurrenceId")
        if name is not None:
            occurrence = api.investigation_runtime.trusted.authority_occurrence(name)
            occurrences.append({"id": name, "kind": occurrence["kind"]})
    return {
        "mode": mode, "synthetic": True, "counts": counts,
        "investigationId": investigation["id"], "attemptId": investigation["attempt"]["id"],
        "nativeTurnId": investigation["attempt"]["turnId"],
        "continuationId": continuation["id"], "processId": continuation["processId"],
        "inquiryId": inquiry["id"], "inquiryStatus": inquiry["status"],
        "pendingCheckpointId": marker["pendingCheckpointId"],
        "checkpointAfterRestart": checkpoint_after_restart,
        "sameCheckpointAfterRestart": checkpoint_after_restart == marker["pendingCheckpointId"],
        "outcomeId": continuation["outcomeId"],
        "artifactId": None if artifact is None else artifact["id"],
        "nativeArtifactId": investigation["nativeArtifact"]["id"],
        "nativeRequestPinId": None if pin is None else pin["id"],
        "nativeManifestId": lineage["attempt"]["manifestId"],
        "offeredManifestId": None if offered is None else offered.get("manifestId"),
        "nativeCorrelationCount": len(lineage["attempt"]["events"]),
        "providerContext": "unknown",
        "sourceOccurrences": occurrences,
        "adoption": None if investigation.get("adoption") is None else investigation["adoption"]["decision"],
    }


def run(path: Path, *, resume: bool) -> dict[str, Any]:
    if resume:
        marker = validated_marker(path)
        store, api = open_api(path)
        try:
            existing = api.investigations.get(marker["investigationId"])
            checkpoint = existing["continuation"]["checkpointId"]
            recovered = call(api, f"/{existing['id']}/recover")
            return summary(store, api, recovered, marker, mode="inspect-and-recover", checkpoint_after_restart=checkpoint)
        finally:
            api.close()
            store.close()

    if path.exists():
        raise ValueError("--db must be a new path; use --resume for a marked existing demo")
    store, api = open_api(path)
    try:
        body = seed(store)
        body["requestId"] = CREATE_REQUEST
        investigation = call(api, "", body)
        identifier = investigation["id"]
        call(api, f"/{identifier}/dispatch", {"contextId": investigation["currentContextId"]})
        completed = wait_native(api, identifier)
        waiting = call(api, f"/{identifier}/continuation", {
            "requestId": "synthetic-cycle-b-demo-open", "attemptId": completed["attempt"]["id"],
            "question": "Will the owner disclose the selected evidence supporting this result?",
        })
        inquiry = waiting["continuation"]["inquiry"]["id"]
        deferred = call(api, f"/{identifier}/inquiries/{inquiry}/responses", {
            "requestId": "synthetic-cycle-b-demo-defer", "decision": "defer",
            "note": "Synthetic source is reviewing which evidence to disclose.",
        })
        marker = {
            "demoVersion": 1, "investigationId": identifier,
            "attemptId": completed["attempt"]["id"],
            "pendingCheckpointId": waiting["continuation"]["checkpointId"],
            "requestPinId": api.investigations.context_lineage(identifier)["attempt"]["pin"]["id"],
        }
        if deferred["continuation"]["checkpointId"] != marker["pendingCheckpointId"]:
            raise RuntimeError("deferral unexpectedly advanced the requesting continuation")
        store.append(source=DEMO_SOURCE, direction="internal", message={
            "method": "$demo/investigationContinuation", "params": marker,
        })
    finally:
        api.close()
        store.close()

    # Validate and reopen the persisted investigation before answering it.
    marker = validated_marker(path)
    store, api = open_api(path)
    try:
        restored = api.investigations.get(marker["investigationId"])
        checkpoint = restored["continuation"]["checkpointId"]
        if checkpoint != marker["pendingCheckpointId"] or restored["status"] != "pending":
            raise RuntimeError("restart did not preserve the pending investigation")
        inquiry = restored["continuation"]["inquiry"]["id"]
        call(api, f"/{identifier}/inquiries/{inquiry}/responses", {
            "requestId": "synthetic-cycle-b-demo-offer", "decision": "offer",
            "note": "Synthetic owner discloses the reviewed source records.",
            "selections": body["selections"],
        })
        resumed = call(api, f"/{identifier}/resume")
        if resumed["artifact"] is None or resumed["continuation"]["outcomeId"] is None:
            raise RuntimeError("Eidos continuation did not reintegrate its final artifact")
        adopted = call(api, f"/{identifier}/adoption", {
            "artifactId": resumed["artifact"]["id"], "decision": "adopt",
            "note": "Synthetic demo adoption records a choice; no patch is applied.",
        })
        return summary(store, api, adopted, marker, mode="complete-demo", checkpoint_after_restart=checkpoint)
    finally:
        api.close()
        store.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, type=Path, help="new SQLite path for the synthetic demo")
    parser.add_argument("--resume", action="store_true", help="only inspect/recover an existing marked synthetic demo")
    args = parser.parse_args()
    try:
        result = run(args.db.expanduser(), resume=args.resume)
    except (ValueError, RuntimeError) as exc:
        parser.exit(1, f"{exc}\n")
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
