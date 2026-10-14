"""Managed preparation against authored values/processes; no real account/native."""
from copy import deepcopy
from dataclasses import replace
import hashlib
from importlib.resources import files
import json
import sys
import threading
import time
import tomllib

import pytest

from eidos.native_managed import (
    CATALOG_ORIGINAL_SHA256, CATALOG_PATCH_SHA256, CATALOG_SHA256, CHATGPT_BASE_URL, ManagedExecutionProfile,
    managed_catalog, managed_config, validate_managed_config, validate_managed_receipt,
)
from eidos.native_managed_contract import (
    DEVICE_VERIFICATION_URL, MANAGED_VERSION, ManagedAttemptIdentity, ManagedLaunchError, ManagedPolicy,
)
from eidos.trace import TraceStore


class AuthoredRuntime:
    instances = []

    def __init__(self, cwd, *, config_toml, catalog_bytes, policy, binary, cancelled=None):
        self.command, self.env = (sys.executable, "-c", "raise SystemExit(0)"), {}
        self.phase, self.transitions = "prepared", []
        self.prep_remaining, self.turn_remaining = policy.preparation_seconds, policy.turn_seconds
        self.cancelled, self.abort, self.policy = cancelled, None, policy
        self.close_report = {"allWorkersJoined": True, "errors": [], "closed": True}
        self.evidence = {"version": MANAGED_VERSION, "binarySha256": hashlib.sha256(b"authored-python-child").hexdigest(),
                         "transport": "authored-local", "classification": "synthetic",
                         "configSha256": hashlib.sha256(config_toml.encode()).hexdigest(),
                         "catalogSha256": hashlib.sha256(catalog_bytes).hexdigest(), "limits": policy.as_dict()}
        self.instances.append(self)

    def remaining_preparation(self):
        if self.phase == "closed" or (self.cancelled and self.cancelled.is_set()) or self.prep_remaining <= 0:
            raise ManagedLaunchError("authored preparation expired")
        return self.prep_remaining

    def remaining_turn(self):
        if self.phase != "provider-only" or (self.cancelled and self.cancelled.is_set()) or self.turn_remaining <= 0:
            raise ManagedLaunchError("authored turn expired")
        return self.turn_remaining

    def require_contained_startup(self):
        assert self.phase == "prepared"
        self.phase = "issuer-only"
        self.transitions.append("issuer-only")

    def activate_provider(self):
        assert self.phase == "issuer-only"
        self.remaining_preparation()
        self.transitions += ["issuer-closed", "provider-only"]
        self.phase = "provider-only"

    def bind_abort(self, callback): self.abort = callback

    def close(self, reason="closed", *, wait=True):
        prior, self.phase = self.phase, "closed"
        if prior != "closed":
            self.transitions.append("closed")
            if self.abort: self.abort()
        return deepcopy(self.close_report)


def identity(name="A", source=None):
    return ManagedAttemptIdentity.from_attempt({"id": "attempt-" + name, "contextId": "context-" + name},
        {"id": "context-" + name, "question": "Pinned " + name, "projectedPrompt": "exact prompt " + name}, source or "native-" + name)


def effective_config():
    return {**tomllib.loads(managed_config()), "chatgpt_base_url": CHATGPT_BASE_URL}


