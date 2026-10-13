"""Local CONNECT destination closure; no native process, auth, TLS or upstream.

Closing a route prevents endpoint creation and interrupts that route's sockets.
It cannot recall bytes already received by a client or establish an auth barrier.
"""

from contextlib import contextmanager
from dataclasses import replace
import importlib.util
from pathlib import Path
import socket
import sys
import threading
import time

import pytest


spec = importlib.util.spec_from_file_location(
    "connect_phase_closure_probe", Path(__file__).parents[1] / "scripts/probe_native_tls_connect.py",
)
assert spec and spec.loader
probe = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = probe
spec.loader.exec_module(probe)

ISSUER = "issuer.fixture.invalid:443"
PROVIDER = probe.AUTHORITY


def _request(authority, *, host=None):
    return f"CONNECT {authority} HTTP/1.1\r\nHost: {host or authority}\r\n\r\n".encode()


def _header(client):
    received = bytearray()
    while not received.endswith(b"\r\n\r\n"):
        chunk = client.recv(1)
        if not chunk:
            break
        received.extend(chunk)
    return bytes(received)


def _receive(client, size):
    received = bytearray()
    while len(received) < size:
        chunk = client.recv(size - len(received))
        assert chunk, "stream closed before the expected local bytes arrived"
        received.extend(chunk)
    return bytes(received)


class _Endpoints:
    def __init__(self):
        self.peers = []

    def open(self):
        broker, endpoint = socket.socketpair()
        endpoint.settimeout(2)
        self.peers.append(endpoint)
        return broker

    def close(self):
        for endpoint in self.peers:
            endpoint.close()


@contextmanager
def _broker(**limits):
    issuer, provider = _Endpoints(), _Endpoints()
    value = probe.ConnectBroker(
        destinations={ISSUER: issuer.open, PROVIDER: provider.open},
        limits=replace(probe.TunnelLimits(), **limits),
    )
    try:
        yield value, issuer, provider
    finally:
        value.close()
        issuer.close()
        provider.close()


@contextmanager
def _exchange(broker, authority=PROVIDER, *, wire=None):
    client, server = socket.socketpair()
    client.settimeout(2)
    errors = []

    def serve():
        try:
            response = broker.exchange(server)
            if response:
                server.sendall(response)
        except OSError:
            pass  # The socket may be interrupted by explicit destination close.
        except BaseException as error:
            errors.append(error)
        finally:
            server.close()

    worker = threading.Thread(target=serve, daemon=True, name="connect-phase-acceptance")
    try:
        client.sendall(wire if wire is not None else _request(authority))
        worker.start()
        yield client, worker
    finally:
        client.close()
        worker.join(2)
        if worker.is_alive():
            broker.close()
            worker.join(2)
        assert not worker.is_alive(), "broker worker did not join after local shutdown"
        assert errors == []


def test_closing_active_issuer_interrupts_both_sockets_and_preserves_provider():
    with _broker() as (broker, issuer, provider):
        broker.admit()
        with _exchange(broker, ISSUER) as (auth_client, auth_worker), _exchange(broker) as (api_client, api_worker):
            assert b" 200 " in _header(auth_client)
            assert b" 200 " in _header(api_client)
            auth_client.sendall(b"issuer-request")
            assert _receive(issuer.peers[0], 14) == b"issuer-request"
            issuer.peers[0].sendall(b"already-delivered")
            assert _receive(auth_client, 17) == b"already-delivered"
            broker.close_authority(ISSUER)
            assert auth_client.recv(1) == b""
            assert issuer.peers[0].recv(1) == b""
            auth_worker.join(1)
            assert not auth_worker.is_alive()
            assert api_worker.is_alive()
            api_client.sendall(b"provider-still-open")
            assert _receive(provider.peers[0], 19) == b"provider-still-open"
            provider.peers[0].sendall(b"provider-response")
            assert _receive(api_client, 17) == b"provider-response"
            assert broker.active == 1
            broker.close_authority(ISSUER)
            with _exchange(broker, ISSUER) as (retry, _):
                assert b" 200 " not in _header(retry)
            assert len(issuer.peers) == 1
            broker.close()
            api_worker.join(1)
            assert not api_worker.is_alive()
        assert broker.active == 0


def test_closure_between_parse_and_endpoint_admission_refuses_without_open(monkeypatch):
    parsed, release = threading.Event(), threading.Event()
    read = probe.read_connect

    def paused_read(*args, **kwargs):
        result = read(*args, **kwargs)
        if result["authority"] == ISSUER:
            parsed.set()
            assert release.wait(2), "test did not release parsed CONNECT"
        return result

    monkeypatch.setattr(probe, "read_connect", paused_read)
    with _broker() as (broker, issuer, provider):
        broker.admit()
        with _exchange(broker, ISSUER) as (client, _):
            try:
                assert parsed.wait(1)
                broker.close_authority(ISSUER)
            finally:
                release.set()
            assert b" 200 " not in _header(client)
        assert issuer.peers == [] and broker.opened == 0
        with _exchange(broker) as (client, _):
            assert b" 200 " in _header(client)
            provider.peers[0].shutdown(socket.SHUT_WR)


def test_closing_before_admission_is_irreversible_and_does_not_reset_budget():
    with _broker(max_connections=3) as (broker, issuer, provider):
        broker.close_authority(ISSUER)
        broker.admit()
        for _ in range(2):
            broker.close_authority(ISSUER)
            with _exchange(broker, ISSUER) as (client, _):
                assert b" 200 " not in _header(client)
        assert issuer.peers == [] and broker.connections == 2
        with _exchange(broker) as (client, _):
            assert b" 200 " in _header(client)
            provider.peers[0].shutdown(socket.SHUT_WR)
        broker.close_authority(ISSUER)
        with pytest.raises(ValueError):
            broker.admit()
        with _exchange(broker) as (client, _):
            assert b" 429 " in _header(client)
        assert broker.connections == 3 and broker.opened == 1
        assert len(provider.peers) == 1


