"""Synthetic socket tests only; actual native login requires explicit opt-in."""
from copy import deepcopy
from dataclasses import asdict
import base64
import importlib.util
import json
import os
from pathlib import Path
import socket
import sys
import threading
import tomllib
from urllib.parse import urlencode

import pytest

spec = importlib.util.spec_from_file_location("native_managed_probe", Path(__file__).parents[1] / "scripts/probe_native_managed_lifecycle.py")
assert spec and spec.loader
probe = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = probe
spec.loader.exec_module(probe)


def record(target, body, *, form=False, side="issuer", method="POST", headers=None):
    return {"method": method, "target": target, "headers": {"host": side + ".fixture.invalid",
            "content-type": "application/x-www-form-urlencoded" if form else "application/json", **(headers or {})},
            "bodyRaw": body if isinstance(body, str) else json.dumps(body)}


def services(variant="nearExpiry"):
    return probe.Services(variant, "authored prompt", probe.Timeline())


def login(value):
    assert value.dispatch("issuer", record("/api/accounts/deviceauth/usercode", {"client_id": probe.CLIENT_ID}))[0] == 200
    assert value.dispatch("issuer", record("/api/accounts/deviceauth/token", {"device_auth_id": "nema-fixture-device", "user_code": "NEMA-FIXTURE"}))[0] == 200
    grant = {"grant_type": "authorization_code", "code": "nema-fixture-code", "client_id": probe.CLIENT_ID,
             "redirect_uri": probe.ISSUER + "/deviceauth/callback", "code_verifier": "nema-fixture-verifier"}
    assert value.dispatch("issuer", record("/oauth/token", urlencode(grant), form=True))[2] == value.tokens["A"]
    return grant


def test_authored_grants_change_plan_only_after_held_refresh_release():
    value = services()
    login(value)
    refresh = record("/oauth/token", {"client_id": probe.CLIENT_ID, "grant_type": "refresh_token", "refresh_token": value.tokens["A"]["refresh_token"]})
    result = []
    worker = threading.Thread(target=lambda: result.append(value.dispatch("issuer", refresh)))
    worker.start()
    try:
        assert value.held.wait(.5)
        assert value.generations == ["A"] and result == []
    finally:
        value.release.set()
        worker.join(1)
    assert not worker.is_alive()
    assert result[0][2] == value.tokens["B"] and value.generations == ["A", "B"]
    with pytest.raises(ValueError, match="duplicate"): value.dispatch("issuer", refresh)


def test_jwt_is_invalid_authored_fixture_with_explicit_claims():
    tokens = probe.token_generation("A", "plus", 1234)
    for name in ("access_token", "id_token"):
        head, body, signature = tokens[name].split(".")
        claims = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
        assert signature == "INVALID_SYNTHETIC_SIGNATURE"
        assert claims["exp"] == 1234 and claims["iss"] == probe.ISSUER
        assert claims["https://api.openai.com/auth"]["chatgpt_plan_type"] == "plus"
    assert tokens["refresh_token"] == "nema-invalid-synthetic-refresh-A"


@pytest.mark.parametrize("mutation", ["client", "unknown", "extra", "duplicate", "host", "type", "auth"])
def test_bad_device_request_cannot_advance_issuer(mutation):
    value = services()
    req = record("/api/accounts/deviceauth/usercode", {"client_id": probe.CLIENT_ID})
    if mutation == "client": req["bodyRaw"] = '{"client_id":"other"}'
    elif mutation == "unknown": req["target"] = "/other"
    elif mutation == "extra": req["bodyRaw"] = json.dumps({"client_id": probe.CLIENT_ID, "extra": True})
    elif mutation == "duplicate": req["bodyRaw"] = '{"client_id":"other","client_id":"' + probe.CLIENT_ID + '"}'
    elif mutation == "host": req["headers"]["host"] = "other.invalid"
    elif mutation == "type": req["headers"]["content-type"] = "text/plain"
    else: req["headers"]["authorization"] = "Bearer invalid"
    with pytest.raises(ValueError): value.dispatch("issuer", req)
    assert value.issuer_step == 0 and value.generations == []


def socket_request(value, raw, side="issuer"):
    client, server = socket.socketpair()
    client.settimeout(2)
    errors = []
    def serve():
        try: server.sendall(value.exchange(side, server))
        except Exception as exc: errors.append(exc)
        finally: server.close()
    worker = threading.Thread(target=serve)
    worker.start()
    try:
        if raw: client.sendall(raw)
        result = bytearray()
        while chunk := client.recv(65536): result.extend(chunk)
    finally:
        client.close()
        worker.join(2)
    assert not worker.is_alive() and not errors
    return bytes(result)


@pytest.mark.parametrize("body", ['NaN', '{"client_id":NaN}', '[' * 2000 + ']' * 2000,
                                    '{"client_id":"x","client_id":"y"}'])
def test_bad_json_gets_recorded_400_without_consuming_grant(body):
    value = services()
    raw = ("POST /api/accounts/deviceauth/usercode HTTP/1.1\r\nHost: issuer.fixture.invalid\r\nContent-Type: application/json\r\n"
           f"Content-Length: {len(body)}\r\n\r\n{body}").encode()
    assert b" 400 " in socket_request(value, raw).split(b"\r\n")[0]
    assert value.events[0]["status"] == 400 and value.issuer_step == 0


@pytest.mark.parametrize("change", ["duplicate", "wrongcode", "extra", "missing"])
def test_invalid_code_grant_not_consumed(change):
    value = services()
    value.issuer_step = 2
    grant = {"grant_type": "authorization_code", "code": "nema-fixture-code", "client_id": probe.CLIENT_ID,
             "redirect_uri": probe.ISSUER + "/deviceauth/callback", "code_verifier": "nema-fixture-verifier"}
    if change == "wrongcode": grant["code"] = "other"
    elif change == "extra": grant["extra"] = "field"
    elif change == "missing": grant.pop("code")
    raw = urlencode(grant) + ("&code=other" if change == "duplicate" else "")
    with pytest.raises(ValueError): value.dispatch("issuer", record("/oauth/token", raw, form=True))
    assert value.issuer_step == 2 and value.generations == []


@pytest.mark.parametrize("bad", [None, "Bearer other", "generation-B", "early", "route"])
def test_provider_auth_or_phase_cannot_be_bypassed(bad):
    value = services("closedIssuer401")
    value.provider_enabled = bad != "early"
    authorization = "Bearer " + value.tokens["A"]["access_token"]
    if bad == "generation-B": authorization = "Bearer " + value.tokens["B"]["access_token"]
    elif bad in (None, "Bearer other"): authorization = bad
    headers = {"upgrade": "websocket"}
    if authorization is not None: headers["authorization"] = authorization
    req = record("/wrong" if bad == "route" else probe.PROVIDER_PATH, "", side="provider", method="GET", headers=headers)
    with pytest.raises(ValueError): value.dispatch("provider", req)


def test_builtin_websocket_handshake_gets_labelled_fixture_426():
    value = services("closedIssuer401")
    value.provider_enabled = True
    req = record(probe.PROVIDER_PATH, "", side="provider", method="GET",
                 headers={"upgrade": "websocket", "authorization": "Bearer " + value.tokens["A"]["access_token"]})
    assert value.dispatch("provider", req)[:2] == (426, "authored-websocket-http-fallback")


@pytest.mark.parametrize("method,params", [("account/read", {"refreshToken": True}), ("account/rateLimits/read", {}),
     ("account/logout", {}), ("account/login/start", {"type": "chatgptAuthTokens"}), ("config/read", {}),
     ("thread/start", {}), ("turn/start", {}), ("process/spawn", {})])
def test_rpc_allowlist_rejects_before_transport(monkeypatch, method, params):
    monkeypatch.setattr(probe.AppServerClient, "request", lambda *a, **k: pytest.fail("reached transport"))
    client = probe.ManagedClient(["never-started"])
    with pytest.raises(ValueError): client.request(method, params)


def test_duplicate_login_and_changed_prepared_turn_rejected(monkeypatch):
    monkeypatch.setattr(probe.AppServerClient, "request", lambda *a, **k: {})
    client = probe.ManagedClient(["never-started"])
    client.request("account/login/start", {"type": "chatgptDeviceCode"})
    with pytest.raises(ValueError): client.request("account/login/start", {"type": "chatgptDeviceCode"})
    client.expected_thread = {"ephemeral": True}
    with pytest.raises(ValueError): client.request("thread/start", client.expected_thread)
    client.issuer_closed = True
    client.request("thread/start", client.expected_thread)
    client.expected_turn = {"exact": "packet"}
    with pytest.raises(ValueError): client.request("turn/start", {"exact": "other"})
    client.request("turn/start", client.expected_turn)
    with pytest.raises(ValueError): client.request("turn/start", client.expected_turn)