class AuthoredPreparation:
    def __init__(self, trace, source="native-A", *, plan="plus", changes=None, events=None, on_phase=None, gate=None):
        self.trace, self.source, self.plan = trace, source, plan
        self.changes, self.on_phase, self.gate = changes or {}, on_phase, gate
        self.requests, self.phases, self.counter = [], [], 1
        self.events = deepcopy(events if events is not None else [
            {"method": "account/login/completed", "params": {"loginId": "login-authored", "success": True,
                "error": None, "unknown": "PRIVATE_COMPLETION"}},
            {"method": "account/updated", "params": {"authMode": "chatgpt", "planType": plan, "unknown": "PRIVATE_UPDATE"}}])
        self.record("client_to_appserver", {"id": 1, "method": "initialize", "params": {}})
        self.record("appserver_to_client", {"id": 1, "result": {"future": "PRIVATE_INIT"}})

    def record(self, direction, msg):
        return self.trace.append_line(source=self.source, direction=direction,
            raw_text=json.dumps(msg, separators=(",", ":")) + "\n")

    def remaining(self): return 180

    def phase(self, phase):
        self.phases.append(phase)
        if self.on_phase: self.on_phase(phase)

    def request(self, method, params):
        names = ["initialAccount", "initialConfig", "loginStart", "orderedAccount", "orderedConfig"]
        name = names[len(self.requests)]
        self.requests.append((method, deepcopy(params)))
        self.counter += 1
        self.record("client_to_appserver", {"id": self.counter, "method": method, "params": params})
        responses = {
            "initialAccount": {"account": None, "requiresOpenaiAuth": True, "unknown": "PRIVATE_EMPTY"},
            "initialConfig": {"config": effective_config(), "unknown": "PRIVATE_CONFIG_0"},
            "loginStart": {"type": "chatgptDeviceCode", "loginId": "login-authored",
                "verificationUrl": DEVICE_VERIFICATION_URL, "userCode": "ABCD-EFGH", "unknown": "PRIVATE_CODE"},
            "orderedAccount": {"account": {"type": "chatgpt", "planType": self.plan,
                "email": "authored@example.invalid", "unknown": "PRIVATE_ACCOUNT"}, "requiresOpenaiAuth": True},
            "orderedConfig": {"config": effective_config(), "unknown": "PRIVATE_CONFIG_1"},
        }
        reply = deepcopy(responses[name])
        if name in self.changes:
            change = self.changes[name]
            reply = change(reply) if callable(change) else deepcopy(change)
        self.record("appserver_to_client", {"id": self.counter, "result": reply})
        return reply

    def recv_event(self, timeout=None):
        if self.gate:
            entered, release = self.gate
            entered.set()
            if not release.wait(2): raise TimeoutError("authored event not released")
        event = self.events.pop(0)
        self.record("appserver_to_client", event)
        return deepcopy(event)


@pytest.fixture
def trace():
    store = TraceStore(":memory:", role="private-control")
    yield store
    store.close()


@pytest.fixture
def profile():
    return ManagedExecutionProfile(runtime_factory=AuthoredRuntime)


def launch_ready(profile, tmp_path, trace, *, selected=None, **kwargs):
    selected = selected or identity()
    launch = profile.prepare(tmp_path, identity=selected)
    launch.require_contained_startup()
    session = AuthoredPreparation(trace, selected.source, **kwargs)
    launch.prepare_native(session)
    return launch, session, AuthoredRuntime.instances[-1]


def test_exact_catalog_packaging_preserves_all_unpatched_fields_and_license():
    root = files("eidos").joinpath("resources")
    original = root.joinpath("native_models_original.json").read_bytes()
    patch = root.joinpath("native_models_patch.json").read_bytes()
    assert hashlib.sha256(original).hexdigest() == CATALOG_ORIGINAL_SHA256
    assert hashlib.sha256(patch).hexdigest() == CATALOG_PATCH_SHA256
    derived = managed_catalog()
    assert hashlib.sha256(derived).hexdigest() == CATALOG_SHA256
    expected = json.loads(original)
    expected["models"][0]["tool_mode"] = "direct"
    expected["models"][0]["experimental_supported_tools"] = []
    assert json.loads(derived) == expected
    assert b"Apache License" in root.joinpath("native_models_LICENSE.txt").read_bytes()
    assert json.loads(root.joinpath("native_models_provenance.json").read_bytes())["derivedSha256"] == CATALOG_SHA256


@pytest.mark.parametrize("resource", ["native_models_original.json", "native_models_patch.json"])
def test_changed_packaged_resource_prevents_runtime_construction(monkeypatch, tmp_path, resource):
    import eidos.native_managed as module
    original = module._resource
    monkeypatch.setattr(module, "_resource", lambda name, limit: b"{}" if name == resource else original(name, limit))
    profile = ManagedExecutionProfile(runtime_factory=lambda *a, **k: pytest.fail("allocated before resource check"))
    with pytest.raises(ManagedLaunchError): profile.prepare(tmp_path, identity=identity())


