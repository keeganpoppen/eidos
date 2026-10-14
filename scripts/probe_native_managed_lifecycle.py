#!/usr/bin/env python3
"""Native-owned ephemeral auth against an authored offline issuer, never real auth."""
from __future__ import annotations

import argparse
import base64
from dataclasses import asdict
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import socketserver
import sys
import tempfile
import threading
import time
from typing import Any
from urllib.parse import parse_qsl

from eidos.codex import AppServerClient
from eidos.investigation import InvestigationStore
from eidos.investigation_worker import NativeInvestigationWorker
from eidos.investigation_context import THREAD_CONFIG, TURN_SANDBOX
from eidos.investigation_inquiries import terminal_inquiry
from eidos.private_investigation import PrivateEvidenceLimits, PrivateInvestigationWorker, validate_publication
from eidos.trace import TraceStore
from eidos.native_managed import ManagedExecutionProfile, managed_config, managed_catalog, validate_managed_config
from eidos.native_managed_contract import MANAGED_VERSION, ManagedLaunchError, ManagedPolicy

_spec = importlib.util.spec_from_file_location("managed_tls_fixture", Path(__file__).with_name("probe_native_tls_connect.py"))
assert _spec and _spec.loader
tls = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = tls
_spec.loader.exec_module(tls)
derived, catalog, transport, boundary = tls.derived, tls.catalog, tls.transport, tls.boundary
ISSUER = "https://issuer.fixture.invalid"
ISSUER_AUTHORITY = "issuer.fixture.invalid:443"
PROVIDER = "https://provider.fixture.invalid/backend-api/codex"
PROVIDER_PATH = "/backend-api/codex/responses"
SETTINGS_PATH = "/backend-api/wham/settings/user"
CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
CASES = ("nearExpiry", "closedIssuer401")
POSITIVE_CASE = "managedText"
WORKER_CASE = "managedWorkerText"
PRODUCT_CASE = "managedProductText"
PRODUCT_ISSUER = "https://auth.openai.com"
PRODUCT_ISSUER_AUTHORITY = "auth.openai.com:443"
PRODUCT_PROVIDER_AUTHORITY = "chatgpt.com:443"
MAX_HTTP = 8
HOLD_SECONDS = 1.5
MAX_EVENTS = 100
LOGIN_COMPLETED = "account/login/completed"
REVIEWED_BINARY_SHA256 = "9b7c1c7abdc26fc3c4f47c77656a8e9121def5483dbae830ef1ee561758448a9"


def checked_binary(path: Path = Path("/usr/bin/codex")) -> str:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != REVIEWED_BINARY_SHA256: raise ValueError("native executable differs from reviewed 0.154.0")
    return digest


def strict_json(raw: str):
    def pairs(items):
        value = {}
        for key, item in items:
            if key in value: raise ValueError("duplicate JSON key")
            value[key] = item
        return value
    def constant(_): raise ValueError("non-finite JSON constant")
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)


def validate_login_completed(event: dict[str, Any], login_id: str) -> None:
    params = event.get("params", {})
    if (event.get("method") != LOGIN_COMPLETED or params.get("loginId") != login_id
            or params.get("success") is not True):
        raise ValueError("matching successful login completion required")


def validate_waited_event(event: dict[str, Any], method: str) -> None:
    if method == LOGIN_COMPLETED and event.get("method") == "account/updated":
        raise ValueError("account update preceded matching login completion")


class Timeline:
    def __init__(self):
        self.started = time.monotonic()
        self.lock = threading.Lock()
        self.events = []

    def add(self, kind: str, **fields: Any) -> dict[str, Any]:
        with self.lock:
            event = {"seq": len(self.events) + 1, "seconds": round(time.monotonic() - self.started, 6),
                     "kind": kind, **fields}
            self.events.append(event)
            return event


def synthetic_jwt(claims: dict[str, Any]) -> str:
    def encode(value):
        return base64.urlsafe_b64encode(json.dumps(value, separators=(",", ":")).encode()).decode().rstrip("=")
    return encode({"alg": "HS256", "typ": "JWT", "kid": "nema-invalid-synthetic-key"}) + "." + encode(claims) + ".INVALID_SYNTHETIC_SIGNATURE"


def token_generation(generation: str, plan: str, expires: int, *, issuer: str = ISSUER) -> dict[str, str]:
    if generation not in ("A", "B") or plan not in ("plus", "free") or type(expires) is not int:
        raise ValueError("only authored token generations are permitted")
    claims = {"iss": issuer, "aud": "nema-synthetic.invalid", "email": "fixture@example.invalid",
              "jti": "nema-synthetic-" + generation, "exp": expires,
              "https://api.openai.com/auth": {"chatgpt_plan_type": plan,
                  "chatgpt_user_id": "nema-fixture-user", "chatgpt_account_id": "nema-fixture-account"}}
    return {"id_token": synthetic_jwt(claims), "access_token": synthetic_jwt({**claims, "token_use": "access"}),
            "refresh_token": "nema-invalid-synthetic-refresh-" + generation}


def fixture_config(*, owned_worker: bool = False) -> str:
    config = derived.fixture_config(derived.MODEL)
    start = config.index(f"[model_providers.{transport.PROVIDER}]")
    end = config.index("[mcp_servers.fixture]", start)
    config = config[:start] + config[end:]
    config = config.replace(f'model_provider="{transport.PROVIDER}"', 'model_provider="openai"')
    config = config.replace("[features]\n", "[features]\nuse_agent_identity=false\nenable_request_compression=false\n")
    if owned_worker:
        # Stored native threads install the goal extension. Disable its default
        # tools at startup; do not change the ordinary worker's thread packet.
        config = config.replace("[features]\n", "[features]\ngoals=false\n")
    return (f'cli_auth_credentials_store="ephemeral"\nforced_login_method="chatgpt"\n'
            f'openai_base_url="{PROVIDER}"\nchatgpt_base_url="https://provider.fixture.invalid/backend-api"\n'
            + config + '\n[otel]\nexporter="none"\nmetrics_exporter="none"\n[analytics]\nenabled=false\n')


def validate_config(reply: dict[str, Any], *, owned_worker: bool = False) -> None:
    if not isinstance(reply, dict) or not isinstance(reply.get("config"), dict):
        raise ValueError("managed fixture config is not an object")
    config = reply["config"]
    expected = {"model_provider": "openai", "model": derived.MODEL,
                "model_catalog_json": "/fixture/models.json", "openai_base_url": PROVIDER,
                "chatgpt_base_url": "https://provider.fixture.invalid/backend-api",
                "cli_auth_credentials_store": "ephemeral", "forced_login_method": "chatgpt"}
    if any(config.get(key) != value for key, value in expected.items()):
        raise ValueError("managed fixture startup config differs")
    otel = config.get("otel") or {}
    if otel.get("exporter") != "none" or otel.get("metrics_exporter") != "none":
        raise ValueError("OTEL worker controls differ")
    if config.get("analytics", {}).get("enabled") is not False:
        raise ValueError("analytics producer not disabled")
    disabled = ("plugins", "apps", "hooks", "use_agent_identity", "enable_request_compression", "shell_tool",
                "shell_snapshot", "code_mode", "multi_agent", "multi_agent_v2", "sleep_tool", "current_time_reminder")
    if any(config.get("features", {}).get(key) is not False for key in disabled):
        raise ValueError("managed fixture feature controls differ")
    if owned_worker and config.get("features", {}).get("goals") is not False:
        raise ValueError("owned worker goal tools are not disabled")
    if config.get("agents", {}).get("enabled") is not False or config.get("mcp_servers", {}).get("fixture", {}).get("enabled") is not False:
        raise ValueError("agent/MCP controls differ")


def account_plan(reply: dict[str, Any]) -> str:
    if not isinstance(reply, dict): raise ValueError("managed fixture account reply is not an object")
    account = reply.get("account")
    if (reply.get("requiresOpenaiAuth") is not True or not isinstance(account, dict)
            or account.get("type") != "chatgpt" or account.get("email") != "fixture@example.invalid"):
        raise ValueError("unexpected managed fixture account")
    plan = account.get("planType")
    if plan not in ("plus", "free"):
        raise ValueError("unexpected fixture plan")
    return plan


