from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import sys
import threading
import time
import tomllib
import uuid
from typing import Any, Callable, Mapping, Sequence

from .trace import TraceStore


class AppServerRPCError(RuntimeError):
    def __init__(self, error: Any) -> None:
        super().__init__(f"Codex app-server RPC error: {error!r}")
        self.error = error


class AppServerClosed(RuntimeError):
    pass


class NativeExecutionProfileError(RuntimeError):
    """Configuration cannot be admitted before an owned native process starts."""


def _profile_fingerprint(path: Path) -> str:
    """Include absence and directory entries, without reading auth or history."""
    if any(parent.is_symlink() for parent in (path, *path.parents)):
        raise NativeExecutionProfileError("native profile source is a symlink")
    if not path.exists():
        return "absent"
    if path.is_dir():
        payload = json.dumps(sorted(child.name for child in path.iterdir())).encode()
        return "directory:" + hashlib.sha256(payload).hexdigest()
    if not path.is_file():
        raise NativeExecutionProfileError("native profile source is not a regular file")
    if path.suffix in {".toml", ".json"} and path.stat().st_size > 1_048_576:
        raise NativeExecutionProfileError("native config source exceeds the admission size limit")
    return "file:" + hashlib.sha256(path.read_bytes()).hexdigest()


@dataclass(frozen=True)
class NativeLaunch:
    command: tuple[str, ...]
    env: Mapping[str, str]
    evidence: Mapping[str, Any]
    _sources: tuple[tuple[Path, str], ...]

    @property
    def live_admitted(self) -> bool:
        # This version intentionally has no opt-out for unresolved cloud policy.
        return False

    def check_unchanged(self) -> None:
        """Detect intervening edits; not an atomic filesystem/config snapshot."""
        for path, expected in self._sources:
            if _profile_fingerprint(path) != expected:
                raise NativeExecutionProfileError("native profile changed after admission; launch refused")

    def require_live_admission(self) -> None:
        self.check_unchanged()
        if not self.live_admitted:
            raise NativeExecutionProfileError(
                "account-backed cloud configuration may refresh during native startup; "
                "no complete pre-launch admission is established"
            )


