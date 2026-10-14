"""Actual local TLS/WebSocket sockets through packaged opaque relay; no native."""
from dataclasses import replace
from importlib import resources
import json
import socket
import ssl
import subprocess
import sys
import threading
import time

from eidos.native_connect import AUTHORITIES, ConnectBroker
from eidos.native_managed_contract import ManagedPolicy, PROVIDER_AUTHORITY
from test_native_connect import headers, eventually, wire
from test_native_tls_connect_probe import probe


def test_opaque_websocket_and_settings_coexist_beyond_old_twenty_second_cap(tmp_path):
    certs = probe.make_certificates(tmp_path)
    server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_context.load_cert_chain(certs["validCert"], certs["validKey"])
    context = ssl.create_default_context(cafile=str(certs["ca"]))
    workers, errors, plaintext = [], [], []
    def endpoint(peer):
        try:
            with server_context.wrap_socket(peer, server_side=True) as secure:
                secure.settimeout(25)
                request = headers(secure); plaintext.append(request)
                if request.startswith(b"GET /socket "):
                    secure.sendall(b"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: s3pPLMBiTxaQ9kYGzzhZRbK+xOo=\r\n\r\n")
                    assert secure.recv(6) == b"\x89\x80\x01\x02\x03\x04"
                    secure.sendall(b"\x8a\x00")
                    assert secure.recv(6) == b"\x88\x80\x01\x02\x03\x04"
                    secure.sendall(b"\x88\x00")
                else:
                    assert request.startswith(b"GET /settings ")
                    secure.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\n{}")
        except BaseException as exc:
            errors.append(exc)
    def dial(authority, addresses, deadline, register, unregister):
        client, peer = socket.socketpair(); register(client)
        worker = threading.Thread(target=endpoint, args=(peer,))
        workers.append(worker); worker.start()
        return client
    failures = []
    policy = replace(ManagedPolicy(), preparation_seconds=30, turn_seconds=30, lifetime_seconds=35, idle_seconds=25)
    broker = ConnectBroker(policy, created=time.monotonic(), dialer=dial, on_failure=failures.append)
    path = tmp_path/"broker.sock"
    broker.start(path, {a: ((socket.AF_INET, "8.8.8.8"),) for a in AUTHORITIES})
    broker.activate_provider()
    config = tmp_path/"relay.json"
    port = tmp_path/"port"
    config.write_text(json.dumps({"deadline": time.monotonic()+32, "broker": str(path), "port_file": str(port),
        "idle_seconds": 25, "buffer_bytes": 8192, "max_active": 2, "max_connections": 256}))
    relay = resources.files("eidos").joinpath("resources/native_runtime.py")
    process = subprocess.Popen([sys.executable, "-I", "-S", str(relay), "relay", str(config)],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    streams = []
    def connect_tls():
        client = socket.create_connection(("127.0.0.1", int(port.read_text())), timeout=2)
        client.sendall(wire(PROVIDER_AUTHORITY))
        assert headers(client).startswith(b"HTTP/1.1 200")
        secured = context.wrap_socket(client, server_hostname="provider.fixture.invalid")
        secured.settimeout(25); streams.append(secured)
        return secured
    try:
        eventually(port.exists)
        websocket = connect_tls()
        websocket.sendall(b"GET /socket HTTP/1.1\r\nHost: provider.fixture.invalid\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\nSec-WebSocket-Version: 13\r\n\r\n")
        assert headers(websocket).startswith(b"HTTP/1.1 101")
        settings = connect_tls()
        settings.sendall(b"GET /settings HTTP/1.1\r\nHost: provider.fixture.invalid\r\n\r\n")
        assert headers(settings).startswith(b"HTTP/1.1 200") and settings.recv(2) == b"{}"
        settings.close()
        # This is a deliberate real-duration local wait, not a native/account call.
        time.sleep(21)
        websocket.sendall(b"\x89\x80\x01\x02\x03\x04")
        assert websocket.recv(2) == b"\x8a\x00"
        websocket.sendall(b"\x88\x80\x01\x02\x03\x04")
        assert websocket.recv(2) == b"\x88\x00"
        assert broker.snapshot()["peakActive"] == 2
        assert len(plaintext) == 2
        assert "GET /socket" not in json.dumps(broker.snapshot())  # endpoint plaintext is not broker evidence
        assert not failures and not errors
    finally:
        for stream in streams: stream.close()
        process.terminate()
        process.wait(timeout=3)
        process.stdout.close(); process.stderr.close()
        report = broker.close()
        for worker in workers: worker.join(2)
        assert report["workersJoined"] and not any(w.is_alive() for w in workers)