class ManagedClient(AppServerClient):
    """Private fixture RPC allowlist, not a production profile or public grant."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.methods = []
        self.login_count = self.turn_count = self.thread_count = 0
        self.expected_thread = self.expected_turn = None
        self.issuer_closed = False
        self.fixture_abort = threading.Event()

    def request(self, method: str, params: Any = None, *, timeout: float = 4.0):
        if self.fixture_abort.is_set(): raise ValueError("fixture stopped before next RPC")
        if method not in {"initialize", "account/login/start", "account/read", "config/read", "thread/start", "turn/start"}:
            raise ValueError("managed fixture refuses RPC: " + method)
        if method == "account/login/start":
            if params != {"type": "chatgptDeviceCode"} or self.login_count or self.issuer_closed:
                raise ValueError("only one authored device login is permitted")
            self.login_count += 1
        if method == "account/read" and params != {"refreshToken": False}:
            raise ValueError("explicit refresh/token export is not permitted")
        if method == "config/read" and params != {"includeLayers": False}:
            raise ValueError("only fixed config read is permitted")
        if method == "thread/start":
            if not self.issuer_closed or self.expected_thread is None or params != self.expected_thread or self.thread_count:
                raise ValueError("thread requires exact prepared input and closed issuer")
            self.thread_count += 1
        if method == "turn/start":
            if not self.issuer_closed or self.expected_turn is None or params != self.expected_turn or self.turn_count or self.thread_count != 1:
                raise ValueError("turn requires one exact prepared synthetic packet")
            self.turn_count += 1
        self.methods.append(method)
        return super().request(method, params, timeout=timeout)

    def notify(self, method, params=None):
        if method != "initialized": raise ValueError("only initialization notification is permitted")
        super().notify(method, params)

    def respond(self, request_id, result=None, *, error=None):
        raise ValueError("fixture cannot approve native requests")


class Services:
    def __init__(self, variant: str, prompt: str, timeline: Timeline):
        if variant not in (*CASES, POSITIVE_CASE, WORKER_CASE, PRODUCT_CASE): raise ValueError("unknown lifecycle case")
        self.variant, self.prompt, self.timeline = variant, prompt, timeline
        self.issuer = PRODUCT_ISSUER if variant == PRODUCT_CASE else ISSUER
        self.issuer_host = "auth.openai.com" if variant == PRODUCT_CASE else "issuer.fixture.invalid"
        self.provider_host = "chatgpt.com" if variant == PRODUCT_CASE else "provider.fixture.invalid"
        now = int(time.time())
        self.tokens = {"A": token_generation("A", "plus", now + (60 if variant == "nearExpiry" else 3600), issuer=self.issuer),
                       "B": token_generation("B", "free", now + 3600, issuer=self.issuer)}
        self.issuer_step = 0
        self.generations = []
        self.provider_enabled = False
        self.settings_served = False
        self.websocket_served = self.response_served = False
        self.held, self.release = threading.Event(), threading.Event()
        self.abort = threading.Event()
        self.events = []
        self.requests = 0
        self.violations = []
        self.lock = threading.Lock()

    def dispatch(self, side: str, record: dict[str, Any]) -> tuple[int, str, Any]:
        if self.abort.is_set(): raise ValueError("fixture stopped after violation")
        method, target, headers, raw = (record[key] for key in ("method", "target", "headers", "bodyRaw"))
        if side == "issuer":
            if method != "POST" or "authorization" in headers:
                raise ValueError("issuer route or authorization refused")
            if headers.get("host") != self.issuer_host: raise ValueError("issuer Host differs")
            expected_type = "application/x-www-form-urlencoded" if target == "/oauth/token" and self.issuer_step == 2 else "application/json"
            if headers.get("content-type", "").split(";")[0] != expected_type: raise ValueError("issuer content type differs")
            if target == "/api/accounts/deviceauth/usercode" and self.issuer_step == 0:
                if strict_json(raw) != {"client_id": CLIENT_ID}: raise ValueError("device client differs")
                self.issuer_step = 1
                return 200, "authored-device-code", {"device_auth_id": "nema-fixture-device", "user_code": "NEMA-FIXTURE", "interval": "1"}
            if target == "/api/accounts/deviceauth/token" and self.issuer_step == 1:
                if strict_json(raw) != {"device_auth_id": "nema-fixture-device", "user_code": "NEMA-FIXTURE"}:
                    raise ValueError("device poll differs")
                self.issuer_step = 2
                return 200, "authored-code-exchange", {"authorization_code": "nema-fixture-code",
                    "code_challenge": "nema-fixture-challenge", "code_verifier": "nema-fixture-verifier"}
            if target != "/oauth/token": raise ValueError("unknown issuer route")
            if self.issuer_step == 2:
                pairs = parse_qsl(raw, keep_blank_values=True, strict_parsing=True, max_num_fields=5)
                expected = {"grant_type": "authorization_code", "code": "nema-fixture-code", "client_id": CLIENT_ID,
                            "redirect_uri": self.issuer + "/deviceauth/callback", "code_verifier": "nema-fixture-verifier"}
                if len(pairs) != 5 or dict(pairs) != expected: raise ValueError("authorization grant differs")
                self.issuer_step = 3
                generation = "A"
            elif self.issuer_step == 3 and self.variant == "nearExpiry":
                expected = {"client_id": CLIENT_ID, "grant_type": "refresh_token", "refresh_token": self.tokens["A"]["refresh_token"]}
                if strict_json(raw) != expected: raise ValueError("refresh grant differs")
                self.held.set()
                self.timeline.add("issuerRefreshHeld")
                if not self.release.wait(HOLD_SECONDS): raise ValueError("held refresh deadline")
                if self.abort.is_set(): raise ValueError("fixture stopped while refresh held")
                self.issuer_step = 4
                generation = "B"
            else: raise ValueError("unexpected or duplicate token request")
            self.generations.append(generation)
            self.timeline.add("fixtureTokenResponseAuthored", generation=generation)
            return 200, "authored-token-" + generation, self.tokens[generation]
        if not self.provider_enabled: raise ValueError("provider contacted before issuer closure")
        if headers.get("host") != self.provider_host: raise ValueError("provider Host differs")
        if headers.get("authorization") != "Bearer " + self.tokens["A"]["access_token"]:
            raise ValueError("provider bearer is not authored generation A")
        if target == SETTINGS_PATH:
            if method != "GET" or raw != "" or self.settings_served:
                raise ValueError("settings requires one exact empty GET")
            self.settings_served = True
            return 200, "authored-attribution-disabled", {"commit_attribution_enabled": False}
        if target != PROVIDER_PATH: raise ValueError("unknown provider route")
        if method == "GET" and headers.get("upgrade", "").lower() == "websocket" and raw == "":
            if self.variant in (POSITIVE_CASE, WORKER_CASE, PRODUCT_CASE) and self.websocket_served:
                raise ValueError("positive fixture permits one WebSocket fallback")
            self.websocket_served = True
            return 426, "authored-websocket-http-fallback", {"synthetic": True}
        if method != "POST": raise ValueError("unknown provider method")
        payload = strict_json(raw)
        if not catalog.provider_shape(payload, headers, derived.MODEL, self.prompt):
            raise ValueError("provider envelope differs")
        tools = [item for item in payload["input"] if item.get("type") == "additional_tools"]
        if tools[0]["tools"]: raise ValueError("unexpected tool declaration")
        if self.variant in (POSITIVE_CASE, WORKER_CASE, PRODUCT_CASE):
            if self.response_served or not self.websocket_served or not self.settings_served:
                raise ValueError("positive response requires one fallback/settings prefix")
            if any(item.get("type") in ("function_call", "function_call_output") for item in payload["input"]):
                raise ValueError("positive fixture refuses tool-call history")
            self.response_served = True
            return 200, "authored-managed-text", catalog.authored_stream(derived.MODEL, 2)
        return 401, "authored-unauthorized", {"error": {"message": "Authored offline 401 fixture", "type": "authentication_error", "code": "invalid_api_key"}}

    def exchange(self, side: str, connection):
        with self.lock:
            if self.abort.is_set():
                return transport.FixtureBroker._http(403, b'{"synthetic":true,"reason":"fixture-stopped"}')
            if self.requests >= MAX_HTTP:
                self.violations.append("endpoint-request-limit")
                self.abort.set()
                return transport.FixtureBroker._http(429, b'{"synthetic":true}')
            self.requests += 1
        record = {"side": side}
        try:
            allowed = frozenset({"Bearer " + value["access_token"] for value in self.tokens.values()}) if side == "provider" else frozenset()
            record.update(transport.read_fixture_http_request(connection, time.monotonic() + 2,
                                                              allowed_authorizations=allowed))
            if side == "issuer" and len(record["bodyRaw"].encode()) > 16384: raise ValueError("issuer body limit")
            status, reason, response = self.dispatch(side, record)
        except transport.FixtureHttpError as exc:
            record.update(exc.record)
            status, reason, response = exc.status, exc.reason, {"synthetic": True}
            self.violations.append(reason)
            self.abort.set()
        except (ValueError, TypeError, UnicodeError, RecursionError, KeyError) as exc:
            status, reason, response = 400, str(exc), {"synthetic": True}
            self.violations.append(reason)
            self.abort.set()
        content_type = "text/event-stream" if isinstance(response, bytes) else "application/json"
        payload = response if isinstance(response, bytes) else json.dumps(response, separators=(",", ":")).encode()
        if len(payload) > 8192: raise ValueError("authored endpoint response limit")
        record.update(status=status, reason=reason, responseRaw=payload.decode())
        if self.variant in (POSITIVE_CASE, WORKER_CASE, PRODUCT_CASE): record["responseContentType"] = content_type
        self.events.append(record)
        self.timeline.add("fixtureHttpResponse", side=side, status=status, reason=reason)
        return transport.FixtureBroker._http(status, payload, content_type)


class Endpoint:
    def __init__(self, services: Services, side: str): self.services, self.side = services, side
    def exchange(self, connection): return self.services.exchange(self.side, connection)


def stop_on_connect_exhaustion(services: Services, broker) -> None:
    if broker.unrecorded_refusals:
        with services.lock:
            if not services.abort.is_set():
                services.violations.append("connect-limit-exhausted")
                services.timeline.add("fixtureResourceStop", reason="connect-limit-exhausted")
            services.abort.set()


def prepare_case(root: Path, helper: Path, paths: dict[str, Path], *, owned_worker: bool = False) -> None:
    """Shared contained fixture bytes, unchanged for the historical cases."""
    boundary.prepare(root, helper)
    original, _ = catalog.checked_catalog()
    (root / "fixture/models.json").write_bytes(derived.derived_catalog(original))
    (root / "fixture/ca.pem").write_bytes(paths["ca"].read_bytes())
    (root / "state/codex/config.toml").write_text(fixture_config(owned_worker=owned_worker))
    (root / "fixture/relay.py").write_text(transport.RELAY)
    anchor = "os.execv('/fixture/guard'"
    assert transport.LAUNCHER.count(anchor) == 1
    environment = ("os.environ['HTTPS_PROXY']='http://127.0.0.1:'+port.read_text()\n"
                   "os.environ['CODEX_CA_CERTIFICATE']='/fixture/ca.pem'\n"
                   f"os.environ['CODEX_APP_SERVER_LOGIN_ISSUER']={ISSUER!r}\n"
                   f"os.environ['CODEX_REFRESH_TOKEN_URL_OVERRIDE']={(ISSUER+'/oauth/token')!r}\n")
    (root / "fixture/launcher.py").write_text(transport.LAUNCHER.replace(anchor, environment + anchor))


def prepare_product_case(root: Path, helper: Path, paths: dict[str, Path]) -> None:
    """Offline transport only; production configuration is supplied by the profile."""
    boundary.prepare(root, helper)
    (root / "assets").mkdir()
    (root / "fixture/ca.pem").write_bytes(paths["ca"].read_bytes())
    (root / "fixture/relay.py").write_text(transport.RELAY)
    rewrite = "config.write_text(config.read_text().replace('FIXTURE_PORT',port.read_text()))\n"
    anchor = "os.execv('/fixture/guard'"
    assert transport.LAUNCHER.count(rewrite) == transport.LAUNCHER.count(anchor) == 1
    launcher = transport.LAUNCHER.replace(rewrite, "")
    launcher = launcher.replace(anchor,
        "os.environ['HTTPS_PROXY']='http://127.0.0.1:'+port.read_text()\n"
        "os.environ['CODEX_CA_CERTIFICATE']='/fixture/ca.pem'\n" + anchor)
    (root / "fixture/launcher.py").write_text(launcher)
    for name in ("ca.pem", "relay.py", "launcher.py"):
        (root / "fixture" / name).chmod(0o400)


def worker_launcher(root: Path, *, product_managed: bool = False) -> tuple[str, ...]:
    """Mirror only the owned cwd spelling inside empty namespace tmpfs."""
    command = boundary.namespace_command(root, Path("/usr/bin/bwrap"),
                                         ["/usr/bin/python3", "/fixture/launcher.py"], broker=True)
    if product_managed:
        index = command.index("--clearenv")
        command[index:index] = ["--ro-bind", str(root / "assets"), "/assets",
                               "--ro-bind", str(root / "assets/config.toml"), "/state/codex/config.toml"]
    script = root / "worker-launcher.py"
    script.write_text("import os\nfrom pathlib import Path\n"
        "cwd = Path.cwd()\n"
        "if cwd.parent != Path('/tmp') or not cwd.name.startswith('nema-investigation-') or cwd.is_symlink():\n"
        "    raise RuntimeError('worker cwd is outside the fixed temporary namespace')\n"
        f"command = {command!r}\n"
        "command[command.index('--chdir') + 1] = str(cwd)\n"
        "index = command.index('--clearenv')\n"
        "command[index:index] = ['--dir', str(cwd)]\n"
        "os.execv(command[0], command)\n")
    # Host-side adapter reads only its authored script and stdlib before exec;
    # disable user site/PYTHON* startup hooks before namespace clearenv applies.
    return ("/usr/bin/python3", "-I", "-S", str(script))


def product_fixture_policy() -> ManagedPolicy:
    # Product configuration/preparation, historical offline traffic budgets.
    return ManagedPolicy(preparation_seconds=8, turn_seconds=120, lifetime_seconds=18,
        max_connections=8, max_active=2, max_received_bytes=2097152,
        idle_seconds=4, buffer_bytes=8192, header_bytes=8192, capture=derived.LIMITS)


def product_fixture_broker(issuer_tls, provider_tls):
    """Two fixed local factories. No hostname-to-address lookup or dial path."""
    return tls.ConnectBroker(destinations={PRODUCT_ISSUER_AUTHORITY: issuer_tls.open_endpoint,
                                          PRODUCT_PROVIDER_AUTHORITY: provider_tls.open_endpoint})


class OfflineManagedRuntime:
    """Explicit authored transport: no production resolver or live dial exists.

    The supplied broker already maps the two production authority *labels* to
    preconstructed local TLS/socketpair factories. No URL/config/reply rewriting.
    Native disposable files remain until the outer fixture snapshots them.
    """

    def __init__(self, owner, cwd, *, config_toml, catalog_bytes, policy, binary="codex", cancelled=None):
        if config_toml != managed_config() or catalog_bytes != managed_catalog() or policy != product_fixture_policy():
            raise ManagedLaunchError("offline product inputs differ")
        self.owner, self.policy, self.cancelled = owner, policy, cancelled
        self.created, self.turn_started = time.monotonic(), None
        self._lock, self._closed = threading.Lock(), threading.Event()
        self._state, self._callback, self._report = "prepared", None, None
        root = owner.probe_root
        for name, value in (("config.toml", config_toml.encode()), ("models.json", catalog_bytes)):
            target = root / "assets" / name
            target.write_bytes(value); target.chmod(0o400)
        self.command, self.env = worker_launcher(root, product_managed=True), {}
        self._assets = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in
            [root / "assets/config.toml", root / "assets/models.json", root / "fixture/ca.pem",
             root / "fixture/guard", root / "fixture/relay.py", root / "fixture/launcher.py", Path(self.command[-1])]}
        self.evidence = {"version": MANAGED_VERSION, "transport": "authored-local", "classification": "synthetic",
            "binarySha256": checked_binary(), "configSha256": hashlib.sha256(config_toml.encode()).hexdigest(),
            "catalogSha256": hashlib.sha256(catalog_bytes).hexdigest(), "limits": policy.as_dict(),
            "fixtureAssets": dict(self._assets), "fixtureOnly": True,
            "destinations": [PRODUCT_ISSUER_AUTHORITY, PRODUCT_PROVIDER_AUTHORITY],
            "dns": False, "liveDial": False, "fixtureCaSha256": self._assets[str(root / "fixture/ca.pem")]}
        owner.runtime = self

    def _active(self):
        if self._state == "closed" or (self.cancelled is not None and self.cancelled.is_set()):
            raise ManagedLaunchError("offline managed runtime closed")
        if time.monotonic() >= self.created + self.policy.lifetime_seconds:
            raise ManagedLaunchError("offline managed lifetime expired")

    def remaining_preparation(self):
        self._active()
        value = min(self.created + self.policy.preparation_seconds, self.created + self.policy.lifetime_seconds) - time.monotonic()
        if value <= 0: raise ManagedLaunchError("offline managed preparation expired")
        return value

    def remaining_turn(self):
        self._active()
        if self.turn_started is None: raise ManagedLaunchError("offline managed provider not active")
        value = min(self.turn_started + self.policy.turn_seconds, self.created + self.policy.lifetime_seconds) - time.monotonic()
        if value <= 0: raise ManagedLaunchError("offline managed turn expired")
        return value

    def bind_abort(self, callback):
        with self._lock:
            self._active()
            if self._callback is not None: raise ManagedLaunchError("offline abort already bound")
            self._callback = callback

    def require_contained_startup(self):
        with self._lock:
            self.remaining_preparation()
            if self._state != "prepared": raise ManagedLaunchError("offline startup already consumed")
            if checked_binary() != self.evidence["binarySha256"]: raise ManagedLaunchError("native executable changed")
            if any(hashlib.sha256(Path(p).read_bytes()).hexdigest() != digest for p, digest in self._assets.items()):
                raise ManagedLaunchError("offline asset changed")
            self._state = "issuer-only"

    def activate_provider(self):
        with self._lock:
            self.remaining_preparation()
            if self._state != "issuer-only": raise ManagedLaunchError("offline provider cannot reopen")
            self.owner.timeline.add("orderedConfigSucceeded")
            self.owner.broker.close_authority(PRODUCT_ISSUER_AUTHORITY)
            self.owner.timeline.add("issuerClosed", connectCount=self.owner.broker.connections,
                issuerHttpRequests=sum(e["side"] == "issuer" for e in self.owner.services.events))
            self.owner.issuer_closed = self.owner.services.provider_enabled = True
            self.turn_started, self._state = time.monotonic(), "provider-only"

    def close(self, reason="closed", *, wait=True):
        with self._lock:
            first = self._state != "closed"
            self._state = "closed"
            callback = self._callback
        if not first:
            if wait: self._closed.wait(5)
            return self._report or {"allWorkersJoined": False, "errors": ["close-in-progress"]}
        errors = []
        for name, action in (("transports", self.owner.close_transports), ("owned-client", callback)):
            if action is not None:
                try: action()
                except Exception as exc: errors.append(name + ":" + type(exc).__name__)
        self._report = {"allWorkersJoined": not errors, "errors": errors, "reason": reason,
                        "stateRetainedForFixtureInspection": True, "classification": "synthetic"}
        self._closed.set()
        return dict(self._report)


class OwnedManagedWorker(PrivateInvestigationWorker):
    """Probe-only before-send guard composed with the production private recorder."""

    def __init__(self, trace, command, *, root: Path, services: Services, broker, timeline: Timeline):
        self.probe_root, self.services, self.broker, self.timeline = root, services, broker, timeline
        self.clients, self.events, self.methods, self.replies = [], [], [], {}
        self.issuer_closed = False
        self.cwd = None
        super().__init__(trace, command, execution_evidence="synthetic",
                         limits=PrivateEvidenceLimits(capture=derived.LIMITS),
                         preparation=self.prepare_managed, preparation_timeout=8)

    def _worker(self, store):
        worker = super()._worker(store)
        factory = worker._client_factory
        def guarded_factory(*args, **kwargs):
            client = factory(*args, **kwargs)  # Retains _PrivateClient and its tracked reader.
            # Clear the host environment before even the authored Python/ELF
            # launcher starts; bwrap's later clearenv alone is insufficient.
            client.env, client.inherit_env = {}, False
            self.clients.append(client)
            self.cwd = str(kwargs["cwd"])
            request, notify, receive = client.request, client.notify, client.recv_event
            def checked_request(method, params=None, *, timeout=30):
                try: self.check_request(method, params)
                except Exception:
                    self.services.abort.set()
                    raise
                result = request(method, params, timeout=timeout)
                if method in {"initialize", "thread/start", "turn/start", "mcpServerStatus/list"}:
                    self.replies[method] = result
                elif self.services.variant == PRODUCT_CASE:
                    key = ["initialize", "initialAccount", "initialConfig", "loginStart",
                           "orderedAccount", "orderedConfig", "thread/start", "mcpServerStatus/list", "turn/start"][len(self.methods)-1]
                    self.replies[key] = result
                return result
            def checked_notify(method, params=None):
                if method != "initialized": raise ValueError("fixture refuses notification")
                return notify(method, params)
            def checked_respond(*args, **kwargs):
                self.services.abort.set()
                raise ValueError("fixture refuses all native interactive requests")
            def checked_receive(*, timeout=None):
                event = receive(timeout=timeout)
                if len(self.events) >= MAX_EVENTS: raise ValueError("fixture native event limit")
                self.events.append(event)
                self.timeline.add("nativeEvent", event=event)
                try: transport.inspect_event(event)
                except Exception:
                    self.services.abort.set()
                    raise
                return event
            client.request, client.notify, client.respond, client.recv_event = (
                checked_request, checked_notify, checked_respond, checked_receive)
            return client
        worker._client_factory = guarded_factory
        return worker

    def check_request(self, method, params):
        if self.services.abort.is_set(): raise ValueError("fixture stopped before next RPC")
        order = ["initialize", "account/read", "config/read", "account/login/start",
                 "account/read", "config/read", "thread/start", "mcpServerStatus/list", "turn/start"]
        if len(self.methods) >= len(order) or method != order[len(self.methods)]:
            raise ValueError("owned fixture RPC order differs")
        expected = None
        if method == "account/read": expected = {"refreshToken": False}
        elif method == "config/read": expected = {"includeLayers": False}
        elif method == "account/login/start": expected = {"type": "chatgptDeviceCode"}
        elif method == "thread/start":
            if not self.issuer_closed: raise ValueError("issuer must close before thread")
            expected = {"cwd": self.cwd, "approvalPolicy": "never", "sandbox": "read-only", "environments": [],
                        "ephemeral": False, "threadSource": "nema-investigation", "config": dict(THREAD_CONFIG)}
            self.timeline.add("threadStartRequested")
        elif method in {"mcpServerStatus/list", "turn/start"}:
            thread_id = self.replies["thread/start"]["thread"]["id"]
            expected = ({"threadId": thread_id, "cursor": None, "limit": 100, "detail": "toolsAndAuthOnly"}
                        if method == "mcpServerStatus/list" else
                        {"threadId": thread_id, "input": [{"type": "text", "text": self.services.prompt}],
                         "sandboxPolicy": dict(TURN_SANDBOX), "environments": []})
        if expected is not None and params != expected: raise ValueError("owned fixture RPC parameters differ")
        self.methods.append(method)

    def prepare_managed(self, preparation):
        replies = self.replies
        replies["initialAccount"] = preparation.request("account/read", {"refreshToken": False})
        if replies["initialAccount"] != {"account": None, "requiresOpenaiAuth": True}:
            raise ValueError("initial managed auth is not fresh/empty")
        replies["initialConfig"] = preparation.request("config/read", {"includeLayers": False})
        validate_config(replies["initialConfig"], owned_worker=True)
        policy = json.loads((self.probe_root / "state/policy.json").read_text())
        if not policy["installedBeforeInitialExec"] or not policy["allListenerCopiesClosed"]:
            raise ValueError("recorded process filter absent")
        replies["loginStart"] = preparation.request("account/login/start", {"type": "chatgptDeviceCode"})
        preparation.phase("awaiting-sign-in")
        for expected in (LOGIN_COMPLETED, "account/updated"):
            while True:
                event = preparation.recv_event()
                validate_waited_event(event, expected)
                if event.get("method") == expected: break
            if expected == LOGIN_COMPLETED:
                validate_login_completed(event, replies["loginStart"]["loginId"])
            else:
                replies["accountUpdated"] = event
        preparation.phase("checking")
        replies["orderedAccount"] = preparation.request("account/read", {"refreshToken": False})
        replies["orderedConfig"] = preparation.request("config/read", {"includeLayers": False})
        validate_config(replies["orderedConfig"], owned_worker=True)
        plan = account_plan(replies["orderedAccount"])
        updated = replies["accountUpdated"]["params"]
        if plan != "plus" or updated.get("planType") != plan or updated.get("authMode") != "chatgpt":
            raise ValueError("ordered synthetic Plus acknowledgement differs")
        self.timeline.add("orderedConfigSucceeded")
        self.broker.close_authority(ISSUER_AUTHORITY)
        self.timeline.add("issuerClosed", connectCount=self.broker.connections,
                          issuerHttpRequests=sum(e["side"] == "issuer" for e in self.services.events))
        self.issuer_closed = True
        self.services.provider_enabled = True


class ProductManagedWorker(OwnedManagedWorker):
    """Same guarded private worker; preparation/admission are production code."""

    def __init__(self, trace, *, root, services, broker, timeline):
        self.probe_root, self.services, self.broker, self.timeline = root, services, broker, timeline
        self.clients, self.events, self.methods, self.replies = [], [], [], {}
        self.issuer_closed, self.cwd, self.runtime = False, None, None
        self.close_transports = None
        def factory(cwd, **kwargs):
            return OfflineManagedRuntime(self, cwd, **kwargs)
        profile = ManagedExecutionProfile(policy=product_fixture_policy(), runtime_factory=factory)
        PrivateInvestigationWorker.__init__(self, trace, managed_profile=profile,
            limits=PrivateEvidenceLimits(capture=derived.LIMITS))


def trace_rows(trace):
    return [{"seq": row.seq, "source": row.source, "direction": row.direction, "rawText": row.raw_text}
            for row in trace.records()]


def terminal_turn(message):
    params = message.get("params")
    turn = params.get("turn") if isinstance(params, dict) else None
    return turn if isinstance(turn, dict) else None


def run_worker_case(helper: Path, paths: dict[str, Path], *, product_managed: bool = False) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="nema-managed-worker-") as temporary:
        root = Path(temporary)
        if product_managed: prepare_product_case(root, helper, paths)
        else: prepare_case(root, helper, paths, owned_worker=True)
        trace = TraceStore(root / "trace.db")
        store, work = transport.fixture_work(trace)
        context, attempt = work["contexts"][0], work["attempt"]
        (root / "packet/context.json").write_text(json.dumps(context))
        timeline = Timeline()
        services = Services(PRODUCT_CASE if product_managed else WORKER_CASE, context["projectedPrompt"], timeline)
        issuer_tls = tls.TlsFixture("", "valid", paths, endpoint=Endpoint(services, "issuer"),
                                   certificate="productIssuer" if product_managed else "issuer")
        provider_tls = tls.TlsFixture("", "valid", paths, endpoint=Endpoint(services, "provider"),
                                     certificate="productProvider" if product_managed else None)
        broker = (product_fixture_broker(issuer_tls, provider_tls) if product_managed else
                  tls.ConnectBroker(destinations={ISSUER_AUTHORITY: issuer_tls.open_endpoint,
                                                  tls.AUTHORITY: provider_tls.open_endpoint}))
        broker.admit()
        command = None if product_managed else worker_launcher(root)
        owned = (ProductManagedWorker(trace, root=root, services=services, broker=broker, timeline=timeline)
                 if product_managed else
                 OwnedManagedWorker(trace, command, root=root, services=services, broker=broker, timeline=timeline))
        owned.reserve(attempt["id"])
        failure = artifact = final_work = proof = replay = reopened_artifact = None
        recovery_failure = None
        cleanup_errors = []
        def cleanup(name, action):
            try:
                return action()
            except Exception as exc:
                detail = str(exc)
                cleanup_errors.append({"operation": name, "type": type(exc).__name__,
                                       "detail": detail[:16000], "detailComplete": len(detail) <= 16000})
                return None
        inquiry_before = inquiry_reopened = None
        durable = False
        progress = []
        expired, observer_stop, server_stop = threading.Event(), threading.Event(), threading.Event()
        def expire():
            expired.set()
            owned.cancel(attempt["id"])
        def abort_native():
            while not observer_stop.is_set():
                if services.abort.wait(.05):
                    if not observer_stop.is_set(): owned.cancel(attempt["id"])
                    return
        def update(**fields):
            progress.append(fields)
            store.update_attempt(work["id"], expected_attempt_id=attempt["id"], **fields)
        class Handler(socketserver.BaseRequestHandler):
            def handle(self):
                try:
                    response = broker.exchange(self.request)
                    stop_on_connect_exhaustion(services, broker)
                    self.request.sendall(response)
                except OSError: pass
        with socketserver.UnixStreamServer(str(root / "broker.sock"), Handler) as server:
            server.timeout = .05
            def serve():
                while not server_stop.is_set(): server.handle_request()
            server_worker = threading.Thread(target=serve, daemon=True)
            abort_worker = threading.Thread(target=abort_native, daemon=True)
            server_worker.start()
            abort_worker.start()
            if product_managed:
                def close_transports():
                    observer_stop.set(); server_stop.set(); services.abort.set()
                    errors = []
                    for closer in (broker.close, issuer_tls.close, provider_tls.close):
                        try: closer()
                        except Exception as exc: errors.append(type(exc).__name__)
                    for thread in (server_worker, abort_worker):
                        if thread is not threading.current_thread(): thread.join(3)
                        if thread.is_alive(): errors.append("fixture-worker-not-joined")
                    if errors: raise RuntimeError("offline transports did not close: " + ",".join(errors))
                owned.close_transports = close_transports
            watchdog = threading.Timer(transport.CASE_SECONDS, expire)
            watchdog.daemon = True
            watchdog.start()
            try:
                artifact = owned.run(attempt, context, update)
                final_work = store.complete(work["id"], artifact, expected_attempt_id=attempt["id"])
                resolved = owned.resolve_result_evidence(final_work["attempt"], context, final_work["artifact"])
                proof = {key: value for key, value in resolved.items() if key != "trace"}
                inquiry_before = terminal_inquiry(store, work["id"], owned)
            except Exception as exc:
                failure = {"type": type(exc).__name__, "message": str(exc)}
            finally:
                watchdog.cancel()
                cleanup("watchdog.join", lambda: watchdog.join(1))
                observer_stop.set()
                services.abort.set()
                services.release.set()
                cleanup("abort_worker.join", lambda: abort_worker.join(1))
                cleanup("owned.close", owned.close)
                server_stop.set()
                cleanup("broker.close", broker.close)
                cleanup("issuer_tls.close", issuer_tls.close)
                cleanup("provider_tls.close", provider_tls.close)
                cleanup("server_worker.join", lambda: server_worker.join(3))
        clients = owned.clients
        private = list(owned._stores.values())
        private_records = trace_rows(private[0]) if len(private) == 1 else []
        public_records = trace_rows(trace)
        binding = trace.db.execute("SELECT * FROM private_investigation_bindings WHERE attempt_id=?", (attempt["id"],)).fetchone()
        ledger = trace.db.execute("SELECT * FROM private_investigation_publications WHERE attempt_id=?", (attempt["id"],)).fetchone()
        saved_attempt = store.get(work["id"])["attempt"]
        cleanup("owned.close_evidence", owned.close_evidence)
        cleanup("trace.close", trace.close)
        reopened_control = None
        if final_work is not None:
            reopened = TraceStore(root / "trace.db")
            reader = PrivateInvestigationWorker(reopened, command=["/never-start-native"])
            try:
                saved = InvestigationStore(reopened).get(work["id"])
                reopened_artifact = saved["artifact"]
                replay = reader.recover(saved["attempt"], context)
                resolved = reader.resolve_result_evidence(saved["attempt"], context, saved["artifact"])
                reopened_proof = {key: value for key, value in resolved.items() if key != "trace"}
                reopened_control = reader.inspect_owned(saved["attempt"]["id"])
                inquiry_reopened = terminal_inquiry(InvestigationStore(reopened), work["id"], reader)
                durable = (saved == final_work and replay == artifact and proof == reopened_proof
                           and inquiry_before == inquiry_reopened)
                if not durable: raise ValueError("private owned recovery differs after reopen")
            except Exception as exc:
                recovery_failure = {"type": type(exc).__name__, "message": str(exc)}
            finally:
                cleanup("reopened_worker.close", reader.close)
                cleanup("reopened_worker.close_evidence", reader.close_evidence)
                cleanup("reopened_trace.close", reopened.close)
        terminals = [terminal_turn(json.loads(row["rawText"])) for row in private_records
                     if json.loads(row["rawText"]).get("method") == "turn/completed"]
        policy_path = root / "state/policy.json"
        initialization = owned.replies.get("initialize")
        report = {"case": PRODUCT_CASE if product_managed else WORKER_CASE,
            "classification": "NATIVE_MANAGED_AUTH_SYNTHETIC_FIXTURE", "failure": failure,
            "command": (owned.runtime.command if owned.runtime is not None else None) if product_managed else command,
            "requestedConfigToml": managed_config() if product_managed else fixture_config(owned_worker=True),
            "policy": json.loads(policy_path.read_text()) if policy_path.exists() else None,
            "nativeReplies": owned.replies, "nativeEvents": owned.events,
            "nativeCapture": clients[0].capture_status if len(clients) == 1 else None,
            "nativeStderr": clients[0].stderr_tail if len(clients) == 1 else [],
            "traceRecords": public_records, "privateTraceRecords": private_records, "selectedContext": context,
            "binding": dict(binding) if binding else None, "publicationLedger": dict(ledger) if ledger else None,
            "nativeMethodsObserved": owned.methods, "nativeLoginRPCs": owned.methods.count("account/login/start"),
            "nativeThreadRPCs": owned.methods.count("thread/start"), "nativeTurnRPCs": owned.methods.count("turn/start"),
            "nativeTurnOutcome": terminals[-1] if terminals else None, "nativeTerminalRecovered": proof is not None,
            "nativeUserAgent": initialization.get("userAgent") if isinstance(initialization, dict) else None,
            "workerCwd": owned.cwd, "cwdMapping": "same-spelling-only; fresh namespace tmpfs directory; no host cwd mount",
            "threadEphemeral": False, "credentialsStore": "ephemeral", "afterTurnAccountObserved": False,
            "preparationTimeoutSeconds": 8, "declaredTurnTimeoutSeconds": attempt["timeoutSeconds"],
            "effectiveOuterSeconds": transport.CASE_SECONDS, "outerDeadlineExpired": expired.is_set(),
            "cleanupErrors": cleanup_errors,
            "progress": progress, "resolvedEvidence": proof, "reopenedControl": reopened_control,
            "terminalInquiryBefore": inquiry_before, "terminalInquiryReopened": inquiry_reopened,
            "recoveredArtifact": artifact, "savedArtifact": final_work["artifact"] if final_work else None,
            "savedAttempt": saved_attempt, "reopenedArtifact": reopened_artifact,
            "replayRecoveredArtifact": replay, "durableReopenMatches": durable, "durableReopenFailure": recovery_failure,
            "endpointEvents": services.events, "fixtureTokenGenerations": services.generations, "authoredTokens": services.tokens,
            "issuerHttpRequests": sum(e["side"] == "issuer" for e in services.events),
            "providerHttpRequests": sum(e["side"] == "provider" for e in services.events),
            "fixtureViolations": services.violations, "timeline": timeline.events,
            "connectEvents": broker.events, "connectAttempts": broker.attempts, "processedConnects": broker.connections,
            "unrecordedConnectRefusals": broker.unrecorded_refusals, "closedAuthorities": sorted(broker.closed_authorities),
            "mappedEndpointOpens": broker.opened, "remainingActiveTunnels": broker.active,
            "tlsHandshakeEvents": {"issuer": issuer_tls.tls_events, "provider": provider_tls.tls_events},
            "allWorkersJoined": not cleanup_errors and all(not thread.is_alive() for thread in [watchdog, server_worker, abort_worker,
                *issuer_tls.workers, *provider_tls.workers, *[c._reader for c in clients if c._reader is not None]]),
            "authFileExists": (root / "state/codex/auth.json").exists(),
            "providerRequestAnalyses": [catalog.analyze_request(e, context["projectedPrompt"])
                for e in services.events if e.get("reason") == "authored-managed-text"]}
        if product_managed:
            report.update(managedRuntime=owned.runtime.evidence if owned.runtime is not None else None,
                          managedClose=owned.runtime._report if owned.runtime is not None else None,
                          managedPolicy=product_fixture_policy().as_dict(),
                          stateRetainedForFixtureInspection=True,
                          authFileInspectedBeforeStateRemoval=True)
        # Public synthetic evidence, not an export path for real private accounts.
        report = json.loads(json.dumps(report))
        report["assessmentProblems"] = assess_worker_case(report)
        report["positiveOwnedWorkerAccepted"] = not report["assessmentProblems"]
        return report


def run_case(helper: Path, paths: dict[str, Path], variant: str) -> dict[str, Any]:
    if variant == PRODUCT_CASE:
        return run_worker_case(helper, paths, product_managed=True)
    if variant == WORKER_CASE:
        return run_worker_case(helper, paths)
    with tempfile.TemporaryDirectory(prefix="nema-managed-case-") as temporary:
        root = Path(temporary)
        prepare_case(root, helper, paths)
        trace = TraceStore(root / "trace.db")
        store, work = transport.fixture_work(trace)
        context = work["contexts"][0]
        (root / "packet/context.json").write_text(json.dumps(context))
        timeline = Timeline()
        services = Services(variant, context["projectedPrompt"], timeline)
        issuer_tls = tls.TlsFixture("", "valid", paths, endpoint=Endpoint(services, "issuer"), certificate="issuer")
        provider_tls = tls.TlsFixture("", "valid", paths, endpoint=Endpoint(services, "provider"))
        broker = tls.ConnectBroker(destinations={ISSUER_AUTHORITY: issuer_tls.open_endpoint,
                                                tls.AUTHORITY: provider_tls.open_endpoint})
        broker.admit()
        replies, events = {}, []
        failure = policy = outcome = None
        held_overtaken = False
        candidate_rejected = False
        recovered = final_work = reopened_artifact = replay = recovery_failure = None
        durable = False

        class Handler(socketserver.BaseRequestHandler):
            def handle(self):
                try:
                    response = broker.exchange(self.request)
                    stop_on_connect_exhaustion(services, broker)
                    self.request.sendall(response)
                except OSError: pass

        def consume(client, timeout):
            if len(events) >= MAX_EVENTS: raise RuntimeError("native event limit")
            event = client.recv_event(timeout=timeout)
            events.append(event)
            timeline.add("nativeEvent", event=event)
            transport.inspect_event(event)
            if services.violations: raise RuntimeError("unexpected fixture request: " + str(services.violations))
            return event

        def wait_event(client, method, *, login_id=None, timeout=4):
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                event = consume(client, max(.001, deadline - time.monotonic()))
                validate_waited_event(event, method)
                if event.get("method") == method:
                    if login_id is not None and event.get("params", {}).get("loginId") != login_id:
                        raise RuntimeError("login completion identity differs")
                    return event
            raise TimeoutError(method)

        with socketserver.UnixStreamServer(str(root / "broker.sock"), Handler) as server:
            server.timeout = .05
            stop = threading.Event()
            def serve():
                while not stop.is_set(): server.handle_request()
            worker = threading.Thread(target=serve, daemon=True)
            worker.start()
            command = boundary.namespace_command(root, Path("/usr/bin/bwrap"), ["/usr/bin/python3", "/fixture/launcher.py"], broker=True)
            client = ManagedClient(command, trace=trace, cwd=root, env={}, inherit_env=False,
                                   source="synthetic-managed-lifecycle/" + variant, limits=derived.LIMITS)
            client.fixture_abort = services.abort
            watchdog = threading.Timer(transport.CASE_SECONDS, client.close)
            watchdog.daemon = True
            watchdog.start()
            observer_stop = threading.Event()
            def abort_native():
                while not observer_stop.is_set():
                    if services.abort.wait(.05):
                        if not observer_stop.is_set(): client.close()
                        return
            abort_worker = threading.Thread(target=abort_native, daemon=True)
            abort_worker.start()
            try:
                replies["initialize"] = client.initialize()
                replies["initialAccount"] = client.request("account/read", {"refreshToken": False})
                if replies["initialAccount"] != {"account": None, "requiresOpenaiAuth": True}:
                    raise RuntimeError("initial managed auth is not fresh/empty")
                replies["initialConfig"] = client.request("config/read", {"includeLayers": False})
                validate_config(replies["initialConfig"])
                policy = json.loads((root / "state/policy.json").read_text())
                if not policy["installedBeforeInitialExec"] or not policy["allListenerCopiesClosed"]:
                    raise RuntimeError("recorded process filter absent")
                replies["loginStart"] = client.request("account/login/start", {"type": "chatgptDeviceCode"})
                login_id = replies["loginStart"]["loginId"]
                completed = wait_event(client, LOGIN_COMPLETED, login_id=login_id)
                validate_login_completed(completed, login_id)
                if variant == "nearExpiry":
                    if not services.held.wait(.5): raise RuntimeError("post-login refresh did not start")
                    deadline = time.monotonic() + .15
                    while time.monotonic() < deadline:
                        try: event = consume(client, max(.001, deadline - time.monotonic()))
                        except TimeoutError: break
                        if event.get("method") == "account/updated": held_overtaken = True
                    timeline.add("releaseHeldRefresh", accountUpdatedOvertook=held_overtaken)
                    services.release.set()
                    if held_overtaken: raise RuntimeError("account update overtook held refresh")
                updated = wait_event(client, "account/updated")
                replies["accountUpdated"] = updated
                if updated["params"].get("authMode") != "chatgpt": raise RuntimeError("unexpected updated auth mode")
                replies["orderedAccount"] = client.request("account/read", {"refreshToken": False})
                timeline.add("orderedAccountResponse", reply=replies["orderedAccount"])
                replies["orderedConfig"] = client.request("config/read", {"includeLayers": False})
                validate_config(replies["orderedConfig"])
                timeline.add("orderedConfigSucceeded")
                plan = account_plan(replies["orderedAccount"])
                if plan != updated["params"].get("planType"): raise RuntimeError("ordered plan acknowledgement differs")
                candidate_rejected = plan not in ("plus", "pro")
                if variant == "nearExpiry":
                    if plan != "free": raise RuntimeError("changed fixture plan not acknowledged")
                    timeline.add("fixtureCandidateRejected", plan=plan)
                else:
                    if candidate_rejected: raise RuntimeError("baseline Plus missing")
                    broker.close_authority(ISSUER_AUTHORITY)
                    timeline.add("issuerClosed", closedAuthorities=sorted(broker.closed_authorities),
                                 mappedEndpointOpens=broker.opened, connectCount=broker.connections,
                                 issuerHttpRequests=sum(event["side"] == "issuer" for event in services.events))
                    client.issuer_closed = True
                    services.provider_enabled = True
                    client.expected_thread = {"cwd": "/state/workspace", "approvalPolicy": "never", "sandbox": "read-only",
                        "environments": [], "ephemeral": True, "model": derived.MODEL, "modelProvider": "openai",
                        "baseInstructions": "Authored offline authentication fixture; no tools or actions are requested."}
                    timeline.add("threadStartRequested")
                    replies["threadStart"] = client.request("thread/start", client.expected_thread)
                    NativeInvestigationWorker._check_thread_policy(replies["threadStart"], "/state/workspace")
                    thread_id = replies["threadStart"]["thread"]["id"]
                    if variant == POSITIVE_CASE:
                        store.update_attempt(work["id"], source=client.source, threadId=thread_id, status="running")
                        trace.append(source=client.source, direction="internal", message={
                            "method": "$native/profile", "params": {
                                "admission": "custom-command-trusted-host", "executionEvidence": "synthetic",
                                "fixture": "offline-managed-text", "liveAdmitted": False}})
                    client.expected_turn = {"threadId": thread_id, "input": [{"type": "text", "text": context["projectedPrompt"]}]}
                    replies["turnStart"] = client.request("turn/start", client.expected_turn)
                    turn_id = replies["turnStart"]["turn"]["id"]
                    if variant == POSITIVE_CASE: store.update_attempt(work["id"], turnId=turn_id)
                    deadline = time.monotonic() + 8
                    try:
                        while time.monotonic() < deadline:
                            event = consume(client, max(.001, deadline - time.monotonic()))
                            if (event.get("method") == "turn/completed" and event.get("params", {}).get("threadId") == thread_id
                                    and event["params"].get("turn", {}).get("id") == turn_id):
                                outcome = event["params"]["turn"]
                                break
                        if outcome is None: outcome = {"status": "consumer-timeout"}
                    except TimeoutError: outcome = {"status": "consumer-timeout"}
                    replies["afterTurnAccount"] = client.request("account/read", {"refreshToken": False}, timeout=2)
                    timeline.add("afterTurnAccountResponse", reply=replies["afterTurnAccount"])
                    if account_plan(replies["afterTurnAccount"]) != "plus": raise RuntimeError("unexpected account change after issuer closure")
                if services.violations: raise RuntimeError("unexpected fixture requests")
            except Exception as exc:
                failure = {"type": type(exc).__name__, "message": str(exc)}
            finally:
                watchdog.cancel()
                observer_stop.set()
                services.abort.set()
                services.release.set()
                abort_worker.join(1)
                client.close()
                stop.set()
                broker.close()
                issuer_tls.close()
                provider_tls.close()
                worker.join(3)
                if worker.is_alive(): raise RuntimeError("fixture server failed to join")
        if variant == POSITIVE_CASE and failure is None:
            try:
                capture = client.capture_status
                if capture["failure"] is not None or capture["diagnosticError"] is not None:
                    raise RuntimeError("positive recovery requires intact reported capture")
                attempt = store.get(work["id"])["attempt"]
                recovered = NativeInvestigationWorker(trace, command=["/never-start-native"]).recover(attempt, context)
                if (recovered is None or recovered["text"] != transport.OUTPUT_TEXT
                        or recovered["executionEvidence"] != "synthetic"):
                    raise RuntimeError("correlated synthetic artifact was not recovered")
                final_work = store.complete(work["id"], recovered, expected_attempt_id=attempt["id"])
            except Exception as exc:
                failure = {"type": type(exc).__name__, "message": str(exc)}
        records = [{"seq": row.seq, "source": row.source, "direction": row.direction, "rawText": row.raw_text} for row in trace.records()]
        sent_methods = [json.loads(row["rawText"]).get("method") for row in records if row["direction"] == "client_to_appserver"]
        trace.close()
        if variant == POSITIVE_CASE and final_work is not None:
            reopened = TraceStore(root / "trace.db")
            try:
                saved = InvestigationStore(reopened).get(work["id"])
                reopened_artifact = saved["artifact"]
                replay = NativeInvestigationWorker(reopened, command=["/never-start-native"]).recover(saved["attempt"], context)
                durable = saved == final_work and replay == recovered
                if not durable: raise RuntimeError("durable synthetic recovery differs")
            except Exception as exc:
                recovery_failure = {"type": type(exc).__name__, "message": str(exc)}
            finally: reopened.close()
        report = {"case": variant, "classification": "NATIVE_MANAGED_AUTH_SYNTHETIC_FIXTURE", "failure": failure,
            "command": command, "requestedConfigToml": fixture_config(), "policy": policy,
            "nativeReplies": replies, "nativeEvents": events, "nativeCapture": client.capture_status,
            "nativeStderr": client.stderr_tail, "traceRecords": records, "selectedContext": context,
            "nativeMethodsObserved": client.methods, "nativeLoginRPCs": client.login_count,
            "nativeThreadRPCs": client.thread_count, "nativeTurnRPCs": client.turn_count, "nativeTurnOutcome": outcome,
            "nativeTurnRPCsRecordedOutbound": sent_methods.count("turn/start"),
            "nativeTurnsAcknowledged": int("turnStart" in replies),
            "nativeUserAgent": replies.get("initialize", {}).get("userAgent"),
            "fixtureCandidateRejected": candidate_rejected, "accountUpdatedOvertookHeldRefresh": held_overtaken,
            "endpointEvents": services.events, "fixtureTokenGenerations": services.generations,
            "authoredTokens": services.tokens, "issuerHttpRequests": sum(event["side"] == "issuer" for event in services.events),
            "providerHttpRequests": sum(event["side"] == "provider" for event in services.events),
            "fixtureViolations": services.violations, "timeline": timeline.events,
            "connectEvents": broker.events, "connectAttempts": broker.attempts, "processedConnects": broker.connections,
            "unrecordedConnectRefusals": broker.unrecorded_refusals, "closedAuthorities": sorted(broker.closed_authorities),
            "mappedEndpointOpens": broker.opened,
            "tlsHandshakeEvents": {"issuer": issuer_tls.tls_events, "provider": provider_tls.tls_events},
            "allWorkersJoined": all(not item.is_alive() for item in [worker, abort_worker, *issuer_tls.workers, *provider_tls.workers]),
            "remainingActiveTunnels": broker.active, "authFileExists": (root / "state/codex/auth.json").exists()}
        if variant == POSITIVE_CASE:
            report.update(recoveredArtifact=recovered, savedArtifact=final_work["artifact"] if final_work else None,
                          savedAttempt=final_work["attempt"] if final_work else None,
                          reopenedArtifact=reopened_artifact, replayRecoveredArtifact=replay,
                          durableReopenMatches=durable, durableReopenFailure=recovery_failure,
                          providerRequestAnalyses=[catalog.analyze_request(event, context["projectedPrompt"])
                              for event in services.events if event.get("reason") == "authored-managed-text"])
        report = json.loads(json.dumps(report).replace(str(root), "<probe>"))
        report["assessmentProblems"] = assess_case(report)
        report["positiveManagedTextAccepted" if variant == POSITIVE_CASE else "boundedNegativeEvidenceAccepted"] = not report["assessmentProblems"]
        report["nativeTerminalRecovered"] = bool(outcome and outcome.get("id"))
        return report


def assess_case(case: dict[str, Any]) -> list[str]:
    """Post-effect synthetic evidence checks; this does not authorize a native process."""
    if case["case"] in (WORKER_CASE, PRODUCT_CASE):
        return assess_worker_case(case)
    problems = []
    resource_stop = (case["case"] == "closedIssuer401"
                     and case["fixtureViolations"] == ["connect-limit-exhausted"]
                     and case["unrecordedConnectRefusals"] > 0
                     and any(e["kind"] == "fixtureResourceStop" and e.get("reason") == "connect-limit-exhausted"
                             for e in case["timeline"]))
    failure = case["failure"]
    expected_stop_error = (resource_stop and failure and (
        failure["type"] == "AppServerClosed"
        or failure == {"type": "ValueError", "message": "fixture stopped before next RPC"}
        or failure == {"type": "RuntimeError", "message": "unexpected fixture request: ['connect-limit-exhausted']"}))
    if failure is not None and not expected_stop_error: problems.append("driver-failure")
    if case["nativeLoginRPCs"] != 1: problems.append("login-attempt-count-differs")
    for name in ("initialConfig", "orderedConfig"):
        try: validate_config(case["nativeReplies"][name])
        except (KeyError, ValueError, TypeError): problems.append(name + "-controls-differ")
    capture = case["nativeCapture"]
    if capture["failure"] is not None or capture["diagnosticError"] is not None:
        problems.append("reported-capture-gap")
    if capture["limits"] != asdict(derived.LIMITS): problems.append("capture-limits-differ")
    records = [(row, json.loads(row["rawText"])) for row in case["traceRecords"]]
    sources = {row["source"] for row, msg in records if row["direction"] == "client_to_appserver"
               and msg.get("method") == "account/login/start"}
    internal = [(row["source"], msg) for row, msg in records if row["direction"] == "internal"]
    limits = [(source, msg.get("params", {}).get("limits")) for source, msg in internal
              if msg.get("method") == "$transport/limits"]
    if len(sources) != 1 or limits != [(next(iter(sources), None), asdict(derived.LIMITS))]:
        problems.append("source-matched-limits-absent")
    if any(msg.get("method") == "$transport/captureGap" for _, msg in internal):
        problems.append("recorded-capture-gap")
    native = [msg for row, msg in records if row["direction"] == "appserver_to_client"]
    completed = [i for i, msg in enumerate(native) if msg.get("method") == LOGIN_COMPLETED]
    updated = [i for i, msg in enumerate(native) if msg.get("method") == "account/updated"]
    if len(completed) != 1 or len(updated) != 1 or completed[0] >= updated[0]:
        problems.append("login-update-order-differs")
    else:
        try: validate_login_completed(native[completed[0]], case["nativeReplies"]["loginStart"]["loginId"])
        except (KeyError, ValueError): problems.append("login-identity-differs")
    if not case["allWorkersJoined"] or case["remainingActiveTunnels"]: problems.append("fixture-not-closed")
    if (case["fixtureViolations"] or case["unrecordedConnectRefusals"]) and not resource_stop:
        problems.append("fixture-refusal-or-exhaustion")
    if case["authFileExists"]: problems.append("ephemeral-auth-file-present")
    timeline = case["timeline"]
    def index(kind): return next((i for i, e in enumerate(timeline) if e["kind"] == kind), -1)
    if case["case"] == "nearExpiry":
        if (case["fixtureTokenGenerations"] != ["A", "B"] or not case["fixtureCandidateRejected"]
                or case["nativeThreadRPCs"] or case["nativeTurnRPCs"] or case["providerHttpRequests"]):
            problems.append("changed-plan-rejection-differs")
        if (case["nativeReplies"].get("orderedAccount", {}).get("account", {}).get("planType") != "free"
                or case["accountUpdatedOvertookHeldRefresh"]): problems.append("free-plan-ack-absent")
        release = index("releaseHeldRefresh")
        ack = next((i for i, e in enumerate(timeline) if e["kind"] == "nativeEvent"
                    and e["event"].get("method") == "account/updated"), -1)
        if not 0 <= index("issuerRefreshHeld") < release < ack: problems.append("held-refresh-order-differs")
    else:
        sent_turns = [msg for row, msg in records if row["direction"] == "client_to_appserver"
                      and msg.get("method") == "turn/start"]
        turn_ack = case["nativeReplies"].get("turnStart")
        thread_id = case["nativeReplies"].get("threadStart", {}).get("thread", {}).get("id")
        matching_replies = ([msg for msg in native if msg.get("id") == sent_turns[0].get("id")
                             and "result" in msg] if len(sent_turns) == 1 else [])
        if (len(sent_turns) != 1 or len(matching_replies) != 1 or not isinstance(turn_ack, dict)
                or matching_replies[0]["result"] != turn_ack
                or not isinstance(turn_ack.get("turn", {}).get("id"), str)
                or not turn_ack["turn"]["id"]
                or sent_turns[0].get("params") != {"threadId": thread_id, "input": [
                    {"type": "text", "text": case["selectedContext"]["projectedPrompt"]}]}
                or case.get("nativeTurnRPCsRecordedOutbound") != 1
                or case.get("nativeTurnsAcknowledged") != 1):
            problems.append("correlated-turn-ack-absent")
        for name in ("orderedAccount", "afterTurnAccount"):
            if name == "afterTurnAccount" and name not in case["nativeReplies"] and expected_stop_error:
                continue  # No post-abort account observation is invented.
            try:
                if account_plan(case["nativeReplies"][name]) != "plus": problems.append(name + "-plan-differs")
            except (KeyError, ValueError, TypeError): problems.append(name + "-plan-absent")
        try: NativeInvestigationWorker._check_thread_policy(case["nativeReplies"]["threadStart"], "/state/workspace")
        except Exception: problems.append("thread-policy-not-acknowledged")
        closure = index("issuerClosed")
        if not 0 <= index("orderedConfigSucceeded") < closure < index("threadStartRequested"):
            problems.append("prethread-closure-order-differs")
        endpoints = case["endpointEvents"]
        statuses = [e["status"] for e in endpoints if e["side"] == "provider"]
        if case["case"] != POSITIVE_CASE and (426 not in statuses or 401 not in statuses or statuses.index(426) >= statuses.index(401)):
            problems.append("426-then-401-absent")
        settings = [e for e in endpoints if e["target"] == SETTINGS_PATH]
        if (len(settings) != 1 or settings[0]["status"] != 200 or settings[0]["method"] != "GET"
                or settings[0]["bodyRaw"] or json.loads(settings[0]["responseRaw"]) != {"commit_attribution_enabled": False}):
            problems.append("fixed-settings-observation-differs")
        connects = case["connectEvents"]
        expected_http = [("issuer", "POST", "/api/accounts/deviceauth/usercode", 200),
                         ("issuer", "POST", "/api/accounts/deviceauth/token", 200),
                         ("issuer", "POST", "/oauth/token", 200),
                         ("provider", "GET", PROVIDER_PATH, 426),
                         ("provider", "GET", SETTINGS_PATH, 200)]
        expected_http += ([("provider", "POST", PROVIDER_PATH, 200)] if case["case"] == POSITIVE_CASE else
                          [("provider", "POST", PROVIDER_PATH, 401)] * 2)
        expected_connects = ([(ISSUER_AUTHORITY, 200)] * 3 + [(tls.AUTHORITY, 200)] * 3
                             if case["case"] == POSITIVE_CASE else
                             [(ISSUER_AUTHORITY, 200)] * 3 + [(tls.AUTHORITY, 200)] * 4 + [(ISSUER_AUTHORITY, 403)])
        if ([(e["side"], e["method"], e["target"], e["status"]) for e in endpoints] != expected_http
                or [(e.get("authority"), e["status"]) for e in connects] != expected_connects):
            problems.append("serial-challenge-prefix-differs")
        if closure >= 0:
            after = connects[timeline[closure]["connectCount"]:]
            if case["case"] != POSITIVE_CASE and not any(e.get("authority") == ISSUER_AUTHORITY and e.get("status") == 403
                       and e.get("reason") == "destination-closed" for e in after):
                problems.append("closed-issuer-denial-absent")
            if any(e.get("authority") == ISSUER_AUTHORITY and e.get("status") == 200 for e in after):
                problems.append("issuer-reopened")
            if timeline[closure]["issuerHttpRequests"] != case["issuerHttpRequests"]:
                problems.append("issuer-http-after-closure")
        if case["fixtureTokenGenerations"] != ["A"]: problems.append("replacement-token-authored")
        if case["nativeThreadRPCs"] != 1 or case["nativeTurnRPCs"] != 1: problems.append("bounded-turn-absent")
        if case["case"] == POSITIVE_CASE:
            if (case["connectAttempts"] != 6 or case["mappedEndpointOpens"] != 6
                    or case["issuerHttpRequests"] != 3 or case["providerHttpRequests"] != 3):
                problems.append("positive-request-budget-differs")
            problems.extend(assess_positive_artifact(case))
    return problems


def recover_recorded_positive(case: dict[str, Any]) -> dict[str, Any] | None:
    """Re-evaluate captured native evidence in memory, never launch a process."""
    trace = TraceStore(":memory:")
    try:
        for row in case["traceRecords"]:
            record = trace.append_line(source=row["source"], direction=row["direction"], raw_text=row["rawText"])
            if record.seq != row["seq"]: raise ValueError("record sequence differs")
        return NativeInvestigationWorker(trace, command=["/never-start-native"]).recover(
            case["savedAttempt"], case["selectedContext"])
    finally: trace.close()


def recover_recorded_worker(case):
    """Reconstruct exact private evidence and validate the reported host ledger."""
    main = TraceStore(":memory:")
    private = TraceStore(":memory:", role="private-control")
    adapter = PrivateInvestigationWorker(main, command=["/never-start-native"])
    try:
        for target, rows in ((main, case["traceRecords"]), (private, case["privateTraceRecords"])):
            for row in rows:
                record = target.append_line(source=row["source"], direction=row["direction"], raw_text=row["rawText"])
                if record.seq != row["seq"]: raise ValueError("reported record sequence differs")
        binding, ledger = case["binding"], case["publicationLedger"]
        main.db.execute("INSERT INTO private_investigation_bindings VALUES (?,?,?,?,?)", tuple(binding[k] for k in
            ("attempt_id", "capsule_id", "context_id", "context_digest", "state_json")))
        main.db.execute("INSERT INTO private_investigation_publications VALUES (?,?,?,?)", tuple(ledger[k] for k in
            ("attempt_id", "capsule_id", "seq", "content_digest")))
        main.db.commit()
        validated = validate_publication(main, case["savedAttempt"], case["selectedContext"], case["savedArtifact"])
        recovered = NativeInvestigationWorker(private, command=["/never-start-native"]).recover(
            case["savedAttempt"], case["selectedContext"])
        return validated, recovered
    finally:
        adapter.close_evidence()
        main.close()
        private.close()


def assess_worker_case(case: dict[str, Any]) -> list[str]:
    """Pure joining-case evidence assessment; never a native admission."""
    try:
        return _assess_worker_case(case)
    except (KeyError, IndexError, AttributeError, TypeError, ValueError, RecursionError, ManagedLaunchError) as exc:
        # The report already retains the exact bounded records. An unknown
        # shape is failed evidence, never grounds to lose that report or accept.
        return ["malformed-worker-evidence:" + type(exc).__name__]


def _assess_worker_case(case: dict[str, Any]) -> list[str]:
    problems = []
    product = case.get("case") == PRODUCT_CASE
    if case.get("failure") is not None: problems.append("worker-failed")
    capture = case.get("nativeCapture") or {}
    if (capture.get("failure") is not None or capture.get("diagnosticError") is not None
            or capture.get("limits") != asdict(derived.LIMITS)):
        problems.append("worker-capture-differs")
    if (not case.get("allWorkersJoined") or case.get("remainingActiveTunnels") != 0
            or case.get("outerDeadlineExpired") or case.get("authFileExists") or case.get("cleanupErrors")):
        problems.append("worker-not-closed-cleanly")
    if (case.get("preparationTimeoutSeconds") != 8 or case.get("declaredTurnTimeoutSeconds") != 120
            or case.get("effectiveOuterSeconds") != transport.CASE_SECONDS):
        problems.append("worker-deadlines-differ")
    for name in ("initialConfig", "orderedConfig"):
        try:
            if product: validate_managed_config(case["nativeReplies"][name])
            else: validate_config(case["nativeReplies"][name], owned_worker=True)
        except (KeyError, ValueError, TypeError, ManagedLaunchError): problems.append(name + "-controls-differ")
    try:
        if case["nativeReplies"]["initialAccount"] != {"account": None, "requiresOpenaiAuth": True}:
            raise ValueError("not fresh")
        if account_plan(case["nativeReplies"]["orderedAccount"]) != "plus": raise ValueError("not Plus")
    except (KeyError, ValueError, TypeError): problems.append("worker-account-differs")
    if case.get("afterTurnAccountObserved") is not False or "afterTurnAccount" in case["nativeReplies"]:
        problems.append("invented-post-turn-observation")
    policy = case.get("policy") or {}
    if not policy.get("installedBeforeInitialExec") or not policy.get("allListenerCopiesClosed"):
        problems.append("worker-process-filter-absent")
    messages = [(row, json.loads(row["rawText"])) for row in case["privateTraceRecords"]]
    source = case["savedAttempt"].get("source")
    limits = [(row["source"], msg.get("params", {}).get("limits")) for row, msg in messages
              if row["direction"] == "internal" and msg.get("method") == "$transport/limits"]
    if limits != [(source, asdict(derived.LIMITS))] or any(msg.get("method") == "$transport/captureGap" for _, msg in messages):
        problems.append("worker-source-capture-gap")
    native = [msg for row, msg in messages if row["direction"] == "appserver_to_client" and row["source"] == source]
    completed = [i for i, msg in enumerate(native) if msg.get("method") == LOGIN_COMPLETED]
    updated = [i for i, msg in enumerate(native) if msg.get("method") == "account/updated"]
    try:
        if len(completed) != 1 or len(updated) != 1 or completed[0] >= updated[0]: raise ValueError("order")
        validate_login_completed(native[completed[0]], case["nativeReplies"]["loginStart"]["loginId"])
        if native[updated[0]]["params"].get("planType") != "plus": raise ValueError("plan")
    except (KeyError, ValueError, TypeError): problems.append("worker-login-correlation-differs")
    sent = [msg for row, msg in messages if row["direction"] == "client_to_appserver" and "id" in msg]
    order = ["initialize", "account/read", "config/read", "account/login/start", "account/read", "config/read",
             "thread/start", "mcpServerStatus/list", "turn/start"]
    if ([msg.get("method") for msg in sent] != order or case["nativeMethodsObserved"] != order
            or case["nativeLoginRPCs"] != 1 or case["nativeThreadRPCs"] != 1 or case["nativeTurnRPCs"] != 1):
        problems.append("worker-rpc-sequence-differs")
    try:
        guard = object.__new__(OwnedManagedWorker)
        guard.services = Services(WORKER_CASE, case["selectedContext"]["projectedPrompt"], Timeline())
        guard.methods, guard.replies = [], case["nativeReplies"]
        guard.cwd, guard.issuer_closed, guard.timeline = case["workerCwd"], True, Timeline()
        reply_keys = ["initialize", "initialAccount", "initialConfig", "loginStart", "orderedAccount", "orderedConfig",
                      "thread/start", "mcpServerStatus/list", "turn/start"]
        for msg, reply_key in zip(sent, reply_keys, strict=True):
            guard.check_request(msg["method"], msg.get("params"))
            matches = [reply for reply in native if reply.get("id") == msg["id"] and "method" not in reply]
            if len(matches) != 1 or "error" in matches[0]: raise ValueError("acknowledgement")
            if matches[0].get("result") != case["nativeReplies"][reply_key]: raise ValueError("ack differs")
        NativeInvestigationWorker._check_thread_policy(case["nativeReplies"]["thread/start"], case["workerCwd"])
        inventory = case["nativeReplies"]["mcpServerStatus/list"]
        if inventory.get("nextCursor") is not None or not isinstance(inventory.get("data"), list): raise ValueError("inventory")
        if any(not isinstance(server, dict) or server.get("tools") != {} or server.get("runtimeStatus") != "disabled" or server.get("toolsError") is not None
               for server in inventory["data"]): raise ValueError("enabled server")
    except (KeyError, ValueError, TypeError): problems.append("worker-packet-or-ack-differs")
    terminals = [terminal_turn(msg) for msg in native if msg.get("method") == "turn/completed"]
    if (len(terminals) != 1 or not isinstance(terminals[0], dict) or terminals[0] != case.get("nativeTurnOutcome")
            or terminals[0].get("status") != "completed" or not case.get("nativeTerminalRecovered")):
        problems.append("worker-terminal-differs")
    selected = case["selectedContext"]["records"]
    public = case["traceRecords"]
    if (len(public) != 3 or len(selected) != 2 or any(row["rawText"] != public[i]["rawText"]
            or row["source"] != public[i]["source"] or row["seq"] != public[i]["seq"]
            or row["sha256"] != hashlib.sha256(row["rawText"].encode()).hexdigest() for i, row in enumerate(selected))):
        problems.append("worker-public-input-differs")
    try:
        published, original = recover_recorded_worker(case)
        if (original is None or original["text"] != transport.OUTPUT_TEXT or original["executionEvidence"] != "synthetic"
                or original["citations"] != [1, 2] or original["unsupportedCitations"] != []): raise ValueError("native result")
        if any(published[k] != original[k] for k in ("text", "executionEvidence", "citations", "unsupportedCitations")):
            raise ValueError("publication")
        if published != case["recoveredArtifact"] or published != case["replayRecoveredArtifact"]:
            raise ValueError("recovered publication")
        proof = case["resolvedEvidence"]
        if (proof["artifact"] != original or proof["kind"] != "private-capsule"
                or proof["capsuleId"] != case["binding"]["capsule_id"]
                or proof["attempt"] != json.loads(case["binding"]["state_json"])["attempt"]):
            raise ValueError("private proof")
    except Exception: problems.append("worker-exact-private-public-recovery-differs")
    if (not case.get("durableReopenMatches") or case.get("durableReopenFailure") is not None
            or case.get("savedArtifact") != case.get("reopenedArtifact") or case["savedAttempt"].get("status") != "completed"
            or case.get("reopenedControl") != {"owned": False, "canCancel": False}):
        problems.append("worker-durable-reopen-differs")
    phases = [p["lifecycle"] for p in case.get("progress", []) if "lifecycle" in p]
    if ([p.get("phase") for p in phases] != ["preparing", "awaiting-sign-in", "checking", "running", "closed"]
            or phases[-1].get("stopReason") != "completed"
            or case.get("terminalInquiryBefore") is not None or case.get("terminalInquiryReopened") is not None
            or case.get("threadEphemeral") is not False or case.get("credentialsStore") != "ephemeral"):
        problems.append("worker-lifecycle-or-inquiry-differs")
    kinds = [e["kind"] for e in case["timeline"]]
    try:
        ordered, closed, thread = [kinds.index(k) for k in ("orderedConfigSucceeded", "issuerClosed", "threadStartRequested")]
        if not ordered < closed < thread or case["timeline"][closed]["connectCount"] != 3: raise ValueError("closure order")
    except (KeyError, ValueError): problems.append("worker-prethread-closure-differs")
    expected_http = [("issuer", "POST", "/api/accounts/deviceauth/usercode", 200),
        ("issuer", "POST", "/api/accounts/deviceauth/token", 200), ("issuer", "POST", "/oauth/token", 200),
        ("provider", "GET", PROVIDER_PATH, 426), ("provider", "GET", SETTINGS_PATH, 200), ("provider", "POST", PROVIDER_PATH, 200)]
    if ([(e["side"], e["method"], e["target"], e["status"]) for e in case["endpointEvents"]] != expected_http
            or [(e.get("authority"), e["status"]) for e in case["connectEvents"]] !=
                [(PRODUCT_ISSUER_AUTHORITY if product else ISSUER_AUTHORITY, 200)] * 3 +
                [(PRODUCT_PROVIDER_AUTHORITY if product else tls.AUTHORITY, 200)] * 3
            or any(case[k] != 6 for k in ("connectAttempts", "processedConnects", "mappedEndpointOpens"))
            or case["fixtureViolations"] or case["unrecordedConnectRefusals"] or case["fixtureTokenGenerations"] != ["A"]):
        problems.append("worker-endpoint-sequence-differs")
    try:
        event = case["endpointEvents"][-1]
        payload = strict_json(event["bodyRaw"])
        if (event["responseRaw"] != catalog.authored_stream(derived.MODEL, 2).decode()
                or event["responseContentType"] != "text/event-stream"
                or not catalog.provider_shape(payload, event["headers"], derived.MODEL, case["selectedContext"]["projectedPrompt"])
                or any(i.get("tools") for i in payload["input"] if i.get("type") == "additional_tools")
                or json.loads(case["endpointEvents"][-2]["responseRaw"]) != {"commit_attribution_enabled": False}):
            raise ValueError("provider payload")
    except (IndexError, KeyError, ValueError, TypeError): problems.append("worker-provider-evidence-differs")
    if product:
        try:
            runtime = case["managedRuntime"]
            if (case["requestedConfigToml"] != managed_config() or runtime["configSha256"] != hashlib.sha256(managed_config().encode()).hexdigest()
                    or runtime["catalogSha256"] != hashlib.sha256(managed_catalog()).hexdigest()
                    or runtime["transport"] != "authored-local" or runtime["classification"] != "synthetic"
                    or runtime["dns"] is not False or runtime["liveDial"] is not False
                    or runtime["destinations"] != [PRODUCT_ISSUER_AUTHORITY, PRODUCT_PROVIDER_AUTHORITY]
                    or runtime["limits"] != product_fixture_policy().as_dict()
                    or case["managedPolicy"] != product_fixture_policy().as_dict()
                    or case["managedClose"]["allWorkersJoined"] is not True or case["managedClose"]["errors"]
                    or case["stateRetainedForFixtureInspection"] is not True
                    or case["authFileInspectedBeforeStateRemoval"] is not True):
                raise ValueError("offline product boundary differs")
            host = [(row, message) for row, message in messages if row["source"] == source and row["direction"] == "internal"]
            admissions = [(row, message) for row, message in host if message.get("method") == "$native/managedAdmission"]
            startups = [(row, message) for row, message in host if message.get("method") == "$native/managedStartup"]
            closes = [(row, message) for row, message in host if message.get("method") == "$native/managedClose"]
            if len(admissions) != 1 or len(startups) != 1 or len(closes) != 1:
                raise ValueError("managed marker count")
            if (startups[0][1]["params"]["manifest"] != admissions[0][1]["params"]["manifest"]
                    or admissions[0][1]["params"]["manifest"]["runtime"] != runtime
                    or closes[0][1]["params"]["complete"] is not True
                    or any(message.get("method") == "$native/profile" for _, message in host)):
                raise ValueError("managed marker differs")
            login = case["nativeReplies"]["loginStart"]
            if login["verificationUrl"] != "https://auth.openai.com/codex/device": raise ValueError("challenge differs")
        except (IndexError, KeyError, ValueError, TypeError): problems.append("product-managed-evidence-differs")
    return problems


def assess_positive_artifact(case: dict[str, Any]) -> list[str]:
    problems = []
    originals = {row["seq"]: row for row in case["traceRecords"]}
    selected = case["selectedContext"]["records"]
    if (len(selected) != 2 or {row["seq"] for row in selected} != {1, 2}
            or any(row["rawText"] != originals.get(row["seq"], {}).get("rawText")
                   or row["source"] != originals[row["seq"]]["source"]
                   or row["direction"] != originals[row["seq"]]["direction"]
                   or row["sha256"] != hashlib.sha256(row["rawText"].encode()).hexdigest() for row in selected)):
        problems.append("positive-selected-records-differ")
    try: recovered = recover_recorded_positive(case)
    except Exception: recovered = None
    if (recovered is None or recovered.get("text") != transport.OUTPUT_TEXT
            or recovered.get("executionEvidence") != "synthetic"
            or recovered.get("citations") != [1, 2] or recovered.get("unsupportedCitations") != []
            or recovered != case.get("recoveredArtifact") or recovered != case.get("replayRecoveredArtifact")):
        problems.append("positive-correlated-artifact-not-recovered")
    saved = case.get("savedArtifact")
    if (not isinstance(saved, dict) or saved != case.get("reopenedArtifact")
            or recovered is None or any(saved.get(key) != value for key, value in recovered.items())
            or saved.get("contextId") != case["selectedContext"]["id"]
            or saved.get("attemptId") != (case.get("savedAttempt") or {}).get("id")
            or (case.get("savedAttempt") or {}).get("status") != "completed"
            or not case.get("durableReopenMatches") or case.get("durableReopenFailure") is not None):
        problems.append("positive-durable-artifact-differs")
    outcome = case.get("nativeTurnOutcome") or {}
    if (outcome.get("status") != "completed" or outcome.get("error") is not None
            or outcome.get("id") != case["nativeReplies"].get("turnStart", {}).get("turn", {}).get("id")):
        problems.append("positive-terminal-not-completed")
    responses = [e for e in case["endpointEvents"] if e.get("reason") == "authored-managed-text"]
    if (len(responses) != 1 or responses[0]["responseRaw"] != catalog.authored_stream(derived.MODEL, 2).decode()
            or responses[0].get("responseContentType") != "text/event-stream"):
        problems.append("positive-fixed-sse-differs")
    else:
        event = responses[0]
        try:
            payload = strict_json(event["bodyRaw"])
            valid = catalog.provider_shape(payload, event["headers"], derived.MODEL, case["selectedContext"]["projectedPrompt"])
            additional = [item for item in payload["input"] if item.get("type") == "additional_tools"]
            if not valid or additional[0]["tools"]: raise ValueError("unexpected tools")
        except (KeyError, TypeError, ValueError, RecursionError): problems.append("positive-wire-input-differs")
    return problems


def run_probe(*, mode: str | None = None):
    if mode not in (None, POSITIVE_CASE, WORKER_CASE, PRODUCT_CASE): raise ValueError("unknown explicit managed probe mode")
    binary_hash = checked_binary()
    with tempfile.TemporaryDirectory(prefix="nema-managed-host-") as temporary:
        directory = Path(temporary)
        hosts = ({"productIssuer": "auth.openai.com", "productProvider": "chatgpt.com"} if mode == PRODUCT_CASE
                 else {"issuer": "issuer.fixture.invalid"})
        paths = tls.make_certificates(directory, extra_fixed_hostnames=hosts)
        helper = boundary.compile_helper(directory)
        cases = {variant: run_case(helper, paths, variant) for variant in ((mode,) if mode else CASES)}
        ca_hash = hashlib.sha256(paths["ca"].read_bytes()).hexdigest()
    return {"schemaVersion": "nema-native-managed-lifecycle/1", "implementationBase": "managed-product-integration" if mode == PRODUCT_CASE else "4b91892" if mode == WORKER_CASE else "6ea405a" if mode else "13abac7", "cases": cases,
            "classification": "NATIVE_MANAGED_AUTH_SYNTHETIC_FIXTURE", "realAuthCalls": 0, "realModelCalls": 0,
            "realUpstreamRequests": 0, "subscriptionExecution": False, "liveAdmission": False,
            "nativeLoginRPCs": sum(case["nativeLoginRPCs"] for case in cases.values()),
            "nativeTurnRPCs": sum(case["nativeTurnRPCs"] for case in cases.values()),
            "fixtureCaSha256": ca_hash, "existingCredentialsMounted": False, "tokenExportOrImportRPCs": 0,
            "keysMountedToNative": False, "keysCommitted": False,
            "limits": {"connect": asdict(tls.TunnelLimits()), "capture": asdict(derived.LIMITS),
                       "httpRequestsPerCase": MAX_HTTP, "httpBodyReadLimitBytes": transport.MAX_BODY,
                       "issuerAcceptedBodyBytes": 16384,
                       "endpointResponseBytes": 8192, "heldRefreshSeconds": HOLD_SECONDS, "eventsConsumed": MAX_EVENTS,
                       "nativeSeconds": transport.CASE_SECONDS, "aggregateResourceQuota": False},
            "binarySha256": binary_hash,
            "sourceHashes": {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in
                             (Path(__file__), Path(tls.__file__), Path(transport.__file__), Path(derived.__file__),
                              Path(catalog.__file__), Path(boundary.__file__),
                              *([Path(__file__).parents[1] / "src/eidos" / name for name in
                                 ("codex.py", "private_investigation.py", "investigation_worker.py", "trace.py", "investigation.py")]
                                if mode in (WORKER_CASE, PRODUCT_CASE) else []),
                              *([Path(__file__).parents[1] / "src/eidos" / name for name in
                                 ("native_managed.py", "native_managed_contract.py")]
                                if mode == PRODUCT_CASE else []))}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--mode", choices=[POSITIVE_CASE, WORKER_CASE, PRODUCT_CASE], help="explicit positive fixture; default retains the negative pair")
    args = parser.parse_args()
    data = json.dumps(run_probe(mode=args.mode), indent=2) + "\n"
    if args.output: args.output.write_text(data)
    else: print(data, end="")


if __name__ == "__main__": main()