@pytest.mark.parametrize("event", [{"method": "account/updated", "params": {}},
    {"method": probe.LOGIN_COMPLETED, "params": {"loginId": "other", "success": True}},
    {"method": probe.LOGIN_COMPLETED, "params": {"loginId": "one", "success": False}}])
def test_completion_must_match_successful_single_login(event):
    with pytest.raises(ValueError): probe.validate_login_completed(event, "one")


def test_early_account_update_is_not_discarded_while_waiting_for_completion():
    with pytest.raises(ValueError, match="preceded"):
        probe.validate_waited_event({"method": "account/updated"}, probe.LOGIN_COMPLETED)


@pytest.mark.parametrize("path", [("model_provider",), ("openai_base_url",), ("cli_auth_credentials_store",),
    ("otel", "exporter"), ("otel", "metrics_exporter"), ("features", "use_agent_identity"),
    ("features", "enable_request_compression"), ("agents", "enabled"), ("mcp_servers", "fixture", "enabled")])
def test_effective_control_drift_rejected(path):
    config = tomllib.loads(probe.fixture_config())
    probe.validate_config({"config": config})
    cursor = config
    for key in path[:-1]: cursor = cursor[key]
    cursor[path[-1]] = "changed"
    with pytest.raises(ValueError): probe.validate_config({"config": config})


def test_wrong_binary_stops_before_compile_or_native(monkeypatch, tmp_path):
    fake = tmp_path / "codex"
    fake.write_bytes(b"unreviewed native")
    with pytest.raises(ValueError, match="reviewed"): probe.checked_binary(fake)
    monkeypatch.setattr(probe, "checked_binary", lambda: (_ for _ in ()).throw(ValueError("reviewed")))
    monkeypatch.setattr(probe.boundary, "compile_helper", lambda *a: pytest.fail("compiled before binary check"))
    with pytest.raises(ValueError): probe.run_probe()


@pytest.fixture(scope="module")
def observed():
    if os.environ.get("NEMA_NATIVE_MANAGED_LIFECYCLE_PROBE") != "1":
        pytest.skip("explicit contained synthetic native managed-login opt-in required")
    result = probe.run_probe()
    if output := os.environ.get("NEMA_NATIVE_MANAGED_LIFECYCLE_OUTPUT"):
        Path(output).write_text(json.dumps(result, indent=2) + "\n")
    return result


@pytest.mark.parametrize("variant", probe.CASES)
def test_contained_managed_lifecycle_evidence(observed, variant):
    case = observed["cases"][variant]
    assert probe.assess_case(case) == [], json.dumps({"failure": case["failure"], "assessment": case["assessmentProblems"], "stderr": case["nativeStderr"]})
    assert case["classification"] == observed["classification"] == "NATIVE_MANAGED_AUTH_SYNTHETIC_FIXTURE"
    assert observed["realAuthCalls"] == observed["realModelCalls"] == observed["realUpstreamRequests"] == 0
    assert observed["binarySha256"] == probe.REVIEWED_BINARY_SHA256
    assert not observed["existingCredentialsMounted"] and not observed["subscriptionExecution"]


def test_unexpected_route_latches_before_later_valid_grant():
    value = services()
    bad = b"POST /wrong HTTP/1.1\r\nHost: issuer.fixture.invalid\r\nContent-Length: 2\r\nContent-Type: application/json\r\n\r\n{}"
    assert b" 400 " in socket_request(value, bad).split(b"\r\n")[0]
    assert value.abort.is_set()
    # No request bytes are required: latched exchange refuses before parsing.
    assert b" 403 " in socket_request(value, b"").split(b"\r\n")[0]
    with pytest.raises(ValueError, match="stopped"):
        value.dispatch("issuer", record("/api/accounts/deviceauth/usercode", {"client_id": probe.CLIENT_ID}))
    assert value.issuer_step == 0 and value.generations == []


def test_issuer_accepted_body_limit_is_distinct_from_shared_read_limit():
    value = services()
    body = json.dumps({"client_id": probe.CLIENT_ID, "extra": "x" * 20000})
    raw = ("POST /api/accounts/deviceauth/usercode HTTP/1.1\r\nHost: issuer.fixture.invalid\r\nContent-Type: application/json\r\n"
           f"Content-Length: {len(body)}\r\n\r\n{body}").encode()
    assert len(body) < probe.transport.MAX_BODY
    assert b" 400 " in socket_request(value, raw).split(b"\r\n")[0]
    assert value.events[0]["bodyRaw"] == body
    assert value.events[0]["reason"] == "issuer body limit" and value.abort.is_set()


def test_visible_abort_after_thread_reply_prevents_next_turn(monkeypatch):
    client = probe.ManagedClient(["never-started"])
    client.issuer_closed = True
    client.expected_thread = {"ephemeral": True}
    client.expected_turn = {"exact": "packet"}
    sent = []
    def reply(self, method, *args, **kwargs):
        sent.append(method)
        client.fixture_abort.set()
        return {}
    monkeypatch.setattr(probe.AppServerClient, "request", reply)
    client.request("thread/start", client.expected_thread)
    with pytest.raises(ValueError, match="stopped before next RPC"):
        client.request("turn/start", client.expected_turn)
    assert sent == ["thread/start"] and client.turn_count == 0


def test_abort_before_releasing_held_refresh_cannot_author_replacement():
    value = services()
    login(value)
    errors = []
    request = record("/oauth/token", {"client_id": probe.CLIENT_ID, "grant_type": "refresh_token", "refresh_token": value.tokens["A"]["refresh_token"]})
    def refresh():
        try: value.dispatch("issuer", request)
        except ValueError as exc: errors.append(str(exc))
    worker = threading.Thread(target=refresh)
    worker.start()
    assert value.held.wait(.5)
    value.abort.set()
    value.release.set()
    worker.join(1)
    assert not worker.is_alive() and errors == ["fixture stopped while refresh held"]
    assert value.generations == ["A"]


def test_provider_lite_envelope_yields_only_authored_401_and_rejects_tool_schema():
    value = services("closedIssuer401")
    value.provider_enabled = True
    payload = {"model": probe.derived.MODEL, "stream": True, "input": [
        {"type": "message", "role": "user", "content": [{"type": "input_text", "text": value.prompt}]},
        {"type": "additional_tools", "role": "developer", "tools": []}]}
    req = record(probe.PROVIDER_PATH, payload, side="provider", headers={
        "authorization": "Bearer " + value.tokens["A"]["access_token"], probe.catalog.LITE_HEADER: "true"})
    assert value.dispatch("provider", req)[:2] == (401, "authored-unauthorized")
    payload["input"][1]["tools"] = [{"type": "function", "name": "unexpected"}]
    req["bodyRaw"] = json.dumps(payload)
    with pytest.raises(ValueError, match="tool declaration"): value.dispatch("provider", req)


def test_analytics_must_be_explicitly_disabled_even_with_otel_disabled():
    config = tomllib.loads(probe.fixture_config())
    config.pop("analytics")
    assert config["otel"] == {"exporter": "none", "metrics_exporter": "none"}
    with pytest.raises(ValueError, match="analytics"): probe.validate_config({"config": config})


def test_one_exact_settings_get_has_no_tool_or_instruction_payload():
    value = services("closedIssuer401")
    value.provider_enabled = True
    req = record(probe.SETTINGS_PATH, "", side="provider", method="GET", headers={
        "authorization": "Bearer " + value.tokens["A"]["access_token"]})
    assert value.dispatch("provider", req) == (200, "authored-attribution-disabled", {"commit_attribution_enabled": False})
    with pytest.raises(ValueError, match="one exact"): value.dispatch("provider", req)


@pytest.mark.parametrize("change", ["method", "body", "query"])
def test_settings_route_rejects_unapproved_variants(change):
    value = services("closedIssuer401")
    value.provider_enabled = True
    req = record(probe.SETTINGS_PATH, "", side="provider", method="GET", headers={
        "authorization": "Bearer " + value.tokens["A"]["access_token"]})
    if change == "method": req["method"] = "POST"
    elif change == "body": req["bodyRaw"] = "{}"
    else: req["target"] += "?other=1"
    with pytest.raises(ValueError): value.dispatch("provider", req)
    assert not value.settings_served