@pytest.mark.parametrize("plan", ["plus", "pro"])
def test_exact_single_consumption_correlated_private_receipt(profile, tmp_path, trace, plan):
    launch, session, runtime = launch_ready(profile, tmp_path, trace, plan=plan)
    assert session.phases == ["awaiting-sign-in", "checking"]
    assert runtime.transitions == ["issuer-only", "issuer-closed", "provider-only"]
    assert launch.read_challenge(identity()) is None
    manifest = launch.evidence
    receipt = launch.consume_turn_admission(identity())
    assert receipt["manifest"] == manifest and receipt["planType"] == plan
    assert validate_managed_receipt(receipt, identity(), trace.records(), before_seq=100) == "synthetic"
    assert "PRIVATE_" not in json.dumps(receipt) and "authored@example.invalid" not in json.dumps(receipt)
    assert "PRIVATE_ACCOUNT" in "".join(r.raw_text for r in trace.records())
    with pytest.raises(ManagedLaunchError): launch.consume_turn_admission(identity())
    assert runtime.phase == "closed"


def test_readiness_A_cannot_authorize_B_or_fresh_factory_launch(profile, tmp_path, trace):
    a, _, _ = launch_ready(profile, tmp_path, trace)
    receipt = a.consume_turn_admission(identity())
    a.close()
    b = profile.prepare(tmp_path, identity=identity("B"))
    assert b.read_challenge(identity()) is None and b.read_challenge(identity("B")) is None
    with pytest.raises(ManagedLaunchError): b.consume_turn_admission(identity("B"))
    with pytest.raises(ManagedLaunchError): validate_managed_receipt(receipt, identity("B"), trace.records(), before_seq=100)
    assert b.evidence["executionEvidence"] == "synthetic"


@pytest.mark.parametrize("field", ["attempt_id", "context_id", "context_sha256", "projected_prompt_sha256", "source"])
def test_every_identity_coordinate_is_checked_before_admission(profile, tmp_path, trace, field):
    launch, _, _ = launch_ready(profile, tmp_path, trace)
    wrong = replace(identity(), **{field: "0" * 64 if field.endswith("sha256") else "wrong"})
    with pytest.raises(ManagedLaunchError): launch.consume_turn_admission(wrong)
    with pytest.raises(ManagedLaunchError): launch.consume_turn_admission(identity())


def test_wrong_preparation_source_sends_no_account_or_login(profile, tmp_path, trace):
    launch = profile.prepare(tmp_path, identity=identity())
    launch.require_contained_startup()
    session = AuthoredPreparation(trace, source="other")
    with pytest.raises(ManagedLaunchError): launch.prepare_native(session)
    assert session.requests == []


def test_challenge_exact_scope_copy_and_retirement(profile, tmp_path, trace):
    launch = profile.prepare(tmp_path, identity=identity())
    launch.require_contained_startup()
    seen = []
    def phase(name):
        challenge = launch.read_challenge(identity())
        seen.append((name, challenge))
        assert launch.read_challenge(identity("B")) is None
        if challenge:
            assert challenge["verificationUrl"] == DEVICE_VERIFICATION_URL
            assert time.time() * 1000 < challenge["expiresAtMs"] <= time.time() * 1000 + 180001
            challenge["userCode"] = "changed caller copy"
            assert launch.read_challenge(identity())["userCode"] == "ABCD-EFGH"
    launch.prepare_native(AuthoredPreparation(trace, on_phase=phase))
    assert seen[0][0] == "awaiting-sign-in" and seen[0][1] is not None
    assert seen[1] == ("checking", None)
    assert launch.read_challenge(identity()) is None


