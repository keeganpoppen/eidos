"""Admit a fixed public Git corpus and an explicitly supplied observation.

Usage: uv run --offline --locked python scripts/recovery_repair_demo.py \
    --output-dir /tmp/new-recovery-corpus --observation /tmp/observed-check.json

The destination must not exist. Historical bytes are read, never executed. Only
the documents enter the workbench; marker/preview diagnostics stay coordinator
artifacts. No investigations, findings, selections or execution are seeded.
"""
from __future__ import annotations

import argparse
import base64
from contextlib import closing
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

from eidos.api import EidosAPI
from eidos.trace import TraceStore

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "recovery-repair-corpus/v1"
CORPUS_BYTES = 177_215
CORPUS = {
    "fa7eabffe93b87b62ed91ac51b84f4fb1ca101c8": (
        "src/eidos/investigation.py", "src/eidos/investigation_context.py",
        "src/eidos/context_manifest.py", "src/eidos/native_managed.py",
        "tests/test_artifact_context_compatibility.py", "pyproject.toml", "uv.lock",
        "docs/evidence/MANAGED_ATTEMPT_INTEGRATION.md",
    ),
    "8ed2f0a5ed107e03863fdcf9623e8571eb606051": (
        "src/eidos/investigation_context.py", "docs/evidence/NATIVE_OWNED_WORKER_EXPERIMENT.md",
        "docs/evidence/OWNED_ATTEMPT_CONTROL_INTEGRATION.md", "docs/evidence/RESULT_DISCOVERY_INTEGRATION.md",
    ),
    "1ee28218cedac5fa121c75334bbdb09dddf68d67": (
        "docs/evidence/ARTIFACT_COMPOSITION_INTEGRATION.md",
    ),
}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git(repository: Path, *args: str) -> bytes:
    return subprocess.run(["git", *args], cwd=repository, check=True,
                          capture_output=True, timeout=15).stdout


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def dispatch(api: EidosAPI, method: str, path: str, body: dict | None = None,
             query: dict[str, list[str]] | None = None) -> tuple[int, dict]:
    raw = b"" if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
    class Handler:
        headers = {"Content-Length": str(len(raw))}
        rfile = io.BytesIO(raw)
    return api.dispatch(Handler(), method, path, query or {})


