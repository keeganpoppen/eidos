"""Local socket/fixture checks by default; native execution requires explicit opt-in."""
from contextlib import contextmanager
from dataclasses import asdict, replace
import importlib.util
import json
import os
from pathlib import Path
import socket
import ssl
import sys
import threading
import time

import pytest

spec = importlib.util.spec_from_file_location(
    "native_tls_connect_probe", Path(__file__).parents[1] / "scripts/probe_native_tls_connect.py")
assert spec and spec.loader
probe = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = probe
spec.loader.exec_module(probe)
CONNECT = (f"CONNECT {probe.AUTHORITY} HTTP/1.1\r\nHost: {probe.AUTHORITY}\r\n\r\n").encode()


@contextmanager
def exchange(broker, request=CONNECT):
    client, server = socket.socketpair()
    client.settimeout(1)
    errors = []
    def serve():
        try:
            server.sendall(broker.exchange(server))
        except OSError:
            pass  # Clients intentionally interrupt reads in shutdown cases.
        except BaseException as exc:
            errors.append(exc)
        finally:
            server.close()
    worker = threading.Thread(target=serve, daemon=True)
    if request is not None:
        client.sendall(request)
    worker.start()
    try:
        yield client, worker
    finally:
        client.close()
        worker.join(1)
        if worker.is_alive():
            broker.close()
            worker.join(1)
        assert not worker.is_alive()
        assert not errors


def header(client):
    data = bytearray()
    while not data.endswith(b"\r\n\r\n"):
        chunk = client.recv(1)
        if not chunk:
            break
        data.extend(chunk)
    return bytes(data)


class Endpoints:
    def __init__(self): self.peers = []
    def open(self):
        proxy, endpoint = socket.socketpair()
        proxy.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 1024)
        endpoint.settimeout(1)
        self.peers.append(endpoint)
        return proxy
    def close(self):
        for peer in self.peers: peer.close()


@pytest.fixture
def broker():
    endpoints = Endpoints()
    value = probe.ConnectBroker(endpoints.open)
    value.admit()
    yield value, endpoints
    value.close()
    endpoints.close()


@pytest.mark.parametrize("authority", [
    "disallowed.fixture.invalid:443", "provider.fixture.invalid:80", "provider.fixture.invalid",
    "provider.fixture.invalid.:443", "PROVIDER.fixture.invalid:443", "127.0.0.1:443", "[::1]:443",
    "user@provider.fixture.invalid:443", "https://provider.fixture.invalid:443",
    "provider.fixture.invalid.evil:443", "provider.fixture.invalid:0443",
    "provider.fixture.invalid%3A443", "provider.fixture.invalid:443/path",
])
def test_unapproved_authority_refused_before_endpoint_open(broker, authority):
    value, endpoints = broker
    request = f"CONNECT {authority} HTTP/1.1\r\nHost: {authority}\r\n\r\n".encode()
    with exchange(value, request) as (client, _):
        assert header(client).startswith(b"HTTP/1.1 403")
    assert value.opened == 0 and endpoints.peers == []
    assert value.events[0]["refusedAuthority"] == authority


@pytest.mark.parametrize("wire", [
    CONNECT.replace(b"CONNECT ", b"GET "), CONNECT.replace(b"HTTP/1.1", b"HTTP/1.0"),
    CONNECT.replace(b"Host:", b"Wrong:"),
    CONNECT.replace(b"\r\n\r\n", b"\r\nHost: other:443\r\n\r\n"),
    CONNECT.replace(b"\r\n\r\n", b"\r\nhost: provider.fixture.invalid:443\r\n\r\n"),
    CONNECT.replace(b"\r\n\r\n", b"\r\nContent-Length: 1\r\n\r\n"),
    CONNECT.replace(b"\r\n\r\n", b"\r\nContent-Length: 00\r\n\r\n"),
    CONNECT.replace(b"\r\n\r\n", b"\r\nTransfer-Encoding: chunked\r\n\r\n"),
    CONNECT.replace(b"\r\n\r\n", b"\r\nProxy-Authorization: hidden\r\n\r\n"),
    CONNECT.replace(b"\r\n\r\n", b"\r\nUser-Agent: x\x00y\r\n\r\n"),
    CONNECT + b"x", CONNECT + CONNECT,
    CONNECT.replace(b"Host:", b"\xffHost:"), b"CONNECT\r\n\r\n",
])
def test_invalid_framing_refused_before_endpoint_open(broker, wire):
    value, endpoints = broker
    with exchange(value, wire) as (client, _):
        assert not header(client).startswith(b"HTTP/1.1 200")
    assert value.opened == 0 and not endpoints.peers