def test_pending_cancel_then_late_success_never_activates_provider(profile, tmp_path, trace):
    entered, release = threading.Event(), threading.Event()
    launch = profile.prepare(tmp_path, identity=identity())
    runtime = AuthoredRuntime.instances[-1]
    launch.require_contained_startup()
    errors = []
    def prepare():
        try: launch.prepare_native(AuthoredPreparation(trace, gate=(entered, release)))
        except Exception as exc: errors.append(exc)
    worker = threading.Thread(target=prepare)
    worker.start()
    try:
        assert entered.wait(1) and launch.read_challenge(identity()) is not None
        launch.close(reason="cancelled")
        assert launch.read_challenge(identity()) is None
    finally:
        release.set()
        worker.join(2)
    assert not worker.is_alive() and len(errors) == 1
    assert "provider-only" not in runtime.transitions
    with pytest.raises(ManagedLaunchError): launch.consume_turn_admission(identity())


def test_deadline_hides_challenge_and_blocks_late_login(profile, tmp_path, trace):
    launch = profile.prepare(tmp_path, identity=identity())
    runtime = AuthoredRuntime.instances[-1]
    launch.require_contained_startup()
    def phase(name):
        if name == "awaiting-sign-in":
            runtime.prep_remaining = 0
            assert launch.read_challenge(identity()) is None
    with pytest.raises(ManagedLaunchError): launch.prepare_native(AuthoredPreparation(trace, on_phase=phase))
    assert "provider-only" not in runtime.transitions


@pytest.mark.parametrize("name,change", [
    ("initialAccount", {"requiresOpenaiAuth": True}),
    ("initialAccount", {"account": {"type": "chatgpt"}, "requiresOpenaiAuth": True}),
    ("initialAccount", {"account": None, "requiresOpenaiAuth": False}),
    ("loginStart", lambda v: {**v, "verificationUrl": "https://auth.openai.com/codex/device?other"}),
    ("loginStart", lambda v: {**v, "userCode": "<" + "A" * 128}),
    ("loginStart", lambda v: {**v, "userCode": "\x00code"}),
    ("loginStart", lambda v: {**v, "userCode": " "}),
    ("loginStart", lambda v: {**v, "type": "apiKey"}),
    ("orderedAccount", {"account": {"type": "apiKey", "planType": "plus"}, "requiresOpenaiAuth": True}),
    ("orderedAccount", {"account": {"type": "chatgpt", "planType": "free"}, "requiresOpenaiAuth": True}),
    ("orderedAccount", {"account": {"type": "chatgpt", "planType": "pro"}, "requiresOpenaiAuth": True}),
])
def test_invalid_readiness_never_grants_thread_admission(profile, tmp_path, trace, name, change):
    launch = profile.prepare(tmp_path, identity=identity())
    runtime = AuthoredRuntime.instances[-1]
    launch.require_contained_startup()
    with pytest.raises(ManagedLaunchError): launch.prepare_native(AuthoredPreparation(trace, changes={name: change}))
    assert runtime.phase == "closed" and "provider-only" not in runtime.transitions
    assert launch.read_challenge(identity()) is None
    with pytest.raises(ManagedLaunchError): launch.consume_turn_admission(identity())


@pytest.mark.parametrize("stage", ["initialConfig", "orderedConfig"])
@pytest.mark.parametrize("mutation", ["missing-goals", "goals-true", "issuer-override", "model", "mcp", "analytics", "layers-error"])
def test_config_drift_at_each_stage_blocks_provider(profile, tmp_path, trace, stage, mutation):
    def change(reply):
        config = reply["config"]
        if mutation == "missing-goals": config["features"].pop("goals")
        elif mutation == "goals-true": config["features"]["goals"] = True
        elif mutation == "issuer-override": config["openai_base_url"] = "https://other.invalid"
        elif mutation == "model": config["model"] = "other"
        elif mutation == "mcp": config["mcp_servers"] = {"unexpected": {"enabled": True}}
        elif mutation == "analytics": config["analytics"]["enabled"] = True
        else: return {"error": {"message": "PRIVATE_ERROR"}}
        return reply
    launch = profile.prepare(tmp_path, identity=identity())
    launch.require_contained_startup()
    with pytest.raises(ManagedLaunchError): launch.prepare_native(AuthoredPreparation(trace, changes={stage: change}))
    assert "provider-only" not in AuthoredRuntime.instances[-1].transitions


