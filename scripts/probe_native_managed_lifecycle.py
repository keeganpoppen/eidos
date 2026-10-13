#!/usr/bin/env python3
"""Native-owned ephemeral auth against an authored offline issuer, never real auth."""
from __future__ import annotations

import argparse
import base64
from dataclasses import asdict
import hashlib
import importlib.util
import json
from pathlib import Path
import socketserver
import sys
import tempfile
import threading
import time
from typing import Any
from urllib.parse import parse_qsl

from eidos.codex import AppServerClient
from eidos.investigation_worker import NativeInvestigationWorker
from eidos.trace import TraceStore

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


def token_generation(generation: str, plan: str, expires: int) -> dict[str, str]:
    if generation not in ("A", "B") or plan not in ("plus", "free") or type(expires) is not int:
        raise ValueError("only authored token generations are permitted")
    claims = {"iss": ISSUER, "aud": "nema-synthetic.invalid", "email": "fixture@example.invalid",
              "jti": "nema-synthetic-" + generation, "exp": expires,
              "https://api.openai.com/auth": {"chatgpt_plan_type": plan,
                  "chatgpt_user_id": "nema-fixture-user", "chatgpt_account_id": "nema-fixture-account"}}
    return {"id_token": synthetic_jwt(claims), "access_token": synthetic_jwt({**claims, "token_use": "access"}),
            "refresh_token": "nema-invalid-synthetic-refresh-" + generation}


def fixture_config() -> str:
    config = derived.fixture_config(derived.MODEL)
    start = config.index(f"[model_providers.{transport.PROVIDER}]")
    end = config.index("[mcp_servers.fixture]", start)
    config = config[:start] + config[end:]
    config = config.replace(f'model_provider="{transport.PROVIDER}"', 'model_provider="openai"')
    config = config.replace("[features]\n", "[features]\nuse_agent_identity=false\nenable_request_compression=false\n")
    return (f'cli_auth_credentials_store="ephemeral"\nforced_login_method="chatgpt"\n'
            f'openai_base_url="{PROVIDER}"\nchatgpt_base_url="https://provider.fixture.invalid/backend-api"\n'
            + config + '\n[otel]\nexporter="none"\nmetrics_exporter="none"\n[analytics]\nenabled=false\n')


def validate_config(reply: dict[str, Any]) -> None:
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
    if config.get("agents", {}).get("enabled") is not False or config.get("mcp_servers", {}).get("fixture", {}).get("enabled") is not False:
        raise ValueError("agent/MCP controls differ")


def account_plan(reply: dict[str, Any]) -> str:
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
        if variant not in CASES: raise ValueError("unknown lifecycle case")
        self.variant, self.prompt, self.timeline = variant, prompt, timeline
        now = int(time.time())
        self.tokens = {"A": token_generation("A", "plus", now + (60 if variant == "nearExpiry" else 3600)),
                       "B": token_generation("B", "free", now + 3600)}
        self.issuer_step = 0
        self.generations = []
        self.provider_enabled = False
        self.settings_served = False
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
            if headers.get("host") != "issuer.fixture.invalid": raise ValueError("issuer Host differs")
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
                            "redirect_uri": ISSUER + "/deviceauth/callback", "code_verifier": "nema-fixture-verifier"}
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
        if headers.get("host") != "provider.fixture.invalid": raise ValueError("provider Host differs")
        if headers.get("authorization") != "Bearer " + self.tokens["A"]["access_token"]:
            raise ValueError("provider bearer is not authored generation A")
        if target == SETTINGS_PATH:
            if method != "GET" or raw != "" or self.settings_served:
                raise ValueError("settings requires one exact empty GET")
            self.settings_served = True
            return 200, "authored-attribution-disabled", {"commit_attribution_enabled": False}
        if target != PROVIDER_PATH: raise ValueError("unknown provider route")
        if method == "GET" and headers.get("upgrade", "").lower() == "websocket" and raw == "":
            return 426, "authored-websocket-http-fallback", {"synthetic": True}
        if method != "POST": raise ValueError("unknown provider method")
        payload = strict_json(raw)
        if not catalog.provider_shape(payload, headers, derived.MODEL, self.prompt):
            raise ValueError("provider envelope differs")
        tools = [item for item in payload["input"] if item.get("type") == "additional_tools"]
        if tools[0]["tools"]: raise ValueError("unexpected tool declaration")
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
        payload = json.dumps(response, separators=(",", ":")).encode()
        if len(payload) > 8192: raise ValueError("authored endpoint response limit")
        record.update(status=status, reason=reason, responseRaw=payload.decode())
        self.events.append(record)
        self.timeline.add("fixtureHttpResponse", side=side, status=status, reason=reason)
        return transport.FixtureBroker._http(status, payload)


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


