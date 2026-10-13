"""Safety guards run offline; installed-native interaction inspection opts in."""
import importlib.util
import os
from pathlib import Path

import pytest


SPEC = importlib.util.spec_from_file_location(
    "probe_native_interactions", Path(__file__).parents[1] / "scripts" / "probe_native_interactions.py")
assert SPEC and SPEC.loader
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)


@pytest.mark.parametrize("method", [
    "turn/start", "turn/steer", "item/tool/call", "item/tool/requestUserInput",
    "thread/resume", "thread/realtime/start", "command/exec", "process/spawn",
])
def test_interaction_probe_denies_model_and_execution_before_launch(method):
    client = probe.ProbeClient(["must-not-launch"])
    with pytest.raises(ValueError, match="not a no-model interaction probe method"):
        client.request(method, {})
    assert client.process is None
    assert client.methods == []


def test_interaction_probe_cannot_send_notifications_or_answer_requests():
    client = probe.ProbeClient(["must-not-launch"])
    with pytest.raises(ValueError, match="not an interaction probe notification"):
        client.notify("turn/start", {})
    with pytest.raises(ValueError, match="cannot answer native requests"):
        client.respond(17, {"answers": {}})
    assert client.process is None


def assert_observations(report):
    assert report["modelTurns"] == 0
    assert report["liveInteractionGate"] == "UNVERIFIED"
    assert set(report["rpcMethods"]) <= probe.ALLOWED_METHODS
    registration = report["dynamicToolRegistration"]
    for label in ("canonicalFunction", "legacyMissingType", "nonObjectInputSchema", "canonicalNamespace"):
        accepted = registration[label]["result"]
        assert accepted["sandbox"] == {"type": "readOnly", "networkAccess": False}
        assert accepted["approvalPolicy"] == "never"
        assert accepted["thread"]["environments"] == []
        assert accepted["runtimeWorkspaceRoots"] == []
    assert registration["duplicateName"]["error"]["code"] == -32600
    assert registration["invalidName"]["error"]["code"] == -32600
    controls = report["emptyThreadControls"]
    assert controls["increment"]["result"] == {"count": 1, "paused": True}
    assert controls["readWhileIncremented"]["result"]["thread"]["status"]["type"] == "idle"
    assert controls["decrement"]["result"] == {"count": 0, "paused": False}
    assert controls["interruptAbsentTurn"]["error"]["code"] == -32600
    # A client-incremented counter is not evidence of a server-originated
    # request: no observed event has both RPC identity and request method.
    assert not any("id" in event and "method" in event
                   for event in report["eventsBeforeCounter"] + report["eventsAfterCounter"])
    assert "isBlocking" in report["schema"]["ToolRequestUserInputParams"]["required"]
    assert set(report["schema"]["v2/ServerRequestResolvedNotification"]["required"]) == {
        "requestId", "threadId"}


@pytest.mark.skipif(os.environ.get("NEMA_NATIVE_PROBE") != "1",
                    reason="explicit opt-in for disposable no-model interaction inspection")
def test_installed_native_interaction_registration_and_empty_thread_controls():
    report = probe.run_probe(os.environ.get("NEMA_CODEX_BINARY", "codex"))
    assert_observations(report)
    # Optional capture avoids rerunning native merely to retain exact evidence.
    output = os.environ.get("NEMA_INTERACTIONS_PROBE_OUTPUT")
    if output:
        import json
        Path(output).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
