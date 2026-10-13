"""Synthetic parser/protocol tests; real contained native calls require opt-in."""
import importlib.util
import json
import os
from pathlib import Path
import socket
import tomllib

import pytest

spec = importlib.util.spec_from_file_location(
    "native_tool_boundary", Path(__file__).parents[1] / "scripts/probe_native_tool_boundary.py")
assert spec and spec.loader
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)

PROMPT = "Exact selected fixture packet."


def provider_payload(*, output=None):
    value = {"model": probe.transport.MODEL, "stream": True,
             "input": [{"role": "user", "content": [{"type": "input_text", "text": PROMPT}]}]}
    if output is not None:
        value["input"].append(output)
    return value


def message(payload, *, route="/v1/responses", method="POST", headers=b""):
    data = json.dumps(payload).encode()
    return (f"{method} {route} HTTP/1.1\r\nHost: fixture\r\nContent-Length: {len(data)}\r\n".encode()
            + headers + b"\r\n" + data)


def exchange(broker, data):
    server, client = socket.socketpair()
    try:
        client.sendall(data)
        client.shutdown(socket.SHUT_WR)
        reply = broker.exchange(server)
        return int(reply.split(b" ")[1]), reply.split(b"\r\n\r\n", 1)[1]
    finally:
        server.close()
        client.close()


def test_fixture_never_requests_anything_beyond_its_one_read_only_resource():
    events = probe.tool_response_events()
    call = events[-1]["response"]["output"][0]
    assert call["type"] == "function_call" and call["name"] == "read_mcp_resource"
    assert json.loads(call["arguments"]) == {"server": "fixture", "uri": probe.URI}
    assert call["call_id"] == probe.CALL_ID
    assert len(probe.tool_response_stream()) < probe.transport.MAX_RESPONSE


@pytest.mark.parametrize("case", probe.CASES)
def test_prelaunch_config_changes_only_supported_explicit_fixture_controls(case):
    config = tomllib.loads(probe.fixture_config(case))
    assert config["mcp_servers"]["fixture"]["enabled_tools"] == []
    assert config["mcp_servers"]["fixture"]["enabled"] == (case != "allMcpDisabled")
    provider = config["model_providers"][probe.transport.PROVIDER]
    assert provider["requires_openai_auth"] is False and "env_key" not in provider
    assert provider["base_url"] == "http://127.0.0.1:FIXTURE_PORT/v1"
    if case != "baseline":
        assert config["tools"]["experimental_request_user_input"]["enabled"] is False
        assert config["orchestrator"]["skills"]["enabled"] is False
        assert config["orchestrator"]["mcp"]["enabled"] is False
        assert config["skills"] == {"include_instructions": False, "bundled": {"enabled": False}}


@pytest.mark.parametrize("method", ["command/exec", "process/spawn", "thread/shellCommand",
                                    "account/login/start", "mcpServer/tool/call"])
def test_inherited_client_cannot_issue_native_effect_rpcs(method):
    client = probe.transport.SyntheticTurnClient(["must-not-execute"])
    with pytest.raises(ValueError, match="refuses"):
        client.request(method, {})
    assert client.process is None


@pytest.mark.parametrize("event", [
    {"id": 1, "method": "item/tool/requestApproval", "params": {}},
    {"method": "item/started", "params": {"item": {"type": "commandExecution"}}},
    {"method": "item/started", "params": {"item": {"type": "mcpToolCall", "server": "other", "tool": probe.TOOL, "arguments": probe.ARGUMENTS}}},
    {"method": "item/started", "params": {"item": {"type": "mcpToolCall", "server": "fixture", "tool": "write", "arguments": probe.ARGUMENTS}}},
])
def test_observer_aborts_unexpected_actions_without_claiming_pre_effect_authorization(event):
    with pytest.raises(RuntimeError):
        probe.inspect_event(event)


def test_provider_service_requires_one_matching_tool_output_before_fixed_final_response():
    broker = probe.ToolFixtureBroker(PROMPT)
    first = message(provider_payload())
    assert exchange(broker, first)[0] == 403
    broker.admit()
    assert exchange(broker, first)[0] == 200
    assert exchange(broker, first)[0] == 422
    wrong = {"type": "function_call_output", "call_id": "other", "output": "unrelated"}
    assert exchange(broker, message(provider_payload(output=wrong)))[0] == 422
    output = {**wrong, "call_id": probe.CALL_ID}
    assert exchange(broker, message(provider_payload(output=output)))[0] == 200
    assert exchange(broker, message(provider_payload(output=output)))[0] == 409
    assert broker.provider_requests == 2
    with pytest.raises(ValueError, match="renewed"):
        broker.admit()


@pytest.mark.parametrize("route,method,headers,status", [
    ("https://unapproved.invalid/v1/responses", "POST", b"", 403),
    ("/v1/responses?redirect=1", "POST", b"", 403),
    ("/mcp", "GET", b"", 403),
    ("/v1/responses", "POST", b"Authorization: prohibited-fixture\r\n", 400),
    ("/v1/responses", "POST", b"Transfer-Encoding: chunked\r\n", 400),
    ("/v1/responses", "POST", b"Content-Encoding: gzip\r\n", 400),
    ("/v1/responses", "POST", b"Host: duplicate\r\n", 400),
])
def test_service_denies_unapproved_routes_headers_and_redirect_shaped_requests(route, method, headers, status):
    broker = probe.ToolFixtureBroker(PROMPT)
    broker.admit()
    assert exchange(broker, message(provider_payload(), route=route, method=method, headers=headers))[0] == status
    assert broker.provider_requests == broker.resource_reads == 0