@pytest.mark.parametrize("stage", ["initialConfig", "orderedConfig"])
@pytest.mark.parametrize("value", [
    "missing", None, "https://chatgpt.com/backend-api", "https://chatgpt.com:443/backend-api/",
    "https://chatgpt.com/backend-api/?x=1", "https://chatgpt.com/backend-api/#fragment",
    "https://CHATGPT.com/backend-api/", "http://chatgpt.com/backend-api/",
    "https://chatgpt.com.evil.invalid/backend-api/", "https://user@chatgpt.com/backend-api/",
    "https://chatgpt.com/backend-api/../other", " https://chatgpt.com/backend-api/",
])
def test_effective_chatgpt_url_requires_exact_native_default(profile, tmp_path, trace, stage, value):
    def change(reply):
        if value == "missing": reply["config"].pop("chatgpt_base_url")
        else: reply["config"]["chatgpt_base_url"] = value
        return reply
    launch = profile.prepare(tmp_path, identity=identity())
    launch.require_contained_startup()
    preparation = AuthoredPreparation(trace, changes={stage: change})
    with pytest.raises(ManagedLaunchError): launch.prepare_native(preparation)
    assert not any(phase == "provider-only" for phase in AuthoredRuntime.instances[-1].transitions)
    assert sum(method == "account/login/start" for method, _ in preparation.requests) == (stage == "orderedConfig")
    assert launch.read_challenge(identity()) is None


def test_canonical_effective_url_is_not_written_as_startup_override():
    assert "chatgpt_base_url" not in tomllib.loads(managed_config())
    reply = {"config": effective_config(), "unknown": {"preserved": True}}
    # The native API omits this requested tool control. Do not invent an
    # acknowledgement by copying the startup field into its effective reply.
    reply["config"]["tools"] = {"web_search": None}
    original = deepcopy(reply)
    validate_managed_config(reply)
    assert reply == original


@pytest.mark.parametrize("variant", ["wrong-id", "failed", "early-update", "duplicate-completion", "unknown", "enabled-remote"])
def test_mismatched_or_reordered_native_events_refuse(profile, tmp_path, trace, variant):
    session = AuthoredPreparation(trace)
    if variant == "wrong-id": session.events[0]["params"]["loginId"] = "copied"
    elif variant == "failed": session.events[0]["params"]["success"] = False
    elif variant == "early-update": session.events.reverse()
    elif variant == "duplicate-completion": session.events.insert(1, deepcopy(session.events[0]))
    elif variant == "unknown": session.events.insert(0, {"method": "thread/started"})
    else: session.events.insert(0, {"method": "remoteControl/status/changed", "params": {"status": "enabled"}})
    launch = profile.prepare(tmp_path, identity=identity())
    launch.require_contained_startup()
    with pytest.raises(ManagedLaunchError): launch.prepare_native(session)
    assert "provider-only" not in AuthoredRuntime.instances[-1].transitions


def test_cancelled_allocation_never_calls_runtime(tmp_path):
    cancelled = threading.Event(); cancelled.set()
    profile = ManagedExecutionProfile(runtime_factory=lambda *a, **k: pytest.fail("runtime created after cancellation"))
    with pytest.raises(ManagedLaunchError): profile.prepare(tmp_path, identity=identity(), cancelled=cancelled)


def test_cancel_during_allocation_is_forwarded_and_cleanup_prevents_late_start(tmp_path):
    cancelled = threading.Event()
    def allocate(*args, **kwargs):
        runtime = AuthoredRuntime(*args, **kwargs)
        assert kwargs["cancelled"] is cancelled
        cancelled.set()
        return runtime
    profile = ManagedExecutionProfile(runtime_factory=allocate)
    with pytest.raises(ManagedLaunchError): profile.prepare(tmp_path, identity=identity(), cancelled=cancelled)
    assert AuthoredRuntime.instances[-1].phase == "closed"