def test_fragmented_header_succeeds_and_bytes_remain_opaque(broker):
    value, endpoints = broker
    with exchange(value, None) as (client, _):
        for fragment in (CONNECT[:7], CONNECT[7:39], CONNECT[39:]): client.sendall(fragment)
        assert header(client).startswith(b"HTTP/1.1 200")
        ciphertext = b"\x16\x03\x01opaque-fixture\x00\xff"
        client.sendall(ciphertext)
        assert endpoints.peers[0].recv(100) == ciphertext
        endpoints.peers[0].sendall(b"opaque-response")
        assert client.recv(100) == b"opaque-response"
        endpoints.peers[0].shutdown(socket.SHUT_WR)
    assert value.events[0]["outboundBytes"] == len(ciphertext)
    assert "opaque-fixture" not in json.dumps(value.events)


@pytest.mark.parametrize("kind", ["oversized", "truncated", "deadline"])
def test_header_size_eof_and_deadline_are_bounded(kind):
    value = probe.ConnectBroker(lambda: pytest.fail("opened refused endpoint"),
                                replace(probe.TunnelLimits(), header_bytes=100, parse_seconds=.08))
    value.admit()
    request = b"x" * 105 if kind == "oversized" else b"CONNECT incomplete"
    with exchange(value, request) as (client, _):
        if kind == "truncated": client.shutdown(socket.SHUT_WR)
        assert header(client).startswith({"oversized": b"HTTP/1.1 413", "truncated": b"HTTP/1.1 400",
                                           "deadline": b"HTTP/1.1 408"}[kind])
    assert value.opened == 0


def test_header_content_limit_excludes_only_four_byte_delimiter(broker):
    value, endpoints = broker
    content_size = len(CONNECT) - 4
    value.limits = replace(value.limits, header_bytes=content_size)
    with exchange(value) as (client, _):
        assert b" 200 " in header(client)
        endpoints.peers[0].shutdown(socket.SHUT_WR)
    value.limits = replace(value.limits, header_bytes=content_size - 1)
    with exchange(value) as (client, _): assert b" 413 " in header(client)
    assert value.opened == 1


def test_early_request_does_not_consume_admission_and_close_prevents_reopening():
    endpoints = Endpoints()
    value = probe.ConnectBroker(endpoints.open)
    try:
        with exchange(value) as (client, _): assert header(client).startswith(b"HTTP/1.1 403")
        assert not value.opened
        value.admit()
        with exchange(value) as (client, _):
            assert header(client).startswith(b"HTTP/1.1 200")
            value.close()
        with pytest.raises(ValueError): value.admit()
        with exchange(value) as (client, _): assert header(client).startswith(b"HTTP/1.1 429")
    finally:
        value.close()
        endpoints.close()


def test_concurrency_and_connection_limit_refuse_without_third_endpoint(broker):
    value, endpoints = broker
    value.limits = replace(value.limits, max_connections=3)
    with exchange(value) as (first, one), exchange(value) as (second, two):
        assert b" 200 " in header(first) and b" 200 " in header(second)
        with exchange(value) as (third, _): assert b" 429 " in header(third)
        assert value.active == value.peak_active == value.opened == 2
        first.sendall(b"one")
        second.sendall(b"two")
        assert sorted(peer.recv(3) for peer in endpoints.peers) == [b"one", b"two"]
        value.close()
        one.join(.5); two.join(.5)
        assert not one.is_alive() and not two.is_alive()
    with exchange(value) as (fourth, _): assert b" 429 " in header(fourth)
    assert value.connections == len(value.events) == 3 and value.active == 0
    assert value.attempts == 4 and value.unrecorded_refusals == 1


@pytest.mark.parametrize("direction", ["outbound", "inbound"])
def test_direction_quota_receives_at_most_one_unforwarded_proof_byte(broker, direction):
    value, endpoints = broker
    value.limits = replace(value.limits, outbound_bytes=7, inbound_bytes=7)
    with exchange(value) as (client, worker):
        assert b" 200 " in header(client)
        sender = client if direction == "outbound" else endpoints.peers[0]
        sender.sendall(b"123456789")
        worker.join(.5)
        assert not worker.is_alive()
    assert value.events[0][direction + "Bytes"] == 8
    assert value.total_bytes == 8 and value.events[0]["reason"] == "direction-limit"


