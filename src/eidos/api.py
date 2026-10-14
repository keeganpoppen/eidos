from __future__ import annotations

from dataclasses import asdict
import json
import os
from pathlib import Path
import threading
import time
import uuid
from typing import Any, Mapping, Sequence
from urllib.parse import unquote

from .codex import AppServerClient, CodexPlace
from .investigation import InvestigationError, InvestigationStore
from .investigation_continuations import InvestigationContinuations
from .investigation_inquiries import terminal_inquiry
from .investigation_experiments import InvestigationExperiments
from .investigation_reads import InvestigationReads
from .compositions import Compositions
from .history import (
    PAGE_SIZE, SourceRecordNotFound, history_snapshot, history_version,
    history_window, thread_preview, window_records,
)
from .semantic_tree import SemanticTreeBuilder
from .trace import TraceStore
from .private_investigation import PrivateInvestigationWorker
from .native_managed_contract import DEVICE_VERIFICATION_URL
from .view import ItemView, project_records


def _json_body(handler: Any, *, max_bytes: int = 256 * 1024) -> dict[str, Any]:
    length = int(handler.headers.get("Content-Length", "0") or 0)
    if length < 0 or length > max_bytes:
        raise ValueError(f"request body must be at most {max_bytes // 1024} KiB")
    if not length:
        return {}
    raw = handler.rfile.read(length)
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("request body must be a JSON object")
    return value


def _item_bounds(item: ItemView) -> tuple[int, int]:
    if not item.events:
        return (0, 0)
    return min(event.seq for event in item.events), max(event.seq for event in item.events)


def _join_deltas(item: ItemView, method: str) -> str:
    chunks: list[str] = []
    for event in item.events:
        if event.method != method:
            continue
        params = event.message.get("params")
        if isinstance(params, Mapping) and isinstance(params.get("delta"), str):
            chunks.append(str(params["delta"]))
    return "".join(chunks)


def _reasoning_parts(item: ItemView, *, summary: bool) -> list[str]:
    raw = item.final_item or {}
    key = "summary" if summary else "content"
    final = raw.get(key)
    if isinstance(final, list) and final:
        return [str(value) for value in final]

    prefix = "item/reasoning/summary" if summary else "item/reasoning/text"
    index_key = "summaryIndex" if summary else "contentIndex"
    parts: dict[int, str] = {}
    for event in item.events:
        if not event.method or not event.method.startswith(prefix):
            continue
        params = event.message.get("params")
        if not isinstance(params, Mapping) or not isinstance(params.get(index_key), int):
            continue
        index = int(params[index_key])
        parts.setdefault(index, "")
        if isinstance(params.get("delta"), str):
            parts[index] += str(params["delta"])
    return [parts[index] for index in sorted(parts) if parts[index]]


def _project_item(item: ItemView) -> dict[str, Any] | None:
    raw = item.final_item or {}
    kind = item.item_type or str(raw.get("type") or "item")
    start, end = _item_bounds(item)
    projected: dict[str, Any] = {
        "id": item.item_id,
        "type": kind,
        "startSeq": start,
        "endSeq": end,
        "recordSeqs": [event.seq for event in item.events],
        "complete": any(event.method in {"item/completed", "$history/item"} for event in item.events),
        "raw": raw,
    }
    if kind == "privateResultPublication":
        projected["text"] = raw["text"]
        projected["complete"] = True
        projected["provenance"] = raw["provenance"]
    elif kind == "agentMessage":
        text = raw.get("text")
        if not isinstance(text, str) or not text:
            text = _join_deltas(item, "item/agentMessage/delta")
        projected["text"] = text or ""
        projected["phase"] = raw.get("phase")
    elif kind == "reasoning":
        summary = _reasoning_parts(item, summary=True)
        content = _reasoning_parts(item, summary=False)
        if not summary and not content:
            return None
        projected["summary"] = summary
        projected["content"] = content
    elif kind == "commandExecution":
        projected["command"] = str(raw.get("command") or "")
        output = raw.get("aggregatedOutput")
        if not isinstance(output, str) or not output:
            output = _join_deltas(item, "item/commandExecution/outputDelta")
        projected["output"] = output or ""
        projected["status"] = raw.get("status")
        projected["exitCode"] = raw.get("exitCode")
    elif kind == "fileChange":
        projected["changes"] = raw.get("changes") or []
        projected["status"] = raw.get("status")
    elif kind == "userMessage":
        projected["content"] = raw.get("content") or []
    elif kind in {"mcpToolCall", "dynamicToolCall", "collabAgentToolCall", "functionCallOutput", "webSearch"}:
        projected["detail"] = raw
    return projected