def test_authored_factory_cannot_claim_fixed_live_native_evidence(tmp_path):
    def allocate(*args, **kwargs):
        runtime = AuthoredRuntime(*args, **kwargs)
        runtime.evidence.update(transport="fixed-live-destinations", classification="native-observed")
        return runtime
    with pytest.raises(ManagedLaunchError): ManagedExecutionProfile(runtime_factory=allocate).prepare(tmp_path, identity=identity())
    assert AuthoredRuntime.instances[-1].phase == "closed"


def test_runtime_abort_and_incomplete_close_never_keep_readiness(profile, tmp_path, trace):
    launch = profile.prepare(tmp_path, identity=identity())
    runtime = AuthoredRuntime.instances[-1]
    aborted = []
    launch.bind_abort(lambda: aborted.append(True))
    launch.require_contained_startup()
    launch.prepare_native(AuthoredPreparation(trace))
    runtime.abort()
    assert aborted == [True]
    runtime.close_report = {"allWorkersJoined": False, "errors": ["authored close failure"]}
    with pytest.raises(ManagedLaunchError): launch.close()
    assert launch.read_challenge(identity()) is None
    with pytest.raises(ManagedLaunchError): launch.consume_turn_admission(identity())


def test_manifest_and_environment_are_defensive_snapshots(profile, tmp_path, trace):
    launch, _, runtime = launch_ready(profile, tmp_path, trace)
    expected = launch.evidence
    exposed = launch.evidence
    exposed["runtime"]["transport"] = "forged"
    runtime.evidence["transport"] = "changed"
    runtime.env["AUTH_CANARY"] = "ignored"
    assert launch.evidence == expected and dict(launch.env) == {}
    with pytest.raises(TypeError): launch.env["AUTH_CANARY"] = "blocked"
    assert launch.consume_turn_admission(identity())["manifest"] == expected


@pytest.mark.parametrize("mutation", ["request-id", "response-id", "refresh", "missing-result", "unknown-result-field",
    "early-updated", "duplicate-result", "copied-source", "completion-native-direction", "capture-gap", "cutoff",
    "receipt-hash", "receipt-identity", "receipt-classification", "receipt-policy"])
def test_receipt_recovery_rejects_correlated_evidence_counterexamples(profile, tmp_path, trace, mutation):
    launch, _, _ = launch_ready(profile, tmp_path, trace)
    receipt = launch.consume_turn_admission(identity())
    rows, before = list(trace.records()), 100
    def rewrite(index, fn):
        message = rows[index].message
        fn(message)
        rows[index] = replace(rows[index], raw_text=json.dumps(message))
    if mutation == "request-id": rewrite(2, lambda m: m.update(id=99))
    elif mutation == "response-id": rewrite(3, lambda m: m.update(id=99))
    elif mutation == "refresh": rewrite(2, lambda m: m["params"].update(refreshToken=True))
    elif mutation == "missing-result": rows.pop(3)
    elif mutation == "unknown-result-field": rewrite(3, lambda m: m["result"].update(unknown="changed bytes"))
    elif mutation == "early-updated":
        index = next(i for i,r in enumerate(rows) if r.method == "account/updated")
        rows[index] = replace(rows[index], seq=rows[index-1].seq-1)
    elif mutation == "duplicate-result": rows.insert(4, rows[3])
    elif mutation == "copied-source": rows = [replace(r, source="different-incarnation") for r in rows]
    elif mutation == "completion-native-direction":
        rows = [replace(r, direction="internal") if r.method == "account/login/completed" else r for r in rows]
    elif mutation == "capture-gap":
        rows.append(trace.append(source=identity().source, direction="internal", message={"method":"$transport/captureGap"}))
    elif mutation == "cutoff": before = rows[-1].seq
    elif mutation == "receipt-hash": receipt["readiness"]["initialAccount"] = "0" * 64
    elif mutation == "receipt-identity": receipt["identity"]["source"] = "other"
    elif mutation == "receipt-classification": receipt["manifest"]["executionEvidence"] = "native-observed"
    else: receipt["manifest"]["policy"]["preparation_seconds"] = float("inf")
    with pytest.raises(ManagedLaunchError): validate_managed_receipt(receipt, identity(), rows, before_seq=before)


