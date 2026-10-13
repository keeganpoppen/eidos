from __future__ import annotations

"""A bounded native worker and evidence-only recovery for investigations.

The surrounding controller admits one attempt before calling this adapter.
Recorded dispatch is not proof of delivery, and recovery never resends it.
"""

import queue
from pathlib import Path
import re
import tempfile
import threading
import time
from typing import Any, Callable, Mapping, Sequence

from .codex import AppServerClient
from .investigation_context import THREAD_CONFIG, TURN_SANDBOX
from .trace import TraceRecord, TraceStore


class NativeInvestigationError(RuntimeError):
    def __init__(self, message: str, *, status: str = "unknown") -> None:
        super().__init__(message)
        self.status = status


class NativeInvestigationWorker:
    """Own one app-server, temporary cwd, and read-only native turn.

    The sandbox is a native execution policy, not a claim that only the selected
    packet is visible or that provider instructions and configured tools were
    fully captured. The constructor is a trusted-host interface.
    """

    MAX_OUTPUT_CHARS = 131_072

    def __init__(self, trace: TraceStore, command: Sequence[str] | None = None) -> None:
        self.trace = trace
        self.command = tuple(command) if command is not None else (
            "codex", "app-server", "--listen", "stdio://",
        )
        self._clients: set[AppServerClient] = set()
        self._clients_lock = threading.RLock()
        self._closed = False

    def close(self) -> None:
        """Cancel only owned processes; a cancelled attempt is not retried."""
        with self._clients_lock:
            self._closed = True
            clients = tuple(self._clients)
        for client in clients:
            client.close()

    @staticmethod
    def _check_thread_policy(result: Mapping[str, Any], cwd: str) -> None:
        """Check the native acknowledgement, not merely our requested policy.

        This verifies the server's reported configuration. It does not prove
        OS enforcement or that inherited instructions and tools are absent.
        """
        sandbox = result.get("sandbox")
        if (
            not isinstance(sandbox, dict)
            or sandbox.get("type") != "readOnly"
            # Preserve unknown policy fields in raw evidence, but require
            # review before accepting a changed native permission contract.
            or not sandbox.keys() <= {"type", "networkAccess"}
            # Native SandboxPolicy defaults an omitted networkAccess to false.
            or sandbox.get("networkAccess", False) is not False
            or result.get("approvalPolicy") != "never"
        ):
            raise NativeInvestigationError(
                "native thread did not acknowledge the required read-only policy",
                status="failed",
            )
        admitted_cwd = result.get("cwd")
        if not isinstance(admitted_cwd, str) or Path(admitted_cwd).resolve() != Path(cwd).resolve():
            raise NativeInvestigationError(
                "native thread did not acknowledge the isolated working directory",
                status="failed",
            )
        thread = result.get("thread")
        if not isinstance(thread, dict) or thread.get("environments") != []:
            raise NativeInvestigationError(
                "native thread did not acknowledge disabled environment access", status="failed",
            )

    def _check_tool_inventory(self, client: AppServerClient, thread_id: str, deadline: float) -> None:
        cursor = None
        seen: set[str] = set()
        for _ in range(100):
            page = client.request("mcpServerStatus/list", {
                "threadId": thread_id, "cursor": cursor, "limit": 100,
                "detail": "toolsAndAuthOnly",
            }, timeout=min(30.0, self._remaining(deadline)))
            servers = page.get("data")
            if not isinstance(servers, list):
                raise NativeInvestigationError("native MCP tool inventory is unavailable", status="failed")
            for server in servers:
                if not isinstance(server, dict) or not isinstance(server.get("tools"), dict):
                    raise NativeInvestigationError("native MCP tool inventory is incomplete", status="failed")
                if server["tools"]:
                    raise NativeInvestigationError(
                        "native MCP tools are configured; this specialist cannot admit their external actions",
                        status="failed",
                    )
                # toolsAndAuthOnly does not reveal resource capabilities. A
                # connected server with no tools can still expose resources,
                # so only an explicitly disabled server is admissible.
                if server.get("toolsError") is not None or server.get("runtimeStatus") != "disabled":
                    raise NativeInvestigationError(
                        "native MCP server is enabled or unresolved; specialist dispatch was refused",
                        status="failed",
                    )
            cursor = page.get("nextCursor")
            if cursor is None:
                return
            if not isinstance(cursor, str) or cursor in seen:
                raise NativeInvestigationError("native MCP inventory pagination is invalid", status="failed")
            seen.add(cursor)
        raise NativeInvestigationError("native MCP inventory exceeded its page limit", status="failed")

    @staticmethod
    def _remaining(deadline: float) -> float:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise NativeInvestigationError("native worker deadline expired; delivery or completion may be unknown")
        return remaining

    def run(
        self,
        attempt: Mapping[str, Any],
        context: Mapping[str, Any],
        update: Callable[..., None],
    ) -> dict[str, Any]:
        timeout = min(120.0, float(attempt.get("timeoutSeconds", 120)))
        if timeout <= 0:
            raise ValueError("worker timeout must be positive")
        if attempt.get("contextId") != context.get("id"):
            raise ValueError("attempt names a different context")
        prompt = context.get("projectedPrompt")
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("context must contain the reviewed prompt")

        deadline = time.monotonic() + timeout
        state = dict(attempt)
        events: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=512)
        errors: queue.Queue[Exception] = queue.Queue()
        stopped = threading.Event()

        def remember(**fields: Any) -> None:
            update(**fields)
            state.update(fields)

        with tempfile.TemporaryDirectory(prefix="nema-investigation-") as cwd:
            client = AppServerClient(self.command, trace=self.trace, cwd=cwd, source="nema-investigation")
            # Persist the incarnation before process launch. A crash before the
            # subsequent native acknowledgement must remain visibly uncertain.
            remember(source=client.source)

            def pump() -> None:
                observed_chars = 0
                try:
                    while not stopped.is_set():
                        try:
                            event = client.recv_event(timeout=0.1)
                        except TimeoutError:
                            continue
                        observed_chars += len(str(event))
                        if observed_chars > self.MAX_OUTPUT_CHARS:
                            raise NativeInvestigationError("native worker output limit exceeded")
                        if "id" in event and "method" in event:
                            client.respond(event["id"], error={
                                "code": -32000,
                                "message": "Nema investigation does not support interactive native requests",
                            })
                            continue
                        try:
                            events.put_nowait(event)
                        except queue.Full as exc:
                            raise NativeInvestigationError("native worker event limit exceeded") from exc
                except Exception as exc:
                    if not stopped.is_set():
                        errors.put(exc)
                        # Release an in-flight RPC promptly when output or the
                        # event stream fails. Only this owned process is closed.
                        client.close()

            reader: threading.Thread | None = None
            watchdog: threading.Timer | None = None
            try:
                with self._clients_lock:
                    if self._closed:
                        raise NativeInvestigationError("native worker has been closed")
                    self._clients.add(client)
                    client.start()
                # request timeouts cannot interrupt a blocked stdin write.
                # An independent deadline closes our child even under native
                # backpressure; closing cannot relaunch this incarnation.
                def expire() -> None:
                    errors.put(NativeInvestigationError("native worker deadline expired; outcome may be unknown"))
                    client.close()
                watchdog = threading.Timer(self._remaining(deadline), expire)
                watchdog.daemon = True
                watchdog.start()
                reader = threading.Thread(target=pump, daemon=True, name="nema-investigation-events")
                reader.start()
                client.initialize(timeout=min(10.0, self._remaining(deadline)))
                result = client.request("thread/start", {
                    "cwd": cwd,
                    "approvalPolicy": "never",
                    "sandbox": "read-only",
                    "environments": [],
                    "ephemeral": False,
                    "threadSource": "nema-investigation",
                    "config": dict(THREAD_CONFIG),
                }, timeout=min(30.0, self._remaining(deadline)))
                thread = result.get("thread")
                if not isinstance(thread, dict) or not isinstance(thread.get("id"), str):
                    raise NativeInvestigationError("thread/start did not acknowledge a native thread")
                remember(threadId=thread["id"])
                self._check_thread_policy(result, cwd)
                self.trace.annotate_thread(
                    thread["id"], kind="investigation-worker",
                    metadata={"attemptId": attempt.get("id"), "contextId": context["id"]},
                )
                self._check_tool_inventory(client, thread["id"], deadline)
                result = client.request("turn/start", {
                    "threadId": thread["id"],
                    "input": [{"type": "text", "text": prompt}],
                    "sandboxPolicy": dict(TURN_SANDBOX),
                    "environments": [],
                }, timeout=min(30.0, self._remaining(deadline)))
                turn = result.get("turn")
                if not isinstance(turn, dict) or not isinstance(turn.get("id"), str):
                    raise NativeInvestigationError("turn/start did not acknowledge a native turn")
                remember(turnId=turn["id"], status="running")

                while True:
                    # A terminal event is already durably recorded before it
                    # reaches this queue. Drain it before treating EOF as loss.
                    try:
                        event = events.get(timeout=min(0.1, self._remaining(deadline)))
                    except queue.Empty:
                        if not errors.empty():
                            raise errors.get_nowait()
                        continue
                    params = event.get("params")
                    if (
                        event.get("method") == "turn/completed"
                        and isinstance(params, dict)
                        and params.get("threadId") == state["threadId"]
                        and isinstance(params.get("turn"), dict)
                        and params["turn"].get("id") == state["turnId"]
                    ):
                        artifact = self.recover(state, context)
                        if artifact is None:
                            raise NativeInvestigationError("native turn ended without a recoverable artifact")
                        return artifact
            except Exception as exc:
                if not isinstance(exc, NativeInvestigationError) and not errors.empty():
                    exc = errors.get_nowait()
                if isinstance(exc, NativeInvestigationError):
                    raise exc
                raise NativeInvestigationError(f"{type(exc).__name__}: {exc}") from exc
            finally:
                stopped.set()
                if watchdog is not None:
                    watchdog.cancel()
                client.close()
                if reader is not None:
                    reader.join(timeout=1.0)
                with self._clients_lock:
                    self._clients.discard(client)

    def recover(self, attempt: Mapping[str, Any], context: Mapping[str, Any]) -> dict[str, Any] | None:
        """Read matching native evidence, including acknowledgements not mapped locally."""
        if attempt.get("contextId") != context.get("id"):
            raise ValueError("attempt names a different context")
        source = attempt.get("source")
        if not isinstance(source, str):
            return None
        records = [record for record in self.trace.records() if record.source == source]
        requests = [
            record for record in records
            if record.direction == "client_to_appserver" and record.method == "turn/start"
        ]
        if not requests:
            return None
        if len(requests) != 1:
            raise NativeInvestigationError("worker incarnation contains ambiguous native turn requests")
        request = requests[0]
        params = request.message.get("params", {})
        if params.get("input") != [{"type": "text", "text": context.get("projectedPrompt")}]:
            raise NativeInvestigationError("recorded native input does not match the frozen context")
        thread_id = params.get("threadId")
        if not isinstance(thread_id, str) or (
            attempt.get("threadId") is not None and attempt["threadId"] != thread_id
        ):
            raise NativeInvestigationError("recorded worker thread contradicts attempt mapping")

        turn_ids: set[str] = set()
        if isinstance(attempt.get("turnId"), str):
            turn_ids.add(attempt["turnId"])
        terminal: list[TraceRecord] = []
        response_errors: list[TraceRecord] = []
        for record in records:
            if record.direction != "appserver_to_client" or record.seq <= request.seq:
                continue
            message = record.message
            result = message.get("result")
            if record.rpc_id == request.rpc_id and "method" not in message and "error" in message:
                response_errors.append(record)
            if record.rpc_id == request.rpc_id and isinstance(result, dict):
                turn = result.get("turn")
                if isinstance(turn, dict) and isinstance(turn.get("id"), str):
                    turn_ids.add(turn["id"])
            event_params = message.get("params", {})
            if (
                record.method == "turn/completed"
                and event_params.get("threadId") == thread_id
                and isinstance(event_params.get("turn"), dict)
                and isinstance(event_params["turn"].get("id"), str)
            ):
                terminal.append(record)
                turn_ids.add(event_params["turn"]["id"])
        if len(turn_ids) > 1:
            raise NativeInvestigationError("worker incarnation contains conflicting native turn identities")
        if not terminal or not turn_ids:
            return None
        if response_errors:
            raise NativeInvestigationError("native turn acknowledgement and terminal evidence are contradictory")
        completed = terminal[-1]
        turn = completed.message["params"]["turn"]
        statuses = [record.message["params"]["turn"].get("status") for record in terminal]
        if any(status != statuses[0] for status in statuses[1:]):
            raise NativeInvestigationError("native terminal evidence is contradictory")
        if turn.get("status") in ("failed", "interrupted"):
            raise NativeInvestigationError(
                f"native turn ended with status {turn.get('status')!r}: {turn.get('error')!r}",
                status="failed",
            )
        if turn.get("status") != "completed":
            raise NativeInvestigationError(f"native terminal status is unsupported: {turn.get('status')!r}")
        if any(record.message["params"]["turn"].get("error") is not None for record in terminal):
            raise NativeInvestigationError("native terminal evidence is contradictory")
        turn_id = next(iter(turn_ids))
        output: dict[str, tuple[str, str | None, int]] = {}
        completed_items: dict[str, tuple[Any, Any, Any]] = {}

        def add(item: Any, seq: int) -> None:
            if not isinstance(item, dict) or not isinstance(item.get("id"), str):
                return
            identity = item["id"]
            signature = (item.get("type"), item.get("text"), item.get("phase"))
            existing = completed_items.get(identity)
            # Compare completed descriptions before filtering usable text. An
            # empty/malformed later description cannot erase a contradiction,
            # nor can an item silently change into or out of an agent message.
            if existing is not None and existing != signature and (
                existing[0] == "agentMessage" or signature[0] == "agentMessage"
            ):
                raise NativeInvestigationError("native completed item evidence is contradictory")
            completed_items[identity] = signature
            if item.get("type") == "agentMessage" and item.get("phase") not in (
                None, "commentary", "final", "final_answer",
            ):
                raise NativeInvestigationError("native completed message phase is unsupported")
            if (
                item.get("type") == "agentMessage" and isinstance(item.get("text"), str)
                and item["text"].strip()
            ):
                output.setdefault(identity, (item["text"], item.get("phase"), seq))

        for record in records:
            if record.seq <= request.seq or record.seq > completed.seq:
                continue
            if record.direction != "appserver_to_client" or record.method != "item/completed":
                continue
            item_params = record.message.get("params", {})
            if item_params.get("threadId") == thread_id and item_params.get("turnId") == turn_id:
                add(item_params.get("item"), record.seq)
        for record in terminal:
            for item in record.message["params"]["turn"].get("items", []):
                # Equivalent replay retains the first dedicated item source;
                # conflicting completed content never silently replaces it.
                add(item, record.seq)
        # Explicit commentary is interim output, even if the turn later ends
        # without a final answer. Missing/null phases remain legacy-compatible.
        selected = [entry for entry in output.values() if entry[1] != "commentary"]
        final_phases = ("final", "final_answer")
        if any(phase in final_phases for _, phase, _ in selected):
            selected = [entry for entry in selected if entry[1] in final_phases]
        selected.sort(key=lambda entry: entry[2])
        if not selected:
            return None
        text = "\n\n".join(entry[0] for entry in selected)
        if len(text) > self.MAX_OUTPUT_CHARS:
            raise NativeInvestigationError("recorded native artifact exceeds output limit")
        cited = {int(value) for value in re.findall(r"\[evidence:(\d+)\]", text)}
        available = {record["seq"] for record in context.get("records", [])}
        return {
            "text": text,
            "outputSeqs": sorted({entry[2] for entry in selected}),
            "citations": sorted(cited & available),
            "unsupportedCitations": sorted(cited - available),
        }
