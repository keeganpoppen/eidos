"""Native probe safety tests; real no-model verification requires explicit opt-in."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest


SPEC = importlib.util.spec_from_file_location(
    "native_mcp_probe", Path(__file__).parents[1] / "scripts" / "native_mcp_probe.py"
)
assert SPEC and SPEC.loader
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)


@pytest.mark.parametrize("method", ["turn/start", "turn/steer", "command/exec", "thread/resume"])
def test_probe_blocks_unapproved_methods_before_transport(method):
    client = probe.ProbeSession.__new__(probe.ProbeSession)
    with pytest.raises(ValueError, match="no-model allowlist"):
        client.request(method, {})


def test_probe_does_not_inherit_credentials_or_user_home(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-secret-that-must-not-propagate")
    monkeypatch.setenv("CODEX_HOME", "/synthetic/personal-home")
    captured = {}

    class StopBeforeLaunch(Exception):
        pass

    def capture(*args, **kwargs):
        captured.update(kwargs)
        raise StopBeforeLaunch

    monkeypatch.setattr(probe.subprocess, "Popen", capture)
    with pytest.raises(StopBeforeLaunch):
        probe.ProbeSession("/synthetic/codex", tmp_path)
    assert captured["env"] == {
        "HOME": str(tmp_path / "home"), "CODEX_HOME": str(tmp_path / "codex"),
        "PATH": "/usr/bin:/bin", "LANG": "C.UTF-8",
    }
    assert captured["start_new_session"] is True


@pytest.mark.skipif(os.environ.get("NEMA_NATIVE_PROBE") != "1",
                    reason="explicit no-model native probe: NEMA_NATIVE_PROBE=1")
def test_installed_native_mcp_inventory_and_startup_boundary():
    result = probe.run_probe(os.environ.get("NEMA_CODEX_BINARY", "codex"))
    tools_only = {row["name"]: row for row in result["inventories"]["toolsAndAuthOnly"]["data"]}
    full = {row["name"]: row for row in result["inventories"]["full"]["data"]}
    assert result["modelTurns"] == 0
    assert set(result["rpcMethods"]) <= probe.ALLOWED_METHODS
    assert tools_only["probe_tools"]["tools"]["synthetic_effect"]
    assert tools_only["probe_failed"]["runtimeStatus"] == "failed"
    assert tools_only["probe_failed"]["toolsError"]
    assert tools_only["probe_disabled"]["runtimeStatus"] == "disabled"
    assert result["fixtureEvents"]["disabled"] == []
    assert tools_only["probe_resources"]["runtimeStatus"] == "connected"
    assert tools_only["probe_resources"]["tools"] == {}
    assert tools_only["probe_resources"]["resources"] == []
    assert tools_only["probe_resources"]["resourceTemplates"] == []
    assert full["probe_resources"]["resources"][0]["uri"] == "nema-probe://synthetic"
    assert full["probe_resources"]["resourceTemplates"]
    assert result["fixtureEventsBeforeInventory"]["resources"][0]["event"] == "started"
    assert result["fixtureEventsBeforeInventory"]["tools"][0]["event"] == "started"
    assert not any(event.get("method") in {"tools/call", "resources/read"}
                   for events in result["fixtureEvents"].values() for event in events)
