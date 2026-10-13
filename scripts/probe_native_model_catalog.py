#!/usr/bin/env python3
"""Compare exact public model metadata using only a contained synthetic provider.

Native turn/provider RPCs are real local transport; every response is authored.
No credentials, upstream route, shell/code call, or production profile is used.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import platform
import socketserver
import tempfile
import threading
import time
from typing import Any

from eidos.investigation_worker import NativeInvestigationWorker
from eidos.trace import TraceStore

_spec = importlib.util.spec_from_file_location(
    "catalog_tool_fixture", Path(__file__).with_name("probe_native_tool_boundary.py"))
assert _spec and _spec.loader
tool_probe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tool_probe)
transport = tool_probe.transport
boundary = transport.boundary

CATALOG_URL = "https://raw.githubusercontent.com/openai/codex/rust-v0.154.0/codex-rs/models-manager/models.json"
CATALOG_SHA256 = "f3b8104396daf6381bed9d7c4b154a8664f9b5089b44b01a9d54f421566ec9a7"
CATALOG_PATH = Path(__file__).parents[1] / "docs/evidence/NATIVE_MODEL_CATALOG_0_154_0_PUBLIC.json"
MODELS = ("gpt-6-astra", "gpt-5.5")
LITE_HEADER = "x-openai-internal-codex-responses-lite"
MAX_PROVIDER_REQUESTS = 3
CLOCK_CALL_ID = "call_nema_fixture_clock"


def checked_catalog(path: Path = CATALOG_PATH) -> tuple[bytes, dict[str, Any]]:
    """Require exact reviewed public bytes before any native process starts."""
    with path.open("rb") as source:
        data = source.read(600001)
    if len(data) > 600000 or hashlib.sha256(data).hexdigest() != CATALOG_SHA256:
        raise ValueError("catalog is not the exact reviewed public tagged catalog")
    entries = {item["slug"]: item for item in json.loads(data)["models"]}
    return data, {name: entries[name] for name in MODELS}


def fixture_config(model: str) -> str:
    if model not in MODELS:
        raise ValueError("unknown catalog fixture model")
    config = tool_probe.fixture_config("allMcpDisabled")
    config = config.replace(f'model="{transport.MODEL}"', f'model="{model}"')
    return 'model_catalog_json="/fixture/models.json"\n' + config


def authored_stream(model: str, step: int) -> bytes:
    if model not in MODELS or step not in (0, 1, 2):
        raise ValueError("unknown fixed fixture response")
    events = tool_probe.tool_response_events() if step < 2 else transport.response_events()
    if step == 1:
        for event in events:
            for item in ([event["item"]] if "item" in event else []) + event.get("response", {}).get("output", []):
                item.update(id="fc_nema_clock", namespace="clock", name="curr_time",
                            call_id=CLOCK_CALL_ID, arguments="{}" if item["status"] == "completed" else "")
            if "item_id" in event:
                event["item_id"] = "fc_nema_clock"
            if "arguments" in event:
                event["arguments"] = "{}"
            if "delta" in event:
                event["delta"] = "{}"
    for event in events:
        if "response" in event:
            event["response"]["model"] = model
            event["response"]["id"] = f"resp_nema_catalog_{step}"
    stream = "".join(f"event: {e['type']}\ndata: {json.dumps(e, separators=(',', ':'))}\n\n"
                     for e in events).encode()
    if len(stream) > transport.MAX_RESPONSE:
        raise ValueError("authored response exceeds fixture bound")
    return stream


def provider_shape(payload: Any, headers: dict[str, str], model: str, prompt: str) -> bool:
    """Validate the tagged standard/Lite envelopes, without caller-auth claims."""
    if not isinstance(payload, dict) or "jsonrpc" in payload:
        return False
    if payload.get("model") != model or payload.get("stream") is not True:
        return False
    items = payload.get("input")
    if not isinstance(items, list) or not all(isinstance(item, dict) for item in items):
        return False
    texts = []
    for item in items:
        if item.get("type") in {"message", None}:
            content = item.get("content")
            if not isinstance(content, list) or not all(isinstance(part, dict) for part in content):
                return False
            if item.get("role") == "user":
                texts.extend(part.get("text") for part in content if part.get("type") == "input_text")
    if texts.count(prompt) != 1:
        return False
    additional = [item for item in items if item.get("type") == "additional_tools"]
    if model == "gpt-6-astra":
        return (headers.get(LITE_HEADER) == "true" and "tools" not in payload
                and "instructions" not in payload and len(additional) == 1
                and additional[0].get("role") == "developer" and isinstance(additional[0].get("tools"), list))
    return LITE_HEADER not in headers and not additional and isinstance(payload.get("tools"), list)


class CatalogFixtureBroker(tool_probe.ToolFixtureBroker):
    """Reuse bounded HTTP parsing; accept exactly three sequenced fixture steps."""
    def __init__(self, prompt: str, model: str) -> None:
        if model not in MODELS:
            raise ValueError("unknown catalog fixture model")
        super().__init__(prompt)
        self.model = model

    def dispatch(self, record: dict[str, Any]) -> tuple[int, str, bytes, str]:
        def refuse(status: int, reason: str) -> tuple[int, str, bytes, str]:
            return status, reason, json.dumps({"synthetic": True, "reason": reason}).encode(), "application/json"
        if record["method"] != "POST" or record["target"] != transport.RESPONSE_PATH:
            return refuse(403, "route-refused")
        payload = json.loads(record["bodyRaw"])
        if not isinstance(payload, dict):
            raise ValueError("object required")
        if not provider_shape(payload, record["headers"], self.model, self.prompt):
            return refuse(422, "fixture-provider-shape-refused")
        if not self.admitted:
            return refuse(403, "not-admitted")
        if self.provider_requests >= MAX_PROVIDER_REQUESTS:
            return refuse(409, "provider-request-limit")
        outputs = [item for item in payload["input"] if item.get("type") == "function_call_output"]
        expected = [tool_probe.CALL_ID, CLOCK_CALL_ID][:self.provider_requests]
        if [item.get("call_id") for item in outputs] != expected:
            return refuse(422, "fixture-output-correlation-refused")
        body = authored_stream(self.model, self.provider_requests)
        reason = ("authored-disabled-resource-call", "authored-clock-observation", "authored-final-text")[self.provider_requests]
        self.provider_requests += 1
        return 200, reason, body, "text/event-stream"


def analyze_request(event: dict[str, Any], prompt: str) -> dict[str, Any]:
    payload = json.loads(event["bodyRaw"])
    summary = transport.summarize_provider_request([event], prompt)
    assert summary is not None
    summary["responsesLiteHeader"] = event["headers"].get(LITE_HEADER)
    summary["topLevelToolsPresent"] = "tools" in payload
    summary["additionalTools"] = [item for item in payload["input"] if item.get("type") == "additional_tools"]
    summary["functionOutputs"] = [item for item in payload["input"] if item.get("type") == "function_call_output"]
    return summary


def run_case(helper: Path, model: str, catalog: bytes) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="nema-model-catalog-") as temporary:
        root = Path(temporary)
        boundary.prepare(root, helper)
        (root / "fixture/models.json").write_bytes(catalog)
        trace = TraceStore(root / "trace.db")
        store, work = transport.fixture_work(trace)
        context = work["contexts"][0]
        prompt = context["projectedPrompt"]
        config = fixture_config(model)
        (root / "packet/context.json").write_text(json.dumps(context))
        (root / "state/codex/config.toml").write_text(config)
        (root / "fixture/relay.py").write_text(transport.RELAY)
        (root / "fixture/launcher.py").write_text(transport.LAUNCHER)
        broker = CatalogFixtureBroker(prompt, model)

        class Handler(socketserver.BaseRequestHandler):
            def handle(self) -> None:
                try:
                    self.request.sendall(broker.exchange(self.request))
                except OSError:
                    pass

        replies, events = {}, []
        policy = failure = saved_artifact = None
        with socketserver.UnixStreamServer(str(root / "broker.sock"), Handler) as server:
            server.timeout = .05
            stop = threading.Event()
            def serve() -> None:
                while not stop.is_set() and broker.requests < transport.MAX_REQUESTS:
                    server.handle_request()
            service = threading.Thread(target=serve, daemon=True)
            service.start()
            command = boundary.namespace_command(root, Path("/usr/bin/bwrap"),
                      ["/usr/bin/python3", "/fixture/launcher.py"], broker=True)
            client = transport.SyntheticTurnClient(command, trace=trace, cwd=root, env={}, inherit_env=False,
                                                   source="synthetic-model-catalog/" + model)
            watchdog = threading.Timer(transport.CASE_SECONDS, client.close)
            watchdog.daemon = True
            watchdog.start()
            try:
                replies["initialize"] = client.initialize()
                replies["account/read"] = client.request("account/read", {"refreshToken": False})
                if replies["account/read"] != {"account": None, "requiresOpenaiAuth": False}:
                    raise RuntimeError("fixture has unexpected auth state")
                replies["config/read"] = client.request("config/read", {"includeLayers": False})
                effective = replies["config/read"]["config"]
                provider = effective["model_providers"][transport.PROVIDER]
                expected_url = "http://127.0.0.1:" + (root / "state/relay-port").read_text() + "/v1"
                if (effective["model_provider"] != transport.PROVIDER or provider["base_url"] != expected_url
                        or provider["requires_openai_auth"] is not False
                        or effective.get("model_catalog_json") != "/fixture/models.json"
                        or effective.get("model") != model):
                    raise RuntimeError("effective provider differs from fixture")
                policy = json.loads((root / "state/policy.json").read_text())
                if not policy["installedBeforeInitialExec"] or not policy["allListenerCopiesClosed"]:
                    raise RuntimeError("pre-exec process filter is absent")
                replies["thread/start"] = client.request("thread/start", {
                    "cwd": "/state/workspace", "approvalPolicy": "never", "sandbox": "read-only",
                    "environments": [], "ephemeral": True, "model": model,
                    "modelProvider": transport.PROVIDER,
                    "baseInstructions": "Synthetic fixture probe. Only authored disabled-resource and read-only clock observations are expected.",
                })
                thread_id = replies["thread/start"]["thread"]["id"]
                replies["mcpServerStatus/list"] = client.request("mcpServerStatus/list", {
                    "threadId": thread_id, "limit": 100, "detail": "full"})
                store.update_attempt(work["id"], source=client.source, threadId=thread_id, status="running")
                client.expected_turn = {"threadId": thread_id, "input": [{"type": "text", "text": prompt}]}
                broker.admit()
                replies["turn/start"] = client.request("turn/start", client.expected_turn)
                turn_id = replies["turn/start"]["turn"]["id"]
                store.update_attempt(work["id"], turnId=turn_id)
                deadline = time.monotonic() + 8
                while len(events) < 100 and time.monotonic() < deadline:
                    event = client.recv_event(timeout=max(.001, deadline - time.monotonic()))
                    events.append(event)
                    transport.inspect_event(event)
                    if event.get("method") == "turn/completed":
                        params = event.get("params", {})
                        if params.get("threadId") == thread_id and params.get("turn", {}).get("id") == turn_id:
                            if params["turn"].get("status") != "completed":
                                raise RuntimeError("synthetic native turn failed: " + json.dumps(params["turn"]))
                            break
                else:
                    raise RuntimeError("completion event deadline/count exceeded")
                attempt = store.get(work["id"])["attempt"]
                recovered = NativeInvestigationWorker(trace, command=["/never-start-native"]).recover(attempt, context)
                if recovered is None or recovered["text"] != transport.OUTPUT_TEXT:
                    raise RuntimeError("authored final output was not recovered")
                recovered["executionEvidence"] = "synthetic"
                saved_artifact = store.complete(work["id"], recovered)["artifact"]
            except Exception as exc:
                failure = {"type": type(exc).__name__, "message": str(exc)}
            finally:
                watchdog.cancel()
                client.close()
                stop.set()
                service.join(timeout=3)
                if service.is_alive():
                    raise RuntimeError("fixture service did not stop")
        records = [{"seq": r.seq, "source": r.source, "direction": r.direction, "rawText": r.raw_text}
                   for r in trace.records()]
        trace.close()
        accepted = [e for e in broker.events if e.get("target") == transport.RESPONSE_PATH and e["status"] == 200]
        report = {"model": model, "catalogSha256": hashlib.sha256(catalog).hexdigest(), "command": command, "requestedConfigToml": config,
                  "nativeReplies": replies, "nativeEvents": events, "nativeStderr": client.stderr_tail,
                  "nativeCapture": client.capture_status,
                  "policy": policy, "failure": failure, "selectedContext": context,
                  "nativeTurnRPCs": client.turn_count, "nativeMethodsObserved": client.methods,
                  "brokerEvents": broker.events, "httpRequests": broker.requests,
                  "providerRequests": sum(e.get("target") == transport.RESPONSE_PATH for e in broker.events),
                  "acceptedProviderRequests": broker.provider_requests, "fixtureResourceReads": broker.resource_reads,
                  "providerRequestAnalyses": [analyze_request(event, prompt) for event in accepted],
                  "savedArtifact": saved_artifact, "traceRecords": records,
                  "validProviderRequestImpersonationTested": False}
        return json.loads(json.dumps(report).replace(str(root), "<probe>"))


def run_probe(catalog_path: Path = CATALOG_PATH) -> dict[str, Any]:
    catalog, entries = checked_catalog(catalog_path)
    with tempfile.TemporaryDirectory(prefix="nema-catalog-helper-") as temporary:
        helper = boundary.compile_helper(Path(temporary))
        cases = {model: run_case(helper, model, catalog) for model in MODELS}
    user_agent = cases[MODELS[0]]["nativeReplies"].get("initialize", {}).get("userAgent", "")
    return {"schemaVersion": "nema-native-model-catalog/1", "implementationBase": "2c447e4",
            "classification": "NATIVE_TRANSPORT_SYNTHETIC_CATALOG_CHALLENGE", "cases": cases,
            "catalog": {"source": CATALOG_URL, "sha256": CATALOG_SHA256, "bytes": len(catalog),
                        "metadata": {model: {key: entry.get(key) for key in (
                            "slug", "tool_mode", "use_responses_lite", "experimental_supported_tools",
                            "shell_type")} for model, entry in entries.items()}},
            "nativeVersion": user_agent.split("/", 1)[1].split(" ", 1)[0] if "/" in user_agent else None,
            "nativeVersionSource": "contained initialize.userAgent", "nativeUserAgent": user_agent,
            "nativeTurnRPCs": sum(c["nativeTurnRPCs"] for c in cases.values()),
            "providerRequests": sum(c["providerRequests"] for c in cases.values()),
            "realModelCalls": 0, "realUpstreamRequests": 0, "existingCredentialsMounted": False,
            "subscriptionExecution": False, "callerAuthenticationEstablished": False, "liveAdmission": False,
            "binarySha256": hashlib.sha256(Path("/usr/bin/codex").read_bytes()).hexdigest(),
            "processFilterSourceSha256": hashlib.sha256(boundary.HELPER_C.encode()).hexdigest(),
            "kernel": platform.release(), "architecture": platform.machine(),
            "limits": {"requestsPerCase": transport.MAX_REQUESTS,
                       "acceptedProviderRequestsPerCase": MAX_PROVIDER_REQUESTS,
                       "headerBytes": transport.MAX_HEADER, "bodyBytes": transport.MAX_BODY,
                       "responseBytes": transport.MAX_RESPONSE, "requestSeconds": transport.REQUEST_SECONDS,
                       "nativeWatchdogSeconds": transport.CASE_SECONDS, "completionEventsConsumed": 100,
                       "traceDatabaseByteQuota": False, "aggregateResourceQuota": False}}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=CATALOG_PATH)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = json.dumps(run_probe(args.catalog), indent=2) + "\n"
    if args.output:
        args.output.write_text(report)
    else:
        print(report, end="")


if __name__ == "__main__":
    main()