def _thread_preview(store: TraceStore, thread_id: str) -> str:
    return thread_preview(store, thread_id)


def thread_payload(
    store: TraceStore, thread_id: str, *, revision_id: str | None = None,
    anchor_seq: int | None = None, around_seq: int | None = None,
    limit: int = PAGE_SIZE, known_version: str | None = None,
) -> dict[str, Any]:
    store.require_workbench()
    with history_snapshot(store):
        selected, window, summary = history_window(
            store, thread_id, anchor_seq=anchor_seq, around_seq=around_seq, limit=limit,
        )
        revisions = store.semantic_revisions(thread_id, lens="thread")
        if revision_id is not None and not any(row["revision_id"] == revision_id for row in revisions):
            raise SourceRecordNotFound("That semantic revision does not belong to this thread's history map.")
        version = history_version(thread_id, revision_id, summary, revisions, window, selected)
        if known_version == version:
            return {"id": thread_id, "unchanged": True, "version": version, "window": window}
        view = project_records(thread_id, window_records(store, thread_id, selected))
        outline = store.semantic_outline(thread_id, revision_id=revision_id)
        preview = _thread_preview(store, thread_id)
    turns: list[dict[str, Any]] = []
    for turn in view.turns:
        seqs = [event.seq for event in turn.events]
        turns.append(
            {
                "id": turn.turn_id,
                "inputs": turn.inputs,
                "items": [
                    projected
                    for item in turn.items.values()
                    if (projected := _project_item(item)) is not None
                ],
                "startSeq": min(seqs) if seqs else 0,
                "endSeq": max(seqs) if seqs else 0,
                "recordSeqs": seqs,
                "eventCount": len(turn.events),
            }
        )
    return {
        "id": thread_id,
        "preview": preview,
        "turns": turns,
        "outline": outline,
        "revisions": revisions,
        **summary,
        "version": version,
        "window": window,
    }


class LiveCodex:
    """One lazily-started app-server evaluator for interactive Eidos chat."""

    def __init__(
        self,
        store: TraceStore,
        *,
        codex: str = "codex",
        command: Sequence[str] | None = None,
    ) -> None:
        self.store = store
        self.codex = codex
        self.command = tuple(command) if command is not None else (
            codex,
            "app-server",
            "--listen",
            "stdio://",
        )
        self._lock = threading.RLock()
        self._client: AppServerClient | None = None
        self._place: CodexPlace | None = None
        self._loaded: set[str] = set()
        self._pump: threading.Thread | None = None

    def _ensure_started(self) -> CodexPlace:
        with self._lock:
            if self._place is not None:
                return self._place
            client = AppServerClient(
                self.command,
                trace=self.store,
                source="codex-live",
            )
            client.start()
            place = CodexPlace("live", client).start()
            self._client = client
            self._place = place
            self._pump = threading.Thread(target=self._pump_events, daemon=True, name="eidos-live-events")
            self._pump.start()
            return place

    def _pump_events(self) -> None:
        client = self._client
        if client is None:
            return
        while True:
            try:
                event = client.recv_event(timeout=1.0)
            except TimeoutError:
                if client.process is None:
                    return
                continue
            except Exception:
                return

            # For this first chat slice we intentionally run with approvals
            # disabled and do not fabricate answers to interactive server
            # requests. Explicitly reject any that still arrive so Codex can
            # observe a failed request rather than hanging forever. Both sides
            # of the exchange are persisted by AppServerClient.
            if "id" in event and "method" in event:
                client.respond(
                    event["id"],
                    error={
                        "code": -32000,
                        "message": (
                            "Eidos live chat does not yet support interactive "
                            f"server request {event['method']!r}"
                        ),
                    },
                )
                continue

    def start_thread(self, *, cwd: str | None = None) -> str:
        place = self._ensure_started()
        params: dict[str, Any] = {
            "cwd": cwd or os.getcwd(),
            "approvalPolicy": "never",
            "sandbox": "workspace-write",
            "threadSource": "eidos-live",
        }
        thread_id = place.start_thread(**params)
        with self._lock:
            self._loaded.add(thread_id)
        return thread_id

    def _ensure_thread(self, thread_id: str) -> None:
        place = self._ensure_started()
        with self._lock:
            if thread_id in self._loaded:
                return
        place.resume_thread(
            thread_id,
            approvalPolicy="never",
            sandbox="workspace-write",
        )
        with self._lock:
            self._loaded.add(thread_id)

    def send(self, thread_id: str, text: str) -> str:
        self._ensure_thread(thread_id)
        assert self._client is not None
        result = self._client.turn_start_text(
            thread_id,
            text,
            summary="detailed",
        )
        turn = result.get("turn")
        if not isinstance(turn, Mapping) or not isinstance(turn.get("id"), str):
            raise ValueError(f"turn/start returned no turn id: {result!r}")
        return str(turn["id"])

    def close(self) -> None:
        with self._lock:
            if self._client is not None:
                self._client.close()
            self._client = None
            self._place = None
            self._loaded.clear()


