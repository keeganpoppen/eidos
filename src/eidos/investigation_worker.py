from __future__ import annotations

"""A bounded native worker and evidence-only recovery for investigations.

The surrounding controller admits one attempt before calling this adapter.
Recorded dispatch is not proof of delivery, and recovery never resends it.
"""

from dataclasses import dataclass, replace
import json
import math
import queue
from pathlib import Path
import re
import tempfile
import threading
import time
from typing import Any, Callable, Literal, Mapping, Sequence

from .codex import AppServerClient, NativeExecutionProfile, NativeExecutionProfileError
from .investigation_context import THREAD_CONFIG, TURN_SANDBOX
from .trace import TraceRecord, TraceStore


class NativeInvestigationError(RuntimeError):
    def __init__(self, message: str, *, status: str = "unknown", stop_reason: str = "failed") -> None:
        super().__init__(message)
        self.status = status
        self.stop_reason = stop_reason


class NativePreparation:
    """Bounded trusted-host preparation on the worker's existing event pump.

    Hooks must wait through these methods. This is not a sandbox for arbitrary
    Python callbacks, and cannot forcibly interrupt an unrelated Python wait.
    """

    METHODS = frozenset({"account/login/start", "account/login/cancel", "account/read", "config/read"})

    def __init__(self, client: AppServerClient, events: queue.Queue, errors: queue.Queue,
                 remaining: Callable[[], float], phase: Callable[[str], None]) -> None:
        self._client, self._events, self._errors = client, events, errors
        self._remaining, self._phase = remaining, phase
        self._finished = threading.Event()

    def remaining(self) -> float:
        if self._finished.is_set():
            raise NativeInvestigationError("preparation has ended")
        return self._remaining()

    def _finish(self) -> None:
        self._finished.set()

    def request(self, method: str, params: Any = None) -> dict[str, Any]:
        if method not in self.METHODS:
            raise NativeInvestigationError("preparation RPC is not allowed", status="failed")
        result = self._client.request(method, params, timeout=self.remaining())
        self.remaining()
        return result

    def recv_event(self, timeout: float | None = None) -> dict[str, Any]:
        if timeout is not None and (not math.isfinite(timeout) or timeout <= 0):
            raise ValueError("preparation event timeout must be finite and positive")
        deadline = time.monotonic() + min(self.remaining(), timeout if timeout is not None else math.inf)
        while True:
            self.remaining()
            if not self._errors.empty():
                raise self._errors.get_nowait()
            wait = min(0.1, deadline - time.monotonic())
            if wait <= 0:
                raise TimeoutError("timed out waiting for preparation event")
            try:
                event = self._events.get(timeout=wait)
                self.remaining()
                return event
            except queue.Empty:
                continue

    def phase(self, value: str) -> None:
        if value not in {"awaiting-sign-in", "checking"}:
            raise ValueError("invalid preparation phase")
        self.remaining()
        self._phase(value)


NativeRequestState = Literal[
    "pending", "unsupported", "response_recorded", "resolved", "conflict", "abandoned",
]
NativeTerminalState = Literal["completed", "failed", "interrupted", "unknown"]
NativeSpecialistEventKind = Literal[
    "observed", "profile_observed", "capture_gap", "correlation_conflict", "request_pending",
    "request_unsupported", "request_duplicate", "request_conflict", "request_response_recorded",
    "request_resolved", "request_abandoned", "terminal_observed", "transport_closed",
]


def _is_capture_gap(record: TraceRecord) -> bool:
    """Recognize this recorder's host marker, never a child-authored claim.

    Internal direction is a trusted-host convention, not authentication against
    arbitrary database writers. The caller must also scope the source incarnation.
    """
    if record.direction != "internal" or record.method != "$transport/captureGap":
        return False
    params = record.message.get("params")
    return (isinstance(params, dict) and type(params.get("version")) is int
            and params["version"] == 1 and params.get("captureComplete") is False)