def test_concurrent_aggregate_quota_has_only_one_shared_proof_byte(broker):
    value, endpoints = broker
    value.limits = replace(value.limits, aggregate_bytes=11)
    with exchange(value) as (first, one), exchange(value) as (second, two):
        assert b" 200 " in header(first) and b" 200 " in header(second)
        first.sendall(b"aaaaaa")
        second.sendall(b"bbbbbbbbbbbb")
        deadline = time.monotonic() + .5
        while value.total_bytes < 12 and time.monotonic() < deadline: time.sleep(.005)
        value.close()
    assert value.total_bytes == 12
    assert sum(item["outboundBytes"] + item["inboundBytes"] for item in value.events) == 12
    assert any(item["reason"] == "aggregate-limit" for item in value.events)


@pytest.mark.parametrize("kind", ["idle", "lifetime", "backpressure"])
def test_idle_lifetime_and_nonreading_peer_have_bounded_buffers_and_exit(broker, kind):
    value, endpoints = broker
    value.limits = replace(value.limits, idle_seconds=.08 if kind == "idle" else .4,
                           lifetime_seconds=.18, buffer_bytes=64)
    with exchange(value) as (client, worker):
        assert b" 200 " in header(client)
        if kind == "backpressure":
            client.sendall(b"x" * 20000)  # Endpoint deliberately never reads.
        elif kind == "lifetime":
            for _ in range(6):
                client.sendall(b"x")
                assert endpoints.peers[0].recv(1) == b"x"
                time.sleep(.015)
        worker.join(.5)
        assert not worker.is_alive()
    assert value.events[0]["reason"] == ("idle-limit" if kind == "idle" else "lifetime-limit")
    assert value.events[0]["maxPendingBytesPerDirection"] <= 64
    assert value.active == 0


@pytest.mark.parametrize("override", [{"header_bytes": 0}, {"max_active": True}, {"idle_seconds": float("nan")},
                                      {"lifetime_seconds": -1}, {"aggregate_bytes": 1.5}])
def test_invalid_limits_fail_before_any_socket(override):
    with pytest.raises(ValueError): probe.TunnelLimits(**override)


@pytest.fixture(scope="module")
def certificates(tmp_path_factory):
    return probe.make_certificates(tmp_path_factory.mktemp("tls-public-fixture"))


def test_tls_fixture_close_interrupts_incomplete_handshake_and_joins(certificates):
    fixture = probe.TlsFixture("authored prompt", "valid", certificates)
    fixture.admit()
    with exchange(fixture.proxy) as (client, worker):
        assert b" 200 " in header(client)
        fixture.close()
        worker.join(.5)
        assert not worker.is_alive()
    assert not fixture.endpoint_sockets and all(not worker.is_alive() for worker in fixture.workers)


@pytest.mark.parametrize("variant", ["valid", "wrongHost"])
def test_local_tls_control_uses_hostname_validation_and_records_no_plaintext_before_handshake(certificates, variant):
    fixture = probe.TlsFixture("authored prompt", variant, certificates)
    fixture.admit()
    context = ssl.create_default_context(cafile=str(certificates["ca"]))
    try:
        with exchange(fixture.proxy) as (client, _):
            assert b" 200 " in header(client)
            if variant == "wrongHost":
                with pytest.raises(ssl.SSLCertVerificationError):
                    context.wrap_socket(client, server_hostname="provider.fixture.invalid")
            else:
                with context.wrap_socket(client, server_hostname="provider.fixture.invalid") as encrypted:
                    encrypted.sendall(b"GET /not-permitted HTTP/1.1\r\nHost: provider.fixture.invalid\r\n\r\n")
                    assert b" 403 " in encrypted.recv(4096)
    finally: fixture.close()
    assert fixture.requests == (1 if variant == "valid" else 0)
    assert len(fixture.tls_events) == 1 and fixture.tls_events[0]["handshakeSucceeded"] == (variant == "valid")
    assert "not-permitted" not in json.dumps(fixture.proxy.events)


@pytest.fixture(scope="module")
def observed():
    if os.environ.get("NEMA_NATIVE_TLS_CONNECT_PROBE") != "1":
        pytest.skip("opt in to contained native no-auth TLS CONNECT challenge")
    report = probe.run_probe()
    if output := os.environ.get("NEMA_NATIVE_TLS_CONNECT_EVIDENCE"):
        Path(output).write_text(json.dumps(report, indent=2) + "\n")
    return report


def test_contained_valid_tls_recovers_authored_synthetic_result(observed):
    case = observed["cases"]["valid"]
    assert case["failure"] is None, case["failure"]
    assert case["savedArtifact"]["text"] == probe.transport.OUTPUT_TEXT
    assert case["savedArtifact"]["executionEvidence"] == "synthetic"
    assert case["httpRequests"] == case["acceptedProviderRequests"] == case["nativeTurnRPCs"] == 1
    assert case["tlsHandshakeEvents"] == [{"handshakeSucceeded": True}]
    tools, = case["providerRequestAnalyses"][0]["additionalTools"]
    assert tools["type"] == "additional_tools" and tools["role"] == "developer" and tools["tools"] == []


