"""Outer containment experiment: default guards; explicit no-model native probe."""
import importlib.util
import os
from pathlib import Path

import pytest


spec = importlib.util.spec_from_file_location(
    "probe_native_outer_boundary", Path(__file__).parents[1] / "scripts/probe_native_outer_boundary.py")
assert spec and spec.loader
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


@pytest.mark.parametrize("method", ["turn/start", "turn/steer", "thread/realtime/start",
                                     "process/spawn", "thread/shellCommand", "account/login/start"])
def test_outer_probe_refuses_model_login_and_process_calls_before_spawn(method):
    client = probe.NoModelClient(["must-not-launch"])
    with pytest.raises(ValueError, match="probe refuses"):
        client.request(method, {})
    assert client.process is None


def test_outer_probe_refuses_non_handshake_notifications_and_responses():
    client = probe.NoModelClient(["must-not-launch"])
    with pytest.raises(ValueError, match="notification"):
        client.notify("turn/start", {})
    with pytest.raises(ValueError, match="does not answer"):
        client.respond(1, {})
    assert client.process is None


@pytest.mark.skipif(os.environ.get("NEMA_NATIVE_OUTER_PROBE") != "1",
                    reason="explicit opt-in for disconnected, no-model native startup")
def test_real_native_startup_effects_are_contained_before_inventory():
    report = probe.run_probe()
    assert report["modelTurns"] == 0
    assert report["account"] == {"account": None, "requiresOpenaiAuth": True}
    assert report["startupBeforeInventory"] is True
    assert report["startup"]["packetRead"] is True
    assert int(report["startup"]["effectiveCapabilities"], 16) == 0
    assert report["startup"]["nestedUserNamespaceRefused"] is True
    assert report["startup"]["packetRemountRefused"] is True
    for name in ("outsideRead", "outsideWrite", "symlinkRead", "packetWrite",
                 "hostLoopback", "externalRoute", "parentRootRead"):
        assert "blockedErrno" in report["startup"][name], name
    assert [server["name"] for server in report["inventory"]["data"]] == ["unexpected"]
    for name in ("hostCanaryUnchanged", "packetUnchanged", "hostListenerUntouched",
                 "descendantHeartbeatChangedBeforeClose",
                 "descendantHeartbeatStoppedAfterClose"):
        assert report[name] is True, name