def build(output: Path, observation: Path, repository: Path = ROOT) -> dict:
    output, observation, repository = output.resolve(), observation.resolve(), repository.resolve()
    if not output.is_relative_to(Path("/tmp")):
        raise ValueError("Use a new /tmp output directory")
    if not observation.is_file():
        raise ValueError("An explicit observation file is required")
    output.mkdir(exist_ok=False)
    documents = output / "documents"
    documents.mkdir()
    marker = {"schemaVersion": SCHEMA, "status": "preparing", "database": str(output / "workbench.db"),
              "runtimeBase": git(ROOT, "rev-parse", "HEAD").decode().strip(),
              "producerSha256": sha(Path(__file__).read_bytes()),
              "runtime": {"python": sys.version, "sqlite": sqlite3.sqlite_version},
              "sourceRepository": str(repository), "observationPath": str(observation),
              "nativeOrModelCalls": 0, "historicalCodeExecuted": False, "files": []}
    write_json(output / "marker.json", marker)
    try:
        files: dict[str, bytes] = {}
        inventory = []
        for revision, paths in CORPUS.items():
            for path in paths:
                data = git(repository, "cat-file", "blob", f"{revision}:{path}")
                name = revision[:7] + "__" + path.replace("/", "__")
                files[name] = data
                (documents / name).write_bytes(data)
                inventory.append({"revision": revision, "path": path, "fileName": name,
                                  "sha256": sha(data), "byteLength": len(data)})
        if len(inventory) != 13 or sum(row["byteLength"] for row in inventory) != CORPUS_BYTES:
            raise ValueError("The fixed corpus must contain 13 complete files / 177215 bytes")
        inventory_name = "corpus-inventory.json"
        if observation.name in {*files, inventory_name}:
            raise ValueError("Observation filename collides with the fixed corpus or inventory")
        files[inventory_name] = (json.dumps(inventory, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
        files[observation.name] = observation.read_bytes()
        for name in (inventory_name, observation.name):
            (documents / name).write_bytes(files[name])
        marker.update({"corpus": inventory, "corpusByteLength": CORPUS_BYTES,
                       "files": [{"fileName": name, "fileSha256": sha(data), "byteLength": len(data)}
                                 for name, data in files.items()]})
        write_json(output / "marker.json", marker)
        with closing(TraceStore(marker["database"])) as trace, closing(EidosAPI(trace)) as api:
            trace.db.execute("CREATE TABLE recovery_repair_marker(marker_json TEXT NOT NULL)")
            trace.db.execute("INSERT INTO recovery_repair_marker VALUES(?)", (json.dumps(marker),))
            previews = []
            bodies = {}
            # Preview every document before admitting any. Refusal preserves all
            # original files and responses; it does not silently trim a document.
            for name, data in files.items():
                body = {"format": "supplied-text/v1", "fileName": name,
                        "contentBase64": base64.b64encode(data).decode("ascii")}
                status, value = dispatch(api, "POST", "/api/evidence/files/preview", body)
                previews.append({"fileName": name, "status": status, "response": value})
                bodies[name] = body
            write_json(output / "previews.json", previews)
            if any(row["status"] != 200 for row in previews):
                raise ValueError("At least one ordinary file preview refused; see previews.json")
            marker["status"] = "admitting"
            for index, (entry, preview) in enumerate(zip(marker["files"], previews, strict=True)):
                body = {**bodies[entry["fileName"]], "requestId": f"recovery-corpus-{index + 1}",
                        "previewFingerprint": preview["response"]["preview"]["previewFingerprint"]}
                status, value = dispatch(api, "POST", "/api/evidence/files", body)
                entry["commitStatus"] = status
                entry["commitResponse"] = value
                write_json(output / "marker.json", marker)
                if status != 201:
                    raise ValueError(f"File admission refused: {entry['fileName']} ({status})")
                receipt = value["receipt"]
                if receipt["fileSha256"] != entry["fileSha256"] or receipt["byteLength"] != entry["byteLength"]:
                    raise ValueError("Admission receipt does not match the original file")
                status, original = dispatch(api, "GET", "/api/evidence/files/" + receipt["id"])
                if status != 200 or original != {"receipt": receipt, "contentBase64": body["contentBase64"]}:
                    raise ValueError("Original-file roundtrip differs from the admitted bytes")
            status, owners = dispatch(api, "GET", "/api/investigations")
            if status != 200 or owners != {"investigations": []}:
                raise ValueError("Corpus admission unexpectedly created investigation state")
            pyproject = next(entry for entry in marker["files"] if entry["fileName"].endswith("__pyproject.toml"))
            status, search = dispatch(api, "GET", "/api/evidence/search", query={
                "q": ["requires-python"], "threadId": [pyproject["commitResponse"]["receipt"]["threadId"]]})
            if status != 200 or len(search["hits"]) != 1 or search["hits"][0]["field"] != "suppliedText.text":
                raise ValueError("Ordinary supplied-text search did not recover the admitted file")
            marker.update({"status": "ready", "verification": {
                "originalFileRoundtrips": len(files), "search": search, "investigationCount": 0,
                "attemptCount": 0, "findingCount": 0, "recordCount": len(trace.records())}})
            trace.db.execute("UPDATE recovery_repair_marker SET marker_json=?", (json.dumps(marker),))
        write_json(output / "marker.json", marker)
        return marker
    except Exception as exc:
        marker.update({"status": "failed", "failure": {"type": type(exc).__name__, "message": str(exc)}})
        write_json(output / "marker.json", marker)
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--observation", type=Path, required=True)
    parser.add_argument("--source-repo", type=Path, default=ROOT)
    args = parser.parse_args()
    result = build(args.output_dir, args.observation, args.source_repo)
    print(json.dumps({"status": result["status"], "database": result["database"],
                      "marker": str(args.output_dir.resolve() / "marker.json"),
                      "corpusByteLength": result["corpusByteLength"], "admittedFiles": len(result["files"])}))