def test_connect_exhaustion_latches_before_future_rpc_or_grant(monkeypatch):
    from types import SimpleNamespace
    value = services()
    client = probe.ManagedClient(["never-started"])
    client.fixture_abort = value.abort
    probe.stop_on_connect_exhaustion(value, SimpleNamespace(unrecorded_refusals=1))
    assert value.violations == ["connect-limit-exhausted"]
    monkeypatch.setattr(probe.AppServerClient, "request", lambda *a, **k: pytest.fail("sent after exhaustion"))
    with pytest.raises(ValueError, match="stopped"): client.request("account/read", {"refreshToken": False})
    with pytest.raises(ValueError, match="stopped"):
        value.dispatch("issuer", record("/api/accounts/deviceauth/usercode", {"client_id": probe.CLIENT_ID}))


RECORDED = Path(__file__).parents[1] / "docs/evidence/NATIVE_MANAGED_LIFECYCLE_0_154_0.json"


def test_committed_evidence_has_exact_negative_result_without_native_startup():
    recorded = json.loads(RECORDED.read_bytes())
    for variant in probe.CASES:
        test_contained_managed_lifecycle_evidence(recorded, variant)
    case = recorded["cases"]["closedIssuer401"]
    assert case["fixtureViolations"] == ["connect-limit-exhausted"]
    assert case["connectAttempts"] == 9 and case["processedConnects"] == 8 and case["unrecordedConnectRefusals"] == 1
    assert case["nativeTurnRPCsRecordedOutbound"] == case["nativeTurnsAcknowledged"] == 1
    assert case["nativeTurnOutcome"] is None and not case["nativeTerminalRecovered"]
    assert "afterTurnAccount" not in case["nativeReplies"]
    assert case["fixtureTokenGenerations"] == ["A"]
    previous = recorded["developmentIterations"]
    first = previous["analyticsUnpinned"]["observed"]["cases"]["closedIssuer401"]
    second = previous["analyticsDisabledSettingsRefused"]["observed"]["cases"]["closedIssuer401"]
    third = previous["settingsAdmittedUnlatchedConnectExhaustion"]["observed"]["cases"]["closedIssuer401"]
    assert first["endpointEvents"][-1]["target"].endswith("analytics-events/events")
    assert "turnStart" not in first["nativeReplies"]
    assert second["endpointEvents"][-1]["target"] == probe.SETTINGS_PATH
    assert first["endpointEvents"][-1]["status"] == second["endpointEvents"][-1]["status"] == 400
    assert third["nativeTurnOutcome"] == {"status": "consumer-timeout"}
    assert third["nativeReplies"]["afterTurnAccount"]["account"]["planType"] == "plus"


@pytest.mark.parametrize("mutation,problem", [
    ("capture-source", "source-matched-limits-absent"), ("limits", "capture-limits-differ"),
    ("diagnostic", "reported-capture-gap"), ("wrongplan", "orderedAccount-plan-differs"),
    ("configerror", "orderedConfig-controls-differ"), ("genericerror", "driver-failure"),
    ("nostopmarker", "fixture-refusal-or-exhaustion"), ("nodenial", "closed-issuer-denial-absent"),
    ("issuer-reopened", "issuer-reopened"), ("replacement", "replacement-token-authored"),
    ("unknownproducer", "fixture-refusal-or-exhaustion"), ("login-count", "login-attempt-count-differs"),
    ("wronglogin", "login-identity-differs"), ("settings", "fixed-settings-observation-differs"),
])
def test_assessor_cannot_launder_mutated_evidence_into_accepted_negative(mutation, problem):
    case = json.loads(RECORDED.read_bytes())["cases"]["closedIssuer401"]
    assert probe.assess_case(case) == []
    if mutation == "capture-source":
        next(row for row in case["traceRecords"] if json.loads(row["rawText"]).get("method") == "$transport/limits")["source"] = "copied"
    elif mutation == "limits": case["nativeCapture"]["limits"]["max_event_count"] += 1
    elif mutation == "diagnostic": case["nativeCapture"]["diagnosticError"] = "authored gap"
    elif mutation == "wrongplan": case["nativeReplies"]["orderedAccount"]["account"]["planType"] = "free"
    elif mutation == "configerror": case["nativeReplies"]["orderedConfig"] = {"error": {"message": "cloud failure"}}
    elif mutation == "genericerror": case["failure"] = {"type": "ValueError", "message": "unrelated fixture failure"}
    elif mutation == "nostopmarker": case["timeline"] = [e for e in case["timeline"] if e["kind"] != "fixtureResourceStop"]
    elif mutation == "nodenial": case["connectEvents"][-1]["reason"] = "different refusal"
    elif mutation == "issuer-reopened": case["connectEvents"][-1]["status"] = 200
    elif mutation == "replacement": case["fixtureTokenGenerations"].append("B")
    elif mutation == "unknownproducer": case["fixtureViolations"].append("unknown provider route")
    elif mutation == "login-count": case["nativeLoginRPCs"] += 1
    elif mutation == "wronglogin": case["nativeReplies"]["loginStart"]["loginId"] = "copied-other-login"
    else: next(e for e in case["endpointEvents"] if e["target"] == probe.SETTINGS_PATH)["responseRaw"] = '{"commit_attribution_enabled":true}'
    assert problem in probe.assess_case(case)


@pytest.mark.parametrize("mutation,problem", [
    ("missing-ack", "correlated-turn-ack-absent"), ("wrong-ack-id", "correlated-turn-ack-absent"),
    ("wrong-thread", "correlated-turn-ack-absent"), ("raw-response-id", "correlated-turn-ack-absent"),
    ("early-denial", "serial-challenge-prefix-differs"), ("early-401", "serial-challenge-prefix-differs")])
def test_exact_request_ack_and_challenge_order_required(mutation, problem):
    case = json.loads(RECORDED.read_bytes())["cases"]["closedIssuer401"]
    if mutation == "missing-ack":
        case["nativeReplies"].pop("turnStart")
        case["nativeTurnsAcknowledged"] = 0
    elif mutation == "wrong-ack-id": case["nativeReplies"]["turnStart"]["turn"]["id"] = "copied-turn"
    elif mutation == "wrong-thread": case["nativeReplies"]["threadStart"]["thread"]["id"] = "copied-thread"
    elif mutation == "raw-response-id":
        for row in case["traceRecords"]:
            msg = json.loads(row["rawText"])
            if row["direction"] == "appserver_to_client" and msg.get("result") == case["nativeReplies"]["turnStart"]:
                msg["id"] = "different-rpc"
                row["rawText"] = json.dumps(msg)
    elif mutation == "early-denial": case["connectEvents"].insert(3, case["connectEvents"].pop())
    else: case["endpointEvents"].insert(3, case["endpointEvents"].pop())
    assert problem in probe.assess_case(case)


def positive_request(value):
    payload = {"model": probe.derived.MODEL, "stream": True, "input": [
        {"type": "message", "role": "user", "content": [{"type": "input_text", "text": value.prompt}]},
        {"type": "additional_tools", "role": "developer", "tools": []}]}
    return record(probe.PROVIDER_PATH, payload, side="provider", headers={
        "authorization": "Bearer " + value.tokens["A"]["access_token"], probe.catalog.LITE_HEADER: "true"})


def positive_prefix(value):
    value.provider_enabled = True
    auth = {"authorization": "Bearer " + value.tokens["A"]["access_token"]}
    value.dispatch("provider", record(probe.PROVIDER_PATH, "", side="provider", method="GET",
                                      headers={**auth, "upgrade": "websocket"}))
    value.dispatch("provider", record(probe.SETTINGS_PATH, "", side="provider", method="GET", headers=auth))


def test_positive_mode_is_explicit_and_defaults_keep_negative_pair(monkeypatch):
    assert probe.CASES == ("nearExpiry", "closedIssuer401")
    monkeypatch.setattr(probe, "checked_binary", lambda: pytest.fail("checked native before mode validation"))
    with pytest.raises(ValueError, match="mode"): probe.run_probe(mode="unknown")


