from __future__ import annotations

"""One owned native preparation and its historical receipt, never a login cache.

The runtime factory seam is for authored local tests only. Trusted Python callers
are not a security boundary; ordinary HTTP callers cannot choose this machinery.
"""

from copy import deepcopy
import hashlib
from importlib.resources import files
import json
import math
from pathlib import Path
import re
import threading
import time
from types import MappingProxyType
from typing import Any, Callable, Mapping, Sequence

from .native_managed_contract import (
    DEVICE_VERIFICATION_URL, ISSUER_AUTHORITY, MANAGED_BINARY_SHA256, MANAGED_VERSION,
    PROVIDER_AUTHORITY, ManagedAttemptIdentity, ManagedLaunchError, ManagedPolicy, canonical_sha256,
)
from .codex import AppServerLimits
from .trace import TraceRecord

MODEL = "gpt-6-astra"
CATALOG_PATH = "/assets/models.json"
# Native 0.154.0 core/config/mod.rs materializes this exact effective default.
# Keep startup free of overrides and require the acknowledged canonical value.
CHATGPT_BASE_URL = "https://chatgpt.com/backend-api/"
CATALOG_ORIGINAL_SHA256 = "f3b8104396daf6381bed9d7c4b154a8664f9b5089b44b01a9d54f421566ec9a7"
CATALOG_PATCH_SHA256 = "320905a79b3d4f34f7dbba953e8fbe0c673fd1a984081c0fd8eeb65ff5d96f5c"
CATALOG_SHA256 = "6571b50e45135f71d0200cb029fb37ffd67d7e829f5b1e3d3a1450c8183dceda"
MAX_PREPARATION_EVENTS = 128
DISABLED_FEATURES = (
    "apps", "plugins", "remote_plugin", "remote_control", "hooks", "shell_tool", "shell_snapshot",
    "multi_agent", "multi_agent_v2", "memories", "goals", "browser_use", "browser_use_external",
    "computer_use", "in_app_browser", "in_app_local_automation", "code_mode", "code_mode_host",
    "code_mode_prewarm", "skill_mcp_dependency_install", "skill_search", "workspace_dependencies",
    "image_generation", "sleep_tool", "current_time_reminder", "use_agent_identity", "enable_request_compression",
)
READINESS_KEYS = ("initialAccount", "initialConfig", "loginStart", "loginCompleted", "accountUpdated",
                  "orderedAccount", "orderedConfig")


def _error() -> ManagedLaunchError:
    return ManagedLaunchError("Managed native preparation is unavailable for this attempt.")


def managed_config() -> str:
    """Fixed owned startup; no ambient credentials, URL hooks or user config."""
    return (
        f'model="{MODEL}"\nmodel_provider="openai"\nmodel_catalog_json="{CATALOG_PATH}"\n'
        'approval_policy="never"\nsandbox_mode="read-only"\nweb_search="disabled"\n'
        'cli_auth_credentials_store="ephemeral"\nforced_login_method="chatgpt"\n'
        '[features]\n' + ''.join(f'{key}=false\n' for key in DISABLED_FEATURES) +
        'skip_host_skill_discovery=true\n[agents]\nenabled=false\n[mcp_servers]\n'
        '[skills]\ninclude_instructions=false\n[skills.bundled]\nenabled=false\n'
        '[orchestrator.skills]\nenabled=false\n[orchestrator.mcp]\nenabled=false\n'
        '[tools.experimental_request_user_input]\nenabled=false\n'
        '[otel]\nexporter="none"\ntrace_exporter="none"\nmetrics_exporter="none"\n'
        '[analytics]\nenabled=false\n'
    )


def _resource(name: str, limit: int) -> bytes:
    try:
        with files("eidos").joinpath("resources", name).open("rb") as stream:
            data = stream.read(limit + 1)
        if len(data) > limit:
            raise _error()
        return data
    except (OSError, ValueError) as exc:
        raise _error() from exc