@pytest.mark.parametrize("method,params,status", [
    ("resources/read", {"uri": probe.URI}, 200),
    ("resources/read", {"uri": probe.URI, "_meta": {"progressToken": 1}}, 200),
    ("resources/read", {"uri": "file:///private/canary"}, 403),
    ("resources/read", {"uri": "https://unapproved.invalid/"}, 403),
    ("resources/read", {"uri": probe.URI, "other": "unsupported"}, 403),
    ("tools/call", {"name": "fixture_echo", "arguments": {}}, 403),
])
def test_mcp_fixture_has_only_its_literal_resource_read_effect(method, params, status):
    broker = probe.ToolFixtureBroker(PROMPT)
    code, body = exchange(broker, message({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}, route="/mcp"))
    assert code == status
    assert broker.resource_reads == (1 if status == 200 else 0)
    if status == 200:
        assert probe.RESOURCE_TEXT in body.decode()


def test_deep_json_and_request_count_remain_bounded_after_parser_extraction():
    broker = probe.ToolFixtureBroker(PROMPT)
    body = b"[" * 2000 + b"0" + b"]" * 2000
    raw = f"POST /v1/responses HTTP/1.1\r\nContent-Length: {len(body)}\r\n\r\n".encode() + body
    assert exchange(broker, raw)[0] == 400
    assert broker.events[-1]["reason"] == "malformed"
    assert broker.provider_requests == broker.resource_reads == 0
    for _ in range(probe.transport.MAX_REQUESTS - 1):
        assert exchange(broker, message(provider_payload()))[0] == 403
    assert exchange(broker, message(provider_payload()))[0] == 429


@pytest.fixture(scope="module")
def observed():
    if os.environ.get("NEMA_NATIVE_TOOL_BOUNDARY_PROBE") != "1":
        pytest.skip("opt in to disconnected native turns with an authored tool-call fixture; zero real models")
    return probe.run_probe()


@pytest.mark.parametrize("name", probe.CASES)
def test_native_turn_tool_observation_and_provider_followup_stay_correlated(observed, name):
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
    assert case["nativeTurnRPCs"] == 1 and case["providerRequests"] == 2
    assert case["providerRequests"] == sum(e.get("target") == "/v1/responses" for e in case["brokerEvents"])
    assert case["acceptedProviderRequests"] == 2
    assert case["policy"]["installedBeforeInitialExec"] and case["policy"]["allListenerCopiesClosed"]
    assert case["nativeReplies"]["account/read"] == {"account": None, "requiresOpenaiAuth": False}
    accepted = [e for e in case["brokerEvents"] if e["reason"] in {"authored-tool-call", "authored-final-text"}]
    assert len(accepted) == 2
    output = next(i for i in json.loads(accepted[1]["bodyRaw"])["input"] if i["type"] == "function_call_output")
    assert output["call_id"] == probe.CALL_ID
    actions = [e["params"]["item"] for e in case["nativeEvents"]
               if e.get("method") == "item/completed" and e["params"]["item"]["type"] == "mcpToolCall"]
    if name == "allMcpDisabled":
        assert output["output"] == "unsupported call: read_mcp_resource"
        assert case["fixtureResourceReads"] == 0 and actions == []
        assert all(e["target"] == "/v1/responses" for e in case["brokerEvents"])
        assert all(json.loads(e["bodyRaw"])["tools"] == [] for e in accepted)
        assert case["nativeReplies"]["mcpServerStatus/list"]["data"][0]["runtimeStatus"] == "disabled"
    else:
        assert probe.RESOURCE_TEXT in output["output"]
        assert case["fixtureResourceReads"] == 1
        assert len(actions) == 1 and actions[0]["status"] == "completed"
        assert actions[0]["id"] == probe.CALL_ID and actions[0]["arguments"] == probe.ARGUMENTS
        status = case["nativeReplies"]["mcpServerStatus/list"]["data"][0]
        assert status["runtimeStatus"] == "connected" and status["tools"] == {}
    assert case["savedArtifact"]["executionEvidence"] == "synthetic"
    assert case["savedArtifact"]["text"] == probe.transport.OUTPUT_TEXT
    for event in case["nativeEvents"]:
        probe.inspect_event(event)


def test_effective_controls_and_wire_contrast_are_recorded_without_authority_inflation(observed):
    cases = observed["cases"]
    tools = {n: {t["name"] for t in c["providerRequestAnalysis"]["offeredToolSchemas"]} for n, c in cases.items()}
    assert tools["baseline"] == {"list_mcp_resources", "list_mcp_resource_templates", "read_mcp_resource", "request_user_input", "skills"}
    assert tools["builtinsDisabled"] == {"list_mcp_resources", "list_mcp_resource_templates", "read_mcp_resource"}
    assert tools["allMcpDisabled"] == set()
    for name in ("builtinsDisabled", "allMcpDisabled"):
        config = cases[name]["nativeReplies"]["config/read"]["config"]
        assert config["orchestrator"] == {"skills": {"enabled": False}, "mcp": {"enabled": False}}
        assert config["skills"] == {"bundled": {"enabled": False}, "include_instructions": False}
        assert config["mcp_servers"]["fixture"]["enabled_tools"] == []
        # The installed config/read projection omits this accepted setting.
        assert "experimental_request_user_input" not in config["tools"]
    assert observed["nativeTurnRPCs"] == 3 and observed["providerRequests"] == 6
    assert observed["realModelCalls"] == observed["realUpstreamRequests"] == 0
    assert not observed["existingCredentialsMounted"] and not observed["subscriptionExecution"]
    assert not observed["callerAuthenticationEstablished"] and not observed["liveAdmission"]