def run_authored_worker(tmp_path, monkeypatch, *, terminal_params="valid", cleanup_failure=None, malformed_reply=None,
                        goals_drift=None, product_managed=False, product_drift=None):
    """Exercise the production join with a local authored stdio child, never native.

    Transport expectations below are separate historical fixture data used for
    assessor mutation tests; they are not observations of this authored child.
    """
    from types import SimpleNamespace
    config = tomllib.loads(probe.managed_config() if product_managed else probe.fixture_config(owned_worker=True))
    if product_managed:
        # Authored effective reply, matching native's packaged default. The
        # production startup bytes and real native responses remain untouched.
        config["chatgpt_base_url"] = "https://chatgpt.com/backend-api/"
    script = tmp_path / "authored.py"
    script.write_text("import json, os, sys\n" + f"config = {config!r}\n" + r'''
reads = 0
def send(value): print(json.dumps(value), flush=True)
for line in sys.stdin:
    msg = json.loads(line)
    ident, method = msg.get('id'), msg.get('method')
    if method == 'initialize':
        print('PRIVATE_AUTHORED_STDERR', file=sys.stderr, flush=True)
        send({'id': ident, 'result': {'userAgent': 'authored-not-native', 'future': 'PRIVATE_INIT'}})
    elif method == 'account/read':
        reads += 1
        send({'id': ident, 'result': {'account': None if reads == 1 else
            {'type': 'chatgpt', 'email': 'fixture@example.invalid', 'planType': 'plus'}, 'requiresOpenaiAuth': True}})
    elif method == 'config/read': send({'id': ident, 'result': {'config': config, 'future': 'PRIVATE_CONFIG'}})
    elif method == 'account/login/start':
        send({'id': ident, 'result': {'loginId': 'authored-login', 'userCode': 'PRIVATE_CODE'}})
        send({'method': 'account/login/completed', 'params': {'loginId': 'authored-login', 'success': True, 'future': 'PRIVATE_LOGIN'}})
        send({'method': 'account/updated', 'params': {'authMode': 'chatgpt', 'planType': 'plus'}})
    elif method == 'thread/start':
        send({'id': ident, 'result': {'thread': {'id': 'authored-thread', 'environments': []},
             'cwd': msg['params']['cwd'], 'approvalPolicy': 'never', 'sandbox': {'type': 'readOnly', 'networkAccess': False}}})
    elif method == 'mcpServerStatus/list': send({'id': ident, 'result': {'data': [], 'nextCursor': None}})
    elif method == 'turn/start':
        send({'id': ident, 'result': {'turn': {'id': 'authored-turn', 'status': 'inProgress', 'items': []}}})
        send({'method': 'item/completed', 'params': {'threadId': 'authored-thread', 'turnId': 'authored-turn',
             'item': {'id': 'result', 'type': 'agentMessage', 'phase': 'final',
                      'text': 'SYNTHETIC FIXTURE: both selected records survived [evidence:1] [evidence:2].', 'future': 'PRIVATE_ITEM'}}})
        send({'method': 'turn/completed', 'params': {'threadId': 'authored-thread', 'turn': {'id': 'authored-turn', 'status': 'completed'}}})
''')
    if product_managed:
        source = script.read_text()
        source = source.replace("'loginId': 'authored-login', 'userCode': 'PRIVATE_CODE'",
            "'loginId': 'authored-login', 'userCode': 'PRIVATE_CODE', 'type': 'chatgptDeviceCode', "
            "'verificationUrl': 'https://auth.openai.com/codex/device'")
        script.write_text(source)
    if product_drift is not None:
        stage, section, key, value = product_drift
        before = "    elif method == 'config/read': send({'id': ident, 'result': {'config': config, 'future': 'PRIVATE_CONFIG'}})"
        mutation = f"config[{section!r}].pop({key!r})" if value == "missing" else f"config[{section!r}][{key!r}] = {value!r}"
        after = ("    elif method == 'config/read':\n"
                 f"        if reads == {stage}: {mutation}\n"
                 "        send({'id': ident, 'result': {'config': config, 'future': 'PRIVATE_CONFIG'}})")
        source = script.read_text()
        assert source.count(before) == 1
        script.write_text(source.replace(before, after))
    if goals_drift is not None:
        stage, value = goals_drift
        before = "    elif method == 'config/read': send({'id': ident, 'result': {'config': config, 'future': 'PRIVATE_CONFIG'}})"
        mutation = "config['features'].pop('goals')" if value == 'missing' else "config['features']['goals'] = True"
        after = ("    elif method == 'config/read':\n"
                 f"        if reads == {stage}: {mutation}\n"
                 "        send({'id': ident, 'result': {'config': config, 'future': 'PRIVATE_CONFIG'}})")
        source = script.read_text()
        assert source.count(before) == 1
        script.write_text(source.replace(before, after))
    if malformed_reply is not None:
        replacements = {
            "account": ("'result': {'account': None if reads == 1 else", "'result': None if reads == 2 else {'account': None if reads == 1 else"),
            "inventory": ("'data': [], 'nextCursor': None", "'data': [None], 'nextCursor': None"),
            "config": ("'config': config, 'future'", "'config': None, 'future'"),
        }
        before, after = replacements[malformed_reply]
        source = script.read_text()
        assert source.count(before) == 1
        script.write_text(source.replace(before, after))
    if terminal_params != "valid":
        source = script.read_text()
        terminal = "send({'method': 'turn/completed', 'params': {'threadId': 'authored-thread', 'turn': {'id': 'authored-turn', 'status': 'completed'}}})"
        assert source.count(terminal) == 1
        script.write_text(source.replace(terminal, f"send({{'method': 'turn/completed', 'params': {terminal_params!r}}})\n        break"))
    if cleanup_failure is not None:
        original = getattr(probe.OwnedManagedWorker, cleanup_failure)
        def interrupted(self):
            original(self)
            raise OSError("authored cleanup failure: " + cleanup_failure)
        monkeypatch.setattr(probe.OwnedManagedWorker, cleanup_failure, interrupted)
    def prepare(root, helper, paths, *, owned_worker=False):
        assert owned_worker is True
        (root / "state/codex").mkdir(parents=True)
        (root / "packet").mkdir()
        (root / "state/policy.json").write_text(json.dumps({"installedBeforeInitialExec": True, "allListenerCopiesClosed": True}))
    monkeypatch.setattr(probe, "prepare_case", prepare)
    if product_managed:
        def prepare_product(root, helper, paths):
            prepare(root, helper, paths, owned_worker=True)
            (root / "assets").mkdir(); (root / "fixture").mkdir()
            for name in ("ca.pem", "guard", "relay.py", "launcher.py"):
                (root / "fixture" / name).write_text("authored unused resource " + name)
        monkeypatch.setattr(probe, "prepare_product_case", prepare_product)
        monkeypatch.setattr(probe, "checked_binary", lambda: probe.REVIEWED_BINARY_SHA256)
    monkeypatch.setattr(probe, "worker_launcher", lambda root, **kwargs: [sys.executable, str(script)])
    monkeypatch.setattr(probe.tls, "TlsFixture", lambda *args, **kwargs: SimpleNamespace(
        workers=[], tls_events=[], open_endpoint=lambda: pytest.fail("network endpoint used"), close=lambda: None))
    return probe.run_worker_case(tmp_path / "not-executed", {}, product_managed=product_managed)


def test_goals_disable_is_worker_only_and_other_startup_bytes_are_unchanged():
    historical = probe.fixture_config()
    worker = probe.fixture_config(owned_worker=True)
    assert worker == historical.replace("[features]\n", "[features]\ngoals=false\n")
    assert "goals" not in tomllib.loads(historical)["features"]
    assert tomllib.loads(worker)["features"]["goals"] is False


def test_first_native_worker_goal_payload_remains_rejected_without_publication():
    path = Path(__file__).parents[1] / "docs/evidence/NATIVE_OWNED_WORKER_0_154_0_FIRST_FAILURE.json"
    case = json.loads(path.read_bytes())["cases"][probe.WORKER_CASE]
    assert case["positiveOwnedWorkerAccepted"] is False and case["publicationLedger"] is None
    assert len(case["traceRecords"]) == 2 and case["allWorkersJoined"] is True
    value = probe.Services(probe.WORKER_CASE, case["selectedContext"]["projectedPrompt"], probe.Timeline())
    positive_prefix(value)
    request = deepcopy(case["endpointEvents"][-1])
    assert request["reason"] == "unexpected tool declaration"
    request["headers"]["authorization"] = "Bearer " + value.tokens["A"]["access_token"]
    with pytest.raises(ValueError, match="unexpected tool declaration"):
        value.dispatch("provider", request)
    assert value.response_served is False


def test_recorded_native_worker_replays_exact_private_public_result_without_launch():
    path = Path(__file__).parents[1] / "docs/evidence/NATIVE_OWNED_WORKER_0_154_0.json"
    report = json.loads(path.read_bytes())
    case = report["cases"][probe.WORKER_CASE]
    assert report["liveAdmission"] is False and report["realModelCalls"] == 0
    assert probe.assess_worker_case(case) == []
    published, original = probe.recover_recorded_worker(case)
    assert published == case["recoveredArtifact"] == case["replayRecoveredArtifact"]
    assert case["savedArtifact"] == case["reopenedArtifact"]
    assert original == case["resolvedEvidence"]["artifact"]
    assert published["outputSeqs"] == [3] and original["outputSeqs"] != [3]
    assert case["reopenedControl"] == {"owned": False, "canCancel": False}


