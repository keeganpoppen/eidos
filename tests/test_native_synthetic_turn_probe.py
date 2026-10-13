"""Fixture service tests; native turn RPCs require an explicit opt-in."""
import concurrent.futures
import importlib.util
import json
import os
from pathlib import Path
import socket

import pytest

spec = importlib.util.spec_from_file_location(
    "probe_native_synthetic_turn", Path(__file__).parents[1] / "scripts/probe_native_synthetic_turn.py")
assert spec and spec.loader
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)

PROMPT = "Selected synthetic packet."


def payload(**changes):
    return {"model": probe.MODEL, "stream": True, "input": [{"role": "user", "content": [
        {"type": "input_text", "text": PROMPT}]}], **changes}


def request(body=None, *, method="POST", target=probe.RESPONSE_PATH, extra=b""):
    data = json.dumps(payload() if body is None else body).encode()
    return (f"{method} {target} HTTP/1.1\r\nHost: fixture\r\nContent-Length: {len(data)}\r\n".encode()
            + extra + b"\r\n" + data)


def exchange(broker, message):
    server, client = socket.socketpair()
    try:
        client.sendall(message)
        client.shutdown(socket.SHUT_WR)
        response = broker.exchange(server)
        return int(response.split(b" ", 2)[1]), response.split(b"\r\n\r\n", 1)[1]
    finally:
        server.close()
        client.close()


@pytest.mark.parametrize("method", ["turn/steer", "thread/realtime/start", "account/login/start",
                                     "process/spawn", "thread/shellCommand", "command/exec",
                                     "mcpServer/oauth/login", "thread/resume"])
def test_unrelated_native_actions_are_refused_before_launch(method):
    client = probe.SyntheticTurnClient(["must-not-launch"])
    with pytest.raises(ValueError, match="refuses"):
        client.request(method, {})
    assert client.process is None and client.methods == []


def test_turn_rpc_requires_one_exact_prepared_input(monkeypatch):
    client = probe.SyntheticTurnClient(["must-not-launch"])
    expected = {"threadId": "fixture", "input": [{"type": "text", "text": PROMPT}]}
    with pytest.raises(ValueError, match="one exact"):
        client.request("turn/start", expected)
    client.expected_turn = expected
    with pytest.raises(ValueError, match="one exact"):
        client.request("turn/start", {**expected, "threadId": "other"})
    with pytest.raises(ValueError, match="one exact"):
        client.request("turn/start", {**expected, "input": []})
    monkeypatch.setattr(probe.AppServerClient, "request", lambda *a, **k: {"synthetic": True})
    assert client.request("turn/start", expected) == {"synthetic": True}
    with pytest.raises(ValueError, match="one exact"):
        client.request("turn/start", expected)
    assert client.turn_count == 1 and client.process is None


def test_refresh_notifications_and_native_approvals_are_refused():
    client = probe.SyntheticTurnClient(["must-not-launch"])
    with pytest.raises(ValueError, match="refresh"):
        client.request("account/read", {"refreshToken": True})
    with pytest.raises(ValueError):
        client.notify("turn/start", {})
    with pytest.raises(ValueError):
        client.respond(1, {"decision": "accept"})
    assert client.process is None


@pytest.mark.parametrize("event", [
    {"id": 7, "method": "item/commandExecution/requestApproval", "params": {}},
    {"id": 9, "method": "unknown/futureRequest", "params": {}},
    *({"method": "item/started", "params": {"item": {"type": kind}}}
      for kind in ("commandExecution", "fileChange", "mcpToolCall", "dynamicToolCall", "futureAction")),
])
def test_native_actions_or_requests_abort_fixture_client(event):
    with pytest.raises(RuntimeError, match="unsupported"):
        probe.inspect_event(event)


