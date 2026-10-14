from __future__ import annotations

"""Destination-limited opaque CONNECT transport for a trusted native executable."""

from collections.abc import Callable, Mapping
import errno
import ipaddress
import json
import os
from pathlib import Path
import re
import selectors
import socket
import threading
import time
from typing import Any

from .native_managed_contract import (ISSUER_AUTHORITY, PROVIDER_AUTHORITY,
                                      ManagedLaunchError, ManagedPolicy)
from .resources.native_runtime import bridge

AUTHORITIES = frozenset({ISSUER_AUTHORITY, PROVIDER_AUTHORITY})


class Refused(ValueError):
    def __init__(self, status: int, reason: str, *, authority: str | None = None):
        self.status, self.reason = status, reason
        self.authority = authority
        super().__init__(reason)


def read_connect(
    connection: socket.socket, limits: ManagedPolicy, *,
    authorities: frozenset[str] = AUTHORITIES,
) -> dict[str, Any]:
    deadline = time.monotonic() + limits.header_seconds
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
        if authority not in authorities:
            raise Refused(403, "destination-refused", authority=authority)
        if headers.get("host") != authority:
            raise Refused(400, "host-mismatch")
        return {"method": method, "authority": authority, "headers": headers}
    except (UnicodeError, ValueError) as exc:
        if isinstance(exc, Refused):
            raise
        raise Refused(400, "malformed-header") from None


def checked_addresses(value: Any, maximum: int) -> tuple[tuple[int, str], ...]:
    if not isinstance(value, list) or not 0 < len(value) <= maximum:
        raise ManagedLaunchError("resolver returned an invalid address count")
    result = []
    for entry in value:
        if not isinstance(entry, list) or len(entry) != 2:
            raise ManagedLaunchError("resolver address shape differs")
        family, text = entry
        if type(family) is not int or not isinstance(text, str) or "%" in text:
            raise ManagedLaunchError("resolver address type differs")
        try: address = ipaddress.ip_address(text)
        except ValueError: raise ManagedLaunchError("resolver address invalid") from None
        if (not address.is_global or address.is_multicast
                or getattr(address, "ipv4_mapped", None) is not None
                or family != (socket.AF_INET if address.version == 4 else socket.AF_INET6)):
            raise ManagedLaunchError("resolver returned a nonpublic address")
        pair = (family, str(address))
        if pair in result: raise ManagedLaunchError("resolver returned duplicate address")
        result.append(pair)
    return tuple(result)