@pytest.mark.parametrize("stage", [1, 2])
@pytest.mark.parametrize("value", ["missing", "true"])
def test_goal_control_drift_stops_authored_worker_before_thread(tmp_path, monkeypatch, stage, value):
    case = run_authored_worker(tmp_path, monkeypatch, goals_drift=(stage, value))
    assert case["failure"] is not None and case["positiveOwnedWorkerAccepted"] is False
    assert case["nativeLoginRPCs"] == stage - 1
    assert case["nativeThreadRPCs"] == case["nativeTurnRPCs"] == 0
    assert case["publicationLedger"] is None and len(case["traceRecords"]) == 2
    name = "initialConfig" if stage == 1 else "orderedConfig"
    assert name + "-controls-differ" in probe.assess_worker_case(case)
    assert "owned worker goal tools are not disabled" in json.dumps(case["privateTraceRecords"])


@pytest.fixture
def authored_worker_case(tmp_path, monkeypatch):
    case = run_authored_worker(tmp_path, monkeypatch)
    assert case["failure"] is None, case["failure"]
    assert case["durableReopenMatches"] and case["nativeUserAgent"] == "authored-not-native"
    assert "PRIVATE_" not in json.dumps(case["traceRecords"]) + json.dumps(case["progress"])
    assert "PRIVATE_CODE" in json.dumps(case["privateTraceRecords"])
    # Build a wholly synthetic assessment example from actual local worker data
    # plus explicitly historical endpoint expectations. Never save it as native evidence.
    previous = json.loads(POSITIVE_RECORDED.read_bytes())["cases"][probe.POSITIVE_CASE]
    for key in ("endpointEvents", "connectEvents", "connectAttempts", "processedConnects", "mappedEndpointOpens",
                "fixtureTokenGenerations", "issuerHttpRequests", "providerHttpRequests"):
        case[key] = deepcopy(previous[key])
    response = case["endpointEvents"][-1]
    response["bodyRaw"] = response["bodyRaw"].replace(
        json.dumps(previous["selectedContext"]["projectedPrompt"])[1:-1], json.dumps(case["selectedContext"]["projectedPrompt"])[1:-1])
    closure = next(e for e in case["timeline"] if e["kind"] == "issuerClosed")
    closure.update(connectCount=3, issuerHttpRequests=3)
    assert probe.assess_worker_case(case) == []
    return case


@pytest.mark.parametrize("params", [{}, None, [], {"turn": None}, {"turn": "scalar"}])
def test_malformed_authored_terminal_retains_failure_report_and_raw_bytes(tmp_path, monkeypatch, params):
    case = run_authored_worker(tmp_path, monkeypatch, terminal_params=params)
    assert case["failure"] is not None
    assert case["positiveOwnedWorkerAccepted"] is False
    assert "worker-terminal-differs" in case["assessmentProblems"]
    terminal = next(row for row in case["privateTraceRecords"] if json.loads(row["rawText"]).get("method") == "turn/completed")
    assert terminal["rawText"] == json.dumps({"method": "turn/completed", "params": params})
    assert case["nativeTurnOutcome"] is None
    assert case["savedArtifact"] is None


@pytest.mark.parametrize("operation", ["close", "close_evidence"])
def test_cleanup_failure_keeps_report_and_does_not_claim_clean_shutdown(tmp_path, monkeypatch, operation):
    case = run_authored_worker(tmp_path, monkeypatch, cleanup_failure=operation)
    assert case["savedArtifact"] is not None  # Already accepted evidence stays inspectable.
    assert case["allWorkersJoined"] is False
    assert case["positiveOwnedWorkerAccepted"] is False
    assert "worker-not-closed-cleanly" in case["assessmentProblems"]
    assert any(item["operation"] == "owned." + operation and item["type"] == "OSError" for item in case["cleanupErrors"])
    assert case["privateTraceRecords"] and case["remainingActiveTunnels"] == 0


def test_owned_private_client_clears_host_environment_before_launcher(tmp_path, monkeypatch):
    monkeypatch.setenv("NEMA_FIXTURE_PARENT_ONLY", "authored-env-canary")
    start = probe.AppServerClient.start
    checked = []
    def audit(client):
        checked.append(client.source)
        assert client.env == {} and client.inherit_env is False
        return start(client)
    monkeypatch.setattr(probe.AppServerClient, "start", audit)
    case = run_authored_worker(tmp_path, monkeypatch)
    assert checked and len(set(checked)) == 1
    assert case["failure"] is None


def test_owned_outer_watchdog_is_joined_before_clean_shutdown_claim(tmp_path, monkeypatch):
    original = threading.Timer
    timers = []
    class ObservedTimer(original):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.join_timeouts = []
            timers.append(self)
        def join(self, timeout=None):
            self.join_timeouts.append(timeout)
            return super().join(timeout)
    monkeypatch.setattr(threading, "Timer", ObservedTimer)
    case = run_authored_worker(tmp_path, monkeypatch)
    outer = [timer for timer in timers if timer.interval == probe.transport.CASE_SECONDS]
    assert len(outer) == 1 and outer[0].join_timeouts == [1]
    assert not outer[0].is_alive() and case["allWorkersJoined"] is True


@pytest.mark.parametrize("key,value", [("orderedAccount", None), ("initialConfig", None),
    ("orderedConfig", {"config": []}), ("mcpServerStatus/list", {"data": [None]}),
    ("mcpServerStatus/list", None), ("thread/start", {"thread": None}), ("turn/start", [])])
def test_malformed_reported_acknowledgements_remain_nonaccepted(authored_worker_case, key, value):
    case = deepcopy(authored_worker_case)
    case["nativeReplies"][key] = value
    assert probe.assess_worker_case(case)


def test_assessment_shape_failure_returns_rejected_report_instead_of_throwing(authored_worker_case):
    case = deepcopy(authored_worker_case)
    case["privateTraceRecords"][0]["rawText"] = "null"
    assert probe.assess_worker_case(case) == ["malformed-worker-evidence:AttributeError"]


@pytest.mark.parametrize("reply", ["account", "inventory", "config"])
def test_malformed_authored_control_reply_retains_failed_report(tmp_path, monkeypatch, reply):
    case = run_authored_worker(tmp_path, monkeypatch, malformed_reply=reply)
    assert case["failure"] is not None
    assert case["positiveOwnedWorkerAccepted"] is False
    assert case["assessmentProblems"]
    raw = [json.loads(row["rawText"]) for row in case["privateTraceRecords"]]
    if reply == "account": assert any(msg.get("result", "absent") is None for msg in raw)
    elif reply == "inventory": assert any(msg.get("result") == {"data": [None], "nextCursor": None} for msg in raw)
    else: assert any(msg.get("result") == {"config": None, "future": "PRIVATE_CONFIG"} for msg in raw)
    assert len(case["traceRecords"]) == 2 and case["savedArtifact"] is None


def test_authored_worker_join_keeps_exact_private_proof_and_no_reopened_owner(authored_worker_case, monkeypatch):
    monkeypatch.setattr(probe.AppServerClient, "start", lambda *a, **k: pytest.fail("process during evidence assessment"))
    case = authored_worker_case
    published, native = probe.recover_recorded_worker(case)
    assert published["outputSeqs"] == [3]
    assert native["outputSeqs"] != [3]
    assert published["executionEvidence"] == native["executionEvidence"] == "synthetic"
    assert case["reopenedControl"] == {"owned": False, "canCancel": False}
    assert [p["lifecycle"]["phase"] for p in case["progress"] if "lifecycle" in p] == [
        "preparing", "awaiting-sign-in", "checking", "running", "closed"]


@pytest.mark.parametrize("mutation", ["terminal", "request", "ack", "classification", "source", "raw-public",
    "ledger", "reopened-owner", "duplicate-provider", "capture", "limits", "post-turn", "inventory"])