class NativeExecutionProfile:
    """Versioned, conservative local configuration admission for Codex 0.154.0.

    This constrains enumerated local startup sources before Popen. It is not an
    OS boundary, a complete model context manifest, or attestation of remotely
    refreshed cloud defaults. Existing subscription authentication stays in its
    original location; this code never reads or copies credential files.
    """

    VERSION = "nema-native-profile/1"
    BINARY_SHA256 = "9b7c1c7abdc26fc3c4f47c77656a8e9121def5483dbae830ef1ee561758448a9"
    DISABLED_FEATURES = (
        "apps", "plugins", "remote_plugin", "hooks", "shell_tool", "shell_snapshot",
        "multi_agent", "multi_agent_v2", "memories", "goals", "browser_use",
        "browser_use_external", "computer_use", "in_app_browser", "in_app_local_automation",
        "code_mode", "code_mode_host", "code_mode_prewarm", "skill_mcp_dependency_install",
        "skill_search", "workspace_dependencies", "image_generation", "sleep_tool",
    )
    # Deliberately narrow. Unknown settings are not copied into a new home or
    # presumed inert merely because a native parser accepts them.
    ADMITTED_KEYS = frozenset({
        "model", "model_provider", "model_reasoning_effort", "model_reasoning_summary",
        "model_verbosity", "personality", "service_tier", "approval_policy", "sandbox_mode",
        "web_search", "features", "mcp_servers", "projects", "cli_auth_credentials_store",
        "forced_login_method", "forced_chatgpt_workspace_id", "history", "tui", "hide_agent_reasoning",
        "show_raw_agent_reasoning", "suppress_unstable_features_warning", "check_for_update_on_startup",
        "analytics", "feedback", "notice", "windows_wsl_setup_acknowledged",
    })

    def __init__(
        self,
        codex_binary: str = "codex",
        *,
        env: Mapping[str, str] | None = None,
        system_root: str | Path = "/etc/codex",
        expected_binary_sha256: str = BINARY_SHA256,
    ) -> None:
        self.codex_binary = codex_binary
        self._ambient_env = dict(os.environ if env is None else env)
        self.system_root = Path(system_root)
        self.expected_binary_sha256 = expected_binary_sha256

    @staticmethod
    def check_account(response: Mapping[str, Any]) -> None:
        account = response.get("account")
        if (
            not isinstance(account, dict)
            or account.get("type") != "chatgpt"
            or response.get("requiresOpenaiAuth") is not True
        ):
            raise NativeExecutionProfileError("native specialist requires existing ChatGPT subscription authentication")

    def prepare(self, cwd: str | Path) -> NativeLaunch:
        if sys.platform != "linux":
            raise NativeExecutionProfileError("native execution profile is verified only for Linux")
        directory = Path(cwd).absolute()
        if not directory.is_dir() or directory.is_symlink():
            raise NativeExecutionProfileError("native profile requires an existing nonsymlink working directory")
        raw_home = self._ambient_env.get("HOME")
        if not raw_home or not Path(raw_home).is_absolute():
            raise NativeExecutionProfileError("native profile requires an explicit absolute HOME")
        home = Path(raw_home)
        codex_home = Path(self._ambient_env.get("CODEX_HOME", str(home / ".codex")))
        if not codex_home.is_absolute():
            raise NativeExecutionProfileError("native profile requires an absolute CODEX_HOME")
        executable = shutil.which(self.codex_binary, path=self._ambient_env.get("PATH", "/usr/bin:/bin"))
        if executable is None:
            raise NativeExecutionProfileError("native executable is unavailable")
        binary = Path(executable).resolve()
        if hashlib.sha256(binary.read_bytes()).hexdigest() != self.expected_binary_sha256:
            raise NativeExecutionProfileError("native binary has no reviewed execution profile")

        configs = [self.system_root / "config.toml", codex_home / "config.toml"]
        # Include all ancestors, even sources native trust/project discovery
        # currently skips. A temporary cwd does not remove ancestor config.
        configs.extend(parent / ".codex" / "config.toml" for parent in (directory, *directory.parents))
        forbidden = [
            self.system_root / "managed_config.toml", self.system_root / "requirements.toml",
            codex_home / "managed_config.toml", codex_home / "requirements.toml",
            codex_home / "cloud-config-bundle-cache.json",
        ]
        sources: dict[Path, str] = {}
        roles: dict[Path, str] = {}
        for path in [binary, *configs, *forbidden]:
            sources[path] = _profile_fingerprint(path)
            roles[path] = (
                "binary" if path == binary else
                "managed-source" if path in forbidden else
                "system-config" if path == self.system_root / "config.toml" else
                "user-config" if path == codex_home / "config.toml" else "ancestor-config"
            )
            if path != binary:
                sources[path.parent] = _profile_fingerprint(path.parent)
                roles[path.parent] = "source-directory"
        # Reject parent symlinks too; this does not defeat concurrent replacement
        # after the final check and is intentionally not called isolation.
        for base in (directory, home, codex_home, self.system_root):
            if any(parent.is_symlink() for parent in (base, *base.parents)):
                raise NativeExecutionProfileError("native profile path traverses a symlink")
        for path in forbidden:
            if sources[path] != "absent":
                raise NativeExecutionProfileError("native managed/cloud configuration requires separate admission")

        mcp_names: set[str] = set()
        for path in dict.fromkeys(configs):
            if sources[path] == "absent":
                continue
            if not path.is_file() or path.stat().st_size > 1_048_576:
                raise NativeExecutionProfileError("native config source is not an admissible small file")
            try:
                raw = path.read_bytes()
                if "file:" + hashlib.sha256(raw).hexdigest() != sources[path]:
                    raise NativeExecutionProfileError("native config changed during admission")
                config = tomllib.loads(raw.decode("utf-8"))
            except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
                raise NativeExecutionProfileError("native config source could not be parsed") from exc
            if config.keys() - self.ADMITTED_KEYS:
                raise NativeExecutionProfileError("native configuration contains unreviewed settings")
            if config.get("model_provider", "openai") != "openai":
                raise NativeExecutionProfileError("native specialist refuses a custom or paid API provider")
            if config.get("forced_login_method", "chatgpt") != "chatgpt":
                raise NativeExecutionProfileError("native specialist refuses API authentication configuration")
            features = config.get("features", {})
            if not isinstance(features, dict) or any(
                name not in {*self.DISABLED_FEATURES, "skip_host_skill_discovery"}
                or not isinstance(value, bool) for name, value in features.items()
            ):
                raise NativeExecutionProfileError("native feature configuration requires review")
            servers = config.get("mcp_servers", {})
            if not isinstance(servers, dict) or any(not isinstance(value, dict) for value in servers.values()):
                raise NativeExecutionProfileError("native MCP declarations are malformed")
            # The native dotted override parser does not safely address every
            # arbitrary TOML key. Restrict identities to its tested bare keys.
            for name in servers:
                if not name or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for char in name):
                    raise NativeExecutionProfileError("native MCP identity cannot be safely overridden")
                mcp_names.add(name)

        overrides = [
            'model_provider="openai"', 'forced_login_method="chatgpt"',
            'approval_policy="never"', 'sandbox_mode="read-only"', 'web_search="disabled"',
            'analytics.enabled=false', 'feedback.enabled=false', 'check_for_update_on_startup=false',
        ]
        overrides.extend(f"features.{name}=false" for name in self.DISABLED_FEATURES)
        overrides.append("features.skip_host_skill_discovery=true")
        overrides.extend(f"mcp_servers.{name}.enabled=false" for name in sorted(mcp_names))
        command = (str(binary), "app-server", "--listen", "stdio://", "--strict-config",
                   *(part for override in overrides for part in ("-c", override)))
        env = {"HOME": str(home), "CODEX_HOME": str(codex_home), "PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"}
        # Do not forward API keys, provider endpoints, code-mode hosts, proxy
        # hooks, preload libraries, or ambient configuration selector variables.
        evidence = {
            "version": self.VERSION, "binarySha256": self.expected_binary_sha256,
            "completeIsolation": False, "localMcpStartupSuppression": True,
            "cloudConfiguration": "unverified-live-launch-refused",
            "liveAdmitted": False,
            "credentialHandling": "existing-location-no-read-no-copy",
            "disabledMcpCount": len(mcp_names),
            "sourceFingerprints": [
                {"role": roles[path], "pathId": hashlib.sha256(str(path).encode()).hexdigest(),
                 "fingerprint": fingerprint} for path, fingerprint in sources.items()
            ],
            "limitations": ["cloud-refresh", "filesystem-check-to-launch-race", "host-read-visibility",
                            "native-auth-and-state-writes", "provider-context", "descendant-processes"],
        }
        launch = NativeLaunch(command, env, evidence, tuple(sources.items()))
        launch.check_unchanged()
        return launch


