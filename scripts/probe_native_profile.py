#!/usr/bin/env python3
"""Explicit no-model experiment for prospective local startup controls.

All homes, configuration, MCP processes, and markers are synthetic. The profile
still refuses account-backed launch: this experiment does not admit cloud policy.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
from typing import Any

from eidos.codex import AppServerClient, NativeExecutionProfile

_fixture_spec = importlib.util.spec_from_file_location("native_mcp_profile_fixture", Path(__file__).with_name("native_mcp_probe.py"))
assert _fixture_spec and _fixture_spec.loader
_fixture_module = importlib.util.module_from_spec(_fixture_spec)
_fixture_spec.loader.exec_module(_fixture_module)
FIXTURE = _fixture_module.FIXTURE


ALLOWED_METHODS = frozenset({"initialize", "config/read", "thread/start", "mcpServerStatus/list"})


class NoModelClient(AppServerClient):
    def request(self, method: str, params: Any = None, *, timeout: float = 10.0) -> dict[str, Any]:
        if method not in ALLOWED_METHODS:
            raise ValueError(f"no-model profile probe refuses {method}")
        return super().request(method, params, timeout=timeout)

    def notify(self, method: str, params: Any = None) -> None:
        if method != "initialized":
            raise ValueError("no-model profile probe refuses non-handshake notifications")
        return super().notify(method, params)

    def respond(self, request_id: Any, result: Any = None, *, error: Any = None) -> None:
        raise ValueError("no-model profile probe does not answer native requests")


def run_probe(codex_binary: str = "/usr/bin/codex") -> dict[str, Any]:
    cases: dict[str, Any] = {}
    with tempfile.TemporaryDirectory(prefix="nema-native-profile-") as tmp:
        root = Path(tmp)
        for name in ("inherited", "emptyMap", "profiled"):
            case = root / name
            for directory in ("home", "codex", "workspace"):
                (case / directory).mkdir(parents=True)
            fixture = case / "fixture.py"
            fixture.write_text(FIXTURE)
            marker = case / "mcp-startup.jsonl"
            (case / "codex/config.toml").write_text("\n".join([
                'model_provider="openai"', 'model="nema-no-model"',
                '[mcp_servers.synthetic]', 'enabled=true',
                f'command={json.dumps(sys.executable)}',
                f'args={json.dumps([str(fixture), "resources", str(marker)])}',
                'startup_timeout_sec=2',
            ]))
            profile = NativeExecutionProfile(codex_binary, env={
                "HOME": str(case / "home"), "CODEX_HOME": str(case / "codex"),
                "PATH": "/usr/bin:/bin",
            })
            launch = profile.prepare(case / "workspace")
            # Deliberate no-model test seam: exercise the prospective command
            # against fresh auth-free homes, never account-backed configuration.
            # NativeLaunch.require_live_admission remains fail-closed in v1.
            command = list(launch.command)
            if name != "profiled":
                index = command.index("mcp_servers.synthetic.enabled=false")
                del command[index - 1:index + 1]
            if name == "emptyMap":
                command.extend(["-c", "mcp_servers={}"])
            client = NoModelClient(command, cwd=case / "workspace", env=launch.env,
                                   inherit_env=False, launch_guard=launch.check_unchanged)
            watchdog = threading.Timer(20, client.close)
            watchdog.daemon = True
            watchdog.start()
            try:
                initialized = client.initialize()
                config = client.request("config/read", {"includeLayers": False})
                thread = client.request("thread/start", {
                    "cwd": str(case / "workspace"), "approvalPolicy": "never",
                    "sandbox": "read-only", "environments": [], "ephemeral": True,
                })
                deadline = time.monotonic() + (0.2 if name == "profiled" else 2.0)
                while not marker.exists() and time.monotonic() < deadline:
                    time.sleep(0.01)
                before = marker.read_text().splitlines() if marker.exists() else []
                inventory = client.request("mcpServerStatus/list", {
                    "threadId": thread["thread"]["id"], "limit": 100, "detail": "full",
                })
                markers = marker.read_text().splitlines() if marker.exists() else []
                cases[name] = {
                    "initialized": initialized,
                    "config": config,
                    "startupMarkersBeforeInventory": [json.loads(line) for line in before],
                    "startupMarkers": [json.loads(line) for line in markers],
                    "inventory": inventory,
                    "prospectiveProfileEvidence": dict(launch.evidence),
                    "generatedProfileCommandApplied": name == "profiled",
                    "command": command,
                }
            finally:
                watchdog.cancel()
                client.close()
        report = {
            "schemaVersion": "nema-native-profile-probe/1",
            "binarySha256": NativeExecutionProfile.BINARY_SHA256,
            "classification": "OBSERVED_NO_MODEL_SYNTHETIC",
            "modelTurns": 0, "allowedMethods": sorted(ALLOWED_METHODS),
            "cloudConfigSuppression": "UNVERIFIED; account-backed launch refused",
            "cases": cases,
        }
        return json.loads(json.dumps(report).replace(str(root), "<probe>").replace(sys.executable, "<python>"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex", default="/usr/bin/codex")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = json.dumps(run_probe(args.codex), indent=2) + "\n"
    if args.output:
        args.output.write_text(report)
    else:
        print(report, end="")


if __name__ == "__main__":
    main()
