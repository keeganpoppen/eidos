"""Authored sockets only: never DNS, native startup, accounts or upstream."""
from dataclasses import replace
import queue
import socket
import threading
import time

import pytest

from eidos.native_connect import AUTHORITIES, ConnectBroker, checked_addresses
from eidos.native_managed_contract import ISSUER_AUTHORITY, PROVIDER_AUTHORITY, ManagedLaunchError, ManagedPolicy


def wire(authority=ISSUER_AUTHORITY):
    return f"CONNECT {authority} HTTP/1.1\r\nHost: {authority}\r\n\r\n".encode()


def headers(client):
    result = bytearray()
    while not result.endswith(b"\r\n\r\n"):
        chunk = client.recv(1)
        if not chunk: break
        result.extend(chunk)
    return bytes(result)


def eventually(predicate):
    deadline = time.monotonic()+2
    while not predicate():
        if time.monotonic() >= deadline: raise AssertionError("condition did not become true")
        time.sleep(.005)


class LocalDialer:
    def __init__(self): self.peers = queue.Queue(); self.opened = []
    def __call__(self, authority, addresses, deadline, register, unregister):
        left, right = socket.socketpair()
        left.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 1024)
        right.settimeout(1)
        register(left)
        self.opened.append(authority); self.peers.put(right)
        return left


@pytest.fixture
def broker(tmp_path):
    dialer, failures = LocalDialer(), []
    policy = replace(ManagedPolicy(), preparation_seconds=5, turn_seconds=5, lifetime_seconds=10, idle_seconds=2)
    broker = ConnectBroker(policy, created=time.monotonic(), dialer=dialer, on_failure=failures.append)
    path = tmp_path/"broker.sock"
    broker.start(path, {authority: ((socket.AF_INET, "1.1.1.1"),) for authority in AUTHORITIES})
    yield broker, dialer, failures, path
    report = broker.close()
    while not dialer.peers.empty(): dialer.peers.get().close()
    assert report["active"] == 0 and report["workersJoined"] and report["serverJoined"]


def connect(path, request):
    client = socket.socket(socket.AF_UNIX)
    client.settimeout(1); client.connect(str(path)); client.sendall(request)
    return client


@pytest.mark.parametrize("payload", [
    wire("auth.openai.com.evil:443"), wire("auth.openai.com:0443"), wire("127.0.0.1:443"),
    wire("https://auth.openai.com:443"), wire().replace(b"CONNECT", b"GET"),
    wire().replace(b"Host:", b"Content-Length: 9\r\nHost:"),
    wire().replace(b"Host:", b"Transfer-Encoding: chunked\r\nHost:"),
    wire().replace(b"Host:", b"Host: other\r\nHost:"), wire()+b"body",
    wire().replace(b"Host:", b"Proxy-Authorization: secret\r\nHost:"),
])
def test_refusal_precedes_any_dial(broker, payload):
    value, dialer, failures, path = broker
    with connect(path, payload) as client:
        assert not headers(client).startswith(b"HTTP/1.1 200")
    eventually(lambda: failures)
    assert dialer.opened == []


def test_phase_closes_existing_issuer_and_enables_provider(broker):
    value, dialer, failures, path = broker
    with connect(path, wire()) as client:
        assert headers(client).startswith(b"HTTP/1.1 200")
        peer = dialer.peers.get(timeout=1)
        client.sendall(b"ciphertext-a"); assert peer.recv(64) == b"ciphertext-a"
        value.activate_provider()
        assert client.recv(1) == b"" and peer.recv(1) == b""
        peer.close()
    eventually(lambda: value.snapshot()["active"] == 0)
    with connect(path, wire(PROVIDER_AUTHORITY)) as client:
        assert headers(client).startswith(b"HTTP/1.1 200")
        peer = dialer.peers.get(timeout=1)
        peer.sendall(b"ciphertext-b"); assert client.recv(64) == b"ciphertext-b"
        peer.close()
    assert not failures
    with pytest.raises(ManagedLaunchError): value.activate_provider()


def test_provider_refused_during_preparation(broker):
    _, dialer, failures, path = broker
    with connect(path, wire(PROVIDER_AUTHORITY)) as client:
        assert headers(client).startswith(b"HTTP/1.1 403")
    assert not dialer.opened


