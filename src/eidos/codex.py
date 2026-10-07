from __future__ import annotations

from collections import deque
import json
import os
from pathlib import Path
import queue
import subprocess
import threading
import uuid
from typing import Any, Mapping, Sequence

from .trace import TraceStore


class AppServerRPCError(RuntimeError):
    def __init__(self, error: Any) -> None:
        super().__init__(f"Codex app-server RPC error: {error!r}")
        self.error = error


class AppServerClosed(RuntimeError):
    pass


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
    ) -> None:
        self.command = tuple(command)
        self.trace = trace
        self.cwd = str(cwd) if cwd is not None else None
        self.env = dict(env) if env is not None else None
        self.source = f"{source}/{uuid.uuid4().hex[:12]}"
        self.process: subprocess.Popen[str] | None = None
        self._next_id = 1
        self._lock = threading.Lock()
        self._write_lock = threading.Lock()
        self._pending: dict[str, queue.Queue[dict[str, Any]]] = {}
        self._events: queue.Queue[dict[str, Any]] = queue.Queue()
        self._backlog: deque[dict[str, Any]] = deque()
        self._stderr: deque[str] = deque(maxlen=200)
        self._reader: threading.Thread | None = None
        self._stderr_reader: threading.Thread | None = None
        self._closed = threading.Event()

    def start(self) -> "AppServerClient":
        if self.process is not None:
            return self
        env = os.environ.copy()
        if self.env is not None:
            env.update(self.env)
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
        self._reader = threading.Thread(target=self._read_stdout, name="eidos-codex-stdout", daemon=True)
        self._stderr_reader = threading.Thread(target=self._read_stderr, name="eidos-codex-stderr", daemon=True)
        self._reader.start()
        self._stderr_reader.start()
        return self

    def close(self) -> None:
        process = self.process
        if process is None:
            return
        try:
            if process.stdin:
                process.stdin.close()
        except OSError:
            pass
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
        self._closed.set()
        self.process = None

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
        self.start()
        with self._lock:
            request_id = self._next_id
            self._next_id += 1
        key = json.dumps(request_id)
        response_queue: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=1)
        self._pending[key] = response_queue
        message: dict[str, Any] = {"jsonrpc": "2.0", "id": request_id, "method": method}
        if params is not None:
            message["params"] = params
        self._send(message)
        try:
            response = response_queue.get(timeout=timeout)
        except queue.Empty as exc:
            self._pending.pop(key, None)
            raise TimeoutError(f"timed out waiting for {method}") from exc
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
        if self._closed.is_set() and self._events.empty():
            raise AppServerClosed("app-server closed")
        try:
            return self._events.get(timeout=timeout)
        except queue.Empty as exc:
            raise TimeoutError("timed out waiting for app-server event") from exc

    def wait_for(
        self,
        method: str,
        *,
        thread_id: str | None = None,
        timeout: float = 30.0,
    ) -> dict[str, Any]:
        import time

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

    def _send(self, message: Mapping[str, Any]) -> None:
        process = self.process
        if process is None or process.stdin is None:
            raise AppServerClosed("app-server is not running")
        raw = json.dumps(message, ensure_ascii=False, separators=(",", ":"))
        if self.trace is not None:
            self.trace.append(source=self.source, direction="client_to_appserver", message=message, raw_text=raw)
        with self._write_lock:
            process.stdin.write(raw + "\n")
            process.stdin.flush()

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
                    pending = self._pending.pop(key, None)
                    if pending is not None:
                        pending.put(message)
                    else:
                        self._events.put(message)
                else:
                    self._events.put(message)
        finally:
            self._closed.set()
            for pending in list(self._pending.values()):
                try:
                    pending.put_nowait({"error": {"message": "app-server closed"}})
                except queue.Full:
                    pass

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
