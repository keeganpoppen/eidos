#!/usr/bin/env python3
"""Probe native MCP discovery using synthetic servers and no model turns.

This intentionally bypasses the user's Codex home and inherited environment.
Run explicitly: uv run python scripts/native_mcp_probe.py --codex /usr/bin/codex
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import queue
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from typing import Any


ALLOWED_METHODS = frozenset({"initialize", "thread/start", "mcpServerStatus/list"})

# Every input and side effect is synthetic and confined to the temporary home.
# The marker also demonstrates that discovery executes a process before any
# model turn or investigation-tool admission decision.
FIXTURE = r'''
import json, pathlib, sys
mode, marker = sys.argv[1:]
with open(marker, "a") as out:
    out.write(json.dumps({"event": "started", "mode": mode}) + "\n")
if mode == "failed":
    sys.exit(23)
for raw in sys.stdin:
    message = json.loads(raw)
    method = message.get("method")
    with open(marker, "a") as out:
        out.write(json.dumps({"event": "request", "method": method}) + "\n")
    if "id" not in message:
        continue
    if method == "initialize":
        result = {"protocolVersion": message["params"]["protocolVersion"],
                  "capabilities": {"tools": {}, "resources": {}},
                  "serverInfo": {"name": "nema-synthetic-" + mode, "version": "1"}}
    elif method == "tools/list":
        result = {"tools": ([{"name": "synthetic_effect", "description": "Never call",
                              "inputSchema": {"type": "object", "properties": {}}}]
                            if mode == "tools" else [])}
    elif method == "resources/list":
        result = {"resources": [{"uri": "nema-probe://synthetic", "name": "Synthetic resource"}]}
    elif method == "resources/templates/list":
        result = {"resourceTemplates": [{"uriTemplate": "nema-probe://{id}", "name": "Synthetic template"}]}
    else:
        print(json.dumps({"jsonrpc": "2.0", "id": message["id"],
                          "error": {"code": -32601, "message": "probe does not execute operations"}}), flush=True)
        continue
    print(json.dumps({"jsonrpc": "2.0", "id": message["id"], "result": result}), flush=True)
'''


class ProbeSession:
    """Small bounded transport whose RPC allowlist excludes all model calls."""

    def __init__(self, codex_binary: str, root: Path) -> None:
        self.methods: list[str] = []
        self.output: queue.Queue[Any] = queue.Queue()
        self.stderr: list[str] = []
        self.deadline = time.monotonic() + 30
        self.process = subprocess.Popen(
            [codex_binary, "app-server", "--listen", "stdio://"],
            cwd=root / "workspace",
            env={"HOME": str(root / "home"), "CODEX_HOME": str(root / "codex"),
                 "PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"},
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", start_new_session=True,
        )
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.err_reader = threading.Thread(target=self._read_err, daemon=True)
        self.reader.start()
        self.err_reader.start()
        self.watchdog = threading.Timer(30, self._kill)
        self.watchdog.daemon = True
        self.watchdog.start()

    def _read(self) -> None:
        assert self.process.stdout is not None
        try:
            for line in self.process.stdout:
                self.output.put(json.loads(line))
        except Exception as exc:
            self.output.put(exc)
        finally:
            self.output.put(EOFError("native MCP probe process exited"))

    def _read_err(self) -> None:
        assert self.process.stderr is not None
        for line in self.process.stderr:
            self.stderr.append(line.rstrip())
            del self.stderr[:-100]

    def _kill(self) -> None:
        try:
            os.killpg(self.process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass

    def close(self) -> None:
        self.watchdog.cancel()
        self._kill()
        self.process.wait(timeout=5)
        self.reader.join(timeout=1)
        self.err_reader.join(timeout=1)
        for stream in (self.process.stdin, self.process.stdout, self.process.stderr):
            if stream is not None:
                stream.close()

    def request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        if method not in ALLOWED_METHODS:
            raise ValueError(f"Probe refuses RPC outside no-model allowlist: {method}")
        self.methods.append(method)
        request_id = len(self.methods)
        assert self.process.stdin is not None
        self.process.stdin.write(json.dumps({"jsonrpc": "2.0", "id": request_id,
                                            "method": method, "params": params}) + "\n")
        self.process.stdin.flush()
        while True:
            remaining = self.deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("native MCP probe deadline expired")
            message = self.output.get(timeout=remaining)
            if isinstance(message, Exception):
                raise message
            if message.get("id") != request_id or "method" in message:
                continue
            if "error" in message:
                raise RuntimeError(f"{method}: {message['error']}")
            if method == "initialize":
                self.process.stdin.write('{"jsonrpc":"2.0","method":"initialized"}\n')
                self.process.stdin.flush()
            return message["result"]


def _marker(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def run_probe(codex_binary: str) -> dict[str, Any]:
    """Return only synthetic observations; clean all spawned processes/files."""
    binary = shutil.which(codex_binary)
    if binary is None:
        raise FileNotFoundError(codex_binary)
    binary = str(Path(binary).resolve())
    with tempfile.TemporaryDirectory(prefix="nema-mcp-probe-") as directory:
        root = Path(directory)
        for name in ("home", "codex", "workspace"):
            (root / name).mkdir()
        fixture = root / "mcp_fixture.py"
        fixture.write_text(FIXTURE)
        config = [
            'model_provider = "nema_probe"',
            'model = "nema-no-model"',
            'web_search = "disabled"',
            '[model_providers.nema_probe]',
            'name = "Nema synthetic probe; no model requests"',
            'base_url = "http://127.0.0.1:9"',
            'wire_api = "responses"',
            'requires_openai_auth = false',
            '[features]', 'apps = false', 'shell_tool = false',
            'multi_agent = false', 'hooks = false', 'memories = false',
        ]
        for mode in ("tools", "resources", "failed", "disabled"):
            config.extend([
                f'[mcp_servers.probe_{mode}]',
                f'command = {json.dumps(sys.executable)}',
                f'args = {json.dumps([str(fixture), mode, str(root / (mode + ".jsonl"))])}',
                'startup_timeout_sec = 3',
                'enabled = ' + ('false' if mode == 'disabled' else 'true'),
            ])
        (root / "codex" / "config.toml").write_text("\n".join(config) + "\n")
        client = ProbeSession(binary, root)
        try:
            initialized = client.request("initialize", {
                "clientInfo": {"name": "nema-native-mcp-probe", "version": "1"},
                "capabilities": {"experimentalApi": True},
            })
            thread = client.request("thread/start", {
                "cwd": str(root / "workspace"), "approvalPolicy": "never",
                "sandbox": "read-only", "environments": [], "ephemeral": True,
            })
            # Thread startup is asynchronous. Observe startup writes before
            # invoking inventory, with a bounded wait that consumes no turns.
            startup_deadline = time.monotonic() + 2
            while time.monotonic() < startup_deadline:
                if all((root / (mode + ".jsonl")).exists()
                       for mode in ("tools", "resources", "failed")):
                    break
                time.sleep(0.01)
            before_inventory = {mode: _marker(root / (mode + ".jsonl"))
                                for mode in ("tools", "resources", "failed", "disabled")}
            inventories = {}
            inventory_events = {}
            for detail in ("toolsAndAuthOnly", "full"):
                inventories[detail] = client.request("mcpServerStatus/list", {
                    "threadId": thread["thread"]["id"], "limit": 100, "detail": detail,
                })
                inventory_events[detail] = {
                    mode: _marker(root / (mode + ".jsonl"))
                    for mode in ("tools", "resources", "failed", "disabled")
                }
            markers = {mode: _marker(root / (mode + ".jsonl"))
                       for mode in ("tools", "resources", "failed", "disabled")}
            return {
                "status": "OBSERVED", "initialize": initialized,
                "inventories": inventories, "fixtureEventsBeforeInventory": before_inventory,
                "fixtureEventsAfterInventory": inventory_events,
                "fixtureEvents": markers, "rpcMethods": client.methods,
                "modelTurns": 0,
            }
        finally:
            client.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex", default="codex")
    args = parser.parse_args()
    print(json.dumps(run_probe(args.codex), indent=2))


if __name__ == "__main__":
    main()
