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
from .semantic_tree import SemanticTreeBuilder
from .trace import TraceStore
from .view import ItemView, project_thread


def _json_body(handler: Any) -> dict[str, Any]:
    length = int(handler.headers.get("Content-Length", "0") or 0)
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
        "complete": any(event.method in {"item/completed", "$history/item"} for event in item.events),
        "raw": raw,
    }
    if kind == "agentMessage":
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
    for record in store.records(thread_id=thread_id):
        message = record.message
        params = message.get("params")
        if record.method == "turn/start" and isinstance(params, Mapping):
            for value in params.get("input") or []:
                if isinstance(value, Mapping) and value.get("type") == "text" and value.get("text"):
                    return str(value["text"])[:100]
        if record.method in {"item/completed", "$history/item"} and isinstance(params, Mapping):
            item = params.get("item")
            if isinstance(item, Mapping) and item.get("type") == "userMessage":
                for value in item.get("content") or []:
                    if isinstance(value, Mapping) and value.get("type") == "text" and value.get("text"):
                        return str(value["text"])[:100]
    return thread_id


def thread_payload(store: TraceStore, thread_id: str, *, revision_id: str | None = None) -> dict[str, Any]:
    view = project_thread(store, thread_id)
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
                "eventCount": len(turn.events),
            }
        )
    records = store.records(thread_id=thread_id)
    outline = store.semantic_outline(thread_id, revision_id=revision_id)
    revisions = store.semantic_revisions(thread_id, lens="thread")
    return {
        "id": thread_id,
        "preview": _thread_preview(store, thread_id),
        "turns": turns,
        "outline": outline,
        "revisions": revisions,
        "recordCount": len(records),
        "lastSeq": records[-1].seq if records else 0,
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
    def __init__(self, store: TraceStore, *, codex: str = "codex") -> None:
        self.store = store
        self.codex = codex
        self.live = LiveCodex(store, codex=codex)
        self._jobs: dict[str, dict[str, Any]] = {}
        self._jobs_lock = threading.RLock()

    def close(self) -> None:
        self.live.close()

    def dispatch(self, handler: Any, method: str, path: str, query: dict[str, list[str]]) -> tuple[int, Any]:
        parts = [unquote(part) for part in path.split("/") if part]
        if parts == ["api", "health"] and method == "GET":
            return 200, {"ok": True}

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
                return 200, thread_payload(self.store, thread_id, revision_id=revision)
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