class AppServerClient:
    """Minimal traced JSONL client for Codex app-server.

    The protocol is intentionally treated as native evidence. This client does
    not normalize unknown notifications away; every line is first appended to
    TraceStore and only then interpreted enough for RPC correlation.
    """

    def __init__(
        self,
        command: Sequence[str] = ("codex", "app-server", "--listen", "stdio://"),
        *,
        trace: TraceStore | None = None,
        cwd: str | Path | None = None,
        env: Mapping[str, str] | None = None,
        source: str = "codex-app-server",
        inherit_env: bool = True,
        launch_guard: Callable[[], None] | None = None,
    ) -> None:
        self.command = tuple(command)
        self.trace = trace
        self.cwd = str(cwd) if cwd is not None else None
        self.env = dict(env) if env is not None else None
        self.inherit_env = inherit_env
        self.launch_guard = launch_guard
        self.source = f"{source}/{uuid.uuid4().hex[:12]}"
        self.process: subprocess.Popen[str] | None = None
        self._next_id = 1
        self._lock = threading.Lock()
        self._write_lock = threading.Lock()
        self._lifecycle_lock = threading.RLock()
        # None is a transport-closure signal, never a fabricated native reply.
        self._pending: dict[str, queue.Queue[dict[str, Any] | None]] = {}
        self._events: queue.Queue[dict[str, Any] | None] = queue.Queue()
        self._backlog: deque[dict[str, Any]] = deque()
        self._stderr: deque[str] = deque(maxlen=200)
        self._reader: threading.Thread | None = None
        self._stderr_reader: threading.Thread | None = None
        self._closed = threading.Event()

    def start(self) -> "AppServerClient":
        with self._lifecycle_lock:
            if self._closed.is_set():
                raise AppServerClosed("app-server incarnation has been closed")
            return self._start()

    def _start(self) -> "AppServerClient":
        if self.process is not None:
            return self
        env = os.environ.copy() if self.inherit_env else {}
        if self.env is not None:
            env.update(self.env)
        if self.launch_guard is not None:
            self.launch_guard()
        self.process = subprocess.Popen(
            list(self.command),
            cwd=self.cwd,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )
        try:
            assert self.process.stdin is not None
            # Buffered writes can hold their stream lock indefinitely when a
            # child (or an inherited descendant pipe) stops reading. Never use
            # that writer: cancellation must not depend on the reader exiting.
            os.set_blocking(self.process.stdin.fileno(), False)
        except (OSError, ValueError, NotImplementedError) as exc:
            self.close()
            raise RuntimeError("app-server transport requires nonblocking pipe writes") from exc
        self._reader = threading.Thread(target=self._read_stdout, name="eidos-codex-stdout", daemon=True)
        self._stderr_reader = threading.Thread(target=self._read_stderr, name="eidos-codex-stderr", daemon=True)
        self._reader.start()
        self._stderr_reader.start()
        return self

    def close(self) -> None:
        with self._lifecycle_lock:
            # An incarnation is terminal even if closed before launch. A later
            # request must not restart a process with this source/RPC sequence.
            self._mark_closed()
            self._close()

    def _close(self) -> None:
        process = self.process
        if process is None:
            return
        # Cancel writers and terminate only our owned child. A descendant may
        # retain its pipes; neither cancellation nor stdin cleanup waits for it.
        if process.poll() is None:
            process.terminate()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=2)
        try:
            with self._write_lock:
                if process.stdin:
                    process.stdin.close()
        except (OSError, ValueError):
            pass
        for reader in (self._reader, self._stderr_reader):
            if reader is not None and reader is not threading.current_thread():
                reader.join(timeout=1)
        self.process = None

    def _mark_closed(self) -> None:
        with self._lock:
            if self._closed.is_set():
                return
            self._closed.set()
            for pending in self._pending.values():
                pending.put_nowait(None)
            self._pending.clear()
            # Wake event readers already blocked in get(), including callers
            # without a timeout. Events queued before EOF remain ahead of this.
            self._events.put(None)

    def __enter__(self) -> "AppServerClient":
        return self.start()

    def __exit__(self, *exc: object) -> None:
        self.close()

    @property
    def stderr_tail(self) -> list[str]:
        return list(self._stderr)

    def initialize(self, *, experimental_api: bool = True, timeout: float = 10.0) -> dict[str, Any]:
        result = self.request(
            "initialize",
            {
                "clientInfo": {"name": "eidos", "version": "0.1.0"},
                "capabilities": {"experimentalApi": experimental_api},
            },
            timeout=timeout,
        )
        self.notify("initialized")
        return result

    def request(self, method: str, params: Any = None, *, timeout: float = 30.0) -> dict[str, Any]:
        deadline = time.monotonic() + timeout
        self.start()
        with self._lock:
            if self._closed.is_set():
                raise AppServerClosed("app-server closed")
            request_id = self._next_id
            self._next_id += 1
            key = json.dumps(request_id)
            response_queue: queue.Queue[dict[str, Any] | None] = queue.Queue(maxsize=1)
            self._pending[key] = response_queue
        message: dict[str, Any] = {"jsonrpc": "2.0", "id": request_id, "method": method}
        if params is not None:
            message["params"] = params
        try:
            self._send(message, deadline=deadline)
            response = response_queue.get(timeout=max(0.0, deadline - time.monotonic()))
        except queue.Empty as exc:
            raise TimeoutError(f"timed out waiting for {method}") from exc
        finally:
            with self._lock:
                self._pending.pop(key, None)
        if response is None:
            raise AppServerClosed("app-server closed while waiting for a response")
        if "error" in response:
            raise AppServerRPCError(response["error"])
        result = response.get("result")
        return result if isinstance(result, dict) else {"value": result}

    def notify(self, method: str, params: Any = None) -> None:
        self.start()
        message: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            message["params"] = params
        self._send(message)

    def respond(self, request_id: Any, result: Any = None, *, error: Any = None) -> None:
        message: dict[str, Any] = {"jsonrpc": "2.0", "id": request_id}
        if error is not None:
            message["error"] = error
        else:
            message["result"] = result
        self._send(message)

    def recv_event(self, *, timeout: float | None = None) -> dict[str, Any]:
        if self._backlog:
            return self._backlog.popleft()
        try:
            event = self._events.get(timeout=timeout)
        except queue.Empty as exc:
            raise TimeoutError("timed out waiting for app-server event") from exc
        if event is None:
            # Keep closure visible to subsequent and concurrent event readers.
            self._events.put(None)
            raise AppServerClosed("app-server closed")
        return event

    def wait_for(
        self,
        method: str,
        *,
        thread_id: str | None = None,
        timeout: float = 30.0,
    ) -> dict[str, Any]:
        deadline = time.monotonic() + timeout
        skipped: list[dict[str, Any]] = []
        try:
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError(f"timed out waiting for {method}")
                event = self.recv_event(timeout=remaining)
                params = event.get("params")
                event_thread = params.get("threadId") if isinstance(params, dict) else None
                if event.get("method") == method and (thread_id is None or event_thread == thread_id):
                    return event
                skipped.append(event)
        finally:
            self._backlog.extendleft(reversed(skipped))

    # Thin typed-ish conveniences. Unknown/new RPCs remain available via request().
    def thread_start(self, **params: Any) -> dict[str, Any]:
        return self.request("thread/start", params)

    def thread_resume(self, thread_id: str, **params: Any) -> dict[str, Any]:
        return self.request("thread/resume", {"threadId": thread_id, "excludeTurns": True, **params})

    def thread_fork(self, thread_id: str, **params: Any) -> dict[str, Any]:
        return self.request("thread/fork", {"threadId": thread_id, "excludeTurns": True, **params})

    def model_list(
        self,
        *,
        cursor: str | None = None,
        limit: int | None = 100,
        include_hidden: bool = False,
    ) -> dict[str, Any]:
        return self.request(
            "model/list",
            {
                "cursor": cursor,
                "limit": limit,
                "includeHidden": include_hidden,
            },
        )

    def thread_list(
        self,
        *,
        cursor: str | None = None,
        limit: int | None = 50,
        sort_key: str | None = None,
        sort_direction: str | None = None,
        **filters: Any,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {"cursor": cursor, "limit": limit, **filters}
        if sort_key is not None:
            params["sortKey"] = sort_key
        if sort_direction is not None:
            params["sortDirection"] = sort_direction
        return self.request("thread/list", params)

    def thread_read(self, thread_id: str, *, include_turns: bool = False) -> dict[str, Any]:
        return self.request("thread/read", {"threadId": thread_id, "includeTurns": include_turns})

    def turn_start_text(self, thread_id: str, text: str, **params: Any) -> dict[str, Any]:
        return self.request(
            "turn/start",
            {"threadId": thread_id, "input": [{"type": "text", "text": text}], **params},
        )

    def thread_turns_list(
        self,
        thread_id: str,
        *,
        cursor: str | None = None,
        limit: int | None = 100,
        sort_direction: str = "asc",
        items_view: str = "notLoaded",
    ) -> dict[str, Any]:
        return self.request(
            "thread/turns/list",
            {
                "threadId": thread_id,
                "cursor": cursor,
                "limit": limit,
                "sortDirection": sort_direction,
                "itemsView": items_view,
            },
        )

    def thread_items_list(
        self,
        thread_id: str,
        *,
        turn_id: str | None = None,
        cursor: Any = None,
        limit: int | None = 100,
        sort_direction: str = "asc",
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "threadId": thread_id,
            "cursor": cursor,
            "limit": limit,
            "sortDirection": sort_direction,
        }
        if turn_id is not None:
            params["turnId"] = turn_id
        return self.request("thread/items/list", params)

    def _send(self, message: Mapping[str, Any], *, deadline: float | None = None) -> None:
        process = self.process
        if self._closed.is_set() or process is None or process.stdin is None:
            raise AppServerClosed("app-server is not running")
        raw = json.dumps(message, ensure_ascii=False, separators=(",", ":"))
        if self.trace is not None:
            self.trace.append(source=self.source, direction="client_to_appserver", message=message, raw_text=raw)
        data = memoryview((raw + "\n").encode("utf-8"))
        # Acquiring the write lock is part of the same deadline as writing and
        # awaiting the acknowledgement. A timeout never triggers a resend.
        while not self._write_lock.acquire(timeout=0.05):
            self._check_send_deadline(deadline)
        try:
            while data:
                self._check_send_deadline(deadline)
                try:
                    written = os.write(process.stdin.fileno(), data)
                except BlockingIOError:
                    self._closed.wait(0.01)
                    continue
                except (OSError, ValueError) as exc:
                    self._mark_closed()
                    raise AppServerClosed("app-server pipe write failed; delivery may be unknown") from exc
                data = data[written:]
        finally:
            self._write_lock.release()

    def _check_send_deadline(self, deadline: float | None) -> None:
        if self._closed.is_set():
            raise AppServerClosed("app-server closed during write; delivery may be unknown")
        if deadline is not None and time.monotonic() >= deadline:
            # A partial JSONL frame cannot safely be followed by another RPC.
            self._mark_closed()
            raise TimeoutError("app-server write deadline expired; delivery may be unknown")

    def _read_stdout(self) -> None:
        process = self.process
        assert process is not None and process.stdout is not None
        try:
            for line in process.stdout:
                raw = line.rstrip("\r\n")
                if not raw:
                    continue
                if self.trace is not None:
                    self.trace.append_line(source=self.source, direction="appserver_to_client", raw_text=raw)
                try:
                    message = json.loads(raw)
                except json.JSONDecodeError:
                    self._events.put({"method": "$parseError", "params": {"raw": raw}})
                    continue
                if not isinstance(message, dict):
                    continue
                if "id" in message and "method" not in message:
                    key = json.dumps(message["id"])
                    with self._lock:
                        pending = self._pending.pop(key, None)
                        if pending is not None:
                            pending.put_nowait(message)
                        else:
                            self._events.put(message)
                else:
                    self._events.put(message)
        finally:
            self._mark_closed()

    def _read_stderr(self) -> None:
        process = self.process
        assert process is not None and process.stderr is not None
        for line in process.stderr:
            self._stderr.append(line.rstrip("\r\n"))


class CodexPlace:
    """A named app-server evaluator realm, intentionally thin in v0."""

    def __init__(self, name: str, client: AppServerClient) -> None:
        self.name = name
        self.client = client

    def start(self) -> "CodexPlace":
        self.client.start()
        self.client.initialize()
        return self

    def start_thread(self, **params: Any) -> str:
        result = self.client.thread_start(**params)
        thread = result.get("thread")
        if not isinstance(thread, dict) or not isinstance(thread.get("id"), str):
            raise ValueError(f"thread/start returned no thread id: {result!r}")
        return thread["id"]

    def resume_thread(self, thread_id: str, **params: Any) -> str:
        result = self.client.thread_resume(thread_id, **params)
        thread = result.get("thread")
        if not isinstance(thread, dict) or not isinstance(thread.get("id"), str):
            raise ValueError(f"thread/resume returned no thread id: {result!r}")
        return thread["id"]

    def fork_thread(self, thread_id: str, **params: Any) -> str:
        result = self.client.thread_fork(thread_id, **params)
        thread = result.get("thread")
        if not isinstance(thread, dict) or not isinstance(thread.get("id"), str):
            raise ValueError(f"thread/fork returned no thread id: {result!r}")
        return thread["id"]

    def list_threads(self, *, limit: int = 50) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        cursor: str | None = None
        while len(out) < limit:
            page = self.client.thread_list(cursor=cursor, limit=min(50, limit - len(out)))
            data = page.get("data") or []
            out.extend(x for x in data if isinstance(x, dict))
            cursor = page.get("nextCursor") if isinstance(page.get("nextCursor"), str) else None
            if cursor is None:
                break
        return out

    def sync_thread_history(self, thread_id: str, *, page_size: int = 100) -> dict[str, int]:
        """Import persisted Codex history into Eidos's own trace projection.

        Native RPC request/response lines remain preserved by AppServerClient. In
        addition, this emits explicitly-derived `$history/*` records so the same
        renderer can consume old threads and live notifications uniformly.
        """

        trace = self.client.trace
        if trace is None:
            raise ValueError("history sync requires an AppServerClient with TraceStore")

        turns = items = 0
        cursor: str | None = None
        while True:
            page = self.client.thread_turns_list(
                thread_id, cursor=cursor, limit=page_size, sort_direction="asc", items_view="notLoaded"
            )
            data = page.get("data") or []
            for turn in data:
                if isinstance(turn, dict):
                    trace.append(
                        source="codex-history-sync",
                        direction="internal",
                        message={
                            "jsonrpc": "2.0",
                            "method": "$history/turn",
                            "params": {"threadId": thread_id, "turn": turn},
                        },
                    )
                    turns += 1
            cursor = page.get("nextCursor") if isinstance(page.get("nextCursor"), str) else None
            if cursor is None:
                break

        cursor_value: Any = None
        while True:
            page = self.client.thread_items_list(
                thread_id, cursor=cursor_value, limit=page_size, sort_direction="asc"
            )
            data = page.get("data") or []
            for entry in data:
                if not isinstance(entry, dict):
                    continue
                turn_id = entry.get("turnId")
                item = entry.get("item")
                if isinstance(turn_id, str) and isinstance(item, dict):
                    trace.append(
                        source="codex-history-sync",
                        direction="internal",
                        message={
                            "jsonrpc": "2.0",
                            "method": "$history/item",
                            "params": {
                                "threadId": thread_id,
                                "turnId": turn_id,
                                "item": item,
                                "startedAtMs": entry.get("startedAtMs"),
                                "completedAtMs": entry.get("completedAtMs"),
                            },
                        },
                    )
                    items += 1
            cursor_value = page.get("nextCursor")
            if not isinstance(cursor_value, str):
                break
        return {"turns": turns, "items": items}