def test_phase_change_during_dial_does_not_send_200(broker):
    value, dialer, failures, path = broker
    entered, release = threading.Event(), threading.Event()
    def held(authority, addresses, deadline, register, unregister):
        pair = dialer(authority, addresses, deadline, register, unregister)
        entered.set(); assert release.wait(1)
        return pair
    value._dialer = held
    with connect(path, wire()) as client:
        assert entered.wait(1)
        completed = threading.Event()
        transition = threading.Thread(target=lambda: (value.activate_provider(), completed.set()))
        transition.start()
        eventually(lambda: value.snapshot()["phase"] == "closing-issuer")
        assert not completed.is_set()
        release.set()
        transition.join(1); assert completed.is_set()
        assert not headers(client).startswith(b"HTTP/1.1 200")
    eventually(lambda: value.snapshot()["active"] == 0)
    assert not failures


def test_transition_drains_both_issuer_slots_before_new_provider(broker):
    value, dialer, failures, path = broker
    clients, peers = [], []
    try:
        for _ in range(2):
            client = connect(path, wire()); clients.append(client)
            assert headers(client).startswith(b"HTTP/1.1 200")
            peers.append(dialer.peers.get(timeout=1))
        value.activate_provider()
        assert value.snapshot()["active"] == 0
        with connect(path, wire(PROVIDER_AUTHORITY)) as client:
            assert headers(client).startswith(b"HTTP/1.1 200")
            dialer.peers.get(timeout=1).close()
        assert not failures
    finally:
        for peer in peers: peer.close()
        for client in clients: client.close()


def test_shared_receipt_limit_counts_one_proof_byte_across_streams(broker):
    value, dialer, failures, path = broker
    value.policy = replace(value.policy, max_received_bytes=127)
    clients, peers = [], []
    try:
        for _ in range(2):
            client = connect(path, wire()); clients.append(client)
            assert headers(client).startswith(b"HTTP/1.1 200")
            peers.append(dialer.peers.get(timeout=1))
        clients[0].sendall(b"a"*100); clients[1].sendall(b"b"*100)
        eventually(lambda: "aggregate-limit" in failures)
        assert value.snapshot()["receivedBytes"] == 128
    finally:
        for client in clients: client.close()
        for peer in peers: peer.close()


def test_close_interrupts_unfinished_header(broker):
    value, _, _, path = broker
    with connect(path, b"CONNECT ") as client:
        eventually(lambda: value.snapshot()["active"] == 1)
        started = time.monotonic(); result = value.close()
        assert time.monotonic()-started < .3
        assert result["workersJoined"] and client.recv(1) == b""


@pytest.mark.parametrize("result", [[], [[2, "127.0.0.1"]], [[2, "10.1.2.3"]], [[10, "::1"]],
    [[10, "::ffff:8.8.8.8"]], [[2, "224.0.0.1"]], [[True, "8.8.8.8"]],
    [[2, "8.8.8.8"], [2, "8.8.8.8"]], [[10, "fe80::1%eth0"]]])
def test_resolver_output_rejects_nonpublic_or_ambiguous_values(result):
    with pytest.raises(ManagedLaunchError): checked_addresses(result, 16)


def test_resolver_output_freezes_public_addresses():
    assert checked_addresses([[2, "8.8.8.8"], [10, "2606:4700:4700::1111"]], 16) == (
        (socket.AF_INET, "8.8.8.8"), (socket.AF_INET6, "2606:4700:4700::1111"))


def test_fragmented_connect_header(broker):
    value, dialer, failures, path = broker
    with socket.socket(socket.AF_UNIX) as client:
        client.settimeout(1); client.connect(str(path))
        for byte in wire(): client.sendall(bytes([byte]))
        assert headers(client).startswith(b"HTTP/1.1 200")
        dialer.peers.get(timeout=1).close()


def test_stalled_receiver_has_bounded_pending_buffer_and_closes(broker):
    value, dialer, failures, path = broker
    value.policy = replace(value.policy, buffer_bytes=1024, idle_seconds=.1)
    with connect(path, wire()) as client:
        assert headers(client).startswith(b"HTTP/1.1 200")
        peer = dialer.peers.get(timeout=1)
        try:
            client.sendall(b"x"*100000)
            eventually(lambda: "idle-limit" in failures)
            assert value.snapshot()["events"][0]["maxPendingBytesPerDirection"] == 1024
        finally: peer.close()


def test_third_concurrent_stream_stops_attempt_without_new_endpoint(broker):
    value, dialer, failures, path = broker
    clients, peers = [], []
    try:
        for _ in range(2):
            client = connect(path, wire()); clients.append(client)
            assert headers(client).startswith(b"HTTP/1.1 200")
            peers.append(dialer.peers.get(timeout=1))
        with connect(path, wire()) as client:
            try: assert client.recv(1) == b""
            except ConnectionResetError: pass
        eventually(lambda: failures)
        assert failures == ["connection-budget"]
        assert len(dialer.opened) == 2
        assert value.snapshot()["peakActive"] == 2
    finally:
        for client in clients: client.close()
        for peer in peers: peer.close()
