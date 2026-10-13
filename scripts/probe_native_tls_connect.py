#!/usr/bin/env python3
"""Offline native HTTPS/CONNECT challenge. No DNS, upstream, or authentication.

The CONNECT broker sees ciphertext only. A separate disposable TLS endpoint owns
its key and the authored plaintext response. The native executable is unchanged.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import asdict, dataclass
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re
import selectors
import socket
import ssl
import subprocess
import tempfile
import threading
import time
from typing import Any, Callable

_spec = importlib.util.spec_from_file_location(
    "tls_derived_fixture", Path(__file__).with_name("probe_native_derived_catalog.py"))
assert _spec and _spec.loader
derived = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(derived)
catalog, transport, boundary = derived.catalog, derived.transport, derived.boundary
AUTHORITY = "provider.fixture.invalid:443"
BASE_URL = "https://provider.fixture.invalid/v1"
CASES = ("valid", "wrongHost", "redirect")
SOURCE_TAG = "rust-v0.154.0"
SOURCE_HASHES = {
    "codex-rs/http-client/src/custom_ca.rs": "c796e150be2d0f93f4ac6620eac4324cfc5168f3eae1d80146a4690acd6fc776",
    "codex-rs/http-client/src/outbound_proxy.rs": "0486978806a9cd5c8f552e985ed9b0c987392cdcdae35ec8b0a555539221aa52",
    "codex-rs/http-client/src/client_builder.rs": "a135ed62bb9e55a8bf091a57d0c5760e3ad453776825d86b2a40300a3303667d",
    "codex-rs/core/src/config/mod.rs": "4967b9f719ac886d5c6dd923f4d07263fe4eef2a7070078c5a291f57973c76a1",
}


@dataclass(frozen=True)
class TunnelLimits:
    header_bytes: int = 8192
    parse_seconds: float = 2.0
    max_connections: int = 8
    max_active: int = 2
    outbound_bytes: int = 262144
    inbound_bytes: int = 524288
    aggregate_bytes: int = 2097152
    buffer_bytes: int = 8192
    idle_seconds: float = 4.0
    lifetime_seconds: float = 8.0

    def __post_init__(self) -> None:
        for name, value in asdict(self).items():
            if name.endswith("seconds"):
                if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
                    raise ValueError("positive finite timing bound required")
            elif type(value) is not int or value <= 0:
                raise ValueError("positive integer byte/count bound required")


class Refused(ValueError):
    def __init__(self, status: int, reason: str, *, authority: str | None = None):
        self.status, self.reason = status, reason
        self.authority = authority
        super().__init__(reason)


def read_connect(connection: socket.socket, limits: TunnelLimits) -> dict[str, Any]:
    deadline = time.monotonic() + limits.parse_seconds
    data = bytearray()
    while b"\r\n\r\n" not in data:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise Refused(408, "parse-deadline")
        connection.settimeout(remaining)
        try:
            chunk = connection.recv(min(1024, limits.header_bytes + 5 - len(data)))
        except TimeoutError:
            raise Refused(408, "parse-deadline") from None
        if not chunk:
            raise Refused(400, "truncated-header")
        data.extend(chunk)
        end = data.find(b"\r\n\r\n")
        if end > limits.header_bytes or end == -1 and len(data) > limits.header_bytes + 3:
            raise Refused(413, "header-limit")
    head, rest = bytes(data).split(b"\r\n\r\n", 1)
    if rest:
        raise Refused(400, "unexpected-connect-body")
    try:
        lines = head.decode("ascii").split("\r\n")
        method, authority, version = lines[0].split(" ")
        if method != "CONNECT" or version != "HTTP/1.1":
            raise Refused(403, "connect-only")
        headers = {}
        for line in lines[1:]:
            name, value = line.split(":", 1)
            if not re.fullmatch(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+", name):
                raise Refused(400, "invalid-header-name")
            name, value = name.lower(), value.strip(" \t")
            if name in headers or any(ord(char) < 32 or ord(char) == 127 for char in value):
                raise Refused(400, "duplicate-or-control-header")
            headers[name] = value
        if set(headers) - {"host", "user-agent", "connection", "proxy-connection", "content-length"}:
            raise Refused(400, "unsupported-header")
        if headers.get("content-length", "0") != "0":
            raise Refused(400, "unexpected-connect-body")
        # Exact fixed authority comparison intentionally rejects normalization
        # ambiguities, alternate ports, IPs, suffixes, userinfo and URL forms.
        if authority != AUTHORITY:
            raise Refused(403, "destination-refused", authority=authority)
        if headers.get("host") != authority:
            raise Refused(400, "host-mismatch")
        return {"method": method, "authority": authority, "headers": headers}
    except (UnicodeError, ValueError) as exc:
        if isinstance(exc, Refused):
            raise
        raise Refused(400, "malformed-header") from None


class ConnectBroker:
    """Bounded fixed-destination tunnel, not a logical caller authenticator."""
    def __init__(self, open_endpoint: Callable[[], socket.socket], limits: TunnelLimits | None = None):
        self.open_endpoint = open_endpoint
        self.limits = limits or TunnelLimits()
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.admitted = False
        self.connections = self.active = self.peak_active = self.opened = self.total_bytes = 0
        self.attempts = self.unrecorded_refusals = 0
        self.events: list[dict[str, Any]] = []
        self.sockets: set[socket.socket] = set()

    def admit(self) -> None:
        with self.lock:
            if self.admitted or self.stop.is_set():
                raise ValueError("fixture admission cannot be renewed")
            self.admitted = True

    def exchange(self, client: socket.socket) -> bytes:
        start = time.monotonic()
        event: dict[str, Any] = {"status": None, "outboundBytes": 0, "inboundBytes": 0,
                                 "maxPendingBytesPerDirection": 0}
        upstream = None
        reserved = False
        with self.lock:
            self.attempts += 1
            if self.connections >= self.limits.max_connections or self.stop.is_set():
                self.unrecorded_refusals += 1
                return self.refusal(429, "connection-limit-or-closed")
            self.connections += 1
            self.events.append(event)
            self.sockets.add(client)
        try:
            event.update(read_connect(client, self.limits))
            with self.lock:
                if not self.admitted:
                    raise Refused(403, "not-admitted")
                if self.stop.is_set() or self.total_bytes >= self.limits.aggregate_bytes:
                    raise Refused(429, "aggregate-limit-or-closed")
                if self.active >= self.limits.max_active:
                    raise Refused(429, "concurrency-limit")
                self.active += 1
                self.peak_active = max(self.peak_active, self.active)
                reserved = True
                # Opening is local socketpair construction, never DNS/TCP dial.
                upstream = self.open_endpoint()
                self.opened += 1
                self.sockets.add(upstream)
            client.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            event["status"] = 200
            event["reason"] = self.bridge(client, upstream, event)
            return b""
        except Refused as exc:
            event.update(status=exc.status, reason=exc.reason)
            if exc.authority is not None:
                event["refusedAuthority"] = exc.authority
            return self.refusal(exc.status, exc.reason)
        except OSError as exc:
            event.update(reason="socket-error", errorType=type(exc).__name__)
            return b""
        finally:
            event["seconds"] = round(time.monotonic() - start, 6)
            with self.lock:
                if reserved:
                    self.active -= 1
                self.sockets.discard(client)
                if upstream is not None:
                    self.sockets.discard(upstream)
            if upstream is not None:
                upstream.close()

    @staticmethod
    def refusal(status: int, reason: str) -> bytes:
        body = json.dumps({"synthetic": True, "reason": reason}).encode()
        return (f"HTTP/1.1 {status} Refused\r\nContent-Length: {len(body)}\r\nConnection: close\r\n\r\n".encode() + body)

    def bridge(self, client: socket.socket, upstream: socket.socket, event: dict[str, Any]) -> str:
        limits = self.limits
        began = progress = time.monotonic()
        peers = {client: upstream, upstream: client}
        pending = {client: bytearray(), upstream: bytearray()}
        ended: set[socket.socket] = set()
        shut: set[socket.socket] = set()
        for connection in peers:
            connection.setblocking(False)
        with selectors.DefaultSelector() as selector:
            while not self.stop.is_set():
                now = time.monotonic()
                if now - began >= limits.lifetime_seconds:
                    return "lifetime-limit"
                if now - progress >= limits.idle_seconds:
                    return "idle-limit"
                if upstream in ended and not pending[client]:
                    return "endpoint-eof"
                for connection, peer in peers.items():
                    if connection in ended and not pending[peer] and peer not in shut:
                        peer.shutdown(socket.SHUT_WR)
                        shut.add(peer)
                    mask = (selectors.EVENT_READ if connection not in ended and len(pending[peer]) < limits.buffer_bytes else 0)
                    if pending[connection]: mask |= selectors.EVENT_WRITE
                    try: selector.unregister(connection)
                    except KeyError: pass
                    if mask: selector.register(connection, mask)
                timeout = min(.05, limits.lifetime_seconds - (now - began), limits.idle_seconds - (now - progress))
                for key, mask in selector.select(max(0, timeout)):
                    connection, peer = key.fileobj, peers[key.fileobj]
                    if mask & selectors.EVENT_WRITE:
                        try: sent = connection.send(pending[connection])
                        except BlockingIOError: sent = 0
                        if sent:
                            del pending[connection][:sent]
                            progress = time.monotonic()
                    if mask & selectors.EVENT_READ:
                        field = "outboundBytes" if connection is client else "inboundBytes"
                        cap = limits.outbound_bytes if connection is client else limits.inbound_bytes
                        # Serialize nonblocking receive/accounting across tunnels,
                        # including the single proof byte beyond a shared budget.
                        with self.lock:
                            if self.total_bytes > limits.aggregate_bytes:
                                return "aggregate-limit"
                            count = min(limits.buffer_bytes - len(pending[peer]), cap - event[field] + 1,
                                        limits.aggregate_bytes - self.total_bytes + 1)
                            try: data = connection.recv(count)
                            except BlockingIOError: continue
                            event[field] += len(data)
                            self.total_bytes += len(data)
                            if self.total_bytes > limits.aggregate_bytes:
                                return "aggregate-limit"
                        if event[field] > cap:
                            return "direction-limit"
                        if data:
                            pending[peer].extend(data)
                            event["maxPendingBytesPerDirection"] = max(
                                event["maxPendingBytesPerDirection"], len(pending[peer]))
                            progress = time.monotonic()
                        else:
                            ended.add(connection)
            return "closed"

    def close(self) -> None:
        self.stop.set()
        with self.lock:
            sockets = tuple(self.sockets)
        for connection in sockets:
            try: connection.shutdown(socket.SHUT_RDWR)
            except OSError: pass


class EndpointBroker(catalog.tool_probe.ToolFixtureBroker):
    def __init__(self, prompt: str, variant: str):
        super().__init__(prompt)
        self.variant = variant

    def dispatch(self, record: dict[str, Any]) -> tuple[int, str, bytes, str]:
        if record["method"] != "POST" or record["target"] != transport.RESPONSE_PATH:
            return 403, "route-refused", b"{}", "application/json"
        payload = json.loads(record["bodyRaw"])
        if not catalog.provider_shape(payload, record["headers"], derived.MODEL, self.prompt):
            return 422, "provider-shape-refused", b"{}", "application/json"
        tools = [item for item in payload["input"] if item.get("type") == "additional_tools"]
        if tools[0]["tools"] != []:
            return 422, "unexpected-tool-declaration", b"{}", "application/json"
        if not self.admitted or self.provider_requests:
            return 409, "not-admitted-or-consumed", b"{}", "application/json"
        self.provider_requests += 1
        if self.variant == "redirect":
            return 307, "authored-disallowed-redirect", b"{}", "application/json"
        return 200, "authored-final-text", catalog.authored_stream(derived.MODEL, 2), "text/event-stream"

    def exchange(self, connection: socket.socket) -> bytes:
        response = super().exchange(connection)
        if response.startswith(b"HTTP/1.1 307 "):
            self.events[-1]["responseLocation"] = "https://disallowed.fixture.invalid/v1/responses"
            response = response.replace(b"\r\n", b"\r\nLocation: https://disallowed.fixture.invalid/v1/responses\r\n", 1)
        return response


def make_certificates(directory: Path) -> dict[str, Path]:
    def openssl(*args: str) -> None:
        subprocess.run(["/usr/bin/openssl", *args], check=True, timeout=10, capture_output=True)
    ca, ca_key = directory / "ca.pem", directory / "ca.key"
    openssl("req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1", "-config", "/dev/null",
            "-subj", "/CN=Nema Disposable Fixture CA", "-addext", "basicConstraints=critical,CA:TRUE",
            "-addext", "keyUsage=critical,keyCertSign,cRLSign", "-keyout", str(ca_key), "-out", str(ca))
    paths = {"ca": ca}
    for name, hostname in (("valid", "provider.fixture.invalid"), ("wrongHost", "wrong.fixture.invalid")):
        key, request, cert, ext = (directory / (name + suffix) for suffix in (".key", ".csr", ".pem", ".ext"))
        ext.write_text(f"subjectAltName=DNS:{hostname}\nbasicConstraints=CA:FALSE\nkeyUsage=digitalSignature,keyEncipherment\nextendedKeyUsage=serverAuth\n")
        openssl("req", "-new", "-newkey", "rsa:2048", "-nodes", "-config", "/dev/null", "-subj", "/CN=" + hostname,
                "-keyout", str(key), "-out", str(request))
        openssl("x509", "-req", "-in", str(request), "-CA", str(ca), "-CAkey", str(ca_key), "-CAcreateserial",
                "-days", "1", "-extfile", str(ext), "-out", str(cert))
        paths[name + "Cert"], paths[name + "Key"] = cert, key
    return paths


class TlsFixture:
    """Adapter for the existing serial native runner; owns TLS endpoint workers."""
    def __init__(self, prompt: str, variant: str, paths: dict[str, Path]):
        self.endpoint = EndpointBroker(prompt, variant)
        self.tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        certificate = "wrongHost" if variant == "wrongHost" else "valid"
        self.tls.load_cert_chain(paths[certificate + "Cert"], paths[certificate + "Key"])
        self.lock = threading.Lock()
        self.endpoint_sockets: set[socket.socket] = set()
        self.workers: list[threading.Thread] = []
        self.tls_events: list[dict[str, Any]] = []
        self.proxy = ConnectBroker(self.open_endpoint)

    @property
    def events(self): return self.endpoint.events
    @property
    def requests(self): return self.endpoint.requests
    @property
    def provider_requests(self): return self.endpoint.provider_requests
    @property
    def resource_reads(self): return self.endpoint.resource_reads

    def admit(self) -> None:
        self.endpoint.admit()
        self.proxy.admit()

    def exchange(self, connection: socket.socket) -> bytes:
        return self.proxy.exchange(connection)

    def open_endpoint(self) -> socket.socket:
        proxy_side, endpoint_side = socket.socketpair()
        endpoint_side.settimeout(2)
        def serve() -> None:
            connection = endpoint_side
            event = {"handshakeSucceeded": False}
            try:
                connection = self.tls.wrap_socket(endpoint_side, server_side=True, do_handshake_on_connect=False)
                with self.lock:
                    self.endpoint_sockets.discard(endpoint_side)
                    self.endpoint_sockets.add(connection)
                connection.do_handshake()
                event["handshakeSucceeded"] = True
                connection.sendall(self.endpoint.exchange(connection))
            except (OSError, ValueError) as exc:
                event.update(errorType=type(exc).__name__, error=str(exc))
            finally:
                connection.close()
                with self.lock:
                    self.endpoint_sockets.discard(connection)
                    self.tls_events.append(event)
        with self.lock: self.endpoint_sockets.add(endpoint_side)
        worker = threading.Thread(target=serve, daemon=True)
        self.workers.append(worker)
        worker.start()
        return proxy_side

    def close(self) -> None:
        self.proxy.close()
        with self.lock: sockets = tuple(self.endpoint_sockets)
        for connection in sockets:
            try: connection.shutdown(socket.SHUT_RDWR)
            except OSError: pass
        deadline = time.monotonic() + 3
        for worker in self.workers:
            worker.join(max(0, deadline - time.monotonic()))
        if any(worker.is_alive() for worker in self.workers):
            raise RuntimeError("TLS fixture worker failed to join")


def run_probe() -> dict[str, Any]:
    original, _ = catalog.checked_catalog()
    model_catalog = derived.derived_catalog(original)
    results = {}
    with tempfile.TemporaryDirectory(prefix="nema-tls-host-") as temporary:
        host = Path(temporary)
        paths = make_certificates(host)
        helper = boundary.compile_helper(host)
        ca_hash = hashlib.sha256(paths["ca"].read_bytes()).hexdigest()
        for variant in CASES:
            fixtures = []
            @contextmanager
            def setup(root: Path, prompt: str, model: str):
                assert model == derived.MODEL
                (root / "fixture/ca.pem").write_bytes(paths["ca"].read_bytes())
                anchor = "os.execv('/fixture/guard'"
                assert transport.LAUNCHER.count(anchor) == 1
                launcher = transport.LAUNCHER.replace(anchor,
                    "os.environ['HTTPS_PROXY']='http://127.0.0.1:'+port.read_text()\n"
                    "os.environ['CODEX_CA_CERTIFICATE']='/fixture/ca.pem'\n" + anchor)
                (root / "fixture/launcher.py").write_text(launcher)
                fixture = TlsFixture(prompt, variant, paths)
                fixtures.append(fixture)
                try: yield fixture
                finally: fixture.close()
            config = derived.fixture_config(derived.MODEL).replace("http://127.0.0.1:FIXTURE_PORT/v1", BASE_URL)
            result = catalog.run_case(helper, derived.MODEL, model_catalog, config=config, limits=derived.LIMITS,
                                      expected_base_url=BASE_URL, fixture_factory=setup)
            fixture, = fixtures
            result["tlsEndpointEvents"] = result.pop("brokerEvents")
            result["connectEvents"] = fixture.proxy.events
            result["connectCount"] = fixture.proxy.connections
            result["connectAttempts"] = fixture.proxy.attempts
            result["unrecordedConnectRefusals"] = fixture.proxy.unrecorded_refusals
            result["mappedEndpointOpens"] = fixture.proxy.opened
            result["peakConcurrentTunnels"] = fixture.proxy.peak_active
            result["ciphertextBytes"] = fixture.proxy.total_bytes
            result["tlsHandshakeEvents"] = fixture.tls_events
            result["allEndpointWorkersJoined"] = not any(worker.is_alive() for worker in fixture.workers)
            result["remainingActiveTunnels"] = fixture.proxy.active
            results[variant] = result
    return {"schemaVersion": "nema-native-tls-connect/1", "implementationBase": "59bec0d",
            "classification": "NATIVE_TRANSPORT_SYNTHETIC_OPAQUE_CONNECT", "cases": results,
            "nativeTurnRPCs": sum(case["nativeTurnRPCs"] for case in results.values()),
            "fixtureHttpRequests": sum(case["httpRequests"] for case in results.values()),
            "connectAttempts": sum(case["connectAttempts"] for case in results.values()),
            "fixtureCaSha256": ca_hash, "fixtureKeysCommitted": False, "fixtureKeysMountedToNative": False,
            "realModelCalls": 0, "realUpstreamRequests": 0, "existingCredentialsMounted": False,
            "subscriptionExecution": False, "callerAuthenticationEstablished": False, "liveAdmission": False,
            "proxyDecryptsTls": False, "proxyHasDnsOrTcpDialer": False,
            "nativeProxyConfiguration": {"HTTPS_PROXY": "http://127.0.0.1:<namespace-relay-port>",
                                         "CODEX_CA_CERTIFICATE": "/fixture/ca.pem", "ambientEnvironmentInherited": False},
            "sourceProvenance": {"tag": SOURCE_TAG, "sha256": SOURCE_HASHES},
            "ciphertextAccounting": "received bytes; at most one non-forwarded proof byte beyond each direction or shared aggregate bound",
            "limits": {"connect": asdict(TunnelLimits()), "nativeCapture": asdict(derived.LIMITS),
                       "namespaceRelayRequestBytes": 140000, "namespaceRelayResponseBytes": 20000,
                       "namespaceRelaySeconds": 4, "nativeWatchdogSeconds": transport.CASE_SECONDS,
                       "namespaceRelayAcceptedSockets": 24,
                       "nativeRunnerConcurrency": 1, "aggregateResourceQuota": False},
            "binarySha256": hashlib.sha256(Path('/usr/bin/codex').read_bytes()).hexdigest(),
            "processFilterSourceSha256": hashlib.sha256(boundary.HELPER_C.encode()).hexdigest()}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = json.dumps(run_probe(), indent=2) + "\n"
    if args.output: args.output.write_text(result)
    else: print(result, end="")


if __name__ == "__main__": main()
