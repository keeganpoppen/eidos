"""Isolated stdlib helpers for one managed namespace; no account/model client."""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import selectors
import signal
import socket
import subprocess
import sys
import threading
import time


def bridge(left, right, *, deadline, idle_seconds, buffer_bytes, stopped,
           receive=None):
    """Bounded nonblocking forwarding. Optional receive owns shared accounting."""
    peers = {left: right, right: left}
    pending = {left: bytearray(), right: bytearray()}
    ended, shut = set(), set()
    progress = time.monotonic()
    peak = 0
    for sock in peers:
        sock.setblocking(False)
    with selectors.DefaultSelector() as selector:
        while not stopped():
            now = time.monotonic()
            if now >= deadline: return "lifetime-limit", peak
            if now - progress >= idle_seconds: return "idle-limit", peak
            if len(ended) == 2 and not any(pending.values()): return "eof", peak
            for sock, peer in peers.items():
                if sock in ended and not pending[peer] and peer not in shut:
                    peer.shutdown(socket.SHUT_WR)
                    shut.add(peer)
                mask = (selectors.EVENT_READ if sock not in ended and len(pending[peer]) < buffer_bytes else 0)
                if pending[sock]: mask |= selectors.EVENT_WRITE
                try: selector.unregister(sock)
                except KeyError: pass
                if mask: selector.register(sock, mask)
            wait = min(.05, deadline-now, idle_seconds-(now-progress))
            for key, mask in selector.select(max(0, wait)):
                sock, peer = key.fileobj, peers[key.fileobj]
                if mask & selectors.EVENT_WRITE:
                    try: sent = sock.send(pending[sock])
                    except BlockingIOError: sent = 0
                    if sent:
                        del pending[sock][:sent]
                        progress = time.monotonic()
                if mask & selectors.EVENT_READ:
                    count = buffer_bytes-len(pending[peer])
                    try:
                        data = receive(sock, count, sock is left) if receive else sock.recv(count)
                    except BlockingIOError:
                        continue
                    if data is None: return "aggregate-limit", peak
                    if data:
                        pending[peer].extend(data)
                        peak = max(peak, len(pending[peer]))
                        progress = time.monotonic()
                    else:
                        ended.add(sock)
        return "closed", peak


def resolve(host: str, maximum: int) -> None:
    # Parent kills this whole process if libc/NSS resolution does not return.
    if host not in {"auth.openai.com", "chatgpt.com"} or not 0 < maximum <= 64:
        raise ValueError("fixed resolver destination required")
    values = []
    for family, kind, protocol, _, address in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM):
        if family in (socket.AF_INET, socket.AF_INET6):
            item = [int(family), address[0]]
            if item not in values: values.append(item)
        if len(values) >= maximum: break
    print(json.dumps(values), flush=True)


def relay(settings: dict) -> None:
    """Two streams may coexist; there is no serial HTTP/WS assumption."""
    stop = threading.Event()
    lock = threading.Lock()
    sockets, workers = set(), []
    active = 0
    accepted = 0
    deadline = settings["deadline"]
    def shutdown(*_):
        stop.set()
        with lock: current = tuple(sockets)
        for sock in current:
            try: sock.shutdown(socket.SHUT_RDWR)
            except OSError: pass
    # A signal can interrupt this main thread while it already owns lock.
    # Only set the flag here; ordinary finally owns locking/socket shutdown.
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    def handle(client):
        nonlocal active
        upstream = socket.socket(socket.AF_UNIX)
        try:
            with lock: sockets.add(upstream)
            upstream.settimeout(min(1, max(.001, deadline-time.monotonic())))
            upstream.connect(settings["broker"])
            bridge(client, upstream, deadline=deadline, idle_seconds=settings["idle_seconds"],
                   buffer_bytes=settings["buffer_bytes"], stopped=stop.is_set)
        except OSError:
            pass
        finally:
            with lock:
                sockets.discard(upstream); sockets.discard(client); active -= 1
            upstream.close(); client.close()
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0)); listener.listen(settings["max_active"])
        listener.settimeout(.05)
        Path(settings["port_file"]).write_text(str(listener.getsockname()[1]))
        try:
            while not stop.is_set() and time.monotonic() < deadline:
                try: client, _ = listener.accept()
                except TimeoutError: continue
                with lock:
                    accepted += 1
                    if accepted > settings["max_connections"]:
                        client.close(); stop.set(); break
                    if active >= settings["max_active"]:
                        client.close()
                        continue
                    active += 1; sockets.add(client)
                    worker = threading.Thread(target=handle, args=(client,))
                    try:
                        worker.start(); workers.append(worker)
                    except RuntimeError:
                        active -= 1; sockets.discard(client); client.close(); stop.set()
        finally:
            shutdown()
            for worker in workers: worker.join(timeout=2)
            if any(worker.is_alive() for worker in workers): raise RuntimeError("relay workers did not join")


def launch(settings: dict) -> None:
    runner = str(Path(__file__).resolve())
    child = subprocess.Popen(["/usr/bin/python3", "-I", "-S", runner, "relay", sys.argv[2]],
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, close_fds=True)
    port_file = Path(settings["port_file"])
    try:
        stop = min(settings["deadline"], time.monotonic()+2)
        while not port_file.exists():
            if child.poll() is not None or time.monotonic() >= stop:
                raise RuntimeError("managed relay failed to start")
            time.sleep(.01)
        port = int(port_file.read_text())
        if not 0 < port < 65536: raise RuntimeError("managed relay port invalid")
        os.environ["HTTPS_PROXY"] = f"http://127.0.0.1:{port}"
        seconds = math.ceil(settings["deadline"]-time.monotonic())
        if seconds <= 0: raise RuntimeError("managed lifetime expired before exec")
        os.execv("/assets/native_guard", ["/assets/native_guard", str(seconds),
                 "/state/policy.json", "/assets/codex", "app-server", "--listen", "stdio://", "--strict-config"])
    finally:
        child.terminate()
        try: child.wait(timeout=2)
        except subprocess.TimeoutExpired:
            child.kill(); child.wait(timeout=2)


if __name__ == "__main__":
    if len(sys.argv) != 3: raise SystemExit(2)
    if sys.argv[1] == "resolve":
        options = json.loads(sys.argv[2]); resolve(options["host"], options["maximum"])
    elif sys.argv[1] in {"launch", "relay"}:
        options = json.loads(Path(sys.argv[2]).read_text())
        (launch if sys.argv[1] == "launch" else relay)(options)
    else: raise SystemExit(2)