def managed_catalog() -> bytes:
    """Apply only the packaged reviewed patch to exact public upstream bytes."""
    original = _resource("native_models_original.json", 600000)
    patch = _resource("native_models_patch.json", 4096)
    if (hashlib.sha256(original).hexdigest() != CATALOG_ORIGINAL_SHA256
            or hashlib.sha256(patch).hexdigest() != CATALOG_PATCH_SHA256):
        raise _error()
    value = json.loads(original)
    for operation in json.loads(patch):
        parent = value["models"][0]
        key = operation["path"].removeprefix("/models/0/")
        if operation["op"] == "test":
            if canonical_sha256(parent[key]) != canonical_sha256(operation["value"]):
                raise _error()
        elif operation["op"] == "replace":
            parent[key] = operation["value"]
        else:
            raise _error()
    derived = (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode()
    if hashlib.sha256(derived).hexdigest() != CATALOG_SHA256:
        raise _error()
    return derived


def validate_managed_config(reply: Any) -> None:
    """Check admitted controls, preserving all other raw fields in the recorder.

    This is not an assertion that every native/cloud default or hidden provider
    instruction is represented by these selected checks.
    """
    if not isinstance(reply, dict) or not isinstance(reply.get("config"), dict):
        raise _error()
    config = reply["config"]
    expected = {"model": MODEL, "model_provider": "openai", "model_catalog_json": CATALOG_PATH,
                "approval_policy": "never", "sandbox_mode": "read-only", "web_search": "disabled",
                "cli_auth_credentials_store": "ephemeral", "forced_login_method": "chatgpt",
                "chatgpt_base_url": CHATGPT_BASE_URL}
    if any(config.get(key) != value for key, value in expected.items()):
        raise _error()
    features = config.get("features")
    if (not isinstance(features, dict) or any(features.get(key) is not False for key in DISABLED_FEATURES)
            or features.get("skip_host_skill_discovery") is not True):
        raise _error()
    for section in ("agents", "analytics"):
        if not isinstance(config.get(section), dict) or config[section].get("enabled") is not False:
            raise _error()
    otel = config.get("otel")
    if not isinstance(otel, dict) or any(otel.get(key) != "none" for key in ("exporter", "trace_exporter", "metrics_exporter")):
        raise _error()
    if config.get("mcp_servers") != {}:
        raise _error()
    for path in (("skills", "include_instructions"), ("skills", "bundled", "enabled"),
                 ("orchestrator", "skills", "enabled"), ("orchestrator", "mcp", "enabled")):
        current = config
        for key in path:
            if not isinstance(current, dict) or key not in current:
                raise _error()
            current = current[key]
        if current is not False:
            raise _error()
    # These overrides are absent in the fixed startup configuration. A native
    # effective reply must not select a different provider/issuer or add hooks.
    for key in ("openai_base_url", "hooks", "instructions", "developer_instructions",
                "model_instructions_file", "experimental_compact_prompt_file"):
        if config.get(key) is not None:
            raise _error()


def _account_plan(reply: Any) -> str:
    if not isinstance(reply, dict) or reply.get("requiresOpenaiAuth") is not True:
        raise _error()
    account = reply.get("account")
    if (not isinstance(account, dict) or account.get("type") != "chatgpt"
            or account.get("planType") not in {"plus", "pro"}):
        raise _error()
    return account["planType"]


def _login_reply(reply: Any) -> str:
    if not isinstance(reply, dict) or reply.get("type") != "chatgptDeviceCode":
        raise _error()
    login_id, code = reply.get("loginId"), reply.get("userCode")
    if (not isinstance(login_id, str) or not 0 < len(login_id) <= 512 or any(ord(c) < 32 for c in login_id)
            or reply.get("verificationUrl") != DEVICE_VERIFICATION_URL
            or not isinstance(code, str) or not 1 <= len(code) <= 128 or not code.strip()
            or any(not 32 <= ord(c) <= 126 for c in code)):
        raise _error()
    return login_id


def _login_completed(event: Any, login_id: str) -> None:
    params = event.get("params") if isinstance(event, dict) else None
    if (not isinstance(params, dict) or event.get("method") != "account/login/completed"
            or params.get("loginId") != login_id or params.get("success") is not True or params.get("error") is not None):
        raise _error()


def _updated_plan(event: Any) -> str:
    params = event.get("params") if isinstance(event, dict) else None
    if (not isinstance(params, dict) or event.get("method") != "account/updated"
            or params.get("authMode") != "chatgpt" or params.get("planType") not in {"plus", "pro"}):
        raise _error()
    return params["planType"]


def _manifest(runtime_evidence: Mapping[str, Any], policy: ManagedPolicy) -> dict[str, Any]:
    evidence = deepcopy(dict(runtime_evidence))
    return {"version": MANAGED_VERSION, "binarySha256": evidence.get("binarySha256"),
            "transport": evidence.get("transport"), "executionEvidence": evidence.get("classification"),
            "runtime": evidence, "configSha256": hashlib.sha256(managed_config().encode()).hexdigest(),
            "catalogOriginalSha256": CATALOG_ORIGINAL_SHA256, "catalogPatchSha256": CATALOG_PATCH_SHA256,
            "catalogSha256": CATALOG_SHA256, "policy": policy.as_dict()}


def validate_managed_manifest(manifest: Any) -> str:
    """Validate descriptive values, not possession of a live runtime."""
    if not isinstance(manifest, dict) or manifest.get("version") != MANAGED_VERSION:
        raise _error()
    runtime = manifest.get("runtime")
    if not isinstance(runtime, dict) or runtime.get("version") != MANAGED_VERSION:
        raise _error()
    for key, expected in (("configSha256", hashlib.sha256(managed_config().encode()).hexdigest()),
                          ("catalogOriginalSha256", CATALOG_ORIGINAL_SHA256),
                          ("catalogPatchSha256", CATALOG_PATCH_SHA256), ("catalogSha256", CATALOG_SHA256)):
        if manifest.get(key) != expected:
            raise _error()
    if (runtime.get("binarySha256") != manifest.get("binarySha256")
            or runtime.get("configSha256") != manifest["configSha256"]
            or runtime.get("catalogSha256") != manifest["catalogSha256"]
            or runtime.get("limits") != manifest.get("policy")):
        raise _error()
    policy = manifest.get("policy")
    if not isinstance(policy, dict) or not isinstance(policy.get("capture"), dict):
        raise _error()
    try:
        checked_policy = ManagedPolicy(**{**policy, "capture": AppServerLimits(**policy["capture"])})
        if canonical_sha256(checked_policy.as_dict()) != canonical_sha256(policy):
            raise _error()
    except (TypeError, ValueError) as exc:
        raise _error() from exc
    if not isinstance(manifest.get("binarySha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", manifest["binarySha256"]):
        raise _error()
    classification = manifest.get("executionEvidence")
    if runtime.get("classification") != classification or runtime.get("transport") != manifest.get("transport"):
        raise _error()
    if manifest.get("transport") == "fixed-live-destinations":
        if (classification != "native-observed" or manifest.get("binarySha256") != MANAGED_BINARY_SHA256
                or runtime.get("platform") != {"system": "Linux", "machine": "aarch64"}
                or runtime.get("destinations") != [ISSUER_AUTHORITY, PROVIDER_AUTHORITY]):
            raise _error()
        for key in ("guardSourceSha256", "guardBinarySha256", "runtimeSourceSha256", "publicRootsSha256"):
            if not isinstance(runtime.get(key), str) or not re.fullmatch(r"[0-9a-f]{64}", runtime[key]):
                raise _error()
    elif manifest.get("transport") == "authored-local":
        if classification not in {"synthetic", "unverified"}:
            raise _error()
    else:
        raise _error()
    return classification


class ManagedExecutionProfile:
    """Reusable factory; it retains no readiness, challenge or launch authority."""

    VERSION = MANAGED_VERSION

    def __init__(self, *, policy: ManagedPolicy | None = None, binary: str = "codex",
                 runtime_factory: Callable[..., Any] | None = None) -> None:
        self.policy = policy if policy is not None else ManagedPolicy()
        if not isinstance(self.policy, ManagedPolicy):
            raise ValueError("managed policy must be finite and typed")
        self.binary, self._runtime_factory = binary, runtime_factory

    def prepare(self, cwd: str | Path, *, identity: ManagedAttemptIdentity,
                cancelled: threading.Event | None = None) -> ManagedLaunch:
        if not isinstance(identity, ManagedAttemptIdentity) or (cancelled is not None and cancelled.is_set()):
            raise _error()
        catalog = managed_catalog()
        factory = self._runtime_factory
        if factory is None:
            from .native_containment import ContainedRuntime
            factory = ContainedRuntime
        runtime = factory(cwd, config_toml=managed_config(), catalog_bytes=catalog,
                          policy=self.policy, binary=self.binary, cancelled=cancelled)
        try:
            if self._runtime_factory is not None and runtime.evidence.get("transport") != "authored-local":
                raise _error()
            return ManagedLaunch(runtime, identity, self.policy, cancelled)
        except BaseException:
            runtime.close(reason="preparation-refused")
            raise


class ManagedLaunch:
    def __init__(self, runtime: Any, identity: ManagedAttemptIdentity, policy: ManagedPolicy,
                 cancelled: threading.Event | None) -> None:
        self._runtime, self._identity, self._cancelled = runtime, identity, cancelled
        self._lock = threading.RLock()
        self._state = "prepared"
        self._challenge: dict[str, Any] | None = None
        self._receipt: dict[str, Any] | None = None
        self._abort_callback: Callable[[], None] | None = None
        self._evidence = _manifest(runtime.evidence, policy)
        validate_managed_manifest(self._evidence)
        self.limits = policy.capture
        self._command, self._env = tuple(runtime.command), MappingProxyType(dict(runtime.env))
        self._expires_at_ms = int(time.time() * 1000 + self.remaining_preparation() * 1000)

    @property
    def evidence(self) -> dict[str, Any]:
        return deepcopy(self._evidence)

    @property
    def command(self) -> tuple[str, ...]:
        return self._command

    @property
    def env(self) -> Mapping[str, str]:
        return self._env

    def _require(self, *states: str) -> None:
        if self._state not in states or (self._cancelled is not None and self._cancelled.is_set()):
            raise _error()

    def remaining_preparation(self) -> float:
        with self._lock:
            self._require("prepared", "starting", "issuer-only", "preparing-native")
        value = self._runtime.remaining_preparation()
        if not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise _error()
        return value

    def remaining_turn(self) -> float:
        with self._lock:
            self._require("ready", "consumed")
        value = self._runtime.remaining_turn()
        if not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise _error()
        return value

    def require_contained_startup(self) -> None:
        try:
            with self._lock:
                self._require("prepared")
                self._state = "starting"
            self.remaining_preparation()
            self._runtime.require_contained_startup()
            with self._lock:
                self._require("starting")
                self._state = "issuer-only"
        except Exception:
            # AppServerClient.start still owns its lifecycle lock here. A
            # concurrent runtime closer may need that lock in its abort
            # callback, so startup unwind must not wait for it. Final worker
            # cleanup still requires the ordinary completed close report.
            with self._lock:
                self._state, self._challenge, self._receipt = "closed", None, None
            try:
                self._runtime.close(reason="startup-refused", wait=False)
            except Exception:
                pass  # Preserve startup failure; final cleanup rechecks closure.
            raise

    def bind_abort(self, close_owned_client: Callable[[], None]) -> None:
        with self._lock:
            if self._abort_callback is not None or not callable(close_owned_client):
                raise _error()
            self._require("prepared")
            self._abort_callback = close_owned_client
        def aborted():
            with self._lock:
                self._state, self._challenge, self._receipt = "closed", None, None
            close_owned_client()
        self._runtime.bind_abort(aborted)

    def _active(self, preparation: Any) -> None:
        with self._lock:
            self._require("preparing-native")
        if preparation.source != self._identity.source:
            raise _error()
        preparation.remaining()
        self.remaining_preparation()

    def prepare_native(self, preparation: Any) -> None:
        try:
            with self._lock:
                self._require("issuer-only")
                self._state = "preparing-native"
            self._active(preparation)
            observed = {}
            def request(name, method, params):
                self._active(preparation)
                observed[name] = preparation.request(method, params)
                self._active(preparation)
                return observed[name]
            initial = request("initialAccount", "account/read", {"refreshToken": False})
            if (not isinstance(initial, dict) or "account" not in initial or initial["account"] is not None
                    or initial.get("requiresOpenaiAuth") is not True):
                raise _error()
            validate_managed_config(request("initialConfig", "config/read", {"includeLayers": False}))
            login = request("loginStart", "account/login/start", {"type": "chatgptDeviceCode"})
            login_id = _login_reply(login)
            with self._lock:
                self._require("preparing-native")
                self._challenge = {"verificationUrl": DEVICE_VERIFICATION_URL, "userCode": login["userCode"],
                                   "expiresAtMs": self._expires_at_ms}
            preparation.phase("awaiting-sign-in")
            expected = "loginCompleted"
            for _ in range(MAX_PREPARATION_EVENTS):
                self._active(preparation)
                event = preparation.recv_event(timeout=self.remaining_preparation())
                self._active(preparation)
                if not isinstance(event, dict):
                    raise _error()
                method = event.get("method")
                if method == "account/login/completed":
                    if expected != "loginCompleted":
                        raise _error()
                    _login_completed(event, login_id)
                    with self._lock:
                        self._challenge = None
                    observed["loginCompleted"] = event
                    expected = "accountUpdated"
                elif method == "account/updated":
                    if expected != "accountUpdated":
                        raise _error()
                    _updated_plan(event)
                    observed["accountUpdated"] = event
                    break
                elif method == "remoteControl/status/changed":
                    if not isinstance(event.get("params"), dict) or event["params"].get("status") != "disabled":
                        raise _error()
                elif method != "warning":
                    raise _error()
            else:
                raise _error()
            preparation.phase("checking")
            plan = _account_plan(request("orderedAccount", "account/read", {"refreshToken": False}))
            if plan != _updated_plan(observed["accountUpdated"]):
                raise _error()
            validate_managed_config(request("orderedConfig", "config/read", {"includeLayers": False}))
            self._active(preparation)
            self._runtime.activate_provider()
            with self._lock:
                self._require("preparing-native")
                self._receipt = {"version": MANAGED_VERSION, "identity": self._identity.as_dict(),
                                 "manifest": self.evidence,
                                 "readiness": {key: canonical_sha256(observed[key]) for key in READINESS_KEYS},
                                 "loginId": login_id, "planType": plan,
                                 "issuerClosed": True, "providerActivated": True}
                self._state = "ready"
            self.remaining_turn()
        except Exception as exc:
            self.close(reason="preparation-failed")
            raise _error() from exc

    def consume_turn_admission(self, identity: ManagedAttemptIdentity) -> dict[str, Any]:
        try:
            with self._lock:
                self._require("ready")
                if identity != self._identity or self._receipt is None:
                    raise _error()
                self.remaining_turn()
                receipt = deepcopy(self._receipt)
                self._receipt = None
                self._state = "consumed"
                return receipt
        except Exception:
            self.close(reason="admission-refused")
            raise

    def read_challenge(self, identity: ManagedAttemptIdentity) -> dict[str, Any] | None:
        with self._lock:
            if identity != self._identity or self._state != "preparing-native" or self._challenge is None:
                return None
            try:
                self.remaining_preparation()
                if time.time() * 1000 >= self._expires_at_ms:
                    raise _error()
                return deepcopy(self._challenge)
            except Exception:
                pass
        self.close(reason="challenge-expired")
        return None

    def close(self, reason: str = "closed") -> dict[str, Any]:
        with self._lock:
            self._state, self._challenge, self._receipt = "closed", None, None
        report = self._runtime.close(reason=reason)
        if not isinstance(report, dict) or report.get("allWorkersJoined") is not True or report.get("errors") != []:
            error = _error()
            error.diagnostic = deepcopy(report)
            raise error
        return report


def validate_managed_receipt(receipt: Any, identity: ManagedAttemptIdentity,
                             records: Sequence[TraceRecord], *, before_seq: int) -> str:
    """Recheck exact private observations. This cannot reconstruct live authority."""
    try:
        return _validate_receipt(receipt, identity, records, before_seq)
    except (KeyError, IndexError, AttributeError, TypeError, ValueError) as exc:
        raise _error() from exc


def _validate_receipt(receipt, identity, records, before_seq):
    if (not isinstance(identity, ManagedAttemptIdentity) or not isinstance(receipt, dict)
            or receipt.get("version") != MANAGED_VERSION or receipt.get("identity") != identity.as_dict()
            or receipt.get("issuerClosed") is not True or receipt.get("providerActivated") is not True
            or type(before_seq) is not int or before_seq <= 0):
        raise _error()
    classification = validate_managed_manifest(receipt.get("manifest"))
    rows = [row for row in records if row.source == identity.source and row.seq < before_seq]
    if not rows or [r.seq for r in rows] != sorted({r.seq for r in rows}):
        raise _error()
    if any(row.direction == "internal" and row.message.get("method") == "$transport/captureGap" for row in rows):
        raise _error()
    requests = [row for row in rows if row.direction == "client_to_appserver" and "id" in row.message]
    methods = ["initialize", "account/read", "config/read", "account/login/start", "account/read", "config/read"]
    if [r.message.get("method") for r in requests] != methods:
        raise _error()
    def rpc_key(message):
        value = message.get("id")
        if type(value) not in (int, str):
            raise _error()
        return canonical_sha256(value)
    if len({rpc_key(r.message) for r in requests}) != len(requests):
        raise _error()
    expected = [{"refreshToken": False}, {"includeLayers": False}, {"type": "chatgptDeviceCode"},
                {"refreshToken": False}, {"includeLayers": False}]
    observed, reply_rows = {}, []
    for index, request in enumerate(requests):
        if index and request.message.get("params") != expected[index - 1]:
            raise _error()
        replies = [row for row in rows if row.direction == "appserver_to_client"
                   and "id" in row.message and "method" not in row.message
                   and rpc_key(row.message) == rpc_key(request.message)]
        if len(replies) != 1:
            raise _error()
        reply = replies[0]
        if (reply.seq <= request.seq or "error" in reply.message or not isinstance(reply.message.get("result"), dict)
                or (index + 1 < len(requests) and reply.seq >= requests[index + 1].seq)):
            raise _error()
        reply_rows.append(reply)
        if index:
            observed[("initialAccount", "initialConfig", "loginStart", "orderedAccount", "orderedConfig")[index - 1]] = reply.message["result"]
    if ("account" not in observed["initialAccount"] or observed["initialAccount"]["account"] is not None
            or observed["initialAccount"].get("requiresOpenaiAuth") is not True):
        raise _error()
    validate_managed_config(observed["initialConfig"])
    validate_managed_config(observed["orderedConfig"])
    login_id = _login_reply(observed["loginStart"])
    completed = [r for r in rows if r.direction == "appserver_to_client" and r.message.get("method") == "account/login/completed"]
    updated = [r for r in rows if r.direction == "appserver_to_client" and r.message.get("method") == "account/updated"]
    if len(completed) != 1 or len(updated) != 1:
        raise _error()
    if not reply_rows[3].seq < completed[0].seq < updated[0].seq < requests[4].seq:
        raise _error()
    observed["loginCompleted"], observed["accountUpdated"] = completed[0].message, updated[0].message
    _login_completed(observed["loginCompleted"], login_id)
    plan = _account_plan(observed["orderedAccount"])
    if (receipt.get("loginId") != login_id or receipt.get("planType") != plan
            or _updated_plan(observed["accountUpdated"]) != plan
            or receipt.get("readiness") != {key: canonical_sha256(observed[key]) for key in READINESS_KEYS}):
        raise _error()
    return classification