class ConnectBroker:
    """Finite opaque transport; phases do not authenticate logical RPC callers."""

    def __init__(self, policy: ManagedPolicy, *, created: float, on_failure: Callable[[str], None],
                 dialer: Callable | None = None):
        self.policy, self.created, self.on_failure = policy, created, on_failure
        self._dialer = dialer or self._dial
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._phase = "prepared"
        self._generation = 0
        self._turn_started = None
        self._addresses = {}
        self._sockets: dict[socket.socket, str | None] = {}
        self._workers: list[threading.Thread] = []
        self._server = None
        self._listener = None
        self._active = 0
        self._attempts = self._received = self._peak = 0
        self._events: list[dict] = []
        self._failure = None

    def start(self, path: Path, addresses: Mapping[str, tuple]) -> None:
        if set(addresses) != AUTHORITIES: raise ManagedLaunchError("fixed destinations required")
        with self._lock:
            if self._phase != "prepared" or self._stop.is_set():
                raise ManagedLaunchError("managed broker cannot be started again")
            self._addresses = {key: tuple(value) for key, value in addresses.items()}
            listener = socket.socket(socket.AF_UNIX)
            try:
                listener.bind(str(path)); os.chmod(path, 0o600)
                listener.listen(self.policy.max_active); listener.settimeout(.05)
            except BaseException:
                listener.close(); raise
            self._listener = listener
            self._phase = "issuer-only"
            self._server = threading.Thread(target=self._serve, name="nema-managed-connect")
            self._server.start()

    def activate_provider(self) -> None:
        with self._lock:
            if self._phase != "issuer-only" or self._stop.is_set():
                raise ManagedLaunchError("issuer closure cannot be repeated or reversed")
            self._phase = "closing-issuer"
            self._generation += 1
            generation = self._generation
            closing = tuple(self._sockets)
            workers = tuple(self._workers)
            self._shutdown(closing)
        # Reclaim actual worker/concurrency reservations before exposing the
        # provider phase; otherwise old stopped issuer streams can exhaust both
        # slots and spuriously reject the first provider connection.
        deadline = min(self._phase_deadline(), time.monotonic()+1)
        for worker in workers:
            worker.join(timeout=max(0, deadline-time.monotonic()))
        with self._lock:
            if (self._phase != "closing-issuer" or self._generation != generation or self._stop.is_set()
                    or self._active or any(worker.is_alive() for worker in workers)
                    or time.monotonic() >= min(self.created+self.policy.preparation_seconds,
                                              self.created+self.policy.lifetime_seconds)):
                raise ManagedLaunchError("issuer workers did not close before provider readiness")
            self._phase = "provider-only"
            self._turn_started = time.monotonic()

    def _phase_deadline(self) -> float:
        if self._phase == "provider-only" and self._turn_started is not None:
            return min(self.created+self.policy.lifetime_seconds, self._turn_started+self.policy.turn_seconds)
        return min(self.created+self.policy.lifetime_seconds, self.created+self.policy.preparation_seconds)

    def _allowed(self, authority: str, generation: int | None = None) -> bool:
        return (not self._stop.is_set() and (generation is None or generation == self._generation)
                and authority == (ISSUER_AUTHORITY if self._phase == "issuer-only"
                                  else PROVIDER_AUTHORITY if self._phase == "provider-only" else None))

    def _fail(self, reason: str) -> None:
        with self._lock:
            if self._failure is not None or self._phase == "closed": return
            self._failure = reason
            self._stop.set()
            sockets = tuple(self._sockets)
        self._shutdown(sockets)
        self.on_failure(reason)  # Always outside the broker lock.

    def _serve(self):
        while not self._stop.is_set():
            with self._lock: deadline = self._phase_deadline()
            if time.monotonic() >= deadline:
                self._fail("phase-deadline"); break
            try: client, _ = self._listener.accept()
            except TimeoutError: continue
            except OSError: break
            with self._lock:
                self._attempts += 1
                refused = (self._attempts > self.policy.max_connections or self._active >= self.policy.max_active
                           or self._stop.is_set())
                if not refused:
                    self._active += 1
                    self._peak = max(self._peak, self._active)
                    self._sockets[client] = None
                    worker = threading.Thread(target=self._handle, args=(client, self._generation), name="nema-managed-tunnel")
                    try:
                        worker.start()
                        self._workers.append(worker)
                    except RuntimeError:
                        self._active -= 1; self._sockets.pop(client, None)
                        refused = True
            if refused:
                client.close(); self._fail("connection-budget"); break

    def _handle(self, client, accepted_generation):
        upstream = None
        generation = None
        event = {"status": None, "outboundBytes": 0, "inboundBytes": 0, "maxPendingBytesPerDirection": 0}
        failure = None
        with self._lock: self._events.append(event)
        try:
            request = read_connect(client, self.policy)
            authority = request["authority"]
            event["authority"] = authority
            with self._lock:
                if not self._allowed(authority): raise Refused(403, "destination-closed", authority=authority)
                generation = self._generation
                self._sockets[client] = authority
                deadline = self._phase_deadline()
            def register(sock):
                with self._lock:
                    if not self._allowed(authority, generation):
                        sock.close(); raise Refused(403, "destination-closed", authority=authority)
                    self._sockets[sock] = authority
            def unregister(sock):
                with self._lock: self._sockets.pop(sock, None)
            # DNS has already finished in a killable process. TCP wait never
            # holds the lock needed by cancellation or phase closure.
            upstream = self._dialer(authority, self._addresses[authority],
                                   min(deadline, time.monotonic()+self.policy.dial_seconds),
                                   register, unregister)
            with self._lock:
                if not self._allowed(authority, generation): raise Refused(403, "destination-closed", authority=authority)
            client.settimeout(min(self.policy.header_seconds, max(.001, deadline-time.monotonic())))
            client.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            event["status"] = 200
            def receive(sock, count, outbound):
                field = "outboundBytes" if outbound else "inboundBytes"
                with self._lock:
                    if self._received > self.policy.max_received_bytes: return None
                    count = min(count, self.policy.max_received_bytes-self._received+1)
                    data = sock.recv(count)
                    self._received += len(data); event[field] += len(data)
                    if self._received > self.policy.max_received_bytes: return None
                    return data
            event["reason"], event["maxPendingBytesPerDirection"] = bridge(
                client, upstream, deadline=deadline, idle_seconds=self.policy.idle_seconds,
                buffer_bytes=self.policy.buffer_bytes, stopped=self._stop.is_set, receive=receive)
            if event["reason"] in {"aggregate-limit", "idle-limit", "lifetime-limit"}:
                failure = event["reason"]
        except Refused as exc:
            event.update(status=exc.status, reason=exc.reason)
            with self._lock:
                phase_cut = accepted_generation != self._generation
            failure = None if phase_cut else exc.reason
            try:
                client.settimeout(.1)
                client.sendall(f"HTTP/1.1 {exc.status} Refused\r\nContent-Length: 0\r\nConnection: close\r\n\r\n".encode())
            except OSError: pass
        except OSError as exc:
            event.update(reason="socket-error", errorType=type(exc).__name__)
            with self._lock:
                expected_close = self._stop.is_set() or accepted_generation != self._generation
            if not expected_close: failure = "socket-error"
        finally:
            with self._lock:
                self._active -= 1
                self._sockets.pop(client, None)
                if upstream is not None: self._sockets.pop(upstream, None)
            client.close()
            if upstream is not None: upstream.close()
            if failure: self._fail(failure)

    def _dial(self, authority, addresses, deadline, register, unregister):
        for family, address in addresses:
            if time.monotonic() >= deadline: break
            upstream = socket.socket(family, socket.SOCK_STREAM)
            register(upstream)
            try:
                upstream.setblocking(False)
                target = (address, 443) if family == socket.AF_INET else (address, 443, 0, 0)
                result = upstream.connect_ex(target)
                if result not in {0, errno.EINPROGRESS, errno.EWOULDBLOCK, errno.EALREADY}:
                    raise OSError(result, "fixed destination connect failed")
                with selectors.DefaultSelector() as selector:
                    selector.register(upstream, selectors.EVENT_WRITE)
                    while not self._stop.is_set() and time.monotonic() < deadline:
                        if selector.select(min(.05, max(0, deadline-time.monotonic()))):
                            error = upstream.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR)
                            if error: raise OSError(error, "fixed destination connect failed")
                            return upstream
                raise TimeoutError("fixed destination dial deadline")
            except OSError:
                unregister(upstream); upstream.close()
        raise Refused(502, "fixed-destination-unavailable", authority=authority)

    @staticmethod
    def _shutdown(sockets):
        for sock in sockets:
            try: sock.shutdown(socket.SHUT_RDWR)
            except OSError: pass

    def close(self) -> dict:
        self._stop.set()
        with self._lock:
            self._phase = "closed"; self._generation += 1
            sockets = tuple(self._sockets)
            listener = self._listener
            server = self._server
        self._shutdown(sockets)
        if listener is not None: listener.close()
        if server is not None and server is not threading.current_thread() and server.ident is not None:
            server.join(timeout=1)
        with self._lock: workers = tuple(self._workers)
        for worker in workers:
            if worker is not threading.current_thread() and worker.ident is not None: worker.join(timeout=1)
        return self.snapshot()

    def snapshot(self) -> dict:
        with self._lock:
            return {"phase": self._phase, "attempts": self._attempts, "active": self._active,
                    "peakActive": self._peak, "receivedBytes": self._received, "failure": self._failure,
                    "events": [dict(e) for e in self._events],
                    "workersJoined": all(not w.is_alive() for w in self._workers),
                    "serverJoined": self._server is None or not self._server.is_alive()}