class EidosAPI:
    def __init__(self, store: TraceStore, *, codex: str = "codex", managed_native: bool = False) -> None:
        store.require_workbench()
        self.store = store
        self.codex = codex
        self.live = LiveCodex(store, codex=codex)
        self._jobs: dict[str, dict[str, Any]] = {}
        self._jobs_lock = threading.RLock()
        self.investigations = InvestigationStore(store)
        self.investigation_reads = InvestigationReads(self.investigations)
        self.investigation_experiments = InvestigationExperiments(self.investigations)
        self.compositions = Compositions(self.investigations)
        self.investigation_continuations = InvestigationContinuations(self.investigations)
        self.investigation_runtime = self.investigation_continuations.runtime
        if managed_native:
            from .native_managed import ManagedExecutionProfile
            self.investigation_worker = PrivateInvestigationWorker(store, managed_profile=ManagedExecutionProfile(binary=codex))
        else:
            self.investigation_worker = PrivateInvestigationWorker(
                store, command=[codex, "app-server", "--listen", "stdio://"],
                execution_evidence=("synthetic" if Path(codex).resolve() ==
                    Path(__file__).resolve().parents[2] / "tests/fixtures/investigation_appserver.py" else "unverified"),
            )
        self._investigation_lock = threading.RLock()
        self._investigation_threads: dict[str, threading.Thread] = {}
        self._closing = False
        # A controller restart can recover recorded completion, but cannot
        # infer delivery or silently relaunch an old external operation.
        for investigation in self.investigations.list():
            attempt = investigation["attempt"]
            if attempt and attempt.get("contextRequestName"):
                self.investigations.reconcile_context(investigation["id"])
            if (attempt is not None and attempt["status"] in {"dispatching", "running", "unknown", "completed"}) or investigation.get("continuation") is not None:
                try:
                    self.recover_investigation(investigation["id"])
                except InvestigationError as exc:
                    if exc.status != 409 or investigation.get("continuation") is None:
                        raise
                    # A descriptive/historical row without its admitted link is
                    # inspectable, but cannot block recovery of other work or
                    # acquire authority by being present during startup.
                    with self.investigations._transaction():
                        current = self.investigations._load(investigation["id"])
                        current["continuation"]["error"] = exc.message
                        self.investigations._save(current)

    def close(self) -> None:
        self._closing = True
        self.live.close()
        self.investigation_worker.close()
        # Keep the trace connection alive until cancellation callbacks stop.
        with self._investigation_lock:
            workers = list(self._investigation_threads.values())
        for worker in workers:
            worker.join()
        finalize = getattr(self.investigation_worker, "close_evidence", None)
        if callable(finalize):
            finalize()

    def _investigation_error(self, exc: Exception) -> str:
        public_error = getattr(self.investigation_worker, "public_error", None)
        if callable(public_error):
            return public_error(exc)
        return f"{type(exc).__name__}: {exc}"[:4000]

    def dispatch(self, handler: Any, method: str, path: str, query: dict[str, list[str]]) -> tuple[int, Any]:
        parts = [unquote(part) for part in path.split("/") if part]
        if parts[:2] == ["api", "compositions"]:
            try:
                if len(parts) == 2:
                    if method == "GET":
                        return 200, self.compositions.list(query)
                    if method == "POST":
                        if query:
                            raise InvestigationError(400, "saving an arrangement takes no query parameters")
                        return 201, {"composition": self.compositions.create(_json_body(handler, max_bytes=16 * 1024))}
                if len(parts) == 3 and method == "GET":
                    if query:
                        raise InvestigationError(400, "saved arrangement detail takes no query parameters")
                    return 200, {"composition": self.compositions.get(parts[2])}
                return 404, {"error": "not found"}
            except InvestigationError as exc:
                return exc.status, {"error": exc.message}
            except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
                return 400, {"error": str(exc)}
        if parts[:2] == ["api", "investigations"]:
            try:
                return self._dispatch_investigation(handler, method, parts, query)
            except InvestigationError as exc:
                return exc.status, {"error": exc.message}
            except (ValueError, TypeError) as exc:
                return 400, {"error": str(exc)}
        if parts == ["api", "health"] and method == "GET":
            return 200, {"ok": True}

        # Legacy chat/index controls use a different adapter from the bounded
        # investigation worker. A synthetic investigation capability must not
        # accidentally authorize that adapter to spend live model resources.
        if method == "POST" and (parts == ["api", "threads"] or
                len(parts) == 4 and parts[:2] == ["api", "threads"] and parts[3] in {"messages", "observe"}):
            return 409, {"error": self.investigation_capabilities()["legacyLiveActions"]["reason"]}

        if parts == ["api", "threads"]:
            if method == "GET":
                rows = []
                for thread in self.store.threads():
                    thread_id = str(thread["thread_id"])
                    rows.append(
                        {
                            **thread,
                            "preview": _thread_preview(self.store, thread_id),
                            "hasSemanticMap": self.store.semantic_outline(thread_id) is not None,
                        }
                    )
                return 200, {"threads": rows}
            if method == "POST":
                body = _json_body(handler)
                thread_id = self.live.start_thread(cwd=body.get("cwd") if isinstance(body.get("cwd"), str) else None)
                return 201, {"threadId": thread_id}

        if len(parts) >= 3 and parts[:2] == ["api", "threads"]:
            thread_id = parts[2]
            if len(parts) == 3 and method == "GET":
                revision = query.get("revision", [None])[0]
                try:
                    def integer(name: str, default: int | None = None) -> int | None:
                        values = query.get(name)
                        if values is None:
                            return default
                        if len(values) != 1 or not values[0].isascii() or not values[0].isdecimal():
                            raise ValueError(f"{name} must be one positive integer")
                        value = int(values[0])
                        if not 1 <= value <= 2**53 - 1:
                            raise ValueError(f"{name} must be a positive safe integer")
                        return value
                    return 200, thread_payload(
                        self.store, thread_id, revision_id=revision,
                        anchor_seq=integer("anchorSeq"), around_seq=integer("aroundSeq"),
                        limit=integer("limit", PAGE_SIZE),  # type: ignore[arg-type]
                        known_version=query.get("knownVersion", [None])[0],
                    )
                except SourceRecordNotFound as exc:
                    return 404, {"error": str(exc)}
                except ValueError as exc:
                    return 400, {"error": str(exc)}
            if len(parts) == 4 and parts[3] == "messages" and method == "POST":
                body = _json_body(handler)
                text = body.get("text")
                if not isinstance(text, str) or not text.strip():
                    return 400, {"error": "text is required"}
                turn_id = self.live.send(thread_id, text.strip())
                return 202, {"turnId": turn_id}
            if len(parts) == 4 and parts[3] == "observe" and method == "POST":
                body = _json_body(handler)
                job_id = self.start_observer(
                    thread_id,
                    max_windows=int(body.get("maxWindows", 0) or 0),
                    effort=str(body.get("effort") or "low"),
                )
                return 202, {"jobId": job_id}

        if len(parts) == 3 and parts[:2] == ["api", "jobs"] and method == "GET":
            job = self.job(parts[2])
            if job is None:
                return 404, {"error": "job not found"}
            return 200, job

        return 404, {"error": "not found"}

    def _dispatch_investigation(self, handler: Any, method: str, parts: list[str], query: dict[str, list[str]]) -> tuple[int, Any]:
        if parts == ["api", "investigations", "capabilities"] and method == "GET":
            return 200, self.investigation_capabilities()
        if len(parts) == 3 and parts[2] in {"catalog", "artifacts"} and method == "GET":
            return 200, self.investigation_reads.catalog(query, artifacts=parts[2] == "artifacts")
        if len(parts) == 2:
            if method == "GET":
                return 200, {"investigations": self.investigations.list()}
            if method == "POST":
                return 201, self.investigations.create(_json_body(handler))
        if len(parts) == 3 and method == "GET":
            return 200, self.investigations.get(parts[2])
        if len(parts) == 4 and parts[3] == "view" and method == "GET":
            return 200, self.investigation_reads.view(parts[2], query)
        if len(parts) == 6 and parts[3] == "artifacts" and parts[5] == "source" and method == "GET":
            return 200, self.investigation_reads.source(parts[2], parts[4], query)
        if len(parts) == 6 and parts[3] == "attempts" and parts[5] == "control":
            if method == "GET":
                return 200, self.attempt_control(parts[2], parts[4])
            if method == "POST":
                if _json_body(handler) != {"action": "cancel"}:
                    raise ValueError("attempt control requires only action=cancel")
                return 200, self.cancel_attempt(parts[2], parts[4])
        if len(parts) == 4 and parts[3] == "experiments":
            if method == "GET":
                return 200, self.investigation_experiments.list(parts[2])
            if method == "POST":
                return 201, self.investigation_experiments.create(parts[2], _json_body(handler))
        if len(parts) == 5 and parts[3] == "experiments" and method == "GET":
            return 200, self.investigation_experiments.get(parts[2], parts[4])
        if (len(parts) == 6 and parts[3] == "experiments" and method == "POST"
                and parts[5] in {"review", "rollback"}):
            return 200, self.investigation_experiments.decide(parts[2], parts[4], parts[5], _json_body(handler))
        if len(parts) == 4 and parts[3] == "context-lineage" and method == "GET":
            return 200, self.investigations.context_lineage(parts[2])
        if len(parts) == 6 and parts[3] == "contexts" and parts[5] == "manifest" and method == "GET":
            return 200, self.investigations.context_manifest(parts[2], parts[4])
        if len(parts) == 5 and parts[3] == "inquiries" and method == "GET":
            return 200, self.investigation_continuations.inquiry(parts[2], parts[4])
        if len(parts) == 6 and parts[3] == "inquiries" and parts[5] == "responses" and method == "POST":
            value = self.investigation_continuations.respond(parts[2], parts[4], _json_body(handler))
            return 200, self._prepare_inquiry_followup(value)
        if len(parts) == 6 and parts[3] == "inquiries" and parts[5] == "cancel" and method == "POST":
            return 200, self.investigation_continuations.cancel(parts[2], parts[4], _json_body(handler))
        if len(parts) == 4 and method == "POST":
            body = _json_body(handler)
            identifier, action = parts[2:]
            if action == "contexts":
                return 201, self.investigations.revise(identifier, body)
            if action == "dispatch":
                if set(body) != {"contextId"} or not isinstance(body["contextId"], str):
                    raise ValueError("dispatch requires only the reviewed contextId")
                return 202, self.start_investigation(identifier, body["contextId"])
            if action == "recover":
                if body:
                    raise ValueError("recovery takes no execution parameters")
                return 200, self.recover_investigation(identifier)
            if action == "adoption":
                return 200, self.investigations.adopt(identifier, body)
            if action == "continuation":
                return 202, self.investigation_continuations.open(identifier, body)
            if action == "continue":
                return 202, self.continue_investigation(identifier, body)
            if action == "resume":
                if body:
                    raise ValueError("resume takes no execution parameters")
                return 200, self.resume_investigation(identifier)
        return 404, {"error": "not found"}

    def investigation_capabilities(self) -> dict[str, Any]:
        worker = self.investigation_worker
        native = worker.execution_profile is not None
        managed = getattr(worker, "managed_profile", None) is not None
        return {"schemaVersion": 1, "nativeExecution": {
            "available": not native,
            "mode": "native" if native or managed else ("synthetic" if worker.execution_evidence == "synthetic" else "unverified"),
            "reason": (
                "Each attempt needs a fresh ChatGPT Plus or Pro sign-in. Sign-in is limited to three minutes; work to two minutes. "
                "Starting work uses the signed-in account's available model allowance."
                if managed else
                "Live model execution is unavailable: account-backed cloud configuration may refresh during startup; "
                "containment is unverified. A separate resource authorization and admitted profile are required."
                if native else "Explicit trusted-host test adapter; no native execution authority is implied."),
        }, "specialistInquiry": {"mode": "terminal-needs-evidence", "interactive": False},
            "legacyLiveActions": {"available": False, "reason":
                "Live chat and model-backed indexing require separate resource authorization and an admitted native profile."}}

    def start_investigation(self, identifier: str, context_id: str) -> dict[str, Any]:
        with self._investigation_lock:
            if self._closing:
                raise InvestigationError(409, "controller is shutting down")
            investigation = self.investigations.get(identifier)
            if investigation["attempt"] is None and self.investigation_worker.execution_profile is not None:
                raise InvestigationError(409, self.investigation_capabilities()["nativeExecution"]["reason"])
            # Bound process-local admission. The durable claim additionally
            # serializes attempts for this investigation across connections.
            if investigation["attempt"] is None and any(
                thread.is_alive() for thread in self._investigation_threads.values()
            ):
                raise InvestigationError(409, "another investigation worker is running")
            investigation, claimed = self.investigations.claim(identifier, context_id)
            if not claimed:
                return investigation
            return self._launch_investigation(investigation)

    def continue_investigation(self, identifier: str, body: Mapping[str, Any]) -> dict[str, Any]:
        with self._investigation_lock:
            if self._closing:
                raise InvestigationError(409, "controller is shutting down")
            current = self.investigations.get(identifier)
            # Exact retries of admitted work are pure recovery reads, even if
            # the original worker is still running.
            next_attempt = (current.get("continuation") or {}).get("nativeNext", {}).get("attemptId")
            if next_attempt is None and self.investigation_worker.execution_profile is not None:
                raise InvestigationError(409, self.investigation_capabilities()["nativeExecution"]["reason"])
            if next_attempt is None and any(t.is_alive() for t in self._investigation_threads.values()):
                raise InvestigationError(409, "another investigation worker is running")
            investigation, claimed = self.investigations.claim_followup(identifier, body)
            if not claimed:
                return investigation
            return self._launch_investigation(investigation)

    def _launch_investigation(self, investigation: dict[str, Any]) -> dict[str, Any]:
        identifier = investigation["id"]
        attempt_id = investigation["attempt"]["id"]
        context = next(value for value in investigation["contexts"] if value["id"] == investigation["attempt"]["contextId"])

        def run() -> None:
            try:
                artifact = self.investigation_worker.run(
                    investigation["attempt"], context,
                    lambda **fields: self.investigations.update_attempt(identifier, expected_attempt_id=attempt_id, **fields),
                )
                self.investigations.complete(identifier, artifact, expected_attempt_id=attempt_id)
                self._admit_native_inquiry(identifier)
            except Exception as exc:
                status = "failed" if getattr(exc, "status", None) == "failed" else "unknown"
                self.investigations.update_attempt(
                    identifier, expected_attempt_id=attempt_id, status=status, error=self._investigation_error(exc),
                )
            finally:
                self.investigations.reconcile_context(identifier)

        worker = threading.Thread(target=run, daemon=True, name=f"nema-investigation-{identifier[-8:]}")
        self._investigation_threads[identifier] = worker
        try:
            reserve = getattr(self.investigation_worker, "reserve", None)
            if callable(reserve):
                reserve(attempt_id)
            worker.start()
        except Exception as exc:
            if worker.ident is None:
                self._investigation_threads.pop(identifier, None)
                cancel = getattr(self.investigation_worker, "cancel", None)
                if callable(cancel):
                    cancel(attempt_id)
            self.investigations.update_attempt(identifier, expected_attempt_id=attempt_id, status="unknown", error=self._investigation_error(exc))
            raise
        return investigation

    def attempt_control(self, identifier: str, attempt_id: str) -> dict[str, Any]:
        """Describe this host's current ownership; persisted names grant none."""
        with self._investigation_lock:
            investigation = self.investigations.get(identifier)
            attempt = investigation["attempt"]
            if attempt is None or attempt["id"] != attempt_id:
                raise InvestigationError(404, "attempt not found in the current investigation")
            inspect = getattr(self.investigation_worker, "inspect_owned", None)
            state = inspect(attempt_id) if callable(inspect) else {}
            control = {"attemptId": attempt_id, "owned": state.get("owned") is True,
                       "canCancel": state.get("owned") is True and state.get("canCancel") is True}
            challenge = state.get("signIn")
            if (control["owned"] and control["canCancel"] and isinstance(challenge, dict)
                    and challenge.get("verificationUrl") == DEVICE_VERIFICATION_URL
                    and isinstance(challenge.get("userCode"), str) and 0 < len(challenge["userCode"]) <= 128
                    and all(32 <= ord(c) < 127 for c in challenge["userCode"])
                    and type(challenge.get("expiresAtMs")) is int
                    and challenge["expiresAtMs"] > int(time.time() * 1000)):
                control["signIn"] = {key: challenge[key] for key in ("verificationUrl", "userCode", "expiresAtMs")}
            return control

    def cancel_attempt(self, identifier: str, attempt_id: str) -> dict[str, Any]:
        with self._investigation_lock:
            control = self.attempt_control(identifier, attempt_id)
            if control["owned"]:
                cancel = getattr(self.investigation_worker, "cancel", None)
                if callable(cancel):
                    try:
                        cancel(attempt_id)
                    except Exception:
                        raise InvestigationError(503, "Attempt stop was not confirmed; retry this same attempt.") from None
            return {"investigation": self.investigations.get(identifier),
                    "control": self.attempt_control(identifier, attempt_id)}

    def recover_investigation(self, identifier: str) -> dict[str, Any]:
        investigation = self._recover_native_investigation(identifier)
        self.investigations.reconcile_context(identifier)
        investigation = self._admit_native_inquiry(identifier)
        if (investigation.get("continuation") is not None
                and investigation["continuation"]["status"] != "cancelled"):
            return self.resume_investigation(identifier)
        return self.investigations.get(identifier)

    def resume_investigation(self, identifier: str) -> dict[str, Any]:
        value = self.investigation_continuations.resume(identifier)
        return self._prepare_inquiry_followup(value)

    def _prepare_inquiry_followup(self, investigation: dict[str, Any]) -> dict[str, Any]:
        continuation = investigation.get("continuation")
        if (not continuation or continuation["origin"] != "native-specialist"
                or continuation["status"] != "completed"):
            return investigation
        try:
            return self.investigations.prepare_followup(investigation["id"])
        except InvestigationError as exc:
            with self.investigations._transaction():
                current = self.investigations._load(investigation["id"])
                current["continuation"]["nativeNext"]["error"] = exc.message
                self.investigations._save(current)
                return current

    def _admit_native_inquiry(self, identifier: str) -> dict[str, Any]:
        """Interpret recorded output only; recovery never sends a native turn."""
        investigation = self.investigations.get(identifier)
        if investigation.get("continuation") is not None:
            if investigation.get("attemptHistory") and (investigation.get("artifact") or {}).get("kind") in {
                "native-needs-evidence", "native-inquiry-invalid",
            }:
                with self.investigations._transaction():
                    current = self.investigations._load(identifier)
                    current["inquiryAdmissionError"] = (
                        "This investigation supports one specialist inquiry and one explicit follow-up attempt. "
                        "The follow-up still needs evidence; no further native attempt was admitted."
                    )
                    self.investigations._save(current)
                    return current
            return investigation
        try:
            observation = terminal_inquiry(self.investigations, identifier, self.investigation_worker)
            if observation is not None:
                investigation = self.investigation_continuations.open_specialist(identifier, observation)
            return investigation
        except (ValueError, InvestigationError) as exc:
            with self.investigations._transaction():
                current = self.investigations._load(identifier)
                current["inquiryAdmissionError"] = str(exc)[:4000]
                self.investigations._save(current)
                return current

    def _recover_native_investigation(self, identifier: str) -> dict[str, Any]:
        investigation = self.investigations.get(identifier)
        attempt = investigation["attempt"]
        if attempt is None or attempt["status"] in {"completed", "failed"}:
            return investigation
        context = next(value for value in investigation["contexts"] if value["id"] == attempt["contextId"])
        try:
            artifact = self.investigation_worker.recover(attempt, context)
            if artifact is not None:
                # The native acknowledgement may have been recorded before a
                # mapping callback committed. Restore navigation from the
                # already-verified output, without consulting native state.
                output = [self.store.get(seq) for seq in artifact["outputSeqs"]]
                mappings: dict[str, str] = {}
                for field, attribute in (("threadId", "thread_id"), ("turnId", "turn_id")):
                    values = {getattr(record, attribute) for record in output}
                    if attempt[field] is None and len(values) == 1 and None not in values:
                        mappings[field] = values.pop()
                if mappings:
                    self.investigations.update_attempt(identifier, expected_attempt_id=attempt["id"], **mappings)
                return self.investigations.complete(identifier, artifact, expected_attempt_id=attempt["id"])
        except Exception as exc:
            status = "failed" if getattr(exc, "status", None) == "failed" else "unknown"
            return self.investigations.update_attempt(identifier, expected_attempt_id=attempt["id"], status=status, error=self._investigation_error(exc))
        with self._investigation_lock:
            worker = self._investigation_threads.get(identifier)
            if worker is not None and worker.is_alive():
                return self.investigations.get(identifier)
        return self.investigations.update_attempt(
            identifier, expected_attempt_id=attempt["id"], status="unknown",
            error="No recorded terminal outcome. This attempt will not be sent again.",
        )

    def job(self, job_id: str) -> dict[str, Any] | None:
        with self._jobs_lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            copy = dict(job)
            copy["events"] = [dict(event) for event in job.get("events", [])]
            return copy

    def start_observer(
        self,
        thread_id: str,
        *,
        max_windows: int,
        effort: str,
    ) -> str:
        # max_windows/effort are retained in the API shape for compatibility.
        # The tree builder owns its own deliberately asymmetric effort policy:
        # low leaf enrichment, medium synthesis.
        job_id = f"job_{uuid.uuid4().hex}"
        with self._jobs_lock:
            now = int(time.time() * 1000)
            self._jobs[job_id] = {
                "id": job_id,
                "threadId": thread_id,
                "status": "queued",
                "createdAtMs": now,
                "startedAtMs": None,
                "completedAtMs": None,
                "lastProgressAtMs": now,
                "phase": "queued",
                "current": 0,
                "total": 0,
                "currentWindow": 0,
                "totalWindows": 0,
                "horizonSeq": None,
                "detail": "queued retrospective tree build",
                "model": None,
                "effort": "low→medium",
                "revisions": [],
                "events": [],
                "error": None,
            }

        def append_event(
            job: dict[str, Any],
            *,
            stage: str,
            current: int,
            total: int,
            detail: str,
            now: int,
        ) -> None:
            started = job.get("startedAtMs") or job["createdAtMs"]
            events = job.setdefault("events", [])
            events.append(
                {
                    "seq": len(events) + 1,
                    "atMs": now,
                    "elapsedMs": max(0, now - int(started)),
                    "stage": stage,
                    "current": int(current),
                    "total": int(total),
                    "detail": detail,
                }
            )
            # Enough for a very long build while keeping job payloads bounded.
            if len(events) > 500:
                del events[:-500]

        def update_progress(stage: str, current: int, total: int, detail: str) -> None:
            with self._jobs_lock:
                now = int(time.time() * 1000)
                job = self._jobs[job_id]
                job["phase"] = stage
                job["current"] = int(current)
                job["total"] = int(total)
                # Backwards-compatible fields consumed by the current UI type.
                job["currentWindow"] = int(current)
                job["totalWindows"] = int(total)
                job["lastProgressAtMs"] = now
                job["detail"] = detail
                append_event(
                    job,
                    stage=stage,
                    current=current,
                    total=total,
                    detail=detail,
                    now=now,
                )

        def run() -> None:
            with self._jobs_lock:
                now = int(time.time() * 1000)
                job = self._jobs[job_id]
                job["status"] = "running"
                job["startedAtMs"] = now
                job["lastProgressAtMs"] = now
                job["detail"] = "starting semantic tree"
                append_event(
                    job,
                    stage="start",
                    current=0,
                    total=1,
                    detail="starting semantic tree",
                    now=now,
                )

            try:
                builder = SemanticTreeBuilder(
                    self.store,
                    command=[self.codex, "app-server", "--listen", "stdio://"],
                )
                result = builder.build(thread_id, progress=update_progress)
                with self._jobs_lock:
                    now = int(time.time() * 1000)
                    job = self._jobs[job_id]
                    job["status"] = "completed"
                    job["phase"] = "completed"
                    job["revisions"] = [result.revision_id]
                    job["model"] = (
                        f"leaf={result.model or 'default'}; "
                        f"synthesis={result.synthesis_model or 'default'}"
                    )
                    job["effort"] = (
                        f"{result.leaf_effort} leaves → "
                        f"{result.synthesis_effort} synthesis"
                    )
                    job["completedAtMs"] = now
                    job["lastProgressAtMs"] = now
                    job["detail"] = (
                        f"tree committed · {result.leaf_windows} windows · "
                        f"{result.leaf_episodes} surviving episodes · "
                        f"{result.levels} rollup levels"
                    )
                    append_event(
                        job,
                        stage="done",
                        current=1,
                        total=1,
                        detail=job["detail"],
                        now=now,
                    )
            except Exception as exc:
                with self._jobs_lock:
                    now = int(time.time() * 1000)
                    job = self._jobs[job_id]
                    job["status"] = "failed"
                    job["phase"] = "failed"
                    job["error"] = f"{type(exc).__name__}: {exc}"
                    job["completedAtMs"] = now
                    job["lastProgressAtMs"] = now
                    job["detail"] = "semantic tree build failed"
                    append_event(
                        job,
                        stage="failed",
                        current=0,
                        total=1,
                        detail=job["error"],
                        now=now,
                    )

        threading.Thread(
            target=run,
            daemon=True,
            name=f"eidos-semantic-tree-{job_id[-8:]}",
        ).start()
        return job_id
