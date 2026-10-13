"""No-model RPC guards by default; real Linux/native evidence only by opt-in."""
import importlib.util
import os
from pathlib import Path

import pytest


spec = importlib.util.spec_from_file_location(
    "probe_native_process_boundary", Path(__file__).parents[1] / "scripts/probe_native_process_boundary.py")
assert spec and spec.loader
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


@pytest.mark.parametrize("method", ["turn/start", "turn/steer", "thread/realtime/start",
                                     "account/login/start", "process/spawn", "thread/shellCommand",
                                     "command/exec", "mcpServer/oauth/login"])
def test_process_probe_refuses_effectful_rpc_before_starting_native(method):
    client = probe.NoModelClient(["must-not-launch"])
    with pytest.raises(ValueError, match="refuses"):
        client.request(method, {})
    assert client.process is None and client.methods == []


def test_process_probe_refuses_nonhandshake_notifications_and_native_requests():
    client = probe.NoModelClient(["must-not-launch"])
    with pytest.raises(ValueError):
        client.notify("turn/start", {})
    with pytest.raises(ValueError):
        client.respond(1, {})
    assert client.process is None


@pytest.fixture(scope="module")
def observed():
    if os.environ.get("NEMA_NATIVE_PROCESS_PROBE") != "1":
        pytest.skip("set NEMA_NATIVE_PROCESS_PROBE=1 for disposable no-model Linux/aarch64 startup")
    return probe.run_probe()


def test_filtered_runtime_can_create_and_join_a_thread(observed):
    case = observed["challenges"]["pthread"]
    assert case["exitCode"] == 0
    assert case["result"]["result"] == 42
    assert not case["unexpectedExecutableRan"]


def test_initial_exec_inherits_neither_listener_nor_bootstrap_socket(observed):
    case = observed["challenges"]["fd-audit"]
    assert case["exitCode"] == 0
    assert case["result"] == {"case": "fd-audit", "openAboveStdio": 0,
                               "seccompListenerVisible": False, "socketVisible": False}


@pytest.mark.parametrize("name", [case for case in probe.CHALLENGES if case not in {"pthread", "fd-audit"}])
def test_kernel_refuses_process_exec_and_filter_replacement_variants(observed, name):
    case = observed["challenges"][name]
    assert case["exitCode"] == 0, case
    expected = 38 if name in {"clone3-process", "clone3-thread", "execve", "execveat", "execveat-path", "pthread-exec"} else 1
    assert case["result"] == {"case": name, "result": -1, "errno": expected}
    assert not case["unexpectedExecutableRan"]
    assert case["policy"] == {
        "recordKind": "trusted-launcher-self-report", "installedBeforeInitialExec": True,
        "initialExecContinued": 1, "allListenerCopiesClosed": True}


@pytest.mark.parametrize("name", ["execve", "execveat", "execveat-path"])
def test_same_exec_target_really_runs_when_filter_is_absent(observed, name):
    case = observed["challenges"]["unfiltered-" + name]
    assert case["exitCode"] == 77
    assert case["unexpectedExecutableRan"]
    assert case["policy"] is None


def test_native_startup_works_but_unexpected_executable_mcp_cannot_reach_open_permit(observed):
    case = observed["nativeCases"]["filtered"]
    assert case["failure"] is None, case
    assert case["nativeReplies"]["threadStarted"]
    assert case["nativeReplies"]["account/read"] == {"account": None, "requiresOpenaiAuth": True}
    assert case["nativeReplies"]["configuredMcp"]["unexpected"]["enabled"]
    status = case["nativeReplies"]["mcpServerStatus/list"]["data"][0]
    assert status["name"] == "unexpected" and status["runtimeStatus"] == "failed"
    assert "Operation not permitted" in status["toolsError"]
    assert case["policy"]["installedBeforeInitialExec"]
    assert not case["mcpRanBeforeInventory"]
    assert case["mcpStartup"] is case["mcpSyntheticEgress"] is None
    assert case["brokerRequests"] == 0 and not case["syntheticPermitConsumed"]


def test_unfiltered_mcp_control_consumes_the_same_public_permit_before_inventory(observed):
    case = observed["nativeCases"]["unfilteredControl"]
    assert case["failure"] is None, case
    assert case["mcpRanBeforeInventory"] and case["syntheticPermitConsumed"]
    assert sum(e["status"] == 200 for e in case["brokerEvents"]) == 1
    assert case["mcpStartup"]["packetRead"]
    assert case["mcpStartup"]["effectiveCapabilities"] == "0000000000000000"
    for name in ("outsideRead", "outsideWrite", "symlinkRead", "packetWrite",
                 "hostLoopback", "externalRoute", "parentRootRead"):
        assert "blockedErrno" in case["mcpStartup"][name]
    assert case["mcpStartup"]["nestedUserNamespaceRefused"]
    assert case["mcpStartup"]["packetRemountRefused"]


def test_native_http_mcp_bypasses_process_denial_but_synthetic_broker_refuses_it(observed):
    case = observed["nativeCases"]["filteredHttpScopeControl"]
    assert case["failure"] is None, case
    assert case["policy"]["installedBeforeInitialExec"]
    statuses = {item["name"]: item for item in case["nativeReplies"]["mcpServerStatus/list"]["data"]}
    assert "Operation not permitted" in statuses["unexpected"]["toolsError"]
    assert "HTTP 422" in statuses["http_inprocess"]["toolsError"]
    assert any(e["status"] == 422 for e in case["brokerEvents"])
    assert any(e.get("target", "").startswith("/.well-known/") for e in case["brokerEvents"])
    assert all(e["status"] in {403, 422} for e in case["brokerEvents"])
    assert not case["syntheticPermitConsumed"]
    assert case["mcpStartup"] is None


def test_every_native_case_stays_disconnected_and_makes_no_model_rpc(observed):
    for case in observed["nativeCases"].values():
        assert case["hostCanaryUnchanged"] and case["packetUnchanged"]
        assert case["hostListenerUntouched"] and case["descendantHeartbeatStoppedAfterClose"]
        assert set(case["nativeMethodsObserved"]) == probe.ALLOWED_METHODS
        assert case["brokerRequests"] <= probe.gateway.MAX_REQUESTS
    assert observed["modelTurns"] == observed["realUpstreamRequests"] == 0
    assert not observed["existingCredentialsMounted"]
    assert not observed["liveAdmission"] and not observed["callerAuthenticationEstablished"]
