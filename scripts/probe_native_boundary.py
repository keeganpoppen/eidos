#!/usr/bin/env python3
"""No-model Codex compatibility probe using disposable, unauthenticated state.

Run with `uv run python scripts/probe_native_boundary.py --output /tmp/native.json`.
This never imports user history/configuration, sends turn/start, or uses an API key.
Standalone command/exec touches only synthetic sentinel files and loopback sockets.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import platform
import shutil
import socket
import subprocess
import sys
import tempfile
from typing import Any
from unittest.mock import patch

from eidos.codex import AppServerClient, AppServerRPCError
from eidos.investigation_worker import NativeInvestigationError, NativeInvestigationWorker
from eidos.trace import TraceStore


READ_ONLY = {"type": "readOnly", "networkAccess": False}
WORKER_CONFIG = {
    "features.apps": False, "features.shell_tool": False,
    "features.multi_agent": False, "features.hooks": False,
    "features.memories": False, "web_search": "disabled",
}
ALLOWED_METHODS = frozenset({
    "initialize", "config/read", "thread/start", "mcpServerStatus/list",
    "thread/read", "thread/resume", "thread/fork", "thread/turns/list",
    "thread/items/list", "command/exec",
})


class ProbeClient(AppServerClient):
    """The probe has no inference operation, even if extended accidentally."""

    def request(self, method: str, params: Any = None, *, timeout: float = 8.0) -> dict[str, Any]:
        if method not in ALLOWED_METHODS:
            raise ValueError(f"not a no-model probe method: {method}")
        return super().request(method, params, timeout=timeout)

    def notify(self, method: str, params: Any = None) -> None:
        if method != "initialized":
            raise ValueError(f"not a probe notification: {method}")
        super().notify(method, params)


def _schema_summary(schema_root: Path) -> dict[str, Any]:
    names = ["ThreadStartParams", "ThreadStartResponse", "TurnStartParams",
             "TurnCompletedNotification", "ErrorNotification", "ThreadResumeParams",
             "ListMcpServerStatusParams", "ListMcpServerStatusResponse", "CommandExecParams"]
    summary = {}
    for name in names:
        raw = (schema_root / "v2" / f"{name}.json").read_bytes()
        schema = json.loads(raw)
        summary[name] = {"sha256": hashlib.sha256(raw).hexdigest(),
                         "required": schema.get("required", []),
                         "fields": sorted(schema["properties"])}
    terminal = json.loads((schema_root / "v2" / "TurnCompletedNotification.json").read_text())
    summary["turnStatuses"] = terminal["definitions"]["TurnStatus"]["enum"]
    return summary


def run_probe(codex_binary: str) -> dict[str, Any]:
    """Return observations, including native RPC errors rather than hiding them."""
    with tempfile.TemporaryDirectory(prefix="nema-native-probe-") as directory:
        root = Path(directory)
        home, codex_home, cwd = (root / name for name in ("home", "codex", "work"))
        for path in (home, codex_home, cwd):
            path.mkdir()
        # Only this child's environment is replaced. The owner's state is never read/copied.
        child_env = {"HOME": str(home), "CODEX_HOME": str(codex_home),
                     "PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"}
        (codex_home / "config.toml").write_text(
            'model_provider="nema_probe"\n'
            '[model_providers.nema_probe]\nname="No-model native probe"\n'
            'base_url="http://127.0.0.1:9"\nwire_api="responses"\n'
            'requires_openai_auth=false\n'
        )

        def cli(*args: str) -> subprocess.CompletedProcess[str]:
            return subprocess.run([codex_binary, *args], env=child_env, cwd=cwd,
                                  capture_output=True, text=True, timeout=20, check=True)

        report: dict[str, Any] = {
            "version": cli("--version").stdout.strip(),
            "platform": {"system": platform.system(), "machine": platform.machine()},
            "scope": "synthetic configuration; no model turns or credentials",
        }
        schema_root = root / "schema"
        cli("app-server", "generate-json-schema", "--experimental", "--out", str(schema_root))
        report["schema"] = _schema_summary(schema_root)
        overrides = [arg for key, value in WORKER_CONFIG.items()
                     for arg in ("-c", f"{key}={json.dumps(value)}")]
        feature_lines = cli(*overrides, "features", "list").stdout.splitlines()
        report["cliFeatureFlags"] = [line for line in feature_lines
                                     if line.split() and line.split()[0] in
                                     {key.removeprefix("features.") for key in WORKER_CONFIG}]
        # env -i is intentional: AppServerClient.env otherwise MERGES with its parent.
        command = [shutil.which("env") or "/usr/bin/env", "-i",
                   *(f"{key}={value}" for key, value in child_env.items()),
                   codex_binary, "app-server", "--listen", "stdio://"]

        def new_client() -> ProbeClient:
            return ProbeClient(command, cwd=cwd)

        def rpc(client: ProbeClient, method: str, params: dict[str, Any]) -> dict[str, Any]:
            try:
                return {"result": client.request(method, params)}
            except AppServerRPCError as exc:
                return {"error": exc.error}

        thread_params = {"cwd": str(cwd), "approvalPolicy": "never", "sandbox": "read-only",
                         "environments": [], "ephemeral": False,
                         "threadSource": "nema-investigation", "config": WORKER_CONFIG}
        with new_client() as client:
            report["initialize"] = client.initialize()
            configured = client.request("config/read", {"includeLayers": False})["config"]
            report["globalConfigBeforeThread"] = {key: configured.get(key) for key in
                                                  ("features", "web_search", "sandbox_mode")}
            start = client.request("thread/start", thread_params)
            tid = start["thread"]["id"]
            report["threadStart"] = {key: start.get(key) for key in
                                     ("sandbox", "approvalPolicy", "cwd", "activePermissionProfile",
                                      "instructionSources", "multiAgentMode", "runtimeWorkspaceRoots")}
            report["threadStart"]["environments"] = start["thread"].get("environments")
            report["threadStart"]["historyMode"] = start["thread"].get("historyMode")
            report["mcpInventory"] = rpc(client, "mcpServerStatus/list", {
                "threadId": tid, "detail": "toolsAndAuthOnly", "limit": 100})
            configured = client.request("config/read", {"includeLayers": False})["config"]
            report["globalConfigAfterThread"] = {key: configured.get(key) for key in
                                                 ("features", "web_search", "sandbox_mode")}
            report["configurationValidation"] = {}
            for label, changes in [
                ("invalidFeatureType", {"config": {"features.shell_tool": "not-a-boolean"}}),
                ("conflictingSandboxAndPermissions", {"permissions": ":read-only"}),
                ("unknownFeature", {"config": {"features.nema_nonexistent_probe": False}}),
            ]:
                outcome = rpc(client, "thread/start", {**thread_params, **changes})
                report["configurationValidation"][label] = (
                    outcome if "error" in outcome else {"accepted": True})
            report["lifecycle"] = {}
            for label, method, params in [
                ("metadataRead", "thread/read", {"threadId": tid, "includeTurns": False}),
                ("historyRead", "thread/read", {"threadId": tid, "includeTurns": True}),
                ("turnsList", "thread/turns/list", {"threadId": tid, "limit": 10}),
                ("itemsList", "thread/items/list", {"threadId": tid, "limit": 10}),
                ("resumeSameProcess", "thread/resume", {"threadId": tid, "excludeTurns": True}),
                ("fork", "thread/fork", {"threadId": tid, "excludeTurns": True}),
            ]:
                outcome = rpc(client, method, params)
                # Preserve errors verbatim; metadata has no useful random IDs to publish.
                report["lifecycle"][label] = outcome if "error" in outcome else {"success": True}

            outside = root / "outside.txt"
            outside.write_text("synthetic-outside-evidence")
            (cwd / "outside-link").symlink_to(outside)
            listener = socket.socket()
            listener.bind(("127.0.0.1", 0))
            listener.listen(1)
            port = listener.getsockname()[1]
            # Control confirms that the loopback listener is reachable before sandboxing.
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                control, _ = listener.accept()
                control.close()
            probe_code = '''import json, pathlib, socket, sys
outside, cwd, port = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]), int(sys.argv[3])
out = {"outsideRead": outside.read_text() == "synthetic-outside-evidence"}
for name, path in [("cwdWrite", cwd / "new.txt"), ("outsideWrite", outside), ("symlinkWrite", cwd / "outside-link")]:
    try:
        path.write_text("unexpected mutation")
        out[name] = "allowed"
    except OSError as exc:
        out[name] = {"blockedErrno": exc.errno}
try:
    with socket.create_connection(("127.0.0.1", port), timeout=1): pass
    out["loopbackConnect"] = "allowed"
except OSError as exc:
    out["loopbackConnect"] = {"blockedErrno": exc.errno, "errorType": type(exc).__name__}
print(json.dumps(out))
'''
            try:
                execution = client.request("command/exec", {
                    "command": [sys.executable, "-c", probe_code, str(outside), str(cwd), str(port)],
                    "cwd": str(cwd), "sandboxPolicy": READ_ONLY,
                    "timeoutMs": 4000, "outputBytesCap": 4000,
                })
            finally:
                listener.close()
            report["standaloneSandbox"] = execution
            if execution.get("exitCode") == 0:
                report["standaloneSandbox"]["observations"] = json.loads(execution["stdout"])
            report["standaloneSandbox"]["hostVerifiedUnchanged"] = (
                outside.read_text() == "synthetic-outside-evidence" and not (cwd / "new.txt").exists())
            report["stderr"] = client.stderr_tail

        with new_client() as client:
            client.initialize()
            resumed = rpc(client, "thread/resume", {
                "threadId": tid, "excludeTurns": True, "cwd": str(cwd),
                "approvalPolicy": "never", "sandbox": "read-only", "config": WORKER_CONFIG,
            })
            if "result" in resumed:
                result = resumed["result"]
                resumed = {"success": True, "sameThreadId": result["thread"]["id"] == tid,
                           "sandbox": result.get("sandbox"),
                           "environments": result["thread"].get("environments"),
                           "runtimeWorkspaceRoots": result.get("runtimeWorkspaceRoots")}
            report["lifecycle"]["resumeAfterRestart"] = resumed
        # Exercise the actual worker's admission path. The guard rejects the
        # model RPC before transport or tracing, so this cannot run inference.
        trace = TraceStore(root / "worker.sqlite3")
        try:
            updates: dict[str, Any] = {}
            with patch("eidos.investigation_worker.AppServerClient", ProbeClient):
                worker = NativeInvestigationWorker(trace, command=command)
                try:
                    worker.run({"id": "probe-attempt", "contextId": "probe-context", "timeoutSeconds": 10},
                               {"id": "probe-context", "projectedPrompt": "Synthetic; must never be sent."},
                               lambda **fields: updates.update(fields))
                except NativeInvestigationError as exc:
                    report["workerPreflight"] = {
                        "reachedGuardBeforeTurn": "not a no-model probe method: turn/start" in str(exc),
                        "threadAcknowledged": "threadId" in updates,
                        "turnRequestsRecorded": sum(record.method == "turn/start" for record in trace.records()),
                    }
                finally:
                    worker.close()
        finally:
            trace.close()
        # Nothing from a personal home was read; normalize temporary paths for review.
        return json.loads(json.dumps(report).replace(str(root), "<probe>"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex", default="codex")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    binary = shutil.which(args.codex)
    if binary is None:
        parser.error("Codex binary not found")
    report = run_probe(binary)
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered)
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
