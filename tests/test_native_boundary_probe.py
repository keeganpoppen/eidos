"""Probe safety guards by default; real native checks require an explicit opt-in."""
import importlib.util
import os
from pathlib import Path
import shutil

import pytest


spec = importlib.util.spec_from_file_location(
    "probe_native_boundary", Path(__file__).parents[1] / "scripts" / "probe_native_boundary.py")
assert spec and spec.loader
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


@pytest.mark.parametrize("method", ["turn/start", "turn/steer", "thread/realtime/start",
                                     "process/spawn", "thread/shellCommand"])
def test_probe_cannot_request_model_or_unsandboxed_process(method):
    client = probe.ProbeClient(["must-not-launch"])
    with pytest.raises(ValueError, match="not a no-model probe method"):
        client.request(method, {})
    assert client.process is None


def test_probe_cannot_notify_model_request():
    client = probe.ProbeClient(["must-not-launch"])
    with pytest.raises(ValueError, match="not a probe notification"):
        client.notify("turn/start", {})
    assert client.process is None


@pytest.mark.skipif(os.environ.get("NEMA_NATIVE_PROBE") != "1",
                    reason="explicit opt-in for isolated, no-model native probes")
def test_installed_native_admission_and_standalone_sandbox():
    binary = shutil.which("codex")
    if binary is None:
        pytest.skip("Codex is not installed")
    report = probe.run_probe(binary)
    assert report["threadStart"]["sandbox"] == probe.READ_ONLY
    assert report["threadStart"]["approvalPolicy"] == "never"
    assert report["threadStart"]["environments"] == []
    assert report["mcpInventory"]["result"]["data"] == []
    assert report["workerPreflight"] == {
        "reachedGuardBeforeTurn": True, "threadAcknowledged": True, "turnRequestsRecorded": 0,
    }
    assert "error" in report["configurationValidation"]["invalidFeatureType"]
    assert "error" in report["configurationValidation"]["conflictingSandboxAndPermissions"]
    sandbox = report["standaloneSandbox"]
    assert sandbox["exitCode"] == 0
    assert sandbox["hostVerifiedUnchanged"] is True
    assert sandbox["observations"]["outsideRead"] is True
    for name in ("cwdWrite", "outsideWrite", "symlinkWrite", "loopbackConnect"):
        assert "blockedErrno" in sandbox["observations"][name]