def test_preparation_event_bound_closes_without_readiness(profile, tmp_path, trace):
    launch = profile.prepare(tmp_path, identity=identity())
    launch.require_contained_startup()
    events = [{"method": "warning", "params": {"message": "authored pending notice"}} for _ in range(128)]
    session = AuthoredPreparation(trace, events=events)
    with pytest.raises(ManagedLaunchError): launch.prepare_native(session)
    assert len(session.requests) == 3 and launch.read_challenge(identity()) is None
    assert "provider-only" not in AuthoredRuntime.instances[-1].transitions


def test_late_provider_activation_cannot_restore_cancelled_receipt(profile, tmp_path, trace):
    launch = profile.prepare(tmp_path, identity=identity())
    runtime = AuthoredRuntime.instances[-1]
    entered, release = threading.Event(), threading.Event()
    original = runtime.activate_provider
    def activate():
        entered.set()
        assert release.wait(2)
        original()  # The runtime also refuses its closed phase.
    runtime.activate_provider = activate
    launch.require_contained_startup()
    errors = []
    def prepare():
        try: launch.prepare_native(AuthoredPreparation(trace))
        except Exception as exc: errors.append(exc)
    worker = threading.Thread(target=prepare)
    worker.start()
    try:
        assert entered.wait(1)
        launch.close(reason="cancelled")
    finally:
        release.set(); worker.join(2)
    assert not worker.is_alive() and len(errors) == 1
    assert "provider-only" not in runtime.transitions
    with pytest.raises(ManagedLaunchError): launch.consume_turn_admission(identity())


def test_concurrent_consumers_receive_one_receipt(profile, tmp_path, trace):
    launch, _, _ = launch_ready(profile, tmp_path, trace)
    barrier = threading.Barrier(3)
    receipts, errors = [], []
    def consume():
        barrier.wait()
        try: receipts.append(launch.consume_turn_admission(identity()))
        except ManagedLaunchError as exc: errors.append(exc)
    threads = [threading.Thread(target=consume) for _ in range(2)]
    for thread in threads: thread.start()
    barrier.wait()
    for thread in threads: thread.join(1)
    assert all(not thread.is_alive() for thread in threads)
    assert len(receipts) == len(errors) == 1


def test_incomplete_shutdown_retains_diagnostic_but_no_challenge(profile, tmp_path):
    launch = profile.prepare(tmp_path, identity=identity())
    runtime = AuthoredRuntime.instances[-1]
    runtime.close_report = {"allWorkersJoined": False, "errors": ["PRIVATE_CLOSE_FAILURE"], "stateRemoved": False}
    with pytest.raises(ManagedLaunchError) as caught: launch.close()
    assert "PRIVATE_CLOSE" not in str(caught.value)
    assert caught.value.diagnostic == runtime.close_report
    assert launch.read_challenge(identity()) is None
    with pytest.raises(ManagedLaunchError): launch.require_contained_startup()


@pytest.mark.parametrize("unwind_close_raises", [False, True])
def test_startup_unwind_does_not_wait_or_hide_original_failure(profile, tmp_path, unwind_close_raises):
    launch = profile.prepare(tmp_path, identity=identity())
    runtime = AuthoredRuntime.instances[-1]
    original = OSError("authored startup failure")
    calls = []
    def fail_startup():
        raise original
    def incomplete_close(reason="closed", *, wait=True):
        calls.append((reason, wait))
        if not wait and unwind_close_raises:
            raise OSError("authored cleanup failure")
        return {"allWorkersJoined": False, "errors": ["cleanup-in-progress"]}
    runtime.require_contained_startup = fail_startup
    runtime.close = incomplete_close
    with pytest.raises(OSError) as caught:
        launch.require_contained_startup()
    assert caught.value is original
    assert calls == [("startup-refused", False)]
    assert launch.read_challenge(identity()) is None
    with pytest.raises(ManagedLaunchError): launch.consume_turn_admission(identity())
    with pytest.raises(ManagedLaunchError) as closing:
        launch.close()
    assert calls[-1] == ("closed", True)
    assert closing.value.diagnostic == {"allWorkersJoined": False, "errors": ["cleanup-in-progress"]}