@pytest.mark.parametrize("message,status,reason", [
    (request(target="https://unapproved.invalid/v1/responses"), 403, "route-refused"),
    (request(target="/v1/responses?redirect=1"), 403, "route-refused"),
    (request(target="/v1/%72esponses"), 403, "route-refused"),
    (request(method="GET"), 403, "route-refused"),
    (request({"jsonrpc": "2.0", "id": 1, "method": "initialize"}), 422, "fixture-provider-shape-refused"),
    (request(payload(model="foreign-model")), 422, "fixture-provider-shape-refused"),
    (request(payload(input=[])), 422, "fixture-provider-shape-refused"),
    (request(payload(stream=False)), 422, "fixture-provider-shape-refused"),
    (request(extra=b"Authorization: synthetic-forbidden\r\n"), 400, "unsupported-header"),
    (request(extra=b"Content-Encoding: gzip\r\n"), 400, "unsupported-header"),
    (request(extra=b"Transfer-Encoding: chunked\r\n"), 400, "unsupported-header"),
    (request(extra=b"Content-Length: 0\r\n"), 400, "malformed"),
    (request()[:-1], 400, "malformed"),
    (b"POST /v1/responses HTTP/1.1\r\nContent-Length: 131073\r\n\r\n", 413, "body-limit"),
    (request(extra=b"X-Long: " + b"x" * probe.MAX_HEADER + b"\r\n"), 413, "header-limit"),
])
def test_service_default_denies_routes_mcp_shapes_and_unbounded_framing(message, status, reason):
    broker = probe.FixtureBroker(PROMPT)
    broker.admit()
    observed, body = exchange(broker, message)
    assert observed == status and json.loads(body)["reason"] == reason
    assert not broker.consumed


def test_fake_service_is_closed_then_one_use_and_emits_only_authored_message():
    broker = probe.FixtureBroker(PROMPT)
    assert exchange(broker, request())[0] == 403
    broker.admit()
    status, body = exchange(broker, request())
    assert status == 200 and body == probe.response_stream()
    assert exchange(broker, request())[0] == 409
    with pytest.raises(ValueError, match="renewed"):
        broker.admit()
    events = probe.response_events()
    assert events[-1]["type"] == "response.completed"
    assert events[-1]["response"]["status"] == "completed"
    assert events[-1]["response"]["output"][0]["content"][0]["text"] == probe.OUTPUT_TEXT
    assert {event["item"]["type"] for event in events if "item" in event} == {"message"}
    assert len(body) < probe.MAX_RESPONSE


def test_concurrent_matching_requests_consume_only_one_fixture_response():
    broker = probe.FixtureBroker(PROMPT)
    broker.admit()
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: exchange(broker, request())[0], range(2)))
    assert sorted(results) == [200, 409]


def test_deeply_nested_json_is_recorded_and_refused_without_consuming_permit():
    broker = probe.FixtureBroker(PROMPT)
    broker.admit()
    body = b"[" * 2000 + b"0" + b"]" * 2000
    assert len(body) < probe.MAX_BODY
    message = (f"POST {probe.RESPONSE_PATH} HTTP/1.1\r\nHost: fixture\r\n"
               f"Content-Length: {len(body)}\r\n\r\n").encode() + body
    assert exchange(broker, message)[0] == 400
    assert not broker.consumed
    assert broker.events[0]["status"] == 400
    assert broker.events[0]["reason"] == "malformed"
    assert broker.events[0]["bodyRaw"] == body.decode()
    assert exchange(broker, request())[0] == 200


def test_service_bounds_request_count_and_incomplete_request_time(monkeypatch):
    broker = probe.FixtureBroker(PROMPT)
    for _ in range(probe.MAX_REQUESTS):
        assert exchange(broker, request())[0] == 403
    assert exchange(broker, request())[0] == 429
    assert broker.requests == len(broker.events) == probe.MAX_REQUESTS
    monkeypatch.setattr(probe, "REQUEST_SECONDS", .02)
    server, client = socket.socketpair()
    try:
        client.sendall(b"POST /v1/responses HTTP/1.1\r\n")
        assert b"408 Fixture" in probe.FixtureBroker(PROMPT).exchange(server)
    finally:
        server.close()
        client.close()


