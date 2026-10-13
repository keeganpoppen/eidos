"""Synthetic broker controls and an opt-in native caller-confusion experiment."""
import concurrent.futures
import importlib.util
import json
import os
from pathlib import Path
import socket
import time

import pytest


spec = importlib.util.spec_from_file_location(
    "probe_native_gateway", Path(__file__).parents[1] / "scripts/probe_native_gateway.py")
assert spec and spec.loader
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


def request(body=probe.EXPECTED_BODY, *, path=probe.RESPONSES_PATH, extra=b""):
    return (f"POST {path} HTTP/1.1\r\nHost: synthetic\r\nContent-Length: {len(body)}\r\n".encode()
            + extra + b"\r\n" + body)


def exchange(broker, data):
    with _socket_pair() as (server, client):
        client.sendall(data)
        client.shutdown(socket.SHUT_WR)
        response = broker.exchange(server)
        header, body = response.split(b"\r\n\r\n", 1)
        return int(header.split(b" ")[1]), json.loads(body)


class _socket_pair:
    def __enter__(self):
        self.pair = socket.socketpair()
        return self.pair

    def __exit__(self, *args):
        for item in self.pair:
            item.close()


@pytest.mark.parametrize("method", ["turn/start", "turn/steer", "thread/realtime/start",
                                     "account/login/start", "process/spawn", "thread/shellCommand"])
def test_gateway_probe_cannot_request_model_login_or_process_before_spawn(method):
    client = probe.NoModelClient(["must-not-launch"])
    with pytest.raises(ValueError, match="gateway probe refuses"):
        client.request(method, {})
    assert client.process is None and client.methods == []


def test_gateway_probe_rejects_non_handshake_notifications_and_native_responses():
    client = probe.NoModelClient(["must-not-launch"])
    with pytest.raises(ValueError):
        client.notify("turn/start", {})
    with pytest.raises(ValueError):
        client.respond(1, {})
    assert client.process is None


@pytest.mark.parametrize("data,status,reason", [
    (request(path="https://unapproved.invalid/action"), 403, "route-refused"),
    (request(path=probe.RESPONSES_PATH + "?redirect=1"), 403, "route-refused"),
    (request(path="/backend-api/codex/%72esponses"), 403, "route-refused"),
    (request(b"changed"), 422, "content-refused"),
    (request(b"x" * (probe.MAX_BODY_BYTES + 1)), 413, "body-limit"),
    (request(extra=b"X-Long: " + b"x" * probe.MAX_HEADER_BYTES + b"\r\n"), 413, "header-limit"),
    (request(extra=b"Content-Length: 1\r\n"), 400, "malformed"),
    (request(extra=b"Transfer-Encoding: chunked\r\n"), 400, "unsupported-header"),
    (request(extra=b"Authorization: synthetic-forbidden\r\n"), 400, "unsupported-header"),
    (request()[:-1], 400, "malformed"),
    (b"POST / HTTP/1.1\r\nContent-Length: -1\r\n\r\n", 413, "body-limit"),
    (b"POST / HTTP/1.1\r\nContent-Length: nope\r\n\r\n", 400, "malformed"),
])
def test_broker_rejects_unapproved_content_routes_and_framing(data, status, reason):
    broker = probe.SyntheticBroker()
    broker.admit()
    observed, body = exchange(broker, data)
    assert observed == status and body["reason"] == reason
    assert broker.consumed is False


def test_exact_content_is_closed_before_admission_and_one_use_afterwards():
    broker = probe.SyntheticBroker()
    assert exchange(broker, request())[0] == 403
    assert not broker.consumed
    broker.admit()
    assert exchange(broker, request())[0] == 200
    assert exchange(broker, request())[0] == 409
    with pytest.raises(ValueError, match="renewed"):
        broker.admit()


def test_coalesced_body_does_not_count_against_header_bytes():
    broker = probe.SyntheticBroker()
    broker.admit()
    baseline = request(extra=b"X-Padding: \r\n")
    header = baseline.split(b"\r\n\r\n", 1)[0]
    padded = request(extra=b"X-Padding: " + b"x" * (probe.MAX_HEADER_BYTES - len(header)) + b"\r\n")
    assert len(padded.split(b"\r\n\r\n", 1)[0]) == probe.MAX_HEADER_BYTES
    assert exchange(broker, padded)[0] == 200