def test_destinations_share_concurrency_and_connection_budget_after_phase_close():
    with _broker(max_connections=4, max_active=2) as (broker, issuer, provider):
        broker.admit()
        with _exchange(broker, ISSUER) as (first, first_worker), _exchange(broker) as (second, _):
            assert b" 200 " in _header(first) and b" 200 " in _header(second)
            with _exchange(broker) as (third, _):
                assert b" 429 " in _header(third)
            assert broker.opened == broker.active == broker.peak_active == 2
            broker.close_authority(ISSUER)
            first_worker.join(1)
            assert not first_worker.is_alive()
            with _exchange(broker) as (fourth, _):
                assert b" 200 " in _header(fourth)
                assert broker.active == broker.peak_active == 2
                broker.close()
        with _exchange(broker) as (fifth, _):
            assert b" 429 " in _header(fifth)
        assert broker.connections == 4 and broker.opened == 3
        assert len(issuer.peers) == 1 and len(provider.peers) == 2
        assert broker.active == 0


def test_concurrent_destinations_share_one_aggregate_proof_byte():
    with _broker(aggregate_bytes=11) as (broker, issuer, provider):
        broker.admit()
        with _exchange(broker, ISSUER) as (first, _), _exchange(broker) as (second, _):
            assert b" 200 " in _header(first) and b" 200 " in _header(second)
            first.sendall(b"aaaaa")
            assert _receive(issuer.peers[0], 5) == b"aaaaa"
            issuer.peers[0].sendall(b"bbbbbbbb")
            second.sendall(b"cccccccc")
            deadline = time.monotonic() + 1
            while broker.total_bytes < 12 and time.monotonic() < deadline:
                time.sleep(.005)
            broker.close()
        assert broker.total_bytes == 12
        assert sum(event["outboundBytes"] + event["inboundBytes"] for event in broker.events) == 12
        assert any(event["reason"] == "aggregate-limit" for event in broker.events)
        assert broker.active == 0


@pytest.mark.parametrize("authority,host", [
    ("unmapped.fixture.invalid:443", None), ("issuer.fixture.invalid:80", None),
    ("issuer.fixture.invalid.:443", None), ("ISSUER.fixture.invalid:443", None),
    ("issuer.fixture.invalid:0443", None), ("issuer.fixture.invalid.evil:443", None),
    ("issuer.fixture.invalid%3A443", None), ("user@issuer.fixture.invalid:443", None),
    ("https://issuer.fixture.invalid:443", None), ("127.0.0.1:443", None),
    (ISSUER, PROVIDER), (PROVIDER, ISSUER),
])
def test_malformed_or_unmapped_authority_never_opens_either_endpoint(authority, host):
    with _broker() as (broker, issuer, provider):
        broker.admit()
        with _exchange(broker, wire=_request(authority, host=host)) as (client, _):
            assert b" 200 " not in _header(client)
        assert issuer.peers == provider.peers == []
        assert broker.opened == broker.active == 0


def test_callback_and_destination_mapping_cannot_both_supply_routes():
    with pytest.raises((TypeError, ValueError)):
        probe.ConnectBroker()
    with pytest.raises((TypeError, ValueError)):
        probe.ConnectBroker(lambda: pytest.fail("must not open"), destinations={PROVIDER: lambda: pytest.fail("must not open")})


def test_destination_map_is_a_fixed_copy_and_unknown_close_cannot_change_routes():
    issuer, provider = _Endpoints(), _Endpoints()
    routes = {ISSUER: issuer.open, PROVIDER: provider.open}
    broker = probe.ConnectBroker(destinations=routes)
    try:
        routes[ISSUER] = lambda: pytest.fail("mutated caller mapping was used")
        routes["later.fixture.invalid:443"] = issuer.open
        del routes[PROVIDER]
        with pytest.raises(TypeError):
            broker.endpoints[ISSUER] = issuer.open
        with pytest.raises(ValueError, match="unknown"):
            broker.close_authority("later.fixture.invalid:443")
        broker.admit()
        with _exchange(broker, "later.fixture.invalid:443") as (client, _):
            assert b" 403 " in _header(client)
        assert broker.opened == 0
        with _exchange(broker, ISSUER) as (client, _):
            assert b" 200 " in _header(client)
            issuer.peers[0].shutdown(socket.SHUT_WR)
        with _exchange(broker) as (client, _):
            assert b" 200 " in _header(client)
            provider.peers[0].shutdown(socket.SHUT_WR)
        assert len(issuer.peers) == len(provider.peers) == 1
    finally:
        broker.close()
        issuer.close()
        provider.close()


@pytest.mark.parametrize("routes", [
    {}, {ISSUER: None}, {"issuer.fixture.invalid": lambda: None},
    {"https://issuer.fixture.invalid:443": lambda: None},
    {"issuer.fixture.invalid.:443": lambda: None},
    {"ISSUER.fixture.invalid:443": lambda: None},
    {"issuer.fixture.invalid:0443": lambda: None},
    {"issuer.fixture.invalid:65536": lambda: None},
])
def test_invalid_destination_map_is_rejected_before_admission(routes):
    with pytest.raises(ValueError):
        probe.ConnectBroker(destinations=routes)
