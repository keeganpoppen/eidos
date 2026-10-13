#!/usr/bin/env python3
"""Inspect installed native interaction contracts without starting a model turn.

Uses disposable HOME/CODEX_HOME, no credentials, and a synthetic provider at
loopback port 9. The RPC allowlist deliberately excludes turn/start and steer.
Registration acceptance does not verify model invocation or interaction delivery.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import platform
import shutil
import subprocess
import tempfile
from typing import Any

from eidos.codex import AppServerClient, AppServerRPCError


ALLOWED_METHODS = frozenset({
    "initialize", "thread/start", "thread/read", "collaborationMode/list",
    "thread/increment_elicitation", "thread/decrement_elicitation", "turn/interrupt",
})
SCHEMA_NAMES = (
    "ServerRequest", "ServerNotification", "ClientRequest",
    "ToolRequestUserInputParams", "ToolRequestUserInputResponse",
    "DynamicToolCallParams", "DynamicToolCallResponse",
    "McpServerElicitationRequestParams", "McpServerElicitationRequestResponse",
    "v2/ServerRequestResolvedNotification", "v2/ThreadStartParams",
    "v2/TurnCompletedNotification", "v2/TurnInterruptParams", "v2/TurnSteerParams",
)


class ProbeClient(AppServerClient):
    """A no-model allowlist applies before transport or process startup."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.methods: list[str] = []

    def request(self, method: str, params: Any = None, *, timeout: float = 8.0) -> dict[str, Any]:
        if method not in ALLOWED_METHODS:
            raise ValueError(f"not a no-model interaction probe method: {method}")
        self.methods.append(method)
        return super().request(method, params, timeout=timeout)

    def notify(self, method: str, params: Any = None) -> None:
        if method != "initialized":
            raise ValueError(f"not an interaction probe notification: {method}")
        super().notify(method, params)

    def respond(self, request_id: Any, result: Any = None, *, error: Any = None) -> None:
        raise ValueError("no-model interaction probe cannot answer native requests")


def schema_observations(root: Path) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name in SCHEMA_NAMES:
        raw = (root / f"{name}.json").read_bytes()
        schema = json.loads(raw)
        entry: dict[str, Any] = {"sha256": hashlib.sha256(raw).hexdigest()}
        if name in {"ServerRequest", "ServerNotification", "ClientRequest"}:
            entry["methods"] = [variant["properties"]["method"]["enum"][0]
                                for variant in schema["oneOf"]]
        else:
            entry["required"] = schema.get("required", [])
            entry["properties"] = schema.get("properties", {})
            # Full definitions preserve the actual question, answer, dynamic
            # tool and terminal enums without copying unrelated protocol types.
            wanted = ("ToolRequestUserInputQuestion", "ToolRequestUserInputOption",
                      "ToolRequestUserInputAnswer", "DynamicToolCallOutputContentItem",
                      "DynamicToolSpec", "DynamicToolNamespaceTool", "TurnStatus", "RequestId")
            entry["definitions"] = {key: value for key, value in schema.get("definitions", {}).items()
                                    if key in wanted}
        result[name] = entry
    return result


