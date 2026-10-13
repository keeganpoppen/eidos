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
