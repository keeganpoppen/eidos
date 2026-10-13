"""Pre-launch local admission, not a claim of account-backed isolation."""
from __future__ import annotations

import hashlib
import importlib.util
import os
from pathlib import Path
import sys

import pytest

from eidos.codex import AppServerClient, NativeExecutionProfile, NativeExecutionProfileError

SPEC = importlib.util.spec_from_file_location(
    "probe_native_profile", Path(__file__).parents[1] / "scripts/probe_native_profile.py")
assert SPEC and SPEC.loader
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)


@pytest.fixture
def profile_fixture(tmp_path):
    root = tmp_path / "case"
    root.mkdir()
    for name in ("home", "codex", "system", "workspace"):
        (root / name).mkdir()
    binary = root / "codex-fixture"
    binary.write_text("synthetic executable; never run")
    binary.chmod(0o700)
    env = {"HOME": str(root / "home"), "CODEX_HOME": str(root / "codex"),
           "PATH": "/usr/bin:/bin", "OPENAI_API_KEY": "synthetic-never-forward",
           "CODEX_SQLITE_HOME": "/should/not/inherit", "LD_PRELOAD": "/should/not/inherit"}
    profile = NativeExecutionProfile(str(binary), env=env, system_root=root / "system",
                                    expected_binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest())
    return root, profile


def test_profile_disables_every_inherited_local_mcp_before_launch(profile_fixture):
    root, profile = profile_fixture
    (root / "codex/config.toml").write_text('[mcp_servers.user]\ncommand="synthetic"\n')
    (root / "system/config.toml").write_text('[mcp_servers.system]\ncommand="synthetic"\n')
    ancestor = root / ".codex"
    ancestor.mkdir()
    (ancestor / "config.toml").write_text('[mcp_servers.ancestor]\ncommand="synthetic"\n')
    launch = profile.prepare(root / "workspace")
    for name in ("user", "system", "ancestor"):
        assert f"mcp_servers.{name}.enabled=false" in launch.command
    assert "mcp_servers={}" not in launch.command
    assert launch.evidence["disabledMcpCount"] == 3
    assert launch.env == {"HOME": str(root / "home"), "CODEX_HOME": str(root / "codex"),
                          "PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"}
    assert 'model_provider="openai"' in launch.command
    assert 'forced_login_method="chatgpt"' in launch.command
    assert "features.hooks=false" in launch.command
    assert "features.plugins=false" in launch.command


@pytest.mark.parametrize("change", ["existing", "absent", "ancestor", "binary"])
def test_profile_rejects_changed_configuration_before_popen(profile_fixture, monkeypatch, change):
    root, profile = profile_fixture
    config = root / "codex/config.toml"
    config.write_text('model="synthetic"\n')
    launch = profile.prepare(root / "workspace")
    if change == "existing":
        config.write_text('model="changed"\n')
    elif change == "absent":
        (root / "system/config.toml").write_text('[mcp_servers.added]\ncommand="synthetic"\n')
    elif change == "ancestor":
        (root / ".codex").mkdir()
        (root / ".codex/config.toml").write_text('[mcp_servers.added]\ncommand="synthetic"\n')
    else:
        (root / "codex-fixture").write_text("changed")
    monkeypatch.setattr("eidos.codex.subprocess.Popen", lambda *a, **kw: pytest.fail("spawned before admission"))
    with pytest.raises(NativeExecutionProfileError, match="changed"):
        AppServerClient(launch.command, env=launch.env, inherit_env=False,
                        launch_guard=launch.check_unchanged).start()


@pytest.mark.parametrize("setting", [
    'model_provider="custom"', 'forced_login_method="api"',
    '[model_providers.openai]\nbase_url="https://unreviewed.invalid"',
    'notify=["synthetic-side-effect"]', 'chatgpt_base_url="https://unreviewed.invalid"',
    '[unreviewed]\nvalue=true',
    '[mcp_servers."has.dot"]\ncommand="synthetic"',
])
def test_unadmitted_configuration_is_refused(profile_fixture, setting):
    root, profile = profile_fixture
    (root / "codex/config.toml").write_text(setting)
    with pytest.raises(NativeExecutionProfileError):
        profile.prepare(root / "workspace")


@pytest.mark.parametrize("name", ["requirements.toml", "managed_config.toml", "cloud-config-bundle-cache.json"])
def test_managed_or_cloud_sources_require_separate_admission(profile_fixture, name):
    root, profile = profile_fixture
    (root / "codex" / name).write_text("synthetic")
    with pytest.raises(NativeExecutionProfileError, match="managed/cloud"):
        profile.prepare(root / "workspace")