def test_contained_wrong_hostname_fails_before_plaintext_http(observed):
    case = observed["cases"]["wrongHost"]
    assert case["failure"] is not None and case["savedArtifact"] is None
    assert case["httpRequests"] == case["acceptedProviderRequests"] == 0
    assert case["mappedEndpointOpens"] >= 1
    assert all(not event["handshakeSucceeded"] for event in case["tlsHandshakeEvents"])


def test_contained_redirect_never_opens_unapproved_target(observed):
    case = observed["cases"]["redirect"]
    assert case["failure"] is not None and case["savedArtifact"] is None
    assert case["httpRequests"] >= 1 and case["tlsEndpointEvents"][0]["status"] == 307
    assert case["acceptedProviderRequests"] == 1
    assert all(event["status"] == 409 for event in case["tlsEndpointEvents"][1:])
    assert any(event.get("refusedAuthority") == "disallowed.fixture.invalid:443"
               and event["status"] == 403 for event in case["connectEvents"])
    assert all(event.get("authority") == probe.AUTHORITY for event in case["connectEvents"] if event["status"] == 200)
    assert all(event["status"] != 200 for event in case["connectEvents"] if event.get("authority") != probe.AUTHORITY)


@pytest.mark.parametrize("variant", probe.CASES)
def test_contained_case_preserves_noauth_process_and_capture_contract_and_closes_workers(observed, variant):
    case = observed["cases"][variant]
    assert case["nativeReplies"]["account/read"] == {"account": None, "requiresOpenaiAuth": False}
    assert case["policy"]["installedBeforeInitialExec"] and case["policy"]["allListenerCopiesClosed"]
    assert case["nativeCapture"]["failure"] is None
    assert case["nativeCapture"]["diagnosticError"] is None
    assert case["nativeCapture"]["limits"] == asdict(probe.derived.LIMITS)
    turn_sources = {row["source"] for row in case["traceRecords"]
                    if row["direction"] == "client_to_appserver"
                    and json.loads(row["rawText"]).get("method") == "turn/start"}
    assert len(turn_sources) == 1
    internal = [(row["source"], json.loads(row["rawText"])) for row in case["traceRecords"]
                if row["direction"] == "internal"]
    limits = [(source, message.get("params", {}).get("limits")) for source, message in internal
              if message.get("method") == "$transport/limits"]
    assert limits == [(next(iter(turn_sources)), asdict(probe.derived.LIMITS))]
    assert not any(message.get("method") == "$transport/captureGap" for _, message in internal)
    assert case["allEndpointWorkersJoined"] and case["remainingActiveTunnels"] == 0
    assert case["nativeTurnRPCs"] == 1
    assert case["connectCount"] <= 8 and case["peakConcurrentTunnels"] == 1
    assert observed["realModelCalls"] == observed["realUpstreamRequests"] == 0
    assert not observed["existingCredentialsMounted"] and not observed["liveAdmission"]
    assert not observed["proxyDecryptsTls"] and not observed["proxyHasDnsOrTcpDialer"]


def test_committed_synthetic_evidence_rechecks_without_native_startup():
    path = Path(__file__).parents[1] / "docs/evidence/NATIVE_TLS_CONNECT_0_154_0.json"
    recorded = json.loads(path.read_bytes())
    test_contained_valid_tls_recovers_authored_synthetic_result(recorded)
    test_contained_wrong_hostname_fails_before_plaintext_http(recorded)
    test_contained_redirect_never_opens_unapproved_target(recorded)
    for variant in probe.CASES:
        test_contained_case_preserves_noauth_process_and_capture_contract_and_closes_workers(recorded, variant)


@pytest.mark.parametrize("mutation", ["diagnostic", "limits", "record-source"])
def test_capture_contract_rejects_diagnostic_limit_or_source_mismatch(mutation):
    path = Path(__file__).parents[1] / "docs/evidence/NATIVE_TLS_CONNECT_0_154_0.json"
    recorded = json.loads(path.read_bytes())
    case = recorded["cases"]["valid"]
    if mutation == "diagnostic": case["nativeCapture"]["diagnosticError"] = "authored diagnostic failure"
    elif mutation == "limits": case["nativeCapture"]["limits"]["max_event_count"] += 1
    else:
        for row in case["traceRecords"]:
            if json.loads(row["rawText"]).get("method") == "$transport/limits":
                row["source"] = "copied-other-client"
    with pytest.raises(AssertionError):
        test_contained_case_preserves_noauth_process_and_capture_contract_and_closes_workers(recorded, "valid")
