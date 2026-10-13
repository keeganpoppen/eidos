#!/usr/bin/env python3
"""Native turn RPCs against an authored local fixture, never a real model.

The only native launch is fresh disconnected bwrap plus the reviewed pre-exec
process filter. The Unix broker has no upstream implementation or credentials.
This is transport/recovery research, not subscription execution or admission.
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

from eidos.codex import AppServerClient
from eidos.investigation import InvestigationStore
from eidos.investigation_worker import NativeInvestigationWorker
from eidos.trace import TraceStore

_spec = importlib.util.spec_from_file_location(
    "synthetic_turn_boundary", Path(__file__).with_name("probe_native_process_boundary.py"))
assert _spec and _spec.loader
boundary = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(boundary)

MODEL = "nema-synthetic-provider-fixture"
PROVIDER = "nema_local_fixture"
RESPONSE_PATH = "/v1/responses"
OUTPUT_TEXT = "SYNTHETIC FIXTURE: both selected records survived [evidence:1] [evidence:2]."
ALLOWED_METHODS = frozenset({"initialize", "account/read", "config/read", "thread/start",
                             "mcpServerStatus/list", "turn/start"})
MAX_HEADER = 8192
MAX_BODY = 131072
MAX_RESPONSE = 16384
MAX_REQUESTS = 24
REQUEST_SECONDS = 2.0
CASE_SECONDS = 18.0  # Reviewed C supervisor also has its unchanged 20-second alarm.


class SyntheticTurnClient(AppServerClient):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.methods: list[str] = []
        self.expected_turn: dict[str, Any] | None = None
        self.turn_count = 0

    def request(self, method: str, params: Any = None, *, timeout: float = 6.0) -> dict[str, Any]:
        if method not in ALLOWED_METHODS:
            raise ValueError(f"synthetic-turn probe refuses {method}")
        if method == "account/read" and params != {"refreshToken": False}:
            raise ValueError("synthetic-turn probe refuses authentication refresh")
        if method == "turn/start":
            if self.expected_turn is None or params != self.expected_turn or self.turn_count:
                raise ValueError("synthetic-turn probe permits one exact prepared fixture input")
            self.turn_count += 1
        self.methods.append(method)
        return super().request(method, params, timeout=timeout)

    def notify(self, method: str, params: Any = None) -> None:
        if method != "initialized":
            raise ValueError("synthetic-turn probe refuses non-handshake notification")
        super().notify(method, params)

    def respond(self, request_id: Any, result: Any = None, *, error: Any = None) -> None:
        raise ValueError("synthetic-turn probe cannot approve or answer native requests")


def response_events() -> list[dict[str, Any]]:
    message = {"id": "msg_nema_fixture", "type": "message", "role": "assistant",
               "status": "completed", "phase": "final_answer",
               "content": [{"type": "output_text", "text": OUTPUT_TEXT, "annotations": []}]}
    response = {"id": "resp_nema_fixture", "object": "response", "created_at": 1,
                "status": "completed", "model": MODEL, "output": [message],
                "error": None, "incomplete_details": None,
                "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0,
                          "input_tokens_details": {"cached_tokens": 0},
                          "output_tokens_details": {"reasoning_tokens": 0}},
                "futureSyntheticField": {"authoredFixture": True}}
    events = [
        {"type": "response.created", "response": {**response, "status": "in_progress", "output": []}},
        {"type": "response.output_item.added", "output_index": 0,
         "item": {**message, "status": "in_progress", "content": []}},
        {"type": "response.content_part.added", "item_id": message["id"], "output_index": 0,
         "content_index": 0, "part": {"type": "output_text", "text": "", "annotations": []}},
        {"type": "response.output_text.delta", "item_id": message["id"], "output_index": 0,
         "content_index": 0, "delta": OUTPUT_TEXT},
        {"type": "response.output_text.done", "item_id": message["id"], "output_index": 0,
         "content_index": 0, "text": OUTPUT_TEXT},
        {"type": "response.content_part.done", "item_id": message["id"], "output_index": 0,
         "content_index": 0, "part": message["content"][0]},
        {"type": "response.output_item.done", "output_index": 0, "item": message},
        {"type": "response.completed", "response": response},
    ]
    return [{**event, "sequence_number": i} for i, event in enumerate(events)]


def response_stream() -> bytes:
    return "".join(f"event: {event['type']}\ndata: {json.dumps(event, separators=(',', ':'))}\n\n"
                   for event in response_events()).encode()


class FixtureHttpError(ValueError):
    def __init__(self, status: int, reason: str, record: dict[str, Any]) -> None:
        super().__init__(reason)
        self.status, self.reason, self.record = status, reason, record


def read_fixture_http_request(connection: socket.socket, deadline: float) -> dict[str, Any]:
    """Read one bounded message; shared by local-only fixture services."""
    record: dict[str, Any] = {}
    def receive(count: int) -> bytes:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError
        connection.settimeout(remaining)
        value = connection.recv(count)
        if not value:
            raise ValueError("truncated")
        return value

    try:
        data = bytearray()
        while b"\r\n\r\n" not in data:
            data.extend(receive(2048))
            split = data.find(b"\r\n\r\n")
            if split > MAX_HEADER or split == -1 and len(data) > MAX_HEADER:
                raise FixtureHttpError(413, "header-limit", record)
        head, body = bytes(data).split(b"\r\n\r\n", 1)
        lines = head.decode("ascii").split("\r\n")
        method, target, version = lines[0].split(" ")
        if version != "HTTP/1.1":
            raise ValueError("version")
        headers: dict[str, str] = {}
        for line in lines[1:]:
            name, value = line.split(":", 1)
            name = name.lower()
            if name in headers:
                raise ValueError("duplicate-header")
            headers[name] = value.strip()
        record.update(method=method, target=target, headers=headers)
        if any(name in headers for name in ("authorization", "transfer-encoding", "content-encoding")):
            raise FixtureHttpError(400, "unsupported-header", record)
        length = int(headers.get("content-length", "0"))
        if not 0 <= length <= MAX_BODY:
            raise FixtureHttpError(413, "body-limit", record)
        while len(body) < length:
            body += receive(length - len(body))
        if len(body) != length:
            raise ValueError("trailing-bytes")
        record.update(bodyRaw=body.decode("utf-8"), bodySha256=hashlib.sha256(body).hexdigest())
        return record
    except FixtureHttpError:
        raise
    except TimeoutError:
        raise FixtureHttpError(408, "deadline", record) from None
    except (ValueError, TypeError, UnicodeError):
        raise FixtureHttpError(400, "malformed", record) from None


class FixtureBroker:
    """Default-deny, single-use fake service. No outbound network client exists."""
    def __init__(self, prompt: str) -> None:
        self.prompt = prompt
        self.events: list[dict[str, Any]] = []
        self.requests = 0
        self.admitted = False
        self.consumed = False
        self.lock = threading.Lock()

    def admit(self) -> None:
        with self.lock:
            if self.admitted:
                raise ValueError("fixture admission cannot be renewed")
            self.admitted = True

    @staticmethod
    def _http(status: int, payload: bytes, content_type: str = "application/json") -> bytes:
        if len(payload) > MAX_RESPONSE:
            raise ValueError("fixture response exceeds bound")
        return (f"HTTP/1.1 {status} Fixture\r\nContent-Type: {content_type}\r\n"
                f"Content-Length: {len(payload)}\r\nConnection: close\r\n\r\n").encode() + payload

    def exchange(self, connection: socket.socket) -> bytes:
        deadline = time.monotonic() + REQUEST_SECONDS
        with self.lock:
            if self.requests >= MAX_REQUESTS:
                return self._http(429, b'{"synthetic":true,"reason":"request-limit"}')
            self.requests += 1
        record: dict[str, Any] = {}

        def finish(status: int, reason: str) -> bytes:
            self.events.append({**record, "status": status, "reason": reason})
            if status == 200:
                return self._http(status, response_stream(), "text/event-stream")
            return self._http(status, json.dumps({"synthetic": True, "reason": reason}).encode())

        try:
            record.update(read_fixture_http_request(connection, deadline))
            method, target, body = record["method"], record["target"], record["bodyRaw"]
            if method != "POST" or target != RESPONSE_PATH:
                return finish(403, "route-refused")
            payload = json.loads(body)
            if not isinstance(payload, dict):
                raise ValueError("body-object")
            # This is fixture dispatch, not a caller authenticator. In-process
            # MCP initialization is compared with the actual provider envelope.
            input_texts = [part.get("text") for item in payload.get("input", []) if isinstance(item, dict)
                           and item.get("role") == "user" for part in item.get("content", [])
                           if isinstance(part, dict) and part.get("type") == "input_text"]
            if (payload.get("model") != MODEL or payload.get("stream") is not True
                    or self.prompt not in input_texts or "jsonrpc" in payload):
                return finish(422, "fixture-provider-shape-refused")
            with self.lock:
                if not self.admitted:
                    return finish(403, "not-admitted")
                if self.consumed:
                    return finish(409, "already-consumed")
                self.consumed = True
                return finish(200, "authored-synthetic-response")
        except FixtureHttpError as exc:
            record.update(exc.record)
            return finish(exc.status, exc.reason)
        except (ValueError, TypeError, UnicodeError, RecursionError):
            return finish(400, "malformed")


RELAY = r'''
import pathlib, selectors, socket, socketserver, time
handled=0
class Relay(socketserver.BaseRequestHandler):
    def handle(self):
        global handled
        handled+=1
        deadline=time.monotonic()+4
        try:
            with socket.socket(socket.AF_UNIX) as upstream, selectors.DefaultSelector() as selector:
                upstream.settimeout(1); upstream.connect('/gateway/broker.sock')
                self.request.settimeout(1)
                selector.register(self.request, selectors.EVENT_READ, (upstream, 'request'))
                selector.register(upstream, selectors.EVENT_READ, (self.request, 'response'))
                totals={'request':0, 'response':0}
                while time.monotonic() < deadline:
                    for key, _ in selector.select(max(0, deadline-time.monotonic())):
                        destination, direction=key.data
                        data=key.fileobj.recv(2048)
                        if not data: return
                        totals[direction]+=len(data)
                        if totals[direction] > (140000 if direction == 'request' else 20000): return
                        destination.sendall(data)
        except OSError:
            return
with socketserver.TCPServer(('127.0.0.1',0),Relay) as server:
    server.timeout=.1
    pathlib.Path('/state/relay-port').write_text(str(server.server_address[1]))
    stop=time.monotonic()+18
    while handled < 24 and time.monotonic() < stop:
        server.handle_request()
'''

LAUNCHER = r'''
import os, pathlib, subprocess, sys, time
subprocess.Popen(['/usr/bin/python3','/fixture/relay.py'],stdin=subprocess.DEVNULL,
                 stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
port=pathlib.Path('/state/relay-port')
deadline=time.monotonic()+2
while not port.exists():
    if time.monotonic() >= deadline: raise RuntimeError('fixture relay failed')
    time.sleep(.01)
config=pathlib.Path('/state/codex/config.toml')
config.write_text(config.read_text().replace('FIXTURE_PORT',port.read_text()))
os.execv('/fixture/guard',['/fixture/guard','guard','/usr/bin/codex','app-server',
                         '--listen','stdio://','--strict-config'])
'''


def fixture_work(trace: TraceStore) -> tuple[InvestigationStore, dict[str, Any]]:
    selections = []
    for index, text in enumerate(("A write was prepared.", "Its acknowledgement is unknown."), 1):
        record = trace.append(source="synthetic-selected-packet", direction="internal", message={
            "method": "$history/item", "params": {"threadId": f"fixture-source-{index}",
            "item": {"id": f"fixture-item-{index}", "type": "agentMessage", "text": text,
                     "futureFixtureField": {"preserve": index}}}})
        selections.append({"threadId": record.thread_id, "startSeq": record.seq,
                           "endSeq": record.seq, "rationale": "Selected synthetic record"})
    store = InvestigationStore(trace)
    work = store.create({"requestId": "synthetic-provider-probe", "title": "Local fixture transport",
                         "question": "Preserve both selected records; the service returns authored fixture text.",
                         "selections": selections})
    return store, store.claim(work["id"], work["currentContextId"])[0]


def inspect_event(event: dict[str, Any]) -> None:
    if "method" in event and "id" in event:
        raise RuntimeError("native requested an unsupported tool, approval or interaction")
    if event.get("method") in {"item/started", "item/completed"}:
        item = event.get("params", {}).get("item", {})
        if item.get("type") not in {"userMessage", "agentMessage"}:
            raise RuntimeError("native emitted an unsupported action item: " + str(item.get("type")))


def summarize_provider_request(events: list[dict[str, Any]], prompt: str) -> dict[str, Any] | None:
    accepted = [event for event in events if event["status"] == 200]
    if not accepted:
        return None
    payload = json.loads(accepted[0]["bodyRaw"])
    fragments = [{"itemIndex": index, "partIndex": part_index, "role": item.get("role"),
                  "text": part.get("text"), "isExactSelectedPrompt": part.get("text") == prompt}
                 for index, item in enumerate(payload.get("input", [])) if isinstance(item, dict)
                 for part_index, part in enumerate(item.get("content", [])) if isinstance(part, dict)
                 and part.get("type") == "input_text"]
    tools = [{"type": tool.get("type"), "name": tool.get("name"),
              "nestedNames": [value.get("name") for value in tool.get("tools", [])]}
             for tool in payload.get("tools", [])]
    return {"requestBytes": len(accepted[0]["bodyRaw"].encode()),
            "instructions": payload.get("instructions"), "inputFragments": fragments,
            "exactSelectedPromptOccurrences": sum(part["isExactSelectedPrompt"] for part in fragments),
            "offeredToolSchemas": tools, "toolChoice": payload.get("tool_choice"),
            "callerAuthenticationEstablished": False}


def run_case(helper: Path, *, http_mcp: bool) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="nema-synthetic-turn-") as tmp:
        root = Path(tmp)
        boundary.prepare(root, helper)
        trace = TraceStore(root / "trace.db")
        store, work = fixture_work(trace)
        context = work["contexts"][0]
        prompt = context["projectedPrompt"]
        (root / "packet/context.json").write_text(json.dumps(context, ensure_ascii=False))
        (root / "fixture/relay.py").write_text(RELAY)
        (root / "fixture/launcher.py").write_text(LAUNCHER)
        (root / "fixture/unexpected.py").write_text("from pathlib import Path\nPath('/state/unexpected-executable-ran').write_text('ran')\n")
        config = [f'model_provider="{PROVIDER}"', f'model="{MODEL}"',
                  'approval_policy="never"', 'sandbox_mode="read-only"', 'web_search="disabled"',
                  '[features]', 'plugins=false', 'apps=false', 'hooks=false', 'shell_tool=false',
                  'shell_snapshot=false', 'code_mode=false', 'skip_host_skill_discovery=true',
                  'multi_agent=false', 'memories=false', 'image_generation=false',
                  f'[model_providers.{PROVIDER}]', 'name="Authored local fixture"',
                  'base_url="http://127.0.0.1:FIXTURE_PORT/v1"', 'requires_openai_auth=false',
                  'wire_api="responses"', 'supports_websockets=false',
                  'request_max_retries=0', 'stream_max_retries=0', 'stream_idle_timeout_ms=3000',
                  '[mcp_servers.unexpected]', 'command="/usr/bin/python3"',
                  'args=["/fixture/unexpected.py"]', 'startup_timeout_sec=2']
        if http_mcp:
            config += ['[mcp_servers.http_inprocess]',
                       'url="http://127.0.0.1:FIXTURE_PORT/v1/responses"', 'startup_timeout_sec=2']
        (root / "state/codex/config.toml").write_text("\n".join(config))
        broker = FixtureBroker(prompt)

        class Handler(socketserver.BaseRequestHandler):
            def handle(self) -> None:
                try:
                    self.request.sendall(broker.exchange(self.request))
                except OSError:
                    pass

        replies: dict[str, Any] = {}
        events: list[dict[str, Any]] = []
        failure = None
        recovered = None
        final_work = None
        policy = None
        with socketserver.UnixStreamServer(str(root / "broker.sock"), Handler) as server:
            server.timeout = .05
            stop = threading.Event()
            def serve() -> None:
                while not stop.is_set() and broker.requests < MAX_REQUESTS:
                    server.handle_request()
            service = threading.Thread(target=serve, daemon=True)
            service.start()
            command = boundary.namespace_command(root, Path("/usr/bin/bwrap"),
                        ["/usr/bin/python3", "/fixture/launcher.py"], broker=True)
            client = SyntheticTurnClient(command, trace=trace, cwd=root, env={}, inherit_env=False,
                                         source="synthetic-provider-native-transport")
            watchdog = threading.Timer(CASE_SECONDS, client.close)
            watchdog.daemon = True
            watchdog.start()
            try:
                replies["initialize"] = client.initialize()
                replies["account/read"] = client.request("account/read", {"refreshToken": False})
                if replies["account/read"] != {"account": None, "requiresOpenaiAuth": False}:
                    raise RuntimeError("fixture launch did not have empty no-auth state")
                replies["config/read"] = client.request("config/read", {"includeLayers": False})
                effective = replies["config/read"]["config"]
                provider = effective["model_providers"][PROVIDER]
                expected_url = "http://127.0.0.1:" + (root / "state/relay-port").read_text() + "/v1"
                if effective["model_provider"] != PROVIDER or provider["base_url"] != expected_url or provider["requires_openai_auth"] is not False:
                    raise RuntimeError("effective provider differs from local fixture")
                policy = json.loads((root / "state/policy.json").read_text())
                if not policy["installedBeforeInitialExec"] or not policy["allListenerCopiesClosed"]:
                    raise RuntimeError("reviewed pre-exec policy is absent")
                replies["thread/start"] = client.request("thread/start", {
                    "cwd": "/state/workspace", "approvalPolicy": "never", "sandbox": "read-only",
                    "environments": [], "ephemeral": True, "model": MODEL, "modelProvider": PROVIDER,
                    "baseInstructions": "Local fixture transport probe. Do not request tools or actions.",
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
                    event = client.recv_event(timeout=max(.001, deadline-time.monotonic()))
                    events.append(event)
                    inspect_event(event)
                    if event.get("method") == "turn/completed":
                        params = event.get("params", {})
                        if params.get("threadId") == thread_id and params.get("turn", {}).get("id") == turn_id:
                            if params["turn"].get("status") != "completed":
                                raise RuntimeError("synthetic native turn failed: " + json.dumps(params["turn"]))
                            break
                else:
                    raise RuntimeError("native event count/deadline exceeded")
                work = store.get(work["id"])
                recovered = NativeInvestigationWorker(trace, command=["/never-start-native"]).recover(work["attempt"], context)
                if recovered is None or recovered["text"] != OUTPUT_TEXT:
                    raise RuntimeError("native recovery did not reproduce the authored output")
                # Native transport observation is not evidence of a real model.
                recovered["executionEvidence"] = "synthetic"
                final_work = store.complete(work["id"], recovered)
            except Exception as exc:
                failure = {"type": type(exc).__name__, "message": str(exc)}
            finally:
                watchdog.cancel()
                client.close()
                stop.set()
                service.join(timeout=3)
                if service.is_alive():
                    raise RuntimeError("fixture service failed to stop")
        records = [{"seq": record.seq, "source": record.source, "direction": record.direction,
                    "rawText": record.raw_text} for record in trace.records()]
        trace.close()
        reopened = TraceStore(root / "trace.db")
        replay_failure = None
        durable = False
        try:
            saved = InvestigationStore(reopened).get(work["id"])
            replay = NativeInvestigationWorker(reopened, command=["/never-start-native"]).recover(saved["attempt"], context)
            if replay:
                replay["executionEvidence"] = "synthetic"
            durable = final_work is not None and saved == final_work and replay == recovered
        except Exception as exc:
            replay_failure = {"type": type(exc).__name__, "message": str(exc)}
        finally:
            reopened.close()
        report = {
            "httpMcpEnabled": http_mcp, "command": command, "failure": failure,
            "policy": policy,
            "nativeReplies": replies, "nativeEvents": events, "nativeStderr": client.stderr_tail,
            "nativeMethodsObserved": client.methods, "nativeTurnRPCs": client.turn_count,
            "selectedContext": context, "promptSha256": hashlib.sha256(prompt.encode()).hexdigest(),
            "brokerEvents": broker.events, "brokerRequests": broker.requests,
            "providerRequestAnalysis": summarize_provider_request(broker.events, prompt),
            "fixturePermitConsumed": broker.consumed, "responseEvents": response_events(),
            "responseSse": response_stream().decode(), "recoveredArtifact": recovered,
            "savedArtifact": final_work["artifact"] if final_work else None,
            "savedAttempt": final_work["attempt"] if final_work else None,
            "durableReopenMatches": durable, "durableReopenFailure": replay_failure, "traceRecords": records,
            "unexpectedExecutableRan": (root / "state/unexpected-executable-ran").exists(),
            "validProviderRequestImpersonationTested": False,
        }
        return json.loads(json.dumps(report).replace(str(root), "<probe>"))


def run_probe() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="nema-turn-helper-") as tmp:
        helper = boundary.compile_helper(Path(tmp))
        cases = {name: run_case(helper, http_mcp=enabled)
                 for name, enabled in (("providerOnly", False), ("withHttpMcp", True))}
    user_agent = cases["providerOnly"]["nativeReplies"].get("initialize", {}).get("userAgent", "")
    native_version = user_agent.split("/", 1)[1].split(" ", 1)[0] if "/" in user_agent else None
    return {
        "schemaVersion": "nema-native-synthetic-turn-probe/1", "classification": "NATIVE_TRANSPORT_SYNTHETIC_PROVIDER",
        "implementationBase": "348f736", "nativeVersion": native_version,
        "nativeVersionSource": "contained initialize.userAgent", "nativeUserAgent": user_agent,
        "binarySha256": hashlib.sha256(Path("/usr/bin/codex").read_bytes()).hexdigest(),
        "processFilterSourceSha256": hashlib.sha256(boundary.HELPER_C.encode()).hexdigest(),
        "kernel": platform.release(), "architecture": platform.machine(),
        "cases": cases, "nativeTurnRPCs": sum(case["nativeTurnRPCs"] for case in cases.values()),
        "realModelCalls": 0, "realUpstreamRequests": 0, "existingCredentialsMounted": False,
        "subscriptionExecution": False, "callerAuthenticationEstablished": False, "liveAdmission": False,
        "limits": {"headerBytes": MAX_HEADER, "bodyBytes": MAX_BODY, "responseBytes": MAX_RESPONSE,
                   "requestsPerCase": MAX_REQUESTS, "requestSeconds": REQUEST_SECONDS,
                   "caseSeconds": CASE_SECONDS, "nativeEventsPerCase": 100, "aggregateResourceQuota": False},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    text = json.dumps(run_probe(), indent=2) + "\n"
    if args.output:
        args.output.write_text(text)
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