def run_case(helper: Path, paths: dict[str, Path], variant: str) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="nema-managed-case-") as temporary:
        root = Path(temporary)
        boundary.prepare(root, helper)
        original, _ = catalog.checked_catalog()
        model_catalog = derived.derived_catalog(original)
        (root / "fixture/models.json").write_bytes(model_catalog)
        (root / "fixture/ca.pem").write_bytes(paths["ca"].read_bytes())
        (root / "state/codex/config.toml").write_text(fixture_config())
        (root / "fixture/relay.py").write_text(transport.RELAY)
        anchor = "os.execv('/fixture/guard'"
        assert transport.LAUNCHER.count(anchor) == 1
        environment = ("os.environ['HTTPS_PROXY']='http://127.0.0.1:'+port.read_text()\n"
                       "os.environ['CODEX_CA_CERTIFICATE']='/fixture/ca.pem'\n"
                       f"os.environ['CODEX_APP_SERVER_LOGIN_ISSUER']={ISSUER!r}\n"
                       f"os.environ['CODEX_REFRESH_TOKEN_URL_OVERRIDE']={(ISSUER+'/oauth/token')!r}\n")
        (root / "fixture/launcher.py").write_text(transport.LAUNCHER.replace(anchor, environment + anchor))
        trace = TraceStore(root / "trace.db")
        _, work = transport.fixture_work(trace)
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
                    client.expected_turn = {"threadId": thread_id, "input": [{"type": "text", "text": context["projectedPrompt"]}]}
                    replies["turnStart"] = client.request("turn/start", client.expected_turn)
                    turn_id = replies["turnStart"]["turn"]["id"]
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
        records = [{"seq": row.seq, "source": row.source, "direction": row.direction, "rawText": row.raw_text} for row in trace.records()]
        sent_methods = [json.loads(row["rawText"]).get("method") for row in records if row["direction"] == "client_to_appserver"]
        trace.close()
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
        report = json.loads(json.dumps(report).replace(str(root), "<probe>"))
        report["assessmentProblems"] = assess_case(report)
        report["boundedNegativeEvidenceAccepted"] = not report["assessmentProblems"]
        report["nativeTerminalRecovered"] = bool(outcome and outcome.get("id"))
        return report


def assess_case(case: dict[str, Any]) -> list[str]:
    """Post-effect synthetic evidence checks; this does not authorize a native process."""
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
        if 426 not in statuses or 401 not in statuses or statuses.index(426) >= statuses.index(401):
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
                         ("provider", "GET", SETTINGS_PATH, 200),
                         ("provider", "POST", PROVIDER_PATH, 401),
                         ("provider", "POST", PROVIDER_PATH, 401)]
        if ([(e["side"], e["method"], e["target"], e["status"]) for e in endpoints] != expected_http
                or [(e.get("authority"), e["status"]) for e in connects] !=
                   [(ISSUER_AUTHORITY, 200)] * 3 + [(tls.AUTHORITY, 200)] * 4 + [(ISSUER_AUTHORITY, 403)]):
            problems.append("serial-challenge-prefix-differs")
        if closure >= 0:
            after = connects[timeline[closure]["connectCount"]:]
            if not any(e.get("authority") == ISSUER_AUTHORITY and e.get("status") == 403
                       and e.get("reason") == "destination-closed" for e in after):
                problems.append("closed-issuer-denial-absent")
            if any(e.get("authority") == ISSUER_AUTHORITY and e.get("status") == 200 for e in after):
                problems.append("issuer-reopened")
            if timeline[closure]["issuerHttpRequests"] != case["issuerHttpRequests"]:
                problems.append("issuer-http-after-closure")
        if case["fixtureTokenGenerations"] != ["A"]: problems.append("replacement-token-authored")
        if case["nativeThreadRPCs"] != 1 or case["nativeTurnRPCs"] != 1: problems.append("bounded-turn-absent")
    return problems


def run_probe():
    binary_hash = checked_binary()
    with tempfile.TemporaryDirectory(prefix="nema-managed-host-") as temporary:
        directory = Path(temporary)
        paths = tls.make_certificates(directory, extra_fixed_hostnames={"issuer": "issuer.fixture.invalid"})
        helper = boundary.compile_helper(directory)
        cases = {variant: run_case(helper, paths, variant) for variant in CASES}
        ca_hash = hashlib.sha256(paths["ca"].read_bytes()).hexdigest()
    return {"schemaVersion": "nema-native-managed-lifecycle/1", "implementationBase": "13abac7", "cases": cases,
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
                              Path(catalog.__file__), Path(boundary.__file__))}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    data = json.dumps(run_probe(), indent=2) + "\n"
    if args.output: args.output.write_text(data)
    else: print(data, end="")


if __name__ == "__main__": main()
