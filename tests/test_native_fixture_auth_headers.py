"""Exact synthetic header matching only; no native, credentials or auth service."""

import hashlib
import importlib.util
import json
from pathlib import Path
import socket
import time

import pytest


spec = importlib.util.spec_from_file_location(
    "fixture_auth_headers_probe", Path(__file__).parents[1] / "scripts/probe_native_synthetic_turn.py",
)
assert spec and spec.loader
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)

SYNTHETIC_AUTH = "Bearer authored-fixture-only-alpha"
ALLOWED = frozenset({SYNTHETIC_AUTH})
BODY = '{ "futureFixtureField": {"retained": [true, "α", 17]}, "input": [] }\n'.encode()


def _request(body=BODY, *, authorization=SYNTHETIC_AUTH, extra=b"", length=None):
    headers = (
        f"POST /fixture-only HTTP/1.1\r\nHost: fixture.invalid\r\n"
        f"Content-Length: {len(body) if length is None else length}\r\n"
    ).encode()
    if authorization is not None:
        headers += f"Authorization: {authorization}\r\n".encode()
    return headers + extra + b"\r\n" + body


def _read(message, *, allowed=None, finish=True, seconds=.2):
    server, client = socket.socketpair()
    try:
        client.sendall(message)
        if finish:
            client.shutdown(socket.SHUT_WR)
        kwargs = {} if allowed is None else {"allowed_authorizations": allowed}
        return probe.read_fixture_http_request(server, time.monotonic() + seconds, **kwargs)
    finally:
        server.close()
        client.close()


def test_default_refuses_even_the_value_used_by_an_explicit_synthetic_allowlist():
    with pytest.raises(probe.FixtureHttpError) as refused:
        _read(_request())
    assert (refused.value.status, refused.value.reason) == (400, "unsupported-header")
    assert refused.value.record["headers"]["authorization"] == SYNTHETIC_AUTH
    with pytest.raises(probe.FixtureHttpError):
        _read(_request(), allowed=frozenset())


@pytest.mark.parametrize("authorization", [SYNTHETIC_AUTH, f" \t{SYNTHETIC_AUTH}\t "])
def test_exact_explicit_value_preserves_body_unknown_fields_and_digest(authorization):
    message = _request(authorization=authorization, extra=b"X-Future-Fixture: untouched\r\n")
    message = message.replace(b"Authorization:", b"aUtHoRiZaTiOn:")
    result = _read(message, allowed=ALLOWED)
    assert result["headers"]["authorization"] == SYNTHETIC_AUTH
    assert result["headers"]["x-future-fixture"] == "untouched"
    assert result["bodyRaw"].encode() == BODY
    assert result["bodySha256"] == hashlib.sha256(BODY).hexdigest()
    assert json.loads(result["bodyRaw"])["futureFixtureField"] == {"retained": [True, "α", 17]}


def test_allowlist_does_not_require_header_presence_or_admit_default_broker():
    result = _read(_request(authorization=None), allowed=ALLOWED)
    assert "authorization" not in result["headers"]
    assert result["bodyRaw"].encode() == BODY
    # Provider fixtures must separately require their expected header. A prior
    # opt-in parser call cannot relax another broker's default-deny behavior.
    server, client = socket.socketpair()
    try:
        client.sendall(_request())
        client.shutdown(socket.SHUT_WR)
        broker = probe.FixtureBroker("Authored local prompt")
        broker.admit()
        response = broker.exchange(server)
        assert response.startswith(b"HTTP/1.1 400 ")
        assert broker.events[-1]["reason"] == "unsupported-header"
        assert not broker.consumed
    finally:
        server.close()
        client.close()


@pytest.mark.parametrize("authorization", [
    "", "bearer authored-fixture-only-alpha", "Bearer Authored-fixture-only-alpha",
    "Bearer  authored-fixture-only-alpha", "Bearer\tauthored-fixture-only-alpha",
    "Bearer authored-fixture-only-alpha-suffix", "prefix-Bearer authored-fixture-only-alpha",
    "Bearer authored-fixture-only-beta", "Basic authored-fixture-only-alpha",
])
def test_near_matches_are_refused_before_body_admission(authorization):
    with pytest.raises(probe.FixtureHttpError) as refused:
        _read(_request(authorization=authorization), allowed=ALLOWED)
    assert (refused.value.status, refused.value.reason) == (400, "unsupported-header")
    assert "bodyRaw" not in refused.value.record


@pytest.mark.parametrize("extra,reason", [
    (f"Authorization: {SYNTHETIC_AUTH}\r\n".encode(), "malformed"),
    (b"authorization: Bearer authored-fixture-only-beta\r\n", "malformed"),
    (f"Content-Length: {len(BODY)}\r\n".encode(), "malformed"),
    (b"content-length: 0\r\n", "malformed"),
    (b"Transfer-Encoding: chunked\r\n", "unsupported-header"),
    (b"Transfer-Encoding: identity\r\n", "unsupported-header"),
    (b"Content-Encoding: gzip\r\n", "unsupported-header"),
    (b"Content-Encoding: identity\r\n", "unsupported-header"),
])
def test_allowed_auth_does_not_relax_duplicate_or_encoding_rejection(extra, reason):
    with pytest.raises(probe.FixtureHttpError) as refused:
        _read(_request(extra=extra), allowed=ALLOWED)
    assert (refused.value.status, refused.value.reason) == (400, reason)
    assert "bodyRaw" not in refused.value.record


@pytest.mark.parametrize("message,status,reason", [
    (_request()[:-1], 400, "malformed"),
    (_request() + b"trailing", 400, "malformed"),
    (_request().replace(b"HTTP/1.1", b"HTTP/1.0"), 400, "malformed"),
    (_request(body=b"\xff"), 400, "malformed"),
    (_request(body=b"", length="unknown"), 400, "malformed"),
    (_request(body=b"", length=-1), 413, "body-limit"),
    (_request(body=b"", length=probe.MAX_BODY + 1), 413, "body-limit"),
    (_request(extra=b"X-Large: " + b"x" * probe.MAX_HEADER + b"\r\n"), 413, "header-limit"),
])
def test_allowed_auth_keeps_framing_and_size_bounds(message, status, reason):
    with pytest.raises(probe.FixtureHttpError) as refused:
        _read(message, allowed=ALLOWED)
    assert (refused.value.status, refused.value.reason) == (status, reason)


def test_exact_body_limit_is_preserved_and_incomplete_authorized_body_times_out():
    body = b"x" * probe.MAX_BODY
    result = _read(_request(body=body), allowed=ALLOWED)
    assert result["bodyRaw"].encode() == body
    assert result["bodySha256"] == hashlib.sha256(body).hexdigest()
    with pytest.raises(probe.FixtureHttpError) as refused:
        _read(_request(body=b"", length=1), allowed=ALLOWED, finish=False, seconds=.02)
    assert (refused.value.status, refused.value.reason) == (408, "deadline")
