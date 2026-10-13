#!/usr/bin/env python3
"""Challenge pre-turn tool controls with a local authored tool-call response.

Every native launch uses the reviewed disconnected namespace and pre-exec filter.
No credentials, owner state, upstream implementation or actual model is involved.
The only authored call reads this experiment's synthetic MCP resource.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import platform
import socket
import socketserver
import tempfile
import threading
import time
from typing import Any

from eidos.investigation_worker import NativeInvestigationWorker
from eidos.trace import TraceStore

_spec = importlib.util.spec_from_file_location(
    "tool_probe_transport", Path(__file__).with_name("probe_native_synthetic_turn.py"))
assert _spec and _spec.loader
transport = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(transport)
boundary = transport.boundary

URI = "fixture://isolated/observation"
RESOURCE_TEXT = "AUTHORED_MCP_RESOURCE_READ: disposable fixture only."
CALL_ID = "call_nema_fixture_resource"
TOOL = "read_mcp_resource"
ARGUMENTS = {"server": "fixture", "uri": URI}
CASES = ("baseline", "builtinsDisabled", "allMcpDisabled")
MAX_PROVIDER_REQUESTS = 2


def tool_response_events() -> list[dict[str, Any]]:
    arguments = json.dumps(ARGUMENTS, separators=(",", ":"))
    item = {"id": "fc_nema_fixture", "type": "function_call", "status": "completed",
            "call_id": CALL_ID, "name": TOOL, "arguments": arguments}
    response = {**transport.response_events()[-1]["response"],
                "id": "resp_nema_fixture_tool", "output": [item]}
    events = [
        {"type": "response.created", "response": {**response, "status": "in_progress", "output": []}},
        {"type": "response.output_item.added", "output_index": 0,
         "item": {**item, "status": "in_progress", "arguments": ""}},
        {"type": "response.function_call_arguments.delta", "item_id": item["id"],
         "output_index": 0, "delta": arguments},
        {"type": "response.function_call_arguments.done", "item_id": item["id"],
         "output_index": 0, "arguments": arguments},
        {"type": "response.output_item.done", "output_index": 0, "item": item},
        {"type": "response.completed", "response": response},
    ]
    return [{**event, "sequence_number": index} for index, event in enumerate(events)]


def tool_response_stream() -> bytes:
    return "".join(f"event: {e['type']}\ndata: {json.dumps(e, separators=(',', ':'))}\n\n"
                   for e in tool_response_events()).encode()


class ToolFixtureBroker:
    """Two fixed local protocols, no generic forwarding or caller authentication."""
    def __init__(self, prompt: str) -> None:
        self.prompt = prompt
        self.events: list[dict[str, Any]] = []
        self.requests = 0
        self.provider_requests = 0
        self.resource_reads = 0
        self.admitted = False
        self.lock = threading.Lock()

    def admit(self) -> None:
        with self.lock:
            if self.admitted:
                raise ValueError("fixture admission cannot be renewed")
            self.admitted = True

    def exchange(self, connection: socket.socket) -> bytes:
        with self.lock:
            if self.requests >= transport.MAX_REQUESTS:
                return transport.FixtureBroker._http(429, b'{"synthetic":true}')
            self.requests += 1
        record: dict[str, Any] = {}
        try:
            record = transport.read_fixture_http_request(connection, time.monotonic() + transport.REQUEST_SECONDS)
            with self.lock:
                status, reason, payload, content_type = self.dispatch(record)
        except transport.FixtureHttpError as exc:
            record, status, reason = exc.record, exc.status, exc.reason
            payload, content_type = b'{"synthetic":true}', "application/json"
        except (ValueError, TypeError, UnicodeError, RecursionError):
            status, reason, payload, content_type = 400, "malformed", b'{"synthetic":true}', "application/json"
        self.events.append({**record, "status": status, "reason": reason,
                            "responseRaw": payload.decode(), "responseContentType": content_type})
        return transport.FixtureBroker._http(status, payload, content_type)

    def dispatch(self, record: dict[str, Any]) -> tuple[int, str, bytes, str]:
        def reply(status: int, reason: str, result: Any = None) -> tuple[int, str, bytes, str]:
            return status, reason, json.dumps(result if result is not None else {
                "synthetic": True, "reason": reason}, separators=(",", ":")).encode(), "application/json"

        if record["method"] != "POST" or record["target"] not in {"/mcp", transport.RESPONSE_PATH}:
            return reply(403, "route-refused")
        payload = json.loads(record["bodyRaw"])
        if not isinstance(payload, dict):
            raise ValueError("object required")
        if record["target"] == transport.RESPONSE_PATH:
            texts = [p.get("text") for item in payload.get("input", []) if isinstance(item, dict)
                     and item.get("role") == "user" for p in item.get("content", []) if isinstance(p, dict)]
            if (payload.get("model") != transport.MODEL or payload.get("stream") is not True
                    or self.prompt not in texts or "jsonrpc" in payload):
                return reply(422, "fixture-provider-shape-refused")
            if not self.admitted:
                return reply(403, "not-admitted")
            if self.provider_requests >= MAX_PROVIDER_REQUESTS:
                return reply(409, "provider-request-limit")
            outputs = [i for i in payload.get("input", []) if isinstance(i, dict) and i.get("type") == "function_call_output"]
            if (self.provider_requests == 0 and outputs) or (self.provider_requests == 1 and
                    (len(outputs) != 1 or outputs[0].get("call_id") != CALL_ID)):
                return reply(422, "fixture-output-correlation-refused")
            self.provider_requests += 1
            body = tool_response_stream() if self.provider_requests == 1 else transport.response_stream()
            return 200, "authored-tool-call" if self.provider_requests == 1 else "authored-final-text", body, "text/event-stream"

        if payload.get("jsonrpc") != "2.0":
            return reply(422, "fixture-mcp-shape-refused")
        method = payload.get("method")
        identifier = payload.get("id")
        if method == "notifications/initialized" and "id" not in payload:
            return 202, "fixture-mcp-initialized", b"", "application/json"
        if type(identifier) is not int:
            return reply(422, "fixture-mcp-id-refused")
        if method == "initialize":
            result = {"protocolVersion": "2025-06-18", "capabilities": {"resources": {}, "tools": {}},
                      "serverInfo": {"name": "nema-authored-fixture", "version": "1"}}
        elif method == "tools/list":
            result = {"tools": [{"name": "fixture_echo", "description": "Authored unused fixture tool",
                                "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}}]}
        elif method == "resources/list":
            result = {"resources": [{"uri": URI, "name": "Disposable observation", "mimeType": "text/plain"}]}
        elif method == "resources/templates/list":
            result = {"resourceTemplates": []}
        elif (method == "resources/read" and isinstance(payload.get("params"), dict)
              and payload["params"].get("uri") == URI
              and set(payload["params"]) <= {"uri", "_meta"}):
            self.resource_reads += 1
            result = {"contents": [{"uri": URI, "mimeType": "text/plain", "text": RESOURCE_TEXT}]}
        else:
            return reply(403, "fixture-mcp-method-refused")
        return reply(200, "fixture-mcp-" + method, {"jsonrpc": "2.0", "id": identifier, "result": result})


def fixture_config(case: str) -> str:
    if case not in CASES:
        raise ValueError("unknown fixture case")
    lines = [f'model_provider="{transport.PROVIDER}"', f'model="{transport.MODEL}"',
             'approval_policy="never"', 'sandbox_mode="read-only"', 'web_search="disabled"',
             '[features]', 'plugins=false', 'apps=false', 'hooks=false', 'shell_tool=false',
             'shell_snapshot=false', 'code_mode=false', 'skip_host_skill_discovery=true',
             'multi_agent=false', 'memories=false', 'image_generation=false']
    if case != "baseline":
        lines += ['[tools.experimental_request_user_input]', 'enabled=false',
                  '[orchestrator.skills]', 'enabled=false', '[orchestrator.mcp]', 'enabled=false',
                  '[skills]', 'include_instructions=false', '[skills.bundled]', 'enabled=false']
    lines += [f'[model_providers.{transport.PROVIDER}]', 'name="Authored local fixture"',
              'base_url="http://127.0.0.1:FIXTURE_PORT/v1"', 'requires_openai_auth=false',
              'wire_api="responses"', 'supports_websockets=false', 'request_max_retries=0',
              'stream_max_retries=0', 'stream_idle_timeout_ms=3000',
              '[mcp_servers.fixture]', 'url="http://127.0.0.1:FIXTURE_PORT/mcp"',
              'enabled_tools=[]', 'startup_timeout_sec=2', 'tool_timeout_sec=2',
              'enabled=' + ('false' if case == "allMcpDisabled" else 'true')]
    return "\n".join(lines)


def inspect_event(event: dict[str, Any]) -> None:
    if "method" in event and "id" in event:
        raise RuntimeError("fixture refuses native approval or interaction requests")
    if event.get("method") in {"item/started", "item/completed"}:
        item = event.get("params", {}).get("item", {})
        if item.get("type") in {"userMessage", "agentMessage"}:
            return
        if (item.get("type") == "mcpToolCall" and item.get("server") == "fixture"
                and item.get("tool") == TOOL and item.get("arguments") == ARGUMENTS):
            return
        raise RuntimeError("fixture observed an unexpected action item: " + json.dumps(item))


def run_case(helper: Path, case: str) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="nema-tool-boundary-") as temporary:
        root = Path(temporary)
        boundary.prepare(root, helper)
        trace = TraceStore(root / "trace.db")
        store, work = transport.fixture_work(trace)
        context = work["contexts"][0]
        prompt = context["projectedPrompt"]
        config = fixture_config(case)
        (root / "packet/context.json").write_text(json.dumps(context))
        (root / "state/codex/config.toml").write_text(config)
        (root / "fixture/relay.py").write_text(transport.RELAY)
        (root / "fixture/launcher.py").write_text(transport.LAUNCHER)
        broker = ToolFixtureBroker(prompt)

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
                                                   source="synthetic-tool-boundary/" + case)
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
                        or provider["requires_openai_auth"] is not False):
                    raise RuntimeError("effective provider differs from fixture")
                policy = json.loads((root / "state/policy.json").read_text())
                if not policy["installedBeforeInitialExec"] or not policy["allListenerCopiesClosed"]:
                    raise RuntimeError("pre-exec process filter is absent")
                replies["thread/start"] = client.request("thread/start", {
                    "cwd": "/state/workspace", "approvalPolicy": "never", "sandbox": "read-only",
                    "environments": [], "ephemeral": True, "model": transport.MODEL,
                    "modelProvider": transport.PROVIDER,
                    "baseInstructions": "Synthetic fixture probe. The authored service may request its isolated fixture resource.",
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
                    inspect_event(event)
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
        report = {"case": case, "command": command, "requestedConfigToml": config,
                  "nativeReplies": replies, "nativeEvents": events, "nativeStderr": client.stderr_tail,
                  "nativeCapture": client.capture_status,
                  "policy": policy, "failure": failure, "selectedContext": context,
                  "nativeTurnRPCs": client.turn_count, "nativeMethodsObserved": client.methods,
                  "brokerEvents": broker.events, "httpRequests": broker.requests,
                  "providerRequests": sum(e.get("target") == transport.RESPONSE_PATH for e in broker.events),
                  "acceptedProviderRequests": broker.provider_requests, "fixtureResourceReads": broker.resource_reads,
                  "providerRequestAnalysis": transport.summarize_provider_request(accepted, prompt),
                  "savedArtifact": saved_artifact, "traceRecords": records,
                  "validProviderRequestImpersonationTested": False}
        return json.loads(json.dumps(report).replace(str(root), "<probe>"))


def run_probe() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="nema-tool-helper-") as temporary:
        helper = boundary.compile_helper(Path(temporary))
        cases = {case: run_case(helper, case) for case in CASES}
    user_agent = cases["baseline"]["nativeReplies"].get("initialize", {}).get("userAgent", "")
    return {"schemaVersion": "nema-native-tool-boundary/1", "implementationBase": "b1896ae",
            "classification": "NATIVE_TRANSPORT_SYNTHETIC_TOOL_CHALLENGE", "cases": cases,
            "nativeVersion": user_agent.split("/", 1)[1].split(" ", 1)[0] if "/" in user_agent else None,
            "nativeVersionSource": "contained initialize.userAgent", "nativeUserAgent": user_agent,
            "nativeTurnRPCs": sum(c["nativeTurnRPCs"] for c in cases.values()),
            "providerRequests": sum(c["providerRequests"] for c in cases.values()),
            "realModelCalls": 0, "realUpstreamRequests": 0, "existingCredentialsMounted": False,
            "subscriptionExecution": False, "callerAuthenticationEstablished": False, "liveAdmission": False,
            "binarySha256": hashlib.sha256(Path("/usr/bin/codex").read_bytes()).hexdigest(),
            "processFilterSourceSha256": hashlib.sha256(boundary.HELPER_C.encode()).hexdigest(),
            "kernel": platform.release(), "architecture": platform.machine(),
            "limits": {"requestsPerCase": transport.MAX_REQUESTS, "acceptedProviderRequestsPerCase": MAX_PROVIDER_REQUESTS,
                       "headerBytes": transport.MAX_HEADER, "bodyBytes": transport.MAX_BODY,
                       "responseBytes": transport.MAX_RESPONSE, "requestSeconds": transport.REQUEST_SECONDS,
                       "nativeWatchdogSeconds": transport.CASE_SECONDS, "completionEventsConsumed": 100,
                       "traceDatabaseByteQuota": False, "aggregateResourceQuota": False}}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = json.dumps(run_probe(), indent=2) + "\n"
    if args.output:
        args.output.write_text(report)
    else:
        print(report, end="")


if __name__ == "__main__":
    main()
