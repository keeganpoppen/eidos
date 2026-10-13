"""Default tests use socket pairs only; contained native turns require opt-in."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import socket
import tomllib

import pytest

spec = importlib.util.spec_from_file_location(
    "native_catalog_probe", Path(__file__).parents[1] / "scripts/probe_native_model_catalog.py")
assert spec and spec.loader
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)
PROMPT = "Exact selected fixture packet."


def payload(model, step=0):
    value = {"model": model, "stream": True, "instructions": "Fixture",
             "tools": [], "input": [{"type": "message", "role": "user",
             "content": [{"type": "input_text", "text": PROMPT}]}]}
    if model == "gpt-6-astra":
        value.pop("tools")
        value.pop("instructions")
        value["input"].insert(0, {"type": "additional_tools", "role": "developer", "tools": []})
    for identifier in [probe.tool_probe.CALL_ID, probe.CLOCK_CALL_ID][:step]:
        value["input"].append({"type": "function_call_output", "call_id": identifier, "output": "synthetic"})
    return value


def message(value, *, route="/v1/responses", method="POST", extra=b"", lite=None):
    body = json.dumps(value).encode()
    if lite is None:
        lite = isinstance(value, dict) and value.get("model") == "gpt-6-astra"
    header = f"{probe.LITE_HEADER}: true\r\n".encode() if lite else b""
    return (f"{method} {route} HTTP/1.1\r\nHost: fixture\r\nContent-Length: {len(body)}\r\n".encode()
            + header + extra + b"\r\n" + body)


def exchange(broker, raw):
    server, client = socket.socketpair()
    try:
        client.sendall(raw)
        client.shutdown(socket.SHUT_WR)
        result = broker.exchange(server)
        return int(result.split(b" ")[1]), result.split(b"\r\n\r\n", 1)[1]
    finally:
        server.close()
        client.close()


def test_exact_public_catalog_is_required_before_startup(tmp_path):
    data, metadata = probe.checked_catalog()
    assert hashlib.sha256(data).hexdigest() == probe.CATALOG_SHA256
    assert metadata["gpt-6-astra"]["tool_mode"] == "code_mode_only"
    assert metadata["gpt-6-astra"]["use_responses_lite"] is True
    assert metadata["gpt-5.5"]["tool_mode"] is None
    assert metadata["gpt-5.5"]["use_responses_lite"] is False
    tampered = tmp_path / "catalog.json"
    tampered.write_bytes(data + b" ")
    with pytest.raises(ValueError, match="exact reviewed"):
        probe.checked_catalog(tampered)
    tampered.write_bytes(b" " * 600001)
    with pytest.raises(ValueError, match="exact reviewed"):
        probe.checked_catalog(tampered)


@pytest.mark.parametrize("model", probe.MODELS)
def test_config_pins_startup_catalog_and_disabled_integrations(model):
    config = tomllib.loads(probe.fixture_config(model))
    assert config["model_catalog_json"] == "/fixture/models.json"
    assert config["model"] == model
    assert config["features"]["code_mode"] is False
    assert config["mcp_servers"]["fixture"]["enabled"] is False
    assert config["orchestrator"] == {"skills": {"enabled": False}, "mcp": {"enabled": False}}
    provider = config["model_providers"][probe.transport.PROVIDER]
    assert provider["requires_openai_auth"] is False
    assert provider["base_url"] == "http://127.0.0.1:FIXTURE_PORT/v1"
    assert not {"env_key", "experimental_bearer_token"} & provider.keys()


@pytest.mark.parametrize("model", probe.MODELS)
def test_authored_response_sequence_has_only_resource_and_clock_calls_then_fixed_text(model):
    for step in range(3):
        raw = probe.authored_stream(model, step)
        assert len(raw) <= probe.transport.MAX_RESPONSE
        events = [json.loads(line[6:]) for line in raw.decode().splitlines() if line.startswith("data: ")]
        response = events[-1]["response"]
        assert response["model"] == model
        item = response["output"][0]
        if step == 0:
            assert item["name"] == "read_mcp_resource"
            assert json.loads(item["arguments"]) == probe.tool_probe.ARGUMENTS
        elif step == 1:
            assert item["name"] == "curr_time" and item["namespace"] == "clock"
            assert item["call_id"] == probe.CLOCK_CALL_ID and item["arguments"] == "{}"
        else:
            assert item["content"][0]["text"] == probe.transport.OUTPUT_TEXT


@pytest.mark.parametrize("model", probe.MODELS)
def test_exact_sequence_denies_early_duplicate_wrong_model_and_wrong_correlation(model):
    broker = probe.CatalogFixtureBroker(PROMPT, model)
    assert exchange(broker, message(payload(model)))[0] == 403
    broker.admit()
    other = next(name for name in probe.MODELS if name != model)
    assert exchange(broker, message(payload(other)))[0] == 422
    assert exchange(broker, message(payload(model, 1)))[0] == 422
    assert exchange(broker, message(payload(model)))[0] == 200
    assert exchange(broker, message(payload(model)))[0] == 422
    assert exchange(broker, message(payload(model, 2)))[0] == 422
    assert exchange(broker, message(payload(model, 1)))[0] == 200
    assert exchange(broker, message(payload(model, 2)))[0] == 200
    assert exchange(broker, message(payload(model, 2)))[0] == 409
    assert broker.provider_requests == 3 and broker.resource_reads == 0


@pytest.mark.parametrize("model", probe.MODELS)
def test_lite_envelope_and_header_must_agree(model):
    broker = probe.CatalogFixtureBroker(PROMPT, model)
    broker.admit()
    assert exchange(broker, message(payload(model), lite=model != "gpt-6-astra"))[0] == 422
    changed = payload(model)
    if model == "gpt-6-astra":
        changed["tools"] = []
    else:
        changed["input"].insert(0, {"type": "additional_tools", "role": "developer", "tools": []})
    assert exchange(broker, message(changed))[0] == 422
    assert broker.provider_requests == 0


@pytest.mark.parametrize("mutation", [
    {"input": None}, {"input": [3]}, {"input": [{"role": "user", "content": None}]},
    {"input": [{"role": "user", "content": [3]}]}, {"stream": False}, {"jsonrpc": "2.0"},
])
def test_malformed_shapes_fail_closed_without_consuming_step(mutation):
    broker = probe.CatalogFixtureBroker(PROMPT, "gpt-5.5")
    broker.admit()
    assert exchange(broker, message({**payload("gpt-5.5"), **mutation}))[0] == 422
    assert broker.provider_requests == 0


@pytest.mark.parametrize("route,method,extra,status", [
    ("https://unapproved.invalid/v1/responses", "POST", b"", 403),
    ("/v1/responses?redirect=1", "POST", b"", 403),
    ("/mcp", "POST", b"", 403), ("/v1/responses", "GET", b"", 403),
    ("/v1/responses", "POST", b"Authorization: prohibited\r\n", 400),
    ("/v1/responses", "POST", b"Transfer-Encoding: chunked\r\n", 400),
    ("/v1/responses", "POST", b"Content-Encoding: gzip\r\n", 400),
    ("/v1/responses", "POST", b"Host: duplicate\r\n", 400),
])
def test_routes_and_headers_are_not_relaxed_for_lite(route, method, extra, status):
    broker = probe.CatalogFixtureBroker(PROMPT, "gpt-6-astra")
    broker.admit()
    assert exchange(broker, message(payload("gpt-6-astra"), route=route, method=method, extra=extra))[0] == status
    assert broker.provider_requests == broker.resource_reads == 0


def test_nested_json_and_request_budget_remain_controlled():
    broker = probe.CatalogFixtureBroker(PROMPT, "gpt-5.5")
    body = b"[" * 2000 + b"0" + b"]" * 2000
    raw = f"POST /v1/responses HTTP/1.1\r\nContent-Length: {len(body)}\r\n\r\n".encode() + body
    assert exchange(broker, raw)[0] == 400
    assert broker.events[-1]["reason"] == "malformed"
    assert broker.provider_requests == 0
    for _ in range(probe.transport.MAX_REQUESTS - 1):
        assert exchange(broker, message(payload("gpt-5.5")))[0] == 403
    assert exchange(broker, message(payload("gpt-5.5")))[0] == 429


def test_nested_object_is_refused_without_consuming_step():
    broker = probe.CatalogFixtureBroker(PROMPT, "gpt-5.5")
    broker.admit()
    body = b'{"nested":' + b"[" * 10000 + b"0" + b"]" * 10000 + b"}"
    raw = f"POST /v1/responses HTTP/1.1\r\nContent-Length: {len(body)}\r\n\r\n".encode() + body
    assert exchange(broker, raw)[0] in {400, 422}
    assert broker.provider_requests == 0


def test_parser_recursion_error_is_recorded_without_consuming_step(monkeypatch):
    broker = probe.CatalogFixtureBroker(PROMPT, "gpt-5.5")
    broker.admit()
    raw = message(payload("gpt-5.5"))
    def fail_decode(_):
        raise RecursionError("fixture decoder exhaustion")
    monkeypatch.setattr(probe.json, "loads", fail_decode)
    assert exchange(broker, raw)[0] == 400
    assert broker.events[-1]["status"] == 400 and broker.events[-1]["reason"] == "malformed"
    assert broker.provider_requests == 0


@pytest.fixture(scope="module")
def observed():
    if os.environ.get("NEMA_NATIVE_MODEL_CATALOG_PROBE") != "1":
        pytest.skip("opt in to disconnected native turns with public catalog/local authored responses")
    report = probe.run_probe()
    if output := os.environ.get("NEMA_NATIVE_MODEL_CATALOG_EVIDENCE"):
        Path(output).write_text(json.dumps(report, indent=2) + "\n")
    return report


@pytest.mark.parametrize("model", probe.MODELS)
def test_contained_catalog_case_preserves_actual_outcome_and_auth_boundary(observed, model):
    case = observed["cases"][model]
    assert case["policy"]["installedBeforeInitialExec"] and case["policy"]["allListenerCopiesClosed"]
    assert case["nativeReplies"]["account/read"] == {"account": None, "requiresOpenaiAuth": False}
    assert case["catalogSha256"] == probe.CATALOG_SHA256
    assert case["nativeReplies"]["config/read"]["config"]["model_catalog_json"] == "/fixture/models.json"
    assert case["nativeTurnRPCs"] == 1
    assert case["providerRequests"] == sum(e.get("target") == "/v1/responses" for e in case["brokerEvents"])
    assert case["fixtureResourceReads"] == 0
    assert not any(e.get("target") == "/mcp" for e in case["brokerEvents"])
    assert case["failure"] is None, case["failure"]
    assert case["acceptedProviderRequests"] == 3
    assert case["savedArtifact"]["executionEvidence"] == "synthetic"
    assert case["savedArtifact"]["text"] == probe.transport.OUTPUT_TEXT
    assert not any("fallback" in event.get("params", {}).get("message", "").lower()
                   for event in case["nativeEvents"] if event.get("method") == "warning")
    assert case["nativeReplies"]["mcpServerStatus/list"]["data"][0]["runtimeStatus"] == "disabled"
    outputs = case["providerRequestAnalyses"][-1]["functionOutputs"]
    assert [item["call_id"] for item in outputs] == [probe.tool_probe.CALL_ID, probe.CLOCK_CALL_ID]
    assert outputs[0]["output"] == "unsupported call: read_mcp_resource"
    if model == "gpt-6-astra":
        assert re.fullmatch(r"It is \d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} UTC\.", outputs[1]["output"])
    else:
        assert outputs[1]["output"] == "unsupported call: clockcurr_time"
    # The successful Astra clock execution has no separate item/started or
    # item/completed action. This observer cannot establish pre-effect admission.
    assert {event["params"]["item"]["type"] for event in case["nativeEvents"]
            if event.get("method") in {"item/started", "item/completed"}} == {"userMessage", "agentMessage"}


def test_catalog_wire_contrast_is_not_subscription_or_caller_authentication(observed):
    assert observed["realModelCalls"] == observed["realUpstreamRequests"] == 0
    assert observed["nativeTurnRPCs"] == 2
    assert not observed["existingCredentialsMounted"] and not observed["subscriptionExecution"]
    assert not observed["callerAuthenticationEstablished"] and not observed["liveAdmission"]
    for model, case in observed["cases"].items():
        assert case["providerRequestAnalyses"]
        first = case["providerRequestAnalyses"][0]
        assert first["exactSelectedPromptOccurrences"] == 1
        assert first["responsesLiteHeader"] == ("true" if model == "gpt-6-astra" else None)
        if model == "gpt-6-astra":
            assert not first["topLevelToolsPresent"]
            tools = {tool["name"]: {nested["name"] for nested in tool["tools"]}
                     for tool in first["additionalTools"][0]["tools"]}
            assert tools == {"functions": {"exec", "wait", "request_user_input_async"},
                             "clock": {"sleep"}, "collaboration": {"followup_task", "interrupt_agent",
                             "list_agents", "send_message", "spawn_agent", "wait_agent"}}
            execution = first["additionalTools"][0]["tools"][0]["tools"][0]
            assert execution["name"] == "exec" and "clock__curr_time" in execution["description"]
        else:
            assert first["topLevelToolsPresent"] and first["offeredToolSchemas"] == []
            assert first["additionalTools"] == []