def test_concurrent_same_content_consumes_one_in_memory_permit():
    broker = probe.SyntheticBroker()
    broker.admit()
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(exchange, broker, request()) for _ in range(2)]
        assert sorted(f.result()[0] for f in futures) == [200, 409]


def test_broker_bounds_processed_requests_and_does_not_reset_its_permit():
    broker = probe.SyntheticBroker()
    for _ in range(probe.MAX_REQUESTS):
        assert exchange(broker, request())[0] == 403
    assert exchange(broker, request())[0] == 429
    assert broker.requests == len(broker.events) == probe.MAX_REQUESTS


def test_broker_has_an_absolute_deadline_for_incomplete_input(monkeypatch):
    monkeypatch.setattr(probe, "REQUEST_SECONDS", 0.06)
    broker = probe.SyntheticBroker()
    with _socket_pair() as (server, client):
        # Partial headers are deliberately never completed, nor is write closed.
        client.sendall(b"POST / HTTP/1.1\r\n")
        started = time.monotonic()
        response = broker.exchange(server)
        assert response.startswith(b"HTTP/1.1 408 ")
        assert time.monotonic() - started < 1


def test_fake_service_redirect_is_refused_without_location_or_upstream_connection():
    broker = probe.SyntheticBroker()
    with _socket_pair() as (server, client):
        client.sendall(f"GET {probe.MODELS_PATH} HTTP/1.1\r\n\r\n".encode())
        response = broker.exchange(server)
    assert response.startswith(b"HTTP/1.1 502 ")
    assert b"Location:" not in response and b"https://" not in response
    assert broker.events[0]["syntheticUpstreamStatus"] == 307


@pytest.mark.skipif(os.environ.get("NEMA_NATIVE_GATEWAY_PROBE") != "1",
                    reason="explicit opt-in for native startup with synthetic gateway; no models")
def test_real_native_namespace_preserves_controls_and_falsifies_shared_relay_caller_identity():
    report = probe.run_probe()
    assert report["modelTurns"] == report["realUpstreamRequests"] == 0
    assert report["callerAuthenticationEstablished"] is False
    assert report["liveAdmission"] is False
    for first, case in report["cases"].items():
        assert case["account"] == {"account": None, "requiresOpenaiAuth": True}
        assert case["effectiveProviderId"] == "synthetic_gateway"
        assert case["effectiveProvider"]["requires_openai_auth"] is True
        assert case["effectiveProvider"]["base_url"].startswith("http://127.0.0.1:")
        assert case["nativeMethodsObserved"] == ["initialize", "account/read", "config/read", "thread/start", "mcpServerStatus/list"]
        assert case["startupBeforeInventory"] is True
        for name in ("outsideRead", "outsideWrite", "symlinkRead", "packetWrite",
                     "hostLoopback", "externalRoute", "parentRootRead"):
            assert "blockedErrno" in case["startup"][name], name
        assert case["startup"]["packetRead"] is True
        assert case["startup"]["nestedUserNamespaceRefused"] is True
        assert case["startup"]["packetRemountRefused"] is True
        assert int(case["startup"]["effectiveCapabilities"], 16) == 0
        for name in ("hostCanaryUnchanged", "packetUnchanged", "hostListenerUntouched",
                     "descendantHeartbeatChangedBeforeClose", "descendantHeartbeatStoppedAfterClose",
                     "sameRelayPeerForBothActorAttempts", "directUnixPeerDiffersFromRelay"):
            assert case[name] is True, name
        expected = {"unapprovedUrl": 403, "redirect": 502, "models": 200, "early": 403,
                    "wrongContent": 422, "oversizedBody": 413, "directUnixEarly": 403}
        assert {k: v["status"] for k, v in case["earlyRequests"].items()} == expected
        assert case["earlyRequests"]["redirect"]["location"] is None
        assert case["actors"][first]["attempt"]["status"] == 200
        second = "rival" if first == "intended" else "intended"
        assert case["actors"][second]["attempt"]["status"] == 409
        assert all(v["duplicate"]["status"] == 409 for v in case["actors"].values())
        assert case["syntheticResponsesAdmitted"] == 1
        assert case["requestsObserved"] <= probe.MAX_REQUESTS