def test_owned_worker_assessment_rejects_boundary_mutations(authored_worker_case, mutation):
    case = deepcopy(authored_worker_case)
    if mutation in {"terminal", "request", "ack", "classification", "source"}:
        for row in case["privateTraceRecords"]:
            msg = json.loads(row["rawText"])
            if mutation == "terminal" and msg.get("method") == "turn/completed":
                msg["params"]["turn"]["id"] = "wrong-turn"
            elif mutation == "request" and msg.get("method") == "turn/start":
                msg["params"]["input"][0]["text"] = "wrong-context"
            elif mutation == "ack" and msg.get("result", {}).get("turn", {}).get("id") == "authored-turn":
                msg["id"] = "wrong-request"
            elif mutation == "classification" and msg.get("method") == "$native/profile":
                msg["params"]["executionEvidence"] = "unverified"
            elif mutation == "source" and msg.get("method") == "$native/profile":
                row["source"] = "copied-source"
            row["rawText"] = json.dumps(msg)
    elif mutation == "raw-public": case["traceRecords"].append(case["privateTraceRecords"][4])
    elif mutation == "ledger": case["publicationLedger"]["content_digest"] = "copied"
    elif mutation == "reopened-owner": case["reopenedControl"]["owned"] = True
    elif mutation == "duplicate-provider": case["endpointEvents"].append(case["endpointEvents"][-1])
    elif mutation == "capture": case["nativeCapture"]["diagnosticError"] = "failed"
    elif mutation == "limits": case["nativeCapture"]["limits"]["max_received_bytes"] += 1
    elif mutation == "post-turn": case["afterTurnAccountObserved"] = True
    else: case["nativeReplies"]["mcpServerStatus/list"]["data"] = [{"tools": {"danger": {}}, "runtimeStatus": "ready"}]
    assert probe.assess_worker_case(case)


def test_worker_namespace_launcher_creates_cwd_spelling_without_host_mount(tmp_path, monkeypatch):
    import tempfile
    command = probe.worker_launcher(tmp_path)
    captured = []
    monkeypatch.setattr(os, "execv", lambda binary, argv: captured.append(argv))
    with tempfile.TemporaryDirectory(prefix="nema-investigation-", dir="/tmp") as cwd:
        monkeypatch.chdir(cwd)
        assert command[1:3] == ("-I", "-S")
        exec(Path(command[-1]).read_text(), {})
    argv = captured[0]
    assert argv[argv.index("--chdir") + 1] == cwd
    assert argv[argv.index("--dir") + 1] == cwd
    assert argv[argv.index("--tmpfs") + 1] == "/tmp"
    for index, value in enumerate(argv):
        if value in {"--bind", "--ro-bind"}: assert argv[index + 1] != cwd
    assert "--unshare-all" in argv and "--clearenv" in argv and "--die-with-parent" in argv


@pytest.fixture(scope="module")
def owned_worker_observed():
    if os.environ.get("NEMA_NATIVE_OWNED_WORKER_PROBE") != "1":
        pytest.skip("explicit reviewed contained owned-worker opt-in required")
    result = probe.run_probe(mode=probe.WORKER_CASE)
    if output := os.environ.get("NEMA_NATIVE_OWNED_WORKER_OUTPUT"):
        Path(output).write_text(json.dumps(result, indent=2) + "\n")
    return result


def test_contained_owned_worker_completes_private_public_recovery(owned_worker_observed):
    report = owned_worker_observed
    case = report["cases"][probe.WORKER_CASE]
    assert probe.assess_worker_case(case) == [], json.dumps({"failure": case["failure"],
        "assessment": case["assessmentProblems"], "stderr": case["nativeStderr"]})
    assert case["positiveOwnedWorkerAccepted"] and case["nativeTerminalRecovered"]
    assert report["realAuthCalls"] == report["realModelCalls"] == report["realUpstreamRequests"] == 0
    assert not report["liveAdmission"] and not report["subscriptionExecution"]


def test_product_managed_authored_worker_uses_production_preparation_and_receipt(tmp_path, monkeypatch):
    case = run_authored_worker(tmp_path, monkeypatch, product_managed=True)
    assert case["failure"] is None, case["failure"]
    assert case["requestedConfigToml"] == probe.managed_config()
    for name in ("initialConfig", "orderedConfig"):
        probe.validate_managed_config(case["nativeReplies"][name])
    messages = [json.loads(row["rawText"]) for row in case["privateTraceRecords"]]
    assert len([m for m in messages if m.get("method") == "$native/managedAdmission"]) == 1
    assert not any(m.get("method") == "$native/profile" for m in messages)
    assert case["managedClose"]["allWorkersJoined"] is True
    assert case["managedRuntime"]["transport"] == "authored-local"
    assert case["managedRuntime"]["classification"] == "synthetic"
    assert case["recoveredArtifact"]["executionEvidence"] == "synthetic"
    assert case["durableReopenMatches"] and case["reopenedControl"] == {"owned": False, "canCancel": False}
    assert "PRIVATE_" not in json.dumps(case["traceRecords"])
    published, original = probe.recover_recorded_worker(case)
    assert published == case["recoveredArtifact"] and original == case["resolvedEvidence"]["artifact"]
    # This child exercised RPCs, not TLS/native: never promote its unused fixture
    # transport fields into a passing actual-native report.
    assert "worker-endpoint-sequence-differs" in case["assessmentProblems"]


def test_product_managed_namespace_assets_are_read_only_without_url_overrides(tmp_path):
    helper = tmp_path / "authored-guard"; helper.write_bytes(b"not executable native")
    ca = tmp_path / "authored-ca"; ca.write_bytes(b"authored public fixture CA")
    root = tmp_path / "case"; root.mkdir()
    probe.prepare_product_case(root, helper, {"ca": ca})
    launcher = (root / "fixture/launcher.py").read_text()
    assert "CODEX_CA_CERTIFICATE" in launcher and "HTTPS_PROXY" in launcher
    assert "CODEX_APP_SERVER_LOGIN_ISSUER" not in launcher and "CODEX_REFRESH_TOKEN_URL_OVERRIDE" not in launcher
    assert "config.write_text" not in launcher and "FIXTURE_PORT" not in launcher
    assert (root / "fixture/ca.pem").read_bytes() == ca.read_bytes()
    assert (root / "fixture/ca.pem").stat().st_mode & 0o222 == 0
    command = probe.worker_launcher(root, product_managed=True)
    source = Path(command[-1]).read_text()
    assert "'--ro-bind', '" + str(root / "assets") + "', '/assets'" in source
    assert "'--ro-bind', '" + str(root / "assets/config.toml") + "', '/state/codex/config.toml'" in source
    assert command[:3] == ("/usr/bin/python3", "-I", "-S")


def test_product_managed_first_failure_retains_exact_native_config_without_reclassification():
    import hashlib
    path = Path(__file__).parents[1] / "docs/evidence/NATIVE_PRODUCT_MANAGED_0_154_0_FIRST_FAILURE.json"
    raw = path.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == "e2e68f68379761cf057dd9e0b31db9c1ef711b6fcd57d86faae442e785d6e0f0"
    case = json.loads(raw)["cases"][probe.PRODUCT_CASE]
    assert case["failure"] is not None and not case["positiveOwnedWorkerAccepted"]
    assert case["nativeMethodsObserved"] == ["initialize", "account/read", "config/read"]
    assert case["nativeLoginRPCs"] == case["nativeThreadRPCs"] == case["nativeTurnRPCs"] == 0
    assert len(case["privateTraceRecords"]) == 13 and len(case["traceRecords"]) == 2
    assert case["issuerHttpRequests"] == case["providerHttpRequests"] == case["processedConnects"] == 0
    reply = case["nativeReplies"]["initialConfig"]
    probe.validate_managed_config(reply)
    assert reply["config"]["chatgpt_base_url"] == "https://chatgpt.com/backend-api/"
    assert "experimental_request_user_input" not in reply["config"]["tools"]
    assert "tools.experimental_request_user_input.enabled" in reply["origins"]
    assert probe.assess_worker_case(case), "corrected validation cannot fabricate the unobserved login/turn"


def test_product_managed_retained_positive_replays_exact_readiness_and_private_proof(monkeypatch):
    import hashlib
    import subprocess
    from eidos.native_managed import validate_managed_receipt
    from eidos.native_managed_contract import ManagedAttemptIdentity
    from eidos.trace import TraceStore
    def forbidden(*args, **kwargs):
        pytest.fail("retained evidence replay must not launch a child")
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    raw = (Path(__file__).parents[1] / "docs/evidence/NATIVE_PRODUCT_MANAGED_0_154_0.json").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == "5175384248ebb905c31949c07f452134d31f8b39584b8592c89be1b7a533cc5d"
    report = json.loads(raw)
    case = report["cases"][probe.PRODUCT_CASE]
    assert probe.assess_worker_case(case) == []
    assert report["realAuthCalls"] == report["realModelCalls"] == report["realUpstreamRequests"] == 0
    published, original = probe.recover_recorded_worker(case)
    assert published == case["recoveredArtifact"] == case["replayRecoveredArtifact"]
    assert published["executionEvidence"] == original["executionEvidence"] == "synthetic"
    assert published["outputSeqs"] == [3] and original["outputSeqs"] == [39]
    assert case["reopenedControl"] == {"owned": False, "canCancel": False}
    assert case["savedArtifact"] == case["reopenedArtifact"]
    private = TraceStore(":memory:", role="private-control")
    try:
        for row in case["privateTraceRecords"]:
            private.append_line(source=row["source"], direction=row["direction"], raw_text=row["rawText"])
        records = private.records()
        admission, = [r for r in records if r.direction == "internal" and r.method == "$native/managedAdmission"]
        closure, = [r for r in records if r.direction == "internal" and r.method == "$native/managedClose"]
        identity = ManagedAttemptIdentity.from_attempt(case["savedAttempt"], case["selectedContext"], case["savedAttempt"]["source"])
        assert validate_managed_receipt(admission.message["params"], identity, records, before_seq=admission.seq) == "synthetic"
        assert closure.message["params"] == {"identity": identity.as_dict(), "complete": True, "diagnostics": []}
        assert closure.seq == 44 and next(r.seq for r in records if r.method == "turn/completed") == 43
    finally: private.close()