def run_probe(codex_binary: str) -> dict[str, Any]:
    binary = shutil.which(codex_binary)
    if binary is None:
        raise FileNotFoundError(codex_binary)
    binary = str(Path(binary).resolve())
    with tempfile.TemporaryDirectory(prefix="nema-interactions-") as directory:
        root = Path(directory)
        for name in ("home", "codex", "work"):
            (root / name).mkdir()
        child_env = {"HOME": str(root / "home"), "CODEX_HOME": str(root / "codex"),
                     "PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"}
        (root / "codex" / "config.toml").write_text(
            'model_provider="nema_probe"\nmodel="nema-no-model"\n'
            '[model_providers.nema_probe]\nname="No-model interaction probe"\n'
            'base_url="http://127.0.0.1:9"\nwire_api="responses"\n'
            'requires_openai_auth=false\n')

        def cli(*args: str) -> str:
            return subprocess.run([binary, *args], env=child_env, cwd=root / "work",
                                  capture_output=True, text=True, timeout=20, check=True).stdout

        schema_root = root / "schema"
        version = cli("--version").strip()
        cli("app-server", "generate-json-schema", "--experimental", "--out", str(schema_root))
        # AppServerClient's historical env argument merges with its parent;
        # explicit env -i makes isolation independent of that default.
        command = [shutil.which("env") or "/usr/bin/env", "-i",
                   *(f"{key}={value}" for key, value in child_env.items()),
                   binary, "app-server", "--listen", "stdio://"]
        report: dict[str, Any] = {
            "artifactVersion": 1, "version": version,
            "binarySha256": hashlib.sha256(Path(binary).read_bytes()).hexdigest(),
            "platform": {"system": platform.system(), "machine": platform.machine()},
            "scope": "disposable unauthenticated state; no model turns or native request responses",
            "modelTurns": 0, "liveInteractionGate": "UNVERIFIED",
            "schema": schema_observations(schema_root),
        }

        def rpc(client: ProbeClient, method: str, params: dict[str, Any]) -> dict[str, Any]:
            try:
                return {"result": client.request(method, params)}
            except AppServerRPCError as exc:
                return {"error": exc.error}

        def drain(client: ProbeClient) -> list[dict[str, Any]]:
            events = []
            # One bounded wait observes current notifications; absence here is
            # not a general no-future-events assertion.
            for _ in range(100):
                try:
                    events.append(client.recv_event(timeout=0.05))
                except TimeoutError:
                    return events
            raise RuntimeError("interaction probe exceeded its notification bound")

        with ProbeClient(command, cwd=root / "work") as client:
            report["initialize"] = client.initialize()
            report["collaborationModes"] = rpc(client, "collaborationMode/list", {})
            base = {
                "cwd": str(root / "work"), "approvalPolicy": "never", "sandbox": "read-only",
                "environments": [], "ephemeral": True, "runtimeWorkspaceRoots": [],
                "config": {"features.apps": False, "features.shell_tool": False,
                           "features.multi_agent": False, "features.hooks": False,
                           "features.memories": False, "web_search": "disabled"},
            }
            tool = {"type": "function", "name": "nema_request_evidence",
                    "description": "Ask the controller for synthetic evidence",
                    "inputSchema": {"type": "object", "properties": {"question": {"type": "string"}},
                                    "required": ["question"], "additionalProperties": False}}
            variants = {
                "canonicalFunction": [tool],
                "legacyMissingType": [{key: value for key, value in tool.items() if key != "type"}],
                "duplicateName": [tool, tool],
                "nonObjectInputSchema": [{**tool, "inputSchema": {"type": "string"}}],
                "invalidName": [{**tool, "name": "name with spaces"}],
                "canonicalNamespace": [{"type": "namespace", "name": "nema",
                                        "description": "Synthetic evidence", "tools": [tool]}],
            }
            report["dynamicToolSpecs"] = variants
            report["dynamicToolRegistration"] = {}
            for label, specs in variants.items():
                report["dynamicToolRegistration"][label] = rpc(
                    client, "thread/start", {**base, "dynamicTools": specs})
            thread_id = report["dynamicToolRegistration"]["canonicalFunction"]["result"]["thread"]["id"]
            report["eventsBeforeCounter"] = drain(client)
            report["emptyThreadControls"] = {}
            for label, method, params in (
                ("increment", "thread/increment_elicitation", {"threadId": thread_id}),
                ("readWhileIncremented", "thread/read", {"threadId": thread_id, "includeTurns": False}),
                ("decrement", "thread/decrement_elicitation", {"threadId": thread_id}),
                ("interruptAbsentTurn", "turn/interrupt", {"threadId": thread_id,
                                                          "turnId": "synthetic-not-a-turn"}),
            ):
                report["emptyThreadControls"][label] = rpc(client, method, params)
            report["eventsAfterCounter"] = drain(client)
            report["rpcMethods"] = client.methods
            report["stderr"] = client.stderr_tail
        return json.loads(json.dumps(report).replace(str(root), "<probe>"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex", default="codex")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    rendered = json.dumps(run_probe(args.codex), indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered)
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
