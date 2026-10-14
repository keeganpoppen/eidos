from __future__ import annotations

"""One disposable Linux managed-native resource, not an agent/controller loop."""

from importlib import resources
import hashlib
import json
import os
from pathlib import Path
import platform
import selectors
import shutil
import stat
import subprocess
import tempfile
import threading
import time
from types import MappingProxyType

from .native_connect import AUTHORITIES, ConnectBroker, checked_addresses
from .native_managed_contract import (MANAGED_BINARY_SHA256, MANAGED_VERSION,
                                      ManagedLaunchError, ManagedPolicy)

PUBLIC_ROOTS = Path("/etc/ssl/certs/ca-certificates.crt")
BINARY_LIMIT = 256 * 1024 * 1024
ROOTS_LIMIT = 2 * 1024 * 1024
CATALOG_LIMIT = 600000


class ContainedRuntime:
    def __init__(self, cwd, *, config_toml, catalog_bytes, policy, binary="codex", cancelled=None):
        if not isinstance(policy, ManagedPolicy): raise ValueError("managed policy required")
        self.policy = policy
        self.created = time.monotonic()
        self._cancelled = cancelled if cancelled is not None else threading.Event()
        self._lock = threading.Lock()
        self._closing = False
        self._closed = threading.Event()
        self._stop = threading.Event()
        self._startup = False
        self._turn_started = None
        self._abort_callback = None
        self._processes = set()
        self._watcher = None
        self._cleanup = None
        self._report = None
        self._root = None
        self._broker = ConnectBroker(policy, created=self.created, on_failure=self._abort)
        self.command = ()
        self.env = MappingProxyType({})
        self._evidence = {}
        try:
            self._check()
            if platform.system() != "Linux" or platform.machine() != "aarch64":
                raise ManagedLaunchError("managed containment requires reviewed Linux/aarch64")
            self.cwd = Path(cwd)
            if (self.cwd.parent != Path("/tmp") or not self.cwd.name.startswith("nema-investigation-")
                    or self.cwd.is_symlink() or not self.cwd.is_dir()):
                raise ManagedLaunchError("managed worker cwd must be its fresh temporary directory")
            if (not isinstance(config_toml, str) or len(config_toml.encode()) > 65536
                    or not isinstance(catalog_bytes, bytes) or len(catalog_bytes) > CATALOG_LIMIT):
                raise ManagedLaunchError("managed startup asset exceeds limit")
            for executable in ("/usr/bin/bwrap", "/usr/bin/python3", "/usr/bin/cc"):
                if not os.access(executable, os.X_OK):
                    raise ManagedLaunchError("required managed runtime dependency unavailable")
            source_binary = shutil.which(binary, path="/usr/bin:/bin")
            if source_binary is None: raise ManagedLaunchError("reviewed native executable unavailable")
            self._root = Path(tempfile.mkdtemp(prefix="nema-managed-"))
            assets, state = self._root/"assets", self._root/"state"
            assets.mkdir(mode=0o700); state.mkdir(mode=0o700)
            for directory in (state/"home", state/"codex", state/"workspace"):
                directory.mkdir(mode=0o700)
            binary_hash = self._copy(Path(source_binary), assets/"codex", BINARY_LIMIT, executable=True)
            if binary_hash != MANAGED_BINARY_SHA256:
                raise ManagedLaunchError("native executable hash differs from reviewed version")
            roots_hash = self._copy(PUBLIC_ROOTS, assets/"public-roots.pem", ROOTS_LIMIT)
            if b"-----BEGIN CERTIFICATE-----" not in (assets/"public-roots.pem").read_bytes():
                raise ManagedLaunchError("public system certificate roots unavailable")
            bundle = resources.files("eidos").joinpath("resources")
            guard_bytes = bundle.joinpath("native_guard.c").read_bytes()
            runtime_bytes = bundle.joinpath("native_runtime.py").read_bytes()
            for name, data in (("native_guard.c", guard_bytes), ("native_runtime.py", runtime_bytes),
                               ("config.toml", config_toml.encode()), ("models.json", catalog_bytes)):
                self._check(); (assets/name).write_bytes(data); (assets/name).chmod(0o400)
            self._run(["/usr/bin/cc", "-O2", "-Wall", "-Wextra", "-Werror", "-pthread",
                       str(assets/"native_guard.c"), "-o", str(assets/"native_guard")], seconds=20)
            (assets/"native_guard").chmod(0o500)
            settings = {"deadline": self.created+policy.lifetime_seconds,
                        "broker": "/gateway/broker.sock", "port_file": "/state/relay-port",
                        "idle_seconds": policy.idle_seconds, "buffer_bytes": policy.buffer_bytes,
                        "max_active": policy.max_active, "max_connections": policy.max_connections}
            (assets/"launch.json").write_text(json.dumps(settings))
            (assets/"launch.json").chmod(0o400)
            self.command = self._namespace_command()
            hashes = {name: hashlib.sha256((assets/name).read_bytes()).hexdigest()
                      for name in ("native_guard", "native_guard.c", "native_runtime.py", "config.toml", "models.json", "launch.json")}
            hashes.update({"codex": binary_hash, "public-roots.pem": roots_hash})
            self._asset_hashes = hashes
            self._evidence = {"version": MANAGED_VERSION, "binarySha256": binary_hash,
                "transport": "fixed-live-destinations", "classification": "native-observed",
                "platform": {"system": "Linux", "machine": "aarch64"},
                "configSha256": hashes["config.toml"], "catalogSha256": hashes["models.json"],
                "guardSourceSha256": hashes["native_guard.c"], "guardBinarySha256": hashes["native_guard"],
                "runtimeSourceSha256": hashes["native_runtime.py"], "publicRootsSha256": roots_hash,
                "limits": policy.as_dict(), "destinations": sorted(AUTHORITIES),
                "observation": {"tls": "opaque", "providerRequestBodies": False,
                                "cpuRssDiskQuota": False, "runtimeMount": "/usr read-only",
                                "cwd": "spelling only in empty namespace tmpfs"}}
            self._check()
            self._watcher = threading.Thread(target=self._watch, name="nema-managed-lifetime")
            self._watcher.start()
        except BaseException:
            self.close("setup-failed")
            raise

    @property
    def evidence(self):
        return json.loads(json.dumps(self._evidence))

    def _check(self):
        if self._cancelled.is_set() or self._stop.is_set():
            raise ManagedLaunchError("managed resource cancelled or closed")
        if time.monotonic() >= self.created+self.policy.preparation_seconds and self._turn_started is None:
            raise ManagedLaunchError("managed preparation deadline expired")
        if time.monotonic() >= self.created+self.policy.lifetime_seconds:
            raise ManagedLaunchError("managed resource lifetime expired")

    def _copy(self, source, target, maximum, *, executable=False):
        digest = hashlib.sha256()
        count = 0
        with source.open("rb") as reader, target.open("xb") as writer:
            if not stat.S_ISREG(os.fstat(reader.fileno()).st_mode):
                raise ManagedLaunchError("managed asset is not a regular file")
            while True:
                self._check()
                chunk = reader.read(min(1024*1024, maximum-count+1))
                if not chunk: break
                count += len(chunk)
                if count > maximum: raise ManagedLaunchError("managed asset exceeds snapshot limit")
                digest.update(chunk); writer.write(chunk)
        target.chmod(0o500 if executable else 0o400)
        return digest.hexdigest()

    def _run(self, command, *, seconds):
        """Cancellable process, capped combined output; no resolver thread survives."""
        self._check()
        deadline = min(self.created+self.policy.preparation_seconds, time.monotonic()+seconds)
        with self._lock:
            self._check()
            child = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE, env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"},
                                     close_fds=True, start_new_session=True)
            self._processes.add(child)
        output = {child.stdout: bytearray(), child.stderr: bytearray()}
        try:
            with selectors.DefaultSelector() as selector:
                for stream in output:
                    os.set_blocking(stream.fileno(), False)
                    selector.register(stream, selectors.EVENT_READ)
                while selector.get_map():
                    self._check()
                    if time.monotonic() >= deadline: raise ManagedLaunchError("managed setup subprocess deadline")
                    for key, _ in selector.select(.05):
                        current = sum(len(data) for data in output.values())
                        data = os.read(key.fd, min(8192, 65537-current))
                        if not data: selector.unregister(key.fileobj)
                        else:
                            output[key.fileobj].extend(data)
                            if current+len(data) > 65536: raise ManagedLaunchError("managed setup subprocess output limit")
                # Both pipes can close before process exit, including during
                # construction before the lifetime watcher has been started.
                while child.poll() is None:
                    self._check()
                    remaining = deadline-time.monotonic()
                    if remaining <= 0: raise ManagedLaunchError("managed setup subprocess deadline")
                    self._cancelled.wait(min(.05, remaining))
                self._check()
                status = child.returncode
                if status: raise ManagedLaunchError("managed setup subprocess failed")
                return bytes(output[child.stdout])
        finally:
            self._terminate(child)
            for stream in output: stream.close()
            with self._lock: self._processes.discard(child)

    @staticmethod
    def _terminate(child):
        # Compiler drivers may exit before descendants close inherited pipes.
        # Every setup process starts a separate session owned by this operation.
        import signal
        try: os.killpg(child.pid, signal.SIGKILL)
        except ProcessLookupError: pass
        try: child.wait(timeout=1)
        except subprocess.TimeoutExpired: pass

    def _namespace_command(self):
        assets, state = self._root/"assets", self._root/"state"
        return ("/usr/bin/bwrap", "--unshare-all", "--unshare-user", "--disable-userns",
                "--die-with-parent", "--new-session", "--cap-drop", "ALL",
                "--ro-bind", "/usr", "/usr", "--symlink", "usr/bin", "/bin", "--symlink", "usr/lib", "/lib",
                "--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp", "--dir", str(self.cwd),
                "--bind", str(state), "/state", "--ro-bind", str(assets), "/assets",
                "--ro-bind", str(assets/"config.toml"), "/state/codex/config.toml",
                "--ro-bind", str(assets/"public-roots.pem"), "/etc/ssl/certs/ca-certificates.crt",
                "--ro-bind", str(self._root/"broker.sock"), "/gateway/broker.sock",
                "--clearenv", "--setenv", "HOME", "/state/home", "--setenv", "CODEX_HOME", "/state/codex",
                "--setenv", "PATH", "/usr/bin:/bin", "--setenv", "LANG", "C.UTF-8", "--chdir", str(self.cwd),
                "--", "/usr/bin/python3", "-I", "-S", "/assets/native_runtime.py", "launch", "/assets/launch.json")

    def require_contained_startup(self):
        try:
            with self._lock:
                self._check()
                if self._startup: raise ManagedLaunchError("managed startup already consumed")
                self._startup = True
            assets = self._root/"assets"
            for name, expected in self._asset_hashes.items():
                self._check()
                digest = hashlib.sha256()
                maximum = BINARY_LIMIT if name == "codex" else ROOTS_LIMIT
                count = 0
                with (assets/name).open("rb") as source:
                    while True:
                        self._check()
                        data = source.read(min(1024*1024, maximum-count+1))
                        if not data: break
                        count += len(data)
                        if count > maximum: raise ManagedLaunchError("managed startup asset exceeds size cap")
                        digest.update(data)
                if digest.hexdigest() != expected:
                    raise ManagedLaunchError("managed startup asset changed")
            addresses = {}
            for authority in sorted(AUTHORITIES):
                payload = self._run(["/usr/bin/python3", "-I", "-S", str(assets/"native_runtime.py"), "resolve",
                                     json.dumps({"host": authority.split(":")[0], "maximum": self.policy.max_resolved_addresses})],
                                    seconds=self.policy.resolve_seconds)
                addresses[authority] = checked_addresses(json.loads(payload), self.policy.max_resolved_addresses)
            self._check()
            self._broker.start(self._root/"broker.sock", addresses)
        except BaseException:
            # The caller may own AppServerClient's startup lock. A concurrent
            # closer can be waiting for that lock inside the abort callback;
            # do not wait for its completion before unwinding this guard.
            self._close("startup-failed", wait=False)
            raise

    def activate_provider(self):
        try:
            self._check()
            with self._lock:
                if not self._startup or self._turn_started is not None:
                    raise ManagedLaunchError("managed provider phase cannot be reused")
                self._broker.activate_provider()
                self._turn_started = time.monotonic()
        except BaseException:
            self.close("activation-failed")
            raise

    def remaining_preparation(self):
        self._check()
        remaining = min(self.created+self.policy.preparation_seconds, self.created+self.policy.lifetime_seconds)-time.monotonic()
        if remaining <= 0: raise ManagedLaunchError("managed preparation deadline expired")
        return remaining

    def remaining_turn(self):
        self._check()
        if self._turn_started is None: raise ManagedLaunchError("managed provider phase not active")
        remaining = min(self._turn_started+self.policy.turn_seconds, self.created+self.policy.lifetime_seconds)-time.monotonic()
        if remaining <= 0: raise ManagedLaunchError("managed turn deadline expired")
        return remaining

    def bind_abort(self, callback):
        if not callable(callback): raise TypeError("owned-client close callback required")
        with self._lock:
            if self._abort_callback is not None: raise ManagedLaunchError("managed abort callback already bound")
            self._abort_callback = callback
            closed = self._closing
        if closed: callback()

    def _abort(self, reason):
        # Broker calls this on its own worker: cleanup runs independently so
        # it can join that worker and never calls client.close under a lock.
        self._stop.set()
        self._failure_reason = reason

    def _watch(self):
        while not self._closed.is_set():
            deadline = self.created+self.policy.preparation_seconds if self._turn_started is None else self._turn_started+self.policy.turn_seconds
            if self._cancelled.is_set() or self._stop.is_set() or time.monotonic() >= min(deadline, self.created+self.policy.lifetime_seconds):
                with self._lock:
                    if self._closing: return
                    reason = getattr(self, "_failure_reason", "cancelled" if self._cancelled.is_set() else "deadline")
                    self._cleanup = threading.Thread(target=self.close, args=(reason,), name="nema-managed-cleanup")
                    self._cleanup.start()
                return
            self._closed.wait(.05)

    def close(self, reason="closed", *, wait=True):
        return self._close(reason, wait=wait)

    def _close(self, reason, *, wait):
        with self._lock:
            first = not self._closing
            self._closing = True
            self._stop.set()
            callback = self._abort_callback
            processes = tuple(self._processes)
        if not first:
            if wait: self._closed.wait(6)
            if wait and self._cleanup is not None and self._cleanup is not threading.current_thread():
                self._cleanup.join(timeout=1)
            return dict(self._report or {"closed": False, "reason": "cleanup-in-progress"})
        errors = []
        try: broker_report = self._broker.close()
        except Exception as exc:
            errors.append("broker-close:"+type(exc).__name__)
            broker_report = {"workersJoined": False, "serverJoined": False}
        for child in processes:
            try: self._terminate(child)
            except Exception as exc: errors.append("setup-process-close:"+type(exc).__name__)
        if callback is not None:
            try: callback()
            except Exception as exc: errors.append("owned-client-close:"+type(exc).__name__)
        if self._watcher is not None and self._watcher is not threading.current_thread():
            self._watcher.join(timeout=1)
            if self._watcher.is_alive(): errors.append("lifetime-worker-not-joined")
        if not broker_report["workersJoined"] or not broker_report["serverJoined"]:
            errors.append("broker-workers-not-joined")
        if not errors and self._root is not None:
            try: shutil.rmtree(self._root)
            except OSError as exc: errors.append("state-removal:"+type(exc).__name__)
        self._report = {"closed": not errors, "reason": reason, "errors": errors,
                        "allWorkersJoined": not errors and all(p.poll() is not None for p in processes),
                        "broker": broker_report, "setupProcessesJoined": all(p.poll() is not None for p in processes),
                        "stateRemoved": self._root is None or not self._root.exists()}
        self._closed.set()
        if self._cleanup is not None and self._cleanup is not threading.current_thread():
            self._cleanup.join(timeout=1)
        return dict(self._report)