@pytest.mark.parametrize("stage", [1, 2])
@pytest.mark.parametrize("section,key,value", [
    ("features", "remote_plugin", "missing"), ("features", "goals", True),
    ("otel", "trace_exporter", "missing"), ("otel", "trace_exporter", None),
    ("otel", "exporter", None), ("otel", "metrics_exporter", None),
])
def test_product_managed_config_drift_cannot_start_thread(tmp_path, monkeypatch, stage, section, key, value):
    case = run_authored_worker(tmp_path, monkeypatch, product_managed=True, product_drift=(stage, section, key, value))
    assert case["failure"] is not None
    assert case["nativeLoginRPCs"] == stage - 1
    assert case["nativeThreadRPCs"] == case["nativeTurnRPCs"] == 0
    assert case["publicationLedger"] is None and len(case["traceRecords"]) == 2
    assert not case["positiveOwnedWorkerAccepted"]


@pytest.mark.parametrize("mutation", ["missing-close", "failed-close", "source", "context-hash", "readiness"])
def test_product_managed_private_recovery_rejects_incomplete_or_foreign_proof(tmp_path, monkeypatch, mutation):
    case = run_authored_worker(tmp_path, monkeypatch, product_managed=True)
    assert case["failure"] is None
    from eidos.trace import TraceStore
    from eidos.investigation_worker import NativeInvestigationWorker, NativeInvestigationError
    private = TraceStore(":memory:", role="private-control")
    try:
        for row in case["privateTraceRecords"]:
            message = json.loads(row["rawText"])
            if message.get("method") == "$native/managedClose":
                if mutation == "missing-close": continue
                if mutation == "failed-close": message["params"]["complete"] = False
            if message.get("method") == "$native/managedAdmission":
                if mutation == "source": row["source"] = "foreign-source"
                if mutation == "context-hash": message["params"]["identity"]["contextSha256"] = "0" * 64
                if mutation == "readiness": message["params"]["readiness"]["orderedConfig"] = "0" * 64
            private.append_line(source=row["source"], direction=row["direction"], raw_text=json.dumps(message))
        try:
            recovered = NativeInvestigationWorker(private, command=["/never-launch"]).recover(case["savedAttempt"], case["selectedContext"])
        except (NativeInvestigationError, probe.ManagedLaunchError):
            recovered = None
        if mutation == "source":
            assert recovered is not None and recovered["executionEvidence"] == "unverified"
        else:
            assert recovered is None
    finally: private.close()