def test_unknown_binary_and_symlink_sources_are_refused(profile_fixture):
    root, profile = profile_fixture
    original = profile.expected_binary_sha256
    profile.expected_binary_sha256 = "unreviewed"
    with pytest.raises(NativeExecutionProfileError, match="binary"):
        profile.prepare(root / "workspace")
    profile.expected_binary_sha256 = original
    config = root / "synthetic.toml"
    config.write_text("")
    (root / "codex/config.toml").symlink_to(config)
    with pytest.raises(NativeExecutionProfileError, match="symlink"):
        profile.prepare(root / "workspace")


def test_v1_cloud_gap_refuses_live_spawn_but_keeps_reviewable_profile(profile_fixture, monkeypatch):
    root, profile = profile_fixture
    # Credentials are deliberately malformed: prepare must never read them.
    auth = root / "codex/auth.json"
    auth.write_bytes(b"synthetic-not-json-secret")
    auth.chmod(0)
    try:
        launch = profile.prepare(root / "workspace")
        assert launch.live_admitted is False
        assert launch.evidence["liveAdmitted"] is False
        assert launch.evidence["completeIsolation"] is False
        assert "auth.json" not in str(launch.evidence)
        monkeypatch.setattr("eidos.codex.subprocess.Popen", lambda *a, **kw: pytest.fail("live spawn"))
        with pytest.raises(NativeExecutionProfileError, match="cloud configuration"):
            AppServerClient(launch.command, env=launch.env, inherit_env=False,
                            launch_guard=launch.require_live_admission).start()
    finally:
        auth.chmod(0o600)


@pytest.mark.parametrize("account", [None, {"type": "apiKey"}, {"type": "amazonBedrock"}, {"type": "future"}])
def test_subscription_check_refuses_alternate_or_unknown_auth(account):
    with pytest.raises(NativeExecutionProfileError, match="ChatGPT"):
        NativeExecutionProfile.check_account({"account": account, "requiresOpenaiAuth": True})


def test_subscription_check_requires_native_acknowledgement():
    NativeExecutionProfile.check_account({"account": {"type": "chatgpt"}, "requiresOpenaiAuth": True})
    with pytest.raises(NativeExecutionProfileError):
        NativeExecutionProfile.check_account({"account": {"type": "chatgpt"}})


def test_exact_child_environment_does_not_merge_parent(monkeypatch):
    monkeypatch.setenv("NEMA_SYNTHETIC_ENVIRONMENT_SECRET", "must-not-inherit")
    program = ('import json,os,sys; '
               'r=json.loads(sys.stdin.readline()); '
               'print(json.dumps({"id":r["id"],"result":{"leaked":'
               '"NEMA_SYNTHETIC_ENVIRONMENT_SECRET" in os.environ}}),flush=True)')
    with AppServerClient((sys.executable, "-c", program), env={"PATH": "/usr/bin:/bin"}, inherit_env=False) as client:
        assert client.request("synthetic") == {"leaked": False}


@pytest.mark.skipif(os.environ.get("NEMA_NATIVE_PROBE") != "1", reason="explicit no-model native opt-in")
def test_native_mcp_profile_probe():
    report = probe.run_probe()
    assert report["modelTurns"] == 0
    cases = report["cases"]
    assert cases["inherited"]["startupMarkers"]
    assert cases["emptyMap"]["startupMarkers"]
    assert cases["inherited"]["generatedProfileCommandApplied"] is False
    assert cases["emptyMap"]["generatedProfileCommandApplied"] is False
    assert cases["profiled"]["generatedProfileCommandApplied"] is True
    assert cases["profiled"]["startupMarkers"] == []
    assert cases["profiled"]["inventory"]["data"][0]["runtimeStatus"] == "disabled"


@pytest.mark.parametrize("method", ["turn/start", "turn/steer", "command/exec", "thread/resume"])
def test_profile_probe_refuses_model_or_execution_methods(method):
    client = probe.NoModelClient(("must-not-launch",))
    with pytest.raises(ValueError, match="refuses"):
        client.request(method)
    assert client.process is None


def test_profile_probe_refuses_unapproved_notifications_and_responses():
    client = probe.NoModelClient(("must-not-launch",))
    with pytest.raises(ValueError, match="refuses"):
        client.notify("turn/start")
    with pytest.raises(ValueError, match="does not answer"):
        client.respond(1, {})
    assert client.process is None