@pytest.fixture(scope="module")
def observed():
    if os.environ.get("NEMA_NATIVE_SYNTHETIC_TURN_PROBE") != "1":
        pytest.skip("opt in to disconnected native turn RPCs with an authored local fixture; zero real models")
    return probe.run_probe()


@pytest.mark.parametrize("name", ["providerOnly", "withHttpMcp"])
def test_native_fixture_turn_completes_and_recovers_the_exact_synthetic_artifact(observed, name):
    case = observed["cases"][name]
    assert case["failure"] is None, case["failure"]
    capture = case["nativeCapture"]
    assert capture["failure"] is None and capture["diagnosticError"] is None
    assert 0 < sum(capture["receivedBytes"].values()) <= capture["limits"]["max_received_bytes"]
    recorded_limits = [json.loads(record["rawText"])["params"] for record in case["traceRecords"]
                       if record["direction"] == "internal"
                       and json.loads(record["rawText"]).get("method") == "$transport/limits"]
    assert len(recorded_limits) == 1
    assert recorded_limits[0]["limits"] == capture["limits"]
    assert case["durableReopenFailure"] is None and case["durableReopenMatches"]
    assert case["nativeTurnRPCs"] == 1
    assert case["nativeReplies"]["account/read"] == {"account": None, "requiresOpenaiAuth": False}
    assert case["savedArtifact"]["executionEvidence"] == "synthetic"
    assert case["savedArtifact"]["text"] == probe.OUTPUT_TEXT
    assert case["savedArtifact"]["citations"] == [1, 2]
    assert case["savedArtifact"]["unsupportedCitations"] == []
    assert case["savedArtifact"]["contextId"] == case["selectedContext"]["id"]
    assert case["savedArtifact"]["attemptId"] == case["savedAttempt"]["id"]
    assert case["policy"]["installedBeforeInitialExec"] and not case["unexpectedExecutableRan"]
    statuses = {item["name"]: item for item in case["nativeReplies"]["mcpServerStatus/list"]["data"]}
    assert "Operation not permitted" in statuses["unexpected"]["toolsError"]
    assert sum(event["status"] == 200 for event in case["brokerEvents"]) == 1
    analysis = case["providerRequestAnalysis"]
    assert analysis["exactSelectedPromptOccurrences"] == 1
    assert any(not item["isExactSelectedPrompt"] for item in analysis["inputFragments"])
    assert analysis["offeredToolSchemas"], "Do not silently claim the native wire has no tools"
    requests = [json.loads(record["rawText"]) for record in case["traceRecords"]
                if record["direction"] == "client_to_appserver"
                and json.loads(record["rawText"]).get("method") == "turn/start"]
    assert len(requests) == 1
    assert requests[0]["params"]["input"] == [{"type": "text", "text": case["selectedContext"]["projectedPrompt"]}]
    assert requests[0]["params"]["threadId"] == case["savedAttempt"]["threadId"]
    for event in case["nativeEvents"]:
        probe.inspect_event(event)
    assert not case["validProviderRequestImpersonationTested"]


def test_http_mcp_startup_is_compared_with_provider_requests_without_claiming_authentication(observed):
    case = observed["cases"]["withHttpMcp"]
    rejected = [event for event in case["brokerEvents"] if event["status"] != 200]
    assert rejected and all(event["status"] in {403, 422} for event in rejected)
    assert any(json.loads(event["bodyRaw"]).get("method") == "initialize"
               for event in rejected if event.get("bodyRaw"))
    assert any(event["target"].startswith("/.well-known/") for event in rejected)
    assert observed["nativeTurnRPCs"] == 2 and observed["realModelCalls"] == 0
    assert observed["realUpstreamRequests"] == 0
    assert not observed["subscriptionExecution"] and not observed["existingCredentialsMounted"]
    assert not observed["callerAuthenticationEstablished"] and not observed["liveAdmission"]