def test_product_managed_local_tls_mapping_has_no_dns_or_live_route(tmp_path, monkeypatch):
    import builtins
    import ssl
    def forbidden(*args, **kwargs):
        pytest.fail("offline product fixture attempted DNS or live dial")
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    original_connect = socket.socket.connect
    def local_connect(self, address):
        if self.family in (socket.AF_INET, socket.AF_INET6): forbidden()
        return original_connect(self, address)
    monkeypatch.setattr(socket.socket, "connect", local_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)
    original_import = builtins.__import__
    def import_without_production_runtime(name, *args, **kwargs):
        if name.endswith("native_containment"): pytest.fail("offline fixture imported live runtime")
        return original_import(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", import_without_production_runtime)
    # Traverse real production preparation/receipt with an authored stdio child
    # while the network entry points remain forbidden.
    case = run_authored_worker(tmp_path, monkeypatch, product_managed=True)
    assert case["failure"] is None
    # Restore the TLS class replaced only for the authored subprocess helper.
    tls_spec = importlib.util.spec_from_file_location("product_tls_default_test", Path(probe.tls.__file__))
    real_tls = importlib.util.module_from_spec(tls_spec)
    sys.modules[tls_spec.name] = real_tls
    tls_spec.loader.exec_module(real_tls)
    paths = real_tls.make_certificates(tmp_path, extra_fixed_hostnames={
        "productIssuer": "auth.openai.com", "productProvider": "chatgpt.com"})
    class Endpoint:
        def exchange(self, connection):
            request = probe.transport.read_fixture_http_request(connection, probe.time.monotonic() + 2)
            assert request["method"] == "GET" and request["target"] == "/local-proof"
            return b"HTTP/1.1 200 OK\r\nContent-Length: 7\r\nConnection: close\r\n\r\nauthored"
    issuer = real_tls.TlsFixture("", "valid", paths, endpoint=Endpoint(), certificate="productIssuer")
    provider = real_tls.TlsFixture("", "valid", paths, endpoint=Endpoint(), certificate="productProvider")
    broker = probe.product_fixture_broker(issuer, provider)
    broker.admit()
    errors = []
    def exchange(authority, *, accepted):
        client, server = socket.socketpair(); client.settimeout(3)
        def serve():
            try:
                response = broker.exchange(server)
                if response: server.sendall(response)
            except Exception as exc: errors.append(exc)
            finally: server.close()
        worker = threading.Thread(target=serve); worker.start()
        try:
            client.sendall(f"CONNECT {authority} HTTP/1.1\r\nHost: {authority}\r\n\r\n".encode())
            head = bytearray()
            while not head.endswith(b"\r\n\r\n"): head.extend(client.recv(1))
            if not accepted:
                assert b" 403 " in head
                return
            assert b" 200 " in head
            context = ssl.create_default_context(cafile=str(paths["ca"]))
            with context.wrap_socket(client, server_hostname=authority.split(":")[0]) as secure:
                secure.sendall(b"GET /local-proof HTTP/1.1\r\nHost: local-proof\r\n\r\n")
                result = bytearray()
                expected = b"HTTP/1.1 200 OK\r\nContent-Length: 7\r\nConnection: close\r\n\r\nauthored"
                while len(result) < len(expected):
                    data = secure.recv(4096)
                    assert data, "truncated local TLS response"
                    result.extend(data)
            assert bytes(result) == expected
        finally:
            client.close(); worker.join(3)
            assert not worker.is_alive()
    try:
        exchange(probe.PRODUCT_ISSUER_AUTHORITY, accepted=True)
        broker.close_authority(probe.PRODUCT_ISSUER_AUTHORITY)
        exchange(probe.PRODUCT_ISSUER_AUTHORITY, accepted=False)
        exchange(probe.PRODUCT_PROVIDER_AUTHORITY, accepted=True)
        for authority in (probe.ISSUER_AUTHORITY, probe.tls.AUTHORITY, "unmapped.invalid:443"):
            exchange(authority, accepted=False)
        assert broker.opened == 2 and not errors
    finally:
        broker.close(); issuer.close(); provider.close()


@pytest.fixture(scope="module")
def product_managed_observed():
    if os.environ.get("NEMA_NATIVE_PRODUCT_MANAGED_PROBE") != "1":
        pytest.skip("explicit reviewed product-managed offline native opt-in required")
    report = probe.run_probe(mode=probe.PRODUCT_CASE)
    if output := os.environ.get("NEMA_NATIVE_PRODUCT_MANAGED_OUTPUT"):
        Path(output).write_text(json.dumps(report, indent=2) + "\n")
    return report


def test_product_managed_contained_native_uses_exact_config_and_private_publication(product_managed_observed):
    report = product_managed_observed
    case = report["cases"][probe.PRODUCT_CASE]
    assert probe.assess_worker_case(case) == [], json.dumps({"failure": case["failure"], "assessment": case["assessmentProblems"], "stderr": case["nativeStderr"]})
    assert case["positiveOwnedWorkerAccepted"] and case["durableReopenMatches"]
    assert report["realAuthCalls"] == report["realModelCalls"] == report["realUpstreamRequests"] == 0
    assert not report["liveAdmission"] and not report["subscriptionExecution"]


def test_positive_response_reuses_exact_bounded_text_sse_once():
    value = services(probe.POSITIVE_CASE)
    positive_prefix(value)
    status, reason, sse = value.dispatch("provider", positive_request(value))
    assert (status, reason) == (200, "authored-managed-text")
    assert sse == probe.catalog.authored_stream(probe.derived.MODEL, 2)
    assert len(sse) == 2769 < 8192
    assert b"function_call" not in sse and b"futureSyntheticField" in sse
    with pytest.raises(ValueError, match="one fallback/settings"): value.dispatch("provider", positive_request(value))


@pytest.mark.parametrize("prefix", ["none", "no-settings", "no-websocket"])
def test_positive_response_requires_both_fixed_preceding_protocol_steps(prefix):
    value = services(probe.POSITIVE_CASE)
    value.provider_enabled = True
    value.websocket_served = prefix == "no-settings"
    value.settings_served = prefix == "no-websocket"
    with pytest.raises(ValueError, match="prefix"): value.dispatch("provider", positive_request(value))
    assert not value.response_served


def test_positive_duplicate_response_is_recorded_and_latches_stop():
    value = services(probe.POSITIVE_CASE)
    positive_prefix(value)
    request = positive_request(value)
    body = request["bodyRaw"]
    headers = {**request["headers"], "content-length": str(len(body))}
    raw = ("POST " + probe.PROVIDER_PATH + " HTTP/1.1\r\n" +
           "\r\n".join(k + ": " + v for k, v in headers.items()) + "\r\n\r\n" + body).encode()
    first = socket_request(value, raw, "provider")
    assert b" 200 " in first.split(b"\r\n")[0] and b"Content-Type: text/event-stream" in first
    second = socket_request(value, raw, "provider")
    assert b" 400 " in second.split(b"\r\n")[0] and value.abort.is_set()
    assert [event["status"] for event in value.events] == [200, 400]


def test_positive_rejects_invented_tool_history_before_sse():
    value = services(probe.POSITIVE_CASE)
    positive_prefix(value)
    req = positive_request(value)
    payload = json.loads(req["bodyRaw"])
    payload["input"].append({"type": "function_call_output", "call_id": "not-authored", "output": "forged"})
    req["bodyRaw"] = json.dumps(payload)
    with pytest.raises(ValueError, match="tool-call history"): value.dispatch("provider", req)
    assert not value.response_served


@pytest.fixture(scope="module")
def positive_observed():
    if os.environ.get("NEMA_NATIVE_MANAGED_TEXT_PROBE") != "1":
        pytest.skip("explicit contained synthetic managed-text opt-in required")
    result = probe.run_probe(mode=probe.POSITIVE_CASE)
    if output := os.environ.get("NEMA_NATIVE_MANAGED_TEXT_OUTPUT"):
        Path(output).write_text(json.dumps(result, indent=2) + "\n")
    return result


def test_contained_positive_managed_text_recovers_and_reopens(positive_observed):
    report = positive_observed
    assert set(report["cases"]) == {probe.POSITIVE_CASE}
    case = report["cases"][probe.POSITIVE_CASE]
    assert probe.assess_case(case) == [], json.dumps({"failure": case["failure"], "assessment": case["assessmentProblems"], "stderr": case["nativeStderr"]})
    assert case["positiveManagedTextAccepted"] and case["nativeTerminalRecovered"]
    assert case["nativeTurnOutcome"]["status"] == "completed"
    assert case["savedArtifact"]["executionEvidence"] == case["replayRecoveredArtifact"]["executionEvidence"] == "synthetic"
    assert case["savedArtifact"] == case["reopenedArtifact"]
    assert case["recoveredArtifact"] == case["replayRecoveredArtifact"]
    assert report["realAuthCalls"] == report["realModelCalls"] == report["realUpstreamRequests"] == 0
    assert report["nativeLoginRPCs"] == report["nativeTurnRPCs"] == 1


POSITIVE_RECORDED = Path(__file__).parents[1] / "docs/evidence/NATIVE_MANAGED_TEXT_0_154_0.json"


def test_committed_positive_recovers_without_starting_another_process(monkeypatch):
    monkeypatch.setattr(probe.AppServerClient, "start", lambda *a, **k: pytest.fail("native process during historical recovery"))
    report = json.loads(POSITIVE_RECORDED.read_bytes())
    test_contained_positive_managed_text_recovers_and_reopens(report)
    case = report["cases"][probe.POSITIVE_CASE]
    assert probe.recover_recorded_positive(case) == case["recoveredArtifact"]
    assert case["fixtureTokenGenerations"] == ["A"]
    assert case["connectAttempts"] == case["processedConnects"] == case["mappedEndpointOpens"] == 6
    assert case["unrecordedConnectRefusals"] == 0
    for i, row in enumerate(case["selectedContext"]["records"], 1):
        assert json.loads(row["rawText"])["params"]["item"]["futureFixtureField"] == {"preserve": i}
    response = next(e for e in case["endpointEvents"] if e["reason"] == "authored-managed-text")
    assert '"futureSyntheticField":{"authoredFixture":true}' in response["responseRaw"]


def edit_raw(case, method, edit, *, direction=None):
    for row in case["traceRecords"]:
        message = json.loads(row["rawText"])
        if message.get("method") == method and (direction is None or row["direction"] == direction):
            edit(message, row)
            row["rawText"] = json.dumps(message)
            return
    pytest.fail("fixture method absent: " + method)


@pytest.mark.parametrize("mutation,problem", [
    ("missing-terminal", "positive-correlated-artifact-not-recovered"),
    ("wrong-terminal-thread", "positive-correlated-artifact-not-recovered"),
    ("wrong-terminal-turn", "positive-correlated-artifact-not-recovered"),
    ("missing-profile", "positive-correlated-artifact-not-recovered"),
    ("copied-profile", "positive-correlated-artifact-not-recovered"),
    ("late-profile", "positive-correlated-artifact-not-recovered"),
    ("native-profile", "positive-correlated-artifact-not-recovered"),
    ("changed-packet", "correlated-turn-ack-absent"),
    ("changed-selected-record", "positive-selected-records-differ"),
    ("capture-gap", "reported-capture-gap"),
    ("duplicate-response", "serial-challenge-prefix-differs"),
    ("missing-ack", "correlated-turn-ack-absent"),
    ("wrong-ack", "correlated-turn-ack-absent"),
    ("wrong-reopened-artifact", "positive-durable-artifact-differs"),
    ("classification-inflation", "positive-correlated-artifact-not-recovered"),
    ("saved-nonterminal-attempt", "positive-durable-artifact-differs"),
])
def test_positive_acceptance_rejects_corrupted_source_recovery_and_classification(mutation, problem):
    case = json.loads(POSITIVE_RECORDED.read_bytes())["cases"][probe.POSITIVE_CASE]
    assert probe.assess_case(case) == []
    if mutation == "missing-terminal":
        edit_raw(case, "turn/completed", lambda m, r: m.update(method="discarded-terminal"))
    elif mutation.startswith("wrong-terminal-"):
        if mutation.endswith("thread"): edit_raw(case, "turn/completed", lambda m, r: m["params"].update(threadId="other"))
        else: edit_raw(case, "turn/completed", lambda m, r: m["params"]["turn"].update(id="other"))
    elif mutation == "missing-profile": edit_raw(case, "$native/profile", lambda m, r: m.update(method="$history/note"))
    elif mutation == "copied-profile": edit_raw(case, "$native/profile", lambda m, r: r.update(source="copied-native-source"))
    elif mutation == "native-profile": edit_raw(case, "$native/profile", lambda m, r: r.update(direction="appserver_to_client"))
    elif mutation == "late-profile":
        original = deepcopy(next(row for row in case["traceRecords"] if json.loads(row["rawText"]).get("method") == "$native/profile"))
        edit_raw(case, "$native/profile", lambda m, r: m.update(method="$history/note"))
        original["seq"] = len(case["traceRecords"]) + 1
        case["traceRecords"].append(original)
    elif mutation == "changed-packet": case["selectedContext"]["projectedPrompt"] += "Changed frozen input"
    elif mutation == "changed-selected-record": case["selectedContext"]["records"][0]["rawText"] = '{}'
    elif mutation == "capture-gap": case["nativeCapture"]["failure"] = {"reason": "authored gap"}
    elif mutation == "duplicate-response": case["endpointEvents"].append(deepcopy(case["endpointEvents"][-1]))
    elif mutation == "missing-ack": case["nativeReplies"].pop("turnStart")
    elif mutation == "wrong-ack": case["nativeReplies"]["turnStart"]["turn"]["id"] = "other"
    elif mutation == "wrong-reopened-artifact": case["reopenedArtifact"]["text"] = "Altered durable output"
    elif mutation == "classification-inflation": case["recoveredArtifact"]["executionEvidence"] = "native-observed"
    else: case["savedAttempt"]["status"] = "running"
    assert problem in probe.assess_case(case)
