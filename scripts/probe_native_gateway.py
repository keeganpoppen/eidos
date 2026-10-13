#!/usr/bin/env python3
"""Test a disconnected native namespace and a synthetic, one-use HTTP broker.

There is no upstream forwarding implementation, credential loading or model RPC.
Both HTTP callers are fixture processes. The sibling-first case is expected to
falsify caller authentication based on exact content or the shared relay's peer.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import platform
import shutil
import socket
import socketserver
import struct
import subprocess
import tempfile
import threading
import time
from typing import Any

from eidos.codex import AppServerClient

_spec = importlib.util.spec_from_file_location(
    "native_outer_fixture", Path(__file__).with_name("probe_native_outer_boundary.py"))
assert _spec and _spec.loader
outer = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(outer)

ALLOWED_METHODS = frozenset({"initialize", "account/read", "config/read", "thread/start", "mcpServerStatus/list"})
MODELS_PATH = "/backend-api/codex/models"
RESPONSES_PATH = "/backend-api/codex/responses"
EXPECTED_BODY = b'{"model":"synthetic-no-model","input":"Inspect selected synthetic packet."}'
MAX_HEADER_BYTES = 8192
MAX_BODY_BYTES = 4096
MAX_RESPONSE_BYTES = 4096
MAX_REQUESTS = 24
REQUEST_SECONDS = 2.0
CASE_SECONDS = 20.0


class NoModelClient(outer.NoModelClient):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.methods: list[str] = []

    def request(self, method: str, params: Any = None, *, timeout: float = 8.0) -> dict[str, Any]:
        if method not in ALLOWED_METHODS:
            raise ValueError(f"gateway probe refuses {method}")
        self.methods.append(method)
        return AppServerClient.request(self, method, params, timeout=timeout)


class SyntheticBroker:
    """An intentionally insufficient exact-content gate, with no network client."""

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []
        self.peers: list[tuple[int, int, int]] = []
        self.admitted = False
        self.consumed = False
        self.redirect_once = True
        self.requests = 0
        self.lock = threading.Lock()

    def admit(self) -> None:
        with self.lock:
            if self.admitted:
                raise ValueError("synthetic admission cannot be renewed")
            self.admitted = True

    def exchange(self, connection: socket.socket) -> bytes:
        """Bound one HTTP/1.1 message; close afterwards, never follow a redirect."""
        deadline = time.monotonic() + REQUEST_SECONDS
        with self.lock:
            if self.requests >= MAX_REQUESTS:
                return self._response(429, "request-limit")
            self.requests += 1
        peer = struct.unpack("3i", connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
        data = bytearray()
        try:
            while b"\r\n\r\n" not in data:
                connection.settimeout(max(0.001, deadline - time.monotonic()))
                if time.monotonic() >= deadline:
                    raise TimeoutError
                chunk = connection.recv(2048)
                if not chunk:
                    raise ValueError("truncated")
                data.extend(chunk)
                delimiter = data.find(b"\r\n\r\n")
                if (delimiter == -1 and len(data) > MAX_HEADER_BYTES) or delimiter > MAX_HEADER_BYTES:
                    return self._record(413, "header-limit", peer)
            head, body = bytes(data).split(b"\r\n\r\n", 1)
            lines = head.decode("ascii").split("\r\n")
            method, target, version = lines[0].split(" ")
            if version != "HTTP/1.1":
                raise ValueError("version")
            headers: dict[str, str] = {}
            for line in lines[1:]:
                key, value = line.split(":", 1)
                key = key.lower()
                if key in headers:
                    raise ValueError("duplicate-header")
                headers[key] = value.strip()
            if "transfer-encoding" in headers or "authorization" in headers:
                return self._record(400, "unsupported-header", peer)
            length = int(headers.get("content-length", "0"))
            if length < 0 or length > MAX_BODY_BYTES:
                return self._record(413, "body-limit", peer)
            while len(body) < length:
                connection.settimeout(max(0.001, deadline - time.monotonic()))
                if time.monotonic() >= deadline:
                    raise TimeoutError
                chunk = connection.recv(length - len(body))
                if not chunk:
                    raise ValueError("truncated")
                body += chunk
            if len(body) != length:
                raise ValueError("trailing-bytes")
        except TimeoutError:
            return self._record(408, "deadline", peer)
        except (ValueError, UnicodeError):
            return self._record(400, "malformed", peer)
        with self.lock:
            if method == "GET" and target == MODELS_PATH and not body:
                # There is no network upstream. Exercise the policy with an
                # explicit fake service response carrying a redirect Location.
                if self.redirect_once:
                    self.redirect_once = False
                    upstream = (307, {"Location": "https://unapproved.invalid/redirect"}, b"")
                else:
                    upstream = (200, {}, b'{"models":[]}')
                if 300 <= upstream[0] < 400:
                    return self._record(502, "synthetic-upstream-redirect-refused", peer,
                                        target=target, syntheticUpstreamStatus=upstream[0])
                return self._record(200, "synthetic-models", peer, target=target)
            if method != "POST" or target != RESPONSES_PATH:
                return self._record(403, "route-refused", peer, target=target)
            if body != EXPECTED_BODY:
                return self._record(422, "content-refused", peer, target=target)
            if not self.admitted:
                return self._record(403, "not-admitted", peer, target=target)
            if self.consumed:
                return self._record(409, "already-consumed", peer, target=target)
            self.consumed = True
            return self._record(200, "synthetic-response", peer, target=target,
                                digest=hashlib.sha256(body).hexdigest(),
                                claimedCaller=headers.get("x-nema-caller"))

    def _record(self, status: int, reason: str, peer: tuple[int, int, int], **fields: Any) -> bytes:
        self.peers.append(peer)
        label = f"peer-{list(dict.fromkeys(self.peers)).index(peer) + 1}"
        self.events.append({"status": status, "reason": reason, "brokerPeer": label, **fields})
        return self._response(status, reason, label)

    @staticmethod
    def _response(status: int, reason: str, peer: str | None = None) -> bytes:
        payload = json.dumps({"synthetic": True, "reason": reason, "brokerPeer": peer}).encode()
        assert len(payload) <= MAX_RESPONSE_BYTES
        return (f"HTTP/1.1 {status} Synthetic\r\nContent-Type: application/json\r\n"
                f"Content-Length: {len(payload)}\r\nConnection: close\r\n\r\n").encode() + payload


RELAY = r'''
import pathlib, selectors, socket, socketserver, time
class Relay(socketserver.BaseRequestHandler):
    def handle(self):
        deadline = time.monotonic() + 3
        with socket.socket(socket.AF_UNIX) as upstream, selectors.DefaultSelector() as selector:
            upstream.settimeout(1)
            upstream.connect('/gateway/broker.sock')
            self.request.settimeout(1)
            selector.register(self.request, selectors.EVENT_READ, (upstream, 'request'))
            selector.register(upstream, selectors.EVENT_READ, (self.request, 'response'))
            totals = {'request': 0, 'response': 0}
            while time.monotonic() < deadline:
                for key, _ in selector.select(max(0, deadline-time.monotonic())):
                    destination, direction = key.data
                    payload = key.fileobj.recv(2048)
                    if not payload:
                        return
                    totals[direction] += len(payload)
                    if totals[direction] > (16384 if direction == 'request' else 8192):
                        return
                    destination.sendall(payload)
with socketserver.TCPServer(('127.0.0.1', 0), Relay) as server:
    pathlib.Path('/state/relay-port').write_text(str(server.server_address[1]))
    for _ in range(24):
        server.handle_request()
'''

ACTOR = r'''
import http.client, json, pathlib, socket, sys, time
role = sys.argv[1]
port = int(pathlib.Path('/state/relay-port').read_text())
body = pathlib.Path('/packet/request.json').read_bytes()
def call(method, target, payload=b''):
    connection = http.client.HTTPConnection('127.0.0.1', port, timeout=4)
    try:
        connection.request(method, target, payload, {'X-Nema-Caller': 'owned-native-attempt'})
        response = connection.getresponse()
        data = response.read(4096)
        return {'status': response.status, 'body': json.loads(data), 'location': response.getheader('Location')}
    finally:
        connection.close()
results = {}
if role == 'rival':
    results['unapprovedUrl'] = call('POST', 'https://unapproved.invalid/action', body)
    results['redirect'] = call('GET', '/backend-api/codex/models')
    results['models'] = call('GET', '/backend-api/codex/models')
    results['early'] = call('POST', '/backend-api/codex/responses', body)
    results['wrongContent'] = call('POST', '/backend-api/codex/responses', b'changed')
    results['oversizedBody'] = call('POST', '/backend-api/codex/responses', b'x' * 4097)
    # A read-only socket mount still permits connecting directly to the broker.
    with socket.socket(socket.AF_UNIX) as direct:
        direct.settimeout(3)
        direct.connect('/gateway/broker.sock')
        direct.sendall(b'POST /backend-api/codex/responses HTTP/1.1\r\nHost: synthetic\r\nContent-Length: ' + str(len(body)).encode() + b'\r\n\r\n' + body)
        response = http.client.HTTPResponse(direct)
        response.begin()
        results['directUnixEarly'] = {'status': response.status, 'body': json.loads(response.read(4096))}
    pathlib.Path('/state/rival-ready').write_text(json.dumps(results))
release = pathlib.Path('/state/release-' + role)
deadline = time.monotonic() + 15
while not release.exists():
    if time.monotonic() >= deadline:
        raise TimeoutError('synthetic actor was not released')
    time.sleep(0.01)
results['attempt'] = call('POST', '/backend-api/codex/responses', body)
results['duplicate'] = call('POST', '/backend-api/codex/responses', body)
pathlib.Path('/state/' + role + '-result').write_text(json.dumps(results))
'''

MCP = r'''
import os, subprocess, sys
subprocess.Popen(['/usr/bin/python3', '/fixture/actor.py', 'rival'], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
os.execv('/usr/bin/python3', ['python3', '/fixture/outer_mcp.py', *sys.argv[1:]])
'''

LAUNCHER = r'''
import pathlib, subprocess, sys, time
subprocess.Popen(['/usr/bin/python3', '/fixture/relay.py'], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
deadline = time.monotonic() + 3
port_file = pathlib.Path('/state/relay-port')
while not port_file.exists():
    if time.monotonic() >= deadline:
        raise TimeoutError('relay failed to bind')
    time.sleep(0.01)
port = port_file.read_text()
config = pathlib.Path('/fixture/config.toml').read_text().replace('RELAY_PORT', port)
pathlib.Path('/state/codex/config.toml').write_text(config)
subprocess.Popen(['/usr/bin/python3', '/fixture/actor.py', 'intended'], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
import os
os.execv(sys.argv[1], [sys.argv[1], 'app-server', '--listen', 'stdio://', '--strict-config'])
'''


def _wait_json(path: Path, deadline: float) -> Any:
    while time.monotonic() < deadline:
        if path.exists():
            try:
                return json.loads(path.read_text())
            except json.JSONDecodeError:
                pass  # Fixture writes are small; do not read a partial write as evidence.
        time.sleep(0.01)
    raise TimeoutError(f"fixture observation not produced: {path.name}")


def run_case(binary: Path, bwrap: Path, first_actor: str) -> dict[str, Any]:
    broker = SyntheticBroker()
    with tempfile.TemporaryDirectory(prefix="nema-gateway-") as tmp, socket.socket() as listener:
        root = Path(tmp)
        for name in ("state/home", "state/codex", "state/workspace", "fixture", "packet", "outside"):
            (root / name).mkdir(parents=True, exist_ok=True)
        canary = root / "outside/canary"
        canary.write_text("synthetic undisclosed canary")
        packet = root / "packet/evidence.txt"
        packet.write_text("synthetic selected packet")
        (root / "packet/request.json").write_bytes(EXPECTED_BODY)
        (root / "packet/escape").symlink_to(canary)
        for name, content in {"outer_mcp.py": outer.FIXTURE, "mcp.py": MCP,
                              "relay.py": RELAY, "actor.py": ACTOR, "launcher.py": LAUNCHER}.items():
            (root / "fixture" / name).write_text(content)
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        listener.settimeout(0.1)
        (root / "fixture/config.toml").write_text("\n".join([
            'model_provider="synthetic_gateway"', 'model="synthetic-no-model"',
            'forced_login_method="chatgpt"', 'approval_policy="never"',
            'sandbox_mode="read-only"', 'web_search="disabled"',
            '[model_providers.synthetic_gateway]', 'name="Synthetic ChatGPT gateway"',
            'base_url="http://127.0.0.1:RELAY_PORT/backend-api/codex"',
            'requires_openai_auth=true', 'wire_api="responses"',
            '[features]', 'plugins=false', 'apps=false', 'hooks=false',
            'shell_tool=false', 'shell_snapshot=false', 'code_mode=false',
            'skip_host_skill_discovery=true',
            '[mcp_servers.unexpected]', 'command="/usr/bin/python3"',
            f'args={json.dumps(["/fixture/mcp.py", str(canary), str(listener.getsockname()[1])])}',
            'startup_timeout_sec=3',
        ]))

        class Handler(socketserver.BaseRequestHandler):
            def handle(self) -> None:
                try:
                    self.request.sendall(broker.exchange(self.request))
                except OSError:
                    pass

        with socketserver.UnixStreamServer(str(root / "broker.sock"), Handler) as server:
            server.timeout = 0.05
            server_stop = threading.Event()

            def serve_bounded() -> None:
                while not server_stop.is_set() and broker.requests < MAX_REQUESTS:
                    server.handle_request()

            server_thread = threading.Thread(target=serve_bounded, daemon=True)
            server_thread.start()
            command = [str(bwrap), "--unshare-all", "--unshare-user", "--disable-userns",
                       "--die-with-parent", "--new-session", "--cap-drop", "ALL",
                       "--ro-bind", "/usr", "/usr", "--symlink", "usr/bin", "/bin",
                       "--symlink", "usr/lib", "/lib", "--proc", "/proc", "--dev", "/dev",
                       "--tmpfs", "/tmp", "--bind", str(root / "state"), "/state",
                       "--ro-bind", str(root / "fixture"), "/fixture",
                       "--ro-bind", str(root / "packet"), "/packet",
                       "--ro-bind", str(root / "broker.sock"), "/gateway/broker.sock",
                       "--clearenv", "--setenv", "HOME", "/state/home",
                       "--setenv", "CODEX_HOME", "/state/codex",
                       "--setenv", "PATH", "/usr/bin:/bin", "--setenv", "LANG", "C.UTF-8",
                       "--chdir", "/state/workspace", "--", "/usr/bin/python3", "/fixture/launcher.py", str(binary)]
            client = NoModelClient(command, cwd=root, env={}, inherit_env=False)
            watchdog = threading.Timer(CASE_SECONDS, client.close)
            watchdog.daemon = True
            watchdog.start()
            deadline = time.monotonic() + CASE_SECONDS - 1
            try:
                initialized = client.initialize()
                account = client.request("account/read", {"refreshToken": False})
                if account != {"account": None, "requiresOpenaiAuth": True}:
                    raise RuntimeError("synthetic gateway unexpectedly has credentials or different auth requirements")
                config = client.request("config/read", {"includeLayers": False})
                thread = client.request("thread/start", {
                    "cwd": "/state/workspace", "approvalPolicy": "never", "sandbox": "read-only",
                    "environments": [], "ephemeral": True,
                })
                startup = _wait_json(root / "state/startup.json", deadline)
                early = _wait_json(root / "state/rival-ready", deadline)
                inventory = client.request("mcpServerStatus/list", {
                    "threadId": thread["thread"]["id"], "limit": 100, "detail": "full",
                })
                broker.admit()
                actors = {}
                for actor in (first_actor, "rival" if first_actor == "intended" else "intended"):
                    (root / f"state/release-{actor}").write_text("synthetic scheduling only; not authority")
                    actors[actor] = _wait_json(root / f"state/{actor}-result", deadline)
                heartbeat = root / "state/heartbeat"
                before = heartbeat.read_text()
                time.sleep(0.08)
                heartbeat_running = heartbeat.read_text() != before
            finally:
                watchdog.cancel()
                client.close()
                server_stop.set()
                server_thread.join(timeout=REQUEST_SECONDS + 1)
                if server_thread.is_alive():
                    raise RuntimeError("bounded synthetic broker did not stop")
            before = heartbeat.read_text()
            time.sleep(0.15)
            stopped = heartbeat.read_text() == before
            try:
                connection, _ = listener.accept()
                connection.close()
                listener_untouched = False
            except TimeoutError:
                listener_untouched = True
        raw_config = config.get("config", {})
        provider = raw_config.get("model_providers", {}).get("synthetic_gateway")
        report = {
            "firstActor": first_actor, "command": command, "initialized": initialized,
            "account": account, "effectiveProviderId": raw_config.get("model_provider"),
            "effectiveProvider": provider,
            "startupBeforeInventory": True, "startup": startup, "earlyRequests": early,
            "inventory": inventory, "actors": actors, "brokerEvents": broker.events,
            "requestsObserved": broker.requests,
            "sameRelayPeerForBothActorAttempts": actors["intended"]["attempt"]["body"]["brokerPeer"] == actors["rival"]["attempt"]["body"]["brokerPeer"],
            "directUnixPeerDiffersFromRelay": early["directUnixEarly"]["body"]["brokerPeer"] != early["early"]["body"]["brokerPeer"],
            "syntheticResponsesAdmitted": sum(e["reason"] == "synthetic-response" for e in broker.events),
            "nativeModelRequests": 0, "realUpstreamRequests": 0, "nativeMethodsObserved": client.methods,
            "hostCanaryUnchanged": canary.read_text() == "synthetic undisclosed canary",
            "packetUnchanged": packet.read_text() == "synthetic selected packet",
            "hostListenerUntouched": listener_untouched,
            "descendantHeartbeatChangedBeforeClose": heartbeat_running,
            "descendantHeartbeatStoppedAfterClose": stopped,
        }
        return json.loads(json.dumps(report).replace(str(root), "<probe>"))


def run_probe(codex_binary: str = "/usr/bin/codex", bwrap_binary: str = "/usr/bin/bwrap") -> dict[str, Any]:
    binary = Path(shutil.which(codex_binary) or codex_binary).resolve(strict=True)
    bwrap = Path(shutil.which(bwrap_binary) or bwrap_binary).resolve(strict=True)
    if not binary.is_relative_to("/usr") or not bwrap.is_relative_to("/usr"):
        raise ValueError("probe executables must be installed under /usr")
    cases = {first: run_case(binary, bwrap, first) for first in ("intended", "rival")}
    return {
        "schemaVersion": "nema-native-synthetic-gateway-probe/1",
        "classification": "OBSERVED_NO_MODEL_SYNTHETIC",
        "nativeVersion": subprocess.check_output([str(binary), "--version"], text=True).strip(),
        "binarySha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
        "bwrapVersion": subprocess.check_output([str(bwrap), "--version"], text=True).strip(),
        "kernel": platform.release(), "architecture": platform.machine(),
        "allowedNativeMethods": sorted(ALLOWED_METHODS),
        "limits": {"headerBytes": MAX_HEADER_BYTES, "bodyBytes": MAX_BODY_BYTES,
                   "responseBytes": MAX_RESPONSE_BYTES, "requestsPerCase": MAX_REQUESTS,
                   "requestSeconds": REQUEST_SECONDS, "caseSeconds": CASE_SECONDS},
        "modelTurns": 0, "existingCredentialsMounted": False, "realUpstreamRequests": 0,
        "cases": cases,
        "callerAuthenticationEstablished": False,
        "mechanismDisposition": "REJECTED: exact content and shared-relay identity do not authenticate the intended caller",
        "liveAdmission": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex", default="/usr/bin/codex")
    parser.add_argument("--bwrap", default="/usr/bin/bwrap")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = json.dumps(run_probe(args.codex, args.bwrap), indent=2) + "\n"
    if args.output:
        args.output.write_text(report)
    else:
        print(report, end="")


if __name__ == "__main__":
    main()