@dataclass(frozen=True)
class NativeSpecialistEvent:
    """Versioned evidence projection, never a live response capability.

    ``evidence_seqs`` reference unchanged TraceStore records. In particular, a
    recorded response does not establish delivery, and an observed completed
    status does not establish an admissible investigation artifact.
    """

    event_id: str
    attempt_id: str
    context_id: str
    source: str
    kind: NativeSpecialistEventKind
    evidence_seqs: tuple[int, ...]
    thread_id: str | None = None
    turn_id: str | None = None
    item_id: str | None = None
    request_key: str | None = None
    rpc_id: int | str | None = None
    method: str | None = None
    request_state: NativeRequestState | None = None
    is_blocking: bool | None = None
    terminal_state: NativeTerminalState | None = None
    detail: str | None = None
    schema_version: int = 1


class UnsupportedNativeOperation(NativeInvestigationError):
    """The adapter has no admitted native operation for this description."""


class NativeSpecialistAdapter:
    """Read-only projection of one owned native incarnation for a controller.

    Reconstructing this object does not reopen the process or revive pending
    requests. ``pending_requests`` are observed unresolved requests, including
    nonblocking ones; only ``is_blocking is True`` describes a native wait.
    This adapter deliberately has no evidence-disclosure execution path yet.
    """

    def __init__(
        self, trace: TraceStore, attempt: Mapping[str, Any], context: Mapping[str, Any],
        source: str, on_event: Callable[[NativeSpecialistEvent], None] | None = None,
    ) -> None:
        if attempt.get("contextId") != context.get("id"):
            raise ValueError("attempt names a different context")
        if not isinstance(attempt.get("id"), str) or not isinstance(context.get("id"), str):
            raise ValueError("adapter requires durable attempt and context identities")
        if attempt.get("source") not in (None, source):
            raise ValueError("adapter source contradicts the admitted attempt")
        self.trace, self.source = trace, source
        self.attempt_id, self.context_id = attempt["id"], context["id"]
        self.thread_id: str | None = attempt.get("threadId")
        self.turn_id: str | None = attempt.get("turnId")
        self.on_event = on_event
        self._prompt = context.get("projectedPrompt")
        self._cursor = 0
        self._lock = threading.RLock()
        self._outbound: dict[str, TraceRecord] = {}
        self._turn_requests: list[TraceRecord] = []
        self._requests: dict[str, NativeSpecialistEvent] = {}
        self._signatures: dict[str, str] = {}
        self._refused: set[str] = set()
        self._terminals: dict[str, tuple[Any, Any]] = {}
        self._events: list[NativeSpecialistEvent] = []
        self.ambiguous = False
        self._closed = False
        self._capture_gap_seq: int | None = None

    @staticmethod
    def _rpc_key(value: Any) -> str | None:
        # bool is an int subclass, but never the same native RPC identity.
        return json.dumps(value, ensure_ascii=False) if type(value) in (int, str) else None

    @property
    def pending_requests(self) -> tuple[NativeSpecialistEvent, ...]:
        with self._lock:
            return tuple(event for event in self._requests.values()
                         if event.request_state in {"pending", "unsupported", "response_recorded"})

    def _emit(self, event: NativeSpecialistEvent) -> None:
        self._events.append(event)
        if self.on_event is not None:
            self.on_event(event)

    def refresh(self) -> tuple[NativeSpecialistEvent, ...]:
        """Project newly recorded evidence without sending any native traffic."""
        with self._lock:
            before = len(self._events)
            # Bound the read by sequence and incarnation. Repeated callbacks
            # must not materialize the owner's complete investigation history.
            # The watermark also advances across unrelated source traffic.
            with self.trace._lock:
                watermark = self.trace.db.execute("SELECT COALESCE(MAX(seq), 0) FROM trace_records").fetchone()[0]
                rows = self.trace.db.execute(
                    "SELECT * FROM trace_records WHERE source=? AND seq>? AND seq<=? ORDER BY seq",
                    (self.source, self._cursor, watermark),
                ).fetchall()
            for row in rows:
                record = TraceRecord(**dict(row))
                self._cursor = record.seq
                self._observe(record)
            self._cursor = watermark
            return tuple(self._events[before:])

    def _observe(self, record: TraceRecord) -> None:
        message = record.message
        params = message.get("params")
        params = params if isinstance(params, dict) else {}
        rpc_key = self._rpc_key(message.get("id"))
        method = message.get("method")
        base = NativeSpecialistEvent(
            event_id=f"{self.source}:{record.seq}", attempt_id=self.attempt_id,
            context_id=self.context_id, source=self.source, kind="observed",
            evidence_seqs=(record.seq,), thread_id=record.thread_id,
            turn_id=record.turn_id, item_id=record.item_id,
            rpc_id=message.get("id") if rpc_key is not None else None, method=method,
        )
        if self._capture_gap_seq is not None:
            self._emit(replace(base, detail="Recorded after capture stopped; excluded from native recovery."))
            return
        if _is_capture_gap(record):
            self._capture_gap_seq = record.seq
            reason = f"Native capture stopped: {params.get('reason', 'unspecified gap')}."
            self._emit(replace(base, kind="capture_gap", detail=reason))
            self.close(reason)
            return
        if record.direction == "internal" and method == "$native/profile":
            self._emit(replace(base, kind="profile_observed", detail=params.get("admission")))
            return
        if record.direction == "client_to_appserver":
            if isinstance(method, str) and rpc_key is not None:
                self._outbound[rpc_key] = record
                if method == "turn/start":
                    self._turn_requests.append(record)
                    if (
                        len(self._turn_requests) != 1
                        or params.get("threadId") != self.thread_id
                        or params.get("input") != [{"type": "text", "text": self._prompt}]
                    ):
                        self.ambiguous = True
                        base = replace(base, kind="correlation_conflict", terminal_state="unknown")
            elif method is None and rpc_key in self._requests:
                prior = self._requests[rpc_key]
                if prior.request_state not in {"conflict", "resolved", "abandoned"}:
                    event = replace(prior, event_id=base.event_id, kind="request_response_recorded",
                                    evidence_seqs=(*prior.evidence_seqs, record.seq),
                                    request_state="response_recorded",
                                    detail="Local response recorded; native receipt is unverified.")
                    self._requests[rpc_key] = event
                    self._emit(event)
                    return
            self._emit(base)
            return
        if record.direction != "appserver_to_client":
            return
        if method is None and rpc_key in self._outbound:
            outbound = self._outbound[rpc_key]
            result = message.get("result")
            if isinstance(result, dict):
                field = "thread" if outbound.method == "thread/start" else "turn"
                identity = result.get(field)
                if outbound.method in {"thread/start", "turn/start"} and isinstance(identity, dict):
                    native_id = identity.get("id")
                    if isinstance(native_id, str):
                        old = self.thread_id if field == "thread" else self.turn_id
                        if old is not None and old != native_id:
                            self.ambiguous = True
                            base = replace(base, kind="correlation_conflict", terminal_state="unknown")
                        elif field == "thread":
                            self.thread_id = native_id
                        else:
                            self.turn_id = native_id
                            if any(event.turn_id not in (None, native_id) for event in self._requests.values()):
                                self.ambiguous = True
                                base = replace(base, kind="correlation_conflict", terminal_state="unknown")
            self._emit(base)
            return
        if "id" in message and isinstance(method, str):
            if rpc_key is None:
                self.ambiguous = True
                self._emit(replace(base, kind="request_unsupported", request_state="unsupported",
                                   detail="Native request has an invalid RPC identity."))
                return
            signature = json.dumps(message, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
            prior = self._requests.get(rpc_key)
            if prior is not None:
                equivalent = self._signatures[rpc_key] == signature
                event = replace(prior, event_id=base.event_id,
                                evidence_seqs=(*prior.evidence_seqs, record.seq),
                                kind="request_duplicate" if equivalent else "request_conflict",
                                request_state=prior.request_state if equivalent else "conflict")
                self._requests[rpc_key] = event
                self.ambiguous |= not equivalent
                self._emit(event)
                return
            thread_id, turn_id = params.get("threadId"), params.get("turnId")
            correlated = (
                isinstance(thread_id, str) and thread_id == self.thread_id
                and isinstance(turn_id, str)
                and (self.turn_id is None or turn_id == self.turn_id)
                and len(self._turn_requests) == 1 and not self.ambiguous
            )
            questions = params.get("questions")
            valid_questions = isinstance(questions, list) and bool(questions) and all(
                isinstance(q, dict) and all(isinstance(q.get(k), str) for k in ("id", "header", "question"))
                and bool(q["id"])
                for q in questions
            )
            if valid_questions:
                valid_questions = len({q["id"] for q in questions}) == len(questions)
            recognized = (
                method == "item/tool/requestUserInput" and correlated
                and type(params.get("isBlocking")) is bool
                and isinstance(params.get("itemId"), str) and valid_questions
            )
            event = replace(base, kind="request_pending" if recognized else "request_unsupported",
                            request_key=f"{self.source}:{rpc_key}",
                            request_state="pending" if recognized else "unsupported",
                            is_blocking=params.get("isBlocking") if recognized else None,
                            detail="Observed native request; answering is not admitted by this adapter.")
            if self._closed:
                event = replace(event, kind="request_abandoned", request_state="abandoned",
                                detail="Late evidence after local closure; no live interaction is available.")
            self._requests[rpc_key], self._signatures[rpc_key] = event, signature
            self._emit(event)
            return
        if method == "serverRequest/resolved":
            key = self._rpc_key(params.get("requestId"))
            prior = self._requests.get(key) if key is not None else None
            if prior is not None and params.get("threadId") == prior.thread_id:
                # A resolution reports closure, not whether an answer was used
                # or whether native cancellation was the reason for closure.
                event = replace(prior, event_id=base.event_id, kind="request_resolved",
                                evidence_seqs=(*prior.evidence_seqs, record.seq),
                                request_state="resolved" if prior.request_state != "conflict" else "conflict",
                                detail="Native reports request resolved; outcome/reason is unspecified.")
                self._requests[key] = event
                self._emit(event)
                return
        if method == "turn/completed" and params.get("threadId") == self.thread_id:
            turn = params.get("turn")
            if isinstance(turn, dict) and isinstance(turn.get("id"), str):
                turn_id = turn["id"]
                status = turn.get("status")
                signature = (status, turn.get("error"))
                previous = self._terminals.get(turn_id)
                self.ambiguous |= (
                    (self.turn_id is not None and turn_id != self.turn_id)
                    or (previous is not None and previous != signature)
                    or (status == "completed" and turn.get("error") is not None)
                    or any(event.is_blocking is True and event.request_state in {"pending", "response_recorded"}
                           for event in self._requests.values())
                )
                self._terminals[turn_id] = signature
                terminal = status if isinstance(status, str) and status in {"completed", "failed", "interrupted"} else "unknown"
                self._emit(replace(base, kind="terminal_observed", terminal_state=(
                    "unknown" if self.ambiguous else terminal),
                    detail="Native terminal observation; artifact admission requires recovery validation."))
                return
        self._emit(base)

    def refuse_once(self, message: Mapping[str, Any]) -> bool:
        """Claim one default refusal, including unsupported future requests."""
        with self._lock:
            key = self._rpc_key(message.get("id"))
            if key is None or key in self._refused:
                return False
            self._refused.add(key)
            prior = self._requests.get(key)
            return prior is not None and prior.request_state in {"pending", "unsupported"}

    def close(self, reason: str) -> None:
        """End local waiting; do not assert a native cancellation succeeded."""
        with self._lock:
            if self._closed:
                return
            self._closed = True
            for key, prior in tuple(self._requests.items()):
                if prior.request_state in {"pending", "unsupported", "response_recorded"}:
                    event = replace(prior, event_id=f"{prior.event_id}:closed", kind="request_abandoned",
                                    request_state="abandoned", detail=reason)
                    self._requests[key] = event
                    self._emit(event)
            self._emit(NativeSpecialistEvent(
                event_id=f"{self.source}:closed", attempt_id=self.attempt_id, context_id=self.context_id,
                source=self.source, kind="transport_closed", evidence_seqs=(),
                thread_id=self.thread_id, turn_id=self.turn_id,
                terminal_state="unknown" if self.ambiguous or not self._terminals else None, detail=reason,
            ))

    def respond(self, request_key: str, answers: Mapping[str, Any]) -> None:
        raise UnsupportedNativeOperation(
            "native evidence responses require a separately admitted live interaction; "
            "replayed request descriptions cannot authorize responses",
        )


class NativeInvestigationWorker:
    """Own one app-server, temporary cwd, and read-only native turn.

    The sandbox is a native execution policy, not a claim that only the selected
    packet is visible or that provider instructions and configured tools were
    fully captured. The constructor is a trusted-host interface.
    """

    MAX_OUTPUT_CHARS = 131_072

    def __init__(
        self, trace: TraceStore, command: Sequence[str] | None = None, *,
        execution_evidence: Literal["synthetic", "unverified"] = "unverified",
        client_factory: Callable[..., AppServerClient] | None = None,
        preparation: Callable[[NativePreparation], None] | None = None,
        preparation_timeout: float = 120,
    ) -> None:
        if execution_evidence not in {"synthetic", "unverified"}:
            raise ValueError("only synthetic or unverified custom execution evidence may be declared")
        self.trace = trace
        self._client_factory = client_factory
        if not math.isfinite(preparation_timeout) or preparation_timeout <= 0:
            raise ValueError("preparation timeout must be finite and positive")
        self.preparation, self.preparation_timeout = preparation, preparation_timeout
        # A trusted host may identify a synthetic fixture, but cannot declare
        # native model observation. Recovery uses this incarnation's recorded
        # admission evidence, never the current worker's constructor setting.
        self.execution_evidence = execution_evidence
        self.command = tuple(command) if command is not None else (
            "codex", "app-server", "--listen", "stdio://",
        )
        # The existing API supplies its native command explicitly. Treat that
        # spelling exactly like the default; an explicit argv is not itself an
        # exemption from pre-launch configuration admission. Other commands
        # remain a trusted-host fixture/probe seam, not an untrusted executor.
        native_command = command is None or (
            bool(self.command) and (
                Path(self.command[0]).name in {"codex", "codex.exe"}
                or (
                    "app-server" in self.command[1:]
                    and Path(self.command[0]).suffix != ".py"
                    and Path(self.command[0]).name != "env"
                )
            )
        )
        # The repository's EidosAPI demo passes an executable Python fixture
        # in the codex slot. Its .py command is explicit trusted-host testing,
        # just like a Python interpreter or disposable env-wrapped probe.
        self.execution_profile = NativeExecutionProfile(codex_binary=self.command[0]) if native_command else None
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
            raise NativeInvestigationError("native worker deadline expired; delivery or completion may be unknown", stop_reason="deadline")
        return remaining

    def run(
        self,
        attempt: Mapping[str, Any],
        context: Mapping[str, Any],
        update: Callable[..., None],
        *,
        on_event: Callable[[NativeSpecialistEvent], None] | None = None,
    ) -> dict[str, Any]:
        reason = "failed"
        try:
            artifact = self._run(attempt, context, update, on_event=on_event)
            reason = "completed"
            return artifact
        except Exception as exc:
            reason = "cancelled" if self._closed else getattr(exc, "stop_reason", "failed")
            raise
        finally:
            update(lifecycle={"phase": "closed", "stopReason": reason})

    def _run(
        self, attempt: Mapping[str, Any], context: Mapping[str, Any], update: Callable[..., None], *,
        on_event: Callable[[NativeSpecialistEvent], None] | None = None,
    ) -> dict[str, Any]:
        with self._clients_lock:
            if self._closed:
                raise NativeInvestigationError("native worker has been closed")
        timeout = min(120.0, float(attempt.get("timeoutSeconds", 120)))
        if timeout <= 0:
            raise ValueError("worker timeout must be positive")
        if attempt.get("contextId") != context.get("id"):
            raise ValueError("attempt names a different context")
        prompt = context.get("projectedPrompt")
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("context must contain the reviewed prompt")

        deadline = time.monotonic() + (self.preparation_timeout if self.preparation is not None else timeout)
        state = dict(attempt)
        events: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=512)
        errors: queue.Queue[Exception] = queue.Queue()
        stopped = threading.Event()
        expired = threading.Event()

        def active_remaining() -> float:
            with self._clients_lock:
                if self._closed:
                    raise NativeInvestigationError("owned worker was cancelled", stop_reason="cancelled")
            if expired.is_set():
                raise NativeInvestigationError("native worker deadline expired", stop_reason="deadline")
            return self._remaining(deadline)

        def remember(**fields: Any) -> None:
            update(**fields)
            state.update(fields)

        with tempfile.TemporaryDirectory(prefix="nema-investigation-") as cwd:
            client = (self._client_factory or AppServerClient)(
                self.command, trace=self.trace, cwd=cwd, source="nema-investigation",
            )
            # Persist the incarnation before process launch. A crash before the
            # subsequent native acknowledgement must remain visibly uncertain.
            remember(source=client.source)
            remember(lifecycle={"phase": "preparing"})
            adapter = NativeSpecialistAdapter(self.trace, state, context, client.source, on_event)
            closure_reason = "Owned worker transport closed; no pending native interaction is resumable."

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
                        adapter.refresh()
                        if "id" in event and "method" in event:
                            if adapter.refuse_once(event):
                                client.respond(event["id"], error={
                                    "code": -32000,
                                    "message": "Nema investigation does not support interactive native requests",
                                })
                                adapter.refresh()
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
                if self.execution_profile is not None:
                    try:
                        launch = self.execution_profile.prepare(cwd)
                        self.trace.append(source=client.source, direction="internal", message={
                            "method": "$native/profile", "params": {
                                "admission": "refused" if not launch.live_admitted else "admitted",
                                "profile": dict(launch.evidence),
                            },
                        })
                        adapter.refresh()
                        client.command = launch.command
                        client.env = dict(launch.env)
                        client.inherit_env = False
                        client.launch_guard = launch.require_live_admission
                        launch.require_live_admission()
                    except NativeExecutionProfileError as exc:
                        self.trace.append(source=client.source, direction="internal", message={
                            "method": "$native/profile", "params": {
                                "admission": "refused", "version": self.execution_profile.VERSION,
                                "reason": str(exc),
                            },
                        })
                        adapter.refresh()
                        raise NativeInvestigationError(f"native pre-launch admission refused: {exc}", status="failed") from exc
                else:
                    self.trace.append(source=client.source, direction="internal", message={
                        "method": "$native/profile", "params": {
                            "admission": "custom-command-trusted-host", "completeIsolation": False,
                            "executionEvidence": self.execution_evidence,
                            "reason": "Explicit custom command; no native execution profile is established.",
                        },
                    })
                    adapter.refresh()
                with self._clients_lock:
                    if self._closed:
                        raise NativeInvestigationError("native worker has been closed")
                    self._clients.add(client)
                    client.start()
                # request timeouts cannot interrupt a blocked stdin write.
                # An independent deadline closes our child even under native
                # backpressure; closing cannot relaunch this incarnation.
                def expire() -> None:
                    expired.set()
                    errors.put(NativeInvestigationError("native worker deadline expired; outcome may be unknown", stop_reason="deadline"))
                    client.close()
                watchdog = threading.Timer(self._remaining(deadline), expire)
                watchdog.daemon = True
                watchdog.start()
                reader = threading.Thread(target=pump, daemon=True, name="nema-investigation-events")
                reader.start()
                client.initialize(timeout=min(10.0, self._remaining(deadline)))
                if self.preparation is not None:
                    preparation = NativePreparation(client, events, errors, active_remaining,
                        lambda phase: remember(lifecycle={"phase": phase}))
                    try:
                        self.preparation(preparation)
                    finally:
                        preparation._finish()
                    active_remaining()
                    watchdog.cancel()
                    watchdog.join()
                    active_remaining()
                    deadline = time.monotonic() + timeout
                    watchdog = threading.Timer(timeout, expire)
                    watchdog.daemon = True
                    watchdog.start()
                if self.execution_profile is not None:
                    # The configured provider/login preference is not an
                    # acknowledgement of the account this process is using.
                    # Keep this before thread creation as well as model work.
                    try:
                        account = client.request("account/read", {
                            "refreshToken": False,
                        }, timeout=min(10.0, self._remaining(deadline)))
                        self.execution_profile.check_account(account)
                    except Exception as exc:
                        raise NativeInvestigationError(
                            f"native subscription admission failed: {exc}", status="failed",
                        ) from exc
                active_remaining()
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
                active_remaining()
                result = client.request("turn/start", {
                    "threadId": thread["id"],
                    "input": [{"type": "text", "text": prompt}],
                    "sandboxPolicy": dict(TURN_SANDBOX),
                    "environments": [],
                }, timeout=min(30.0, self._remaining(deadline)))
                turn = result.get("turn")
                if not isinstance(turn, dict) or not isinstance(turn.get("id"), str):
                    raise NativeInvestigationError("turn/start did not acknowledge a native turn")
                remember(turnId=turn["id"], status="running", lifecycle={"phase": "running"})

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
                if expired.is_set():
                    exc = NativeInvestigationError("native worker deadline expired; outcome may be unknown", stop_reason="deadline")
                if not isinstance(exc, NativeInvestigationError) and not errors.empty():
                    exc = errors.get_nowait()
                closure_reason = f"Local worker stopped: {type(exc).__name__}: {exc}. Native delivery/outcome may be unknown."
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
                adapter.refresh()
                adapter.close(closure_reason)
                with self._clients_lock:
                    self._clients.discard(client)

    @staticmethod
    def _execution_evidence(records: Sequence[TraceRecord], request_seq: int) -> str:
        """Classify historical output using only preceding host admissions.

        Child output, selected text, and later annotations cannot establish a
        model resource claim. Internal records are a trusted-host seam, not a
        security boundary against a caller that can alter the trace database.
        Unknown, missing, or contradictory admissions remain unverified.
        """
        classifications: set[str] = set()
        for record in records:
            if (record.direction != "internal" or record.method != "$native/profile"
                    or record.seq >= request_seq):
                continue
            params = record.message.get("params")
            if not isinstance(params, dict):
                classifications.add("unverified")
                continue
            if params.get("admission") == "custom-command-trusted-host":
                classifications.add(
                    "synthetic" if params.get("executionEvidence") == "synthetic" else "unverified"
                )
                continue
            profile = params.get("profile")
            admitted = (
                params.get("admission") == "admitted" and isinstance(profile, dict)
                and profile.get("version") == NativeExecutionProfile.VERSION
                and profile.get("binarySha256") == NativeExecutionProfile.BINARY_SHA256
                and profile.get("liveAdmitted") is True
            )
            classifications.add("native-observed" if admitted else "unverified")
        return next(iter(classifications)) if len(classifications) == 1 else "unverified"

    def recover(self, attempt: Mapping[str, Any], context: Mapping[str, Any]) -> dict[str, Any] | None:
        """Read matching native evidence, including acknowledgements not mapped locally."""
        if attempt.get("contextId") != context.get("id"):
            raise ValueError("attempt names a different context")
        source = attempt.get("source")
        if not isinstance(source, str):
            return None
        records = [record for record in self.trace.records() if record.source == source]
        # A stopped incarnation cannot regain contiguous evidence through a later
        # import. Preserve any accepted terminal before the gap, while excluding
        # later frames from both completion and contradiction checks.
        gap = next((record.seq for record in records if _is_capture_gap(record)), None)
        if gap is not None:
            records = [record for record in records if record.seq < gap]
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
        # Recovery can establish the historical thread from the one validated
        # outbound request even if the local mapping/acknowledgement was lost.
        # This never makes a reconstructed interaction answerable.
        adapter = NativeSpecialistAdapter(self.trace, {**attempt, "threadId": thread_id}, context, source)
        adapter.refresh()
        if adapter.ambiguous:
            raise NativeInvestigationError("native interaction or terminal evidence is contradictory")

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
                if "id" in message:
                    raise NativeInvestigationError(
                        "native terminal event is an RPC request, not a completion notification"
                    )
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
                if "id" in record.message:
                    raise NativeInvestigationError(
                        "native completed item is an RPC request, not a completion notification"
                    )
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
            "executionEvidence": self._execution_evidence(records, request.seq),
            "outputSeqs": sorted({entry[2] for entry in selected}),
            "citations": sorted(cited & available),
            "unsupportedCitations": sorted(cited - available),
        }
