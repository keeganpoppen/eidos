from __future__ import annotations

"""Private native evidence and explicit, idempotent result publication.

This is a trusted-host adapter. Filesystem permissions and store roles prevent
accidental workbench disclosure, not access by arbitrary code running as owner.
Logical record budgets are not SQLite file-size or whole-disk quotas.
"""

import base64
import fcntl
from dataclasses import asdict, dataclass, field
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import threading
from typing import Any, Callable, Literal, Mapping, Sequence
import uuid

from .codex import AppServerClient, AppServerLimits
from .investigation_worker import NativeInvestigationError, NativeInvestigationWorker, NativePreparation
from .trace import TraceRecord, TraceStore


# A recording lock is host writer exclusion, never caller authentication. Keep
# it alive if a bounded close returns before its recorder thread terminates.
_retired_lock = threading.Lock()
_retired_writers: list[tuple[Any, list[threading.Thread]]] = []


def _reap_writers() -> None:
    with _retired_lock:
        pending = []
        for lease, readers in _retired_writers:
            if any(reader.is_alive() for reader in readers):
                pending.append((lease, readers))
            else:
                lease.close()
        _retired_writers[:] = pending


class _WriterLease:
    def __init__(self, path: Path) -> None:
        _reap_writers()
        self.path = path
        self.fd: int | None = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(self.fd)
            self.fd = None

    def close(self) -> None:
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None

    def finish(self, readers: list[threading.Thread]) -> None:
        if any(reader.is_alive() for reader in readers):
            with _retired_lock:
                _retired_writers.append((self, readers))
        else:
            self.close()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _digest(value: Any) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


class PrivateEvidenceError(NativeInvestigationError):
    """Fixed public reason; original diagnostic belongs only in private evidence."""

    def __init__(self, reason: str = "unavailable", *, status: str = "unknown") -> None:
        self.reason = reason
        super().__init__(f"Private investigation evidence {reason}; no task was resent.", status=status)


@dataclass(frozen=True)
class PrivateEvidenceLimits:
    max_capsules: int = 32
    max_records: int = 4096
    max_record_bytes: int = 16 * 1024 * 1024
    max_outbound_records: int = 64
    max_outbound_bytes: int = 512 * 1024
    # One capture-gap record has its own reserve: rejected/partial bytes can be
    # retained even when the ordinary record budget caused the capture failure.
    max_diagnostic_bytes: int = 16 * 1024 * 1024
    capture: AppServerLimits = field(default_factory=lambda: AppServerLimits(max_received_bytes=8 * 1024 * 1024))

    def __post_init__(self) -> None:
        if not isinstance(self.capture, AppServerLimits):
            raise ValueError("capture must be AppServerLimits")
        for key, value in asdict(self).items():
            if key != "capture" and (type(value) is not int or value <= 0):
                raise ValueError(f"{key} must be a positive finite integer")


class _PrivateTrace(TraceStore):
    def __init__(self, path: Path, limits: PrivateEvidenceLimits) -> None:
        super().__init__(path, role="private-control")
        self.limits = limits
        with self._lock:
            self.db.execute("CREATE TABLE IF NOT EXISTS private_record_budget(id INTEGER PRIMARY KEY CHECK(id=1), records INTEGER, bytes INTEGER, outbound_records INTEGER, outbound_bytes INTEGER, diagnostics INTEGER)")
            usage = self._usage()
            self.db.execute("INSERT OR IGNORE INTO private_record_budget VALUES(1,?,?,?,?,?)", tuple(usage.values()))
            self._counts = usage
        for name in (path, Path(str(path) + "-wal"), Path(str(path) + "-shm")):
            if name.exists():
                os.chmod(name, 0o600)

    def _usage(self) -> dict[str, int]:
        counts = {"records": 0, "bytes": 0, "outbound_records": 0, "outbound_bytes": 0, "diagnostics": 0}
        for row in self.db.execute("SELECT direction,method,length(CAST(raw_text AS BLOB)) AS size FROM trace_records"):
            if row["direction"] == "internal" and row["method"] == "$transport/captureGap":
                counts["diagnostics"] += 1
            else:
                counts["records"] += 1
                counts["bytes"] += row["size"]
            if row["direction"] == "client_to_appserver":
                counts["outbound_records"] += 1
                counts["outbound_bytes"] += row["size"] + 1
        return counts

    def append(self, *, source: str, direction: Any, message: Mapping[str, Any],
               raw_text: str | None = None, observed_at_ms: int | None = None) -> TraceRecord:
        raw = raw_text if raw_text is not None else _json(message)
        size = len(raw.encode("utf-8"))
        diagnostic = direction == "internal" and message.get("method") == "$transport/captureGap"
        with self._lock:
            own_transaction = not self.db.in_transaction
            if own_transaction:
                self.db.execute("BEGIN IMMEDIATE")
            try:
                usage = dict(self.db.execute("SELECT records,bytes,outbound_records,outbound_bytes,diagnostics FROM private_record_budget WHERE id=1").fetchone())
                if diagnostic:
                    exceeded = usage["diagnostics"] >= 1 or size > self.limits.max_diagnostic_bytes
                else:
                    exceeded = (usage["records"] >= self.limits.max_records
                                or usage["bytes"] + size > self.limits.max_record_bytes)
                if direction == "client_to_appserver":
                    exceeded |= (usage["outbound_records"] >= self.limits.max_outbound_records
                                 or usage["outbound_bytes"] + size + 1 > self.limits.max_outbound_bytes)
                if exceeded:
                    raise PrivateEvidenceError("record-limit-reached")
                record = super().append(source=source, direction=direction, message=message,
                                        raw_text=raw, observed_at_ms=observed_at_ms)
                if diagnostic:
                    usage["diagnostics"] += 1
                else:
                    usage["records"] += 1
                    usage["bytes"] += size
                if direction == "client_to_appserver":
                    usage["outbound_records"] += 1
                    usage["outbound_bytes"] += size + 1
                self.db.execute("UPDATE private_record_budget SET records=?,bytes=?,outbound_records=?,outbound_bytes=?,diagnostics=? WHERE id=1", tuple(usage.values()))
                if own_transaction:
                    self.db.commit()
                self._counts = usage
                return record
            except Exception:
                if own_transaction:
                    self.db.rollback()
                raise


class _PrivateClient(AppServerClient):
    def _accept_frame(self, stream: str, frame: bytes) -> str | None:
        if stream == "stderr" and self.trace is not None:
            try:
                self.trace.append(source=self.source, direction="internal", message={
                    "method": "$transport/stderr", "params": {
                        "version": 1, "capturedBase64": base64.b64encode(frame).decode("ascii"),
                        "capturedBytes": len(frame), "frameComplete": True,
                    },
                })
            except Exception:
                return "privateStderrStorageFailed"
        return super()._accept_frame(stream, frame)


def _binding(trace: TraceStore, attempt: Mapping[str, Any], context: Mapping[str, Any]) -> dict[str, Any] | None:
    row = trace.db.execute("SELECT * FROM private_investigation_bindings WHERE attempt_id=?", (attempt.get("id"),)).fetchone()
    if row is None:
        return None
    value = dict(row)
    if (value["context_id"] != context.get("id") or attempt.get("contextId") != context.get("id")
            or value["context_digest"] != _digest(context)):
        raise PrivateEvidenceError("binding-conflict", status="failed")
    state = json.loads(value["state_json"])
    for key in ("source", "threadId", "turnId"):
        if attempt.get(key) is not None and attempt[key] != state["attempt"].get(key):
            raise PrivateEvidenceError("binding-conflict", status="failed")
    value["state"] = state
    return value


def _publication(trace: TraceStore, binding: Mapping[str, Any]) -> dict[str, Any] | None:
    row = trace.db.execute("SELECT * FROM private_investigation_publications WHERE attempt_id=?", (binding["attempt_id"],)).fetchone()
    if row is None:
        return None
    try:
        record = trace.get(row["seq"])
        message = record.message
        params = message["params"]
        state = binding["state"]["attempt"]
        if (row["capsule_id"] != binding["capsule_id"] or _digest(params) != row["content_digest"]
                or record.direction != "internal" or message.get("method") != "$capsule/result"
                or params.get("version") != 1 or params.get("attemptId") != binding["attempt_id"]
                or params.get("contextId") != binding["context_id"]
                or params.get("provenance") != {"kind": "private-capsule", "capsuleId": binding["capsule_id"]}
                or any(params.get(k) != state.get(k) for k in ("threadId", "turnId"))
                or record.source != state.get("source") or record.thread_id != state.get("threadId")
                or record.turn_id != state.get("turnId")):
            raise ValueError("publication mismatch")
        return {"text": params["text"], "executionEvidence": params["executionEvidence"],
                "outputSeqs": [record.seq], "citations": params["citations"],
                "unsupportedCitations": params["unsupportedCitations"],
                "outputEvidence": {"kind": "private-capsule-publication", "version": 1,
                                   "capsuleId": binding["capsule_id"]}}
    except Exception:
        raise PrivateEvidenceError("publication-conflict", status="failed") from None


def validate_publication(trace: TraceStore, attempt: Mapping[str, Any], context: Mapping[str, Any],
                         artifact: Mapping[str, Any]) -> dict[str, Any]:
    """Verify the host ledger, not a child message or copied output envelope."""
    try:
        with trace._lock:
            binding = _binding(trace, attempt, context)
            published = _publication(trace, binding) if binding is not None else None
            if published is None or any(artifact.get(key) != published[key] for key in published):
                raise PrivateEvidenceError("publication-conflict", status="failed")
            return published
    except PrivateEvidenceError:
        raise
    except Exception:
        raise PrivateEvidenceError("publication-conflict", status="failed") from None


@dataclass
class _OwnedAttempt:
    cancelled: bool = False
    started: bool = False
    closed: bool = False
    worker: NativeInvestigationWorker | None = None


class PrivateInvestigationWorker:
    @staticmethod
    def public_error(exc: Exception) -> str:
        # Even a failure outside run/recover must not put exception details in
        # the public investigation envelope. This includes trusted-host IO errors.
        return "Private investigation stopped; no task was resent."

    def __init__(self, trace: TraceStore, command: Sequence[str] | None = None, *,
                 execution_evidence: Literal["synthetic", "unverified"] = "unverified",
                 limits: PrivateEvidenceLimits | None = None,
                 preparation: Callable[[NativePreparation], None] | None = None,
                 preparation_timeout: float = 120) -> None:
        trace.require_workbench()
        self.trace = trace
        self.limits = limits or PrivateEvidenceLimits()
        self._legacy = NativeInvestigationWorker(trace, command, execution_evidence=execution_evidence,
                                                preparation=preparation, preparation_timeout=preparation_timeout)
        self.preparation, self.preparation_timeout = preparation, preparation_timeout
        self.command = self._legacy.command
        self.execution_profile = self._legacy.execution_profile
        self.execution_evidence = self._legacy.execution_evidence
        self._lock = threading.RLock()
        self._workers: set[NativeInvestigationWorker] = set()
        self._owned: dict[str, _OwnedAttempt] = {}
        self._stores: dict[str, _PrivateTrace] = {}
        self._closed = False
        with trace._lock:
            trace.db.executescript("""
                CREATE TABLE IF NOT EXISTS private_investigation_bindings(
                    attempt_id TEXT PRIMARY KEY, capsule_id TEXT NOT NULL UNIQUE,
                    context_id TEXT NOT NULL, context_digest TEXT NOT NULL, state_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS private_investigation_publications(
                    attempt_id TEXT PRIMARY KEY REFERENCES private_investigation_bindings(attempt_id),
                    capsule_id TEXT NOT NULL, seq INTEGER NOT NULL UNIQUE REFERENCES trace_records(seq),
                    content_digest TEXT NOT NULL
                );
            """)
            if str(trace.path) == ":memory:":
                if not hasattr(trace, "_private_investigation_directory"):
                    trace._private_investigation_directory = tempfile.TemporaryDirectory(prefix="nema-private-evidence-")
                self.root = Path(trace._private_investigation_directory.name)
            else:
                self.root = Path(str(trace.path) + ".private")

    def reserve(self, attempt_id: str) -> None:
        """Reserve before the controller starts its thread; never revive history."""
        if not isinstance(attempt_id, str) or not 0 < len(attempt_id) <= 300:
            raise ValueError("invalid attempt identity")
        with self.trace._lock:
            bound = self.trace.db.execute("SELECT 1 FROM private_investigation_bindings WHERE attempt_id=?",
                                          (attempt_id,)).fetchone()
        with self._lock:
            if self._closed and attempt_id not in self._owned:
                raise PrivateEvidenceError("worker-closed")
            if not bound and attempt_id not in self._owned:
                self._owned[attempt_id] = _OwnedAttempt()

    def inspect_owned(self, attempt_id: str) -> dict[str, bool]:
        with self._lock:
            owned = self._owned.get(attempt_id)
            live = owned is not None and not owned.closed
            return {"owned": live, "canCancel": live and not owned.cancelled}

    def cancel(self, attempt_id: str) -> None:
        with self._lock:
            owned = self._owned.get(attempt_id)
            if owned is None or owned.closed:
                return
            owned.cancelled = True
            worker = owned.worker
        if worker is not None:
            try:
                worker.close()
            except Exception as exc:
                clients = getattr(worker, "_private_clients", [])
                source = clients[0].source if len(clients) == 1 else None
                self._diagnose(worker.trace, source, exc)
                raise PrivateEvidenceError("cancellation-failed") from None

    def _directory(self, path: Path) -> None:
        try:
            path.mkdir(mode=0o700)
        except FileExistsError:
            pass
        if path.is_symlink() or not path.is_dir() or path.stat().st_mode & 0o077 or path.stat().st_uid != os.getuid():
            raise PrivateEvidenceError("storage-permissions-invalid", status="failed")

    def _claim(self, attempt: Mapping[str, Any], context: Mapping[str, Any]) -> tuple[dict[str, Any], bool]:
        if (not isinstance(attempt.get("id"), str) or not attempt["id"] or attempt.get("contextId") != context.get("id")):
            raise PrivateEvidenceError("binding-conflict", status="failed")
        with self.trace._lock:
            self.trace.db.execute("BEGIN IMMEDIATE")
            try:
                prior = _binding(self.trace, attempt, context)
                if prior is not None:
                    self.trace.db.commit()
                    return prior, False
                count = self.trace.db.execute("SELECT COUNT(*) FROM private_investigation_bindings").fetchone()[0]
                if count >= self.limits.max_capsules:
                    raise PrivateEvidenceError("retention-limit-reached", status="failed")
                capsule = "capsule_" + uuid.uuid4().hex
                bound = {key: attempt[key] for key in ("id", "contextId", "timeoutSeconds") if key in attempt}
                state = {"attempt": bound, "limits": asdict(self.limits)}
                self.trace.db.execute("INSERT INTO private_investigation_bindings VALUES (?,?,?,?,?)",
                                      (attempt["id"], capsule, context["id"], _digest(context), _json(state)))
                self.trace.db.commit()
                return _binding(self.trace, attempt, context), True
            except Exception:
                self.trace.db.rollback()
                raise

    def _store(self, binding: Mapping[str, Any], *, create: bool = False) -> _PrivateTrace:
        capsule = binding["capsule_id"]
        if not isinstance(capsule, str) or re.fullmatch(r"capsule_[0-9a-f]{32}", capsule) is None:
            raise PrivateEvidenceError("binding-conflict", status="failed")
        with self._lock:
            if capsule in self._stores:
                return self._stores[capsule]
            folder = self.root / capsule
            path = folder / "evidence.sqlite"
            if create:
                self._directory(self.root)
                self._directory(folder)
                fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
                os.close(fd)
            elif not path.is_file():
                raise PrivateEvidenceError("unavailable")
            self._directory(self.root)
            self._directory(folder)
            if path.is_symlink() or path.stat().st_mode & 0o077:
                raise PrivateEvidenceError("storage-permissions-invalid", status="failed")
            values = dict(binding["state"]["limits"])
            values["capture"] = AppServerLimits(**values["capture"])
            store = _PrivateTrace(path, PrivateEvidenceLimits(**values))
            self._stores[capsule] = store
            return store

    def _remember(self, attempt: Mapping[str, Any], context: Mapping[str, Any], fields: Mapping[str, Any]) -> None:
        with self.trace._lock:
            self.trace.db.execute("BEGIN IMMEDIATE")
            try:
                binding = _binding(self.trace, attempt, context)
                state = binding["state"]
                if fields.get("closedBeforeLaunch") is True:
                    if state["attempt"].get("source") is not None:
                        raise PrivateEvidenceError("binding-conflict", status="failed")
                    state["closedBeforeLaunch"] = True
                for name in ("source", "threadId", "turnId"):
                    if name in fields:
                        if not isinstance(fields[name], str) or not 0 < len(fields[name]) <= 300:
                            raise PrivateEvidenceError("binding-conflict", status="failed")
                        if state["attempt"].get(name) not in (None, fields[name]):
                            raise PrivateEvidenceError("binding-conflict", status="failed")
                        state["attempt"][name] = fields[name]
                self.trace.db.execute("UPDATE private_investigation_bindings SET state_json=? WHERE attempt_id=?",
                                      (_json(state), attempt["id"]))
                self.trace.db.commit()
            except Exception:
                self.trace.db.rollback()
                raise

    def _worker(self, store: _PrivateTrace) -> NativeInvestigationWorker:
        clients = []
        def factory(*args: Any, **kwargs: Any) -> AppServerClient:
            client = _PrivateClient(*args, **kwargs, limits=store.limits.capture)
            clients.append(client)
            return client
        worker = NativeInvestigationWorker(store, self.command, execution_evidence=self.execution_evidence,
                                           client_factory=factory, preparation=self.preparation,
                                           preparation_timeout=self.preparation_timeout)
        worker.execution_profile = self.execution_profile
        worker._private_clients = clients
        return worker

    @staticmethod
    def _readers(worker: NativeInvestigationWorker | None) -> list[threading.Thread]:
        return [client._reader for client in getattr(worker, "_private_clients", []) if client._reader is not None]

    @staticmethod
    def _writer_lease(store: _PrivateTrace) -> _WriterLease:
        return _WriterLease(Path(str(store.path) + ".writer-lock"))

    def _diagnose(self, store: _PrivateTrace | None, source: str | None, exc: Exception) -> None:
        if store is None:
            return
        detail = str(exc)
        try:
            message = {
                "method": "$capsule/failure", "params": {"version": 1, "exceptionType": type(exc).__name__,
                    "detail": detail[:16000], "detailComplete": len(detail) <= 16000},
            }
            with store._lock:
                previous = store.db.execute("SELECT raw_text FROM trace_records WHERE direction='internal' AND method='$capsule/failure' ORDER BY seq DESC LIMIT 1").fetchone()
                if previous is None or previous[0] != _json(message):
                    store.append(source=source or "private-investigation", direction="internal", message=message)
        except Exception:
            pass  # Public failure cannot imply that a diagnostic was persisted.

    def _publish(self, binding: Mapping[str, Any], artifact: Mapping[str, Any]) -> dict[str, Any]:
        state = binding["state"]["attempt"]
        if any(not isinstance(state.get(key), str) or not state[key] for key in ("source", "threadId", "turnId")):
            raise PrivateEvidenceError("binding-incomplete")
        params = {"version": 1, "attemptId": binding["attempt_id"], "contextId": binding["context_id"],
                  "threadId": state["threadId"], "turnId": state["turnId"],
                  **{key: artifact[key] for key in ("text", "executionEvidence", "citations", "unsupportedCitations")},
                  "provenance": {"kind": "private-capsule", "capsuleId": binding["capsule_id"]}}
        digest = _digest(params)
        with self.trace._lock:
            self.trace.db.execute("BEGIN IMMEDIATE")
            try:
                existing = _publication(self.trace, binding)
                if existing is not None:
                    row = self.trace.db.execute("SELECT content_digest FROM private_investigation_publications WHERE attempt_id=?",
                                                (binding["attempt_id"],)).fetchone()
                    if row[0] != digest:
                        raise PrivateEvidenceError("publication-conflict", status="failed")
                else:
                    record = self.trace.append(source=state["source"], direction="internal",
                                               message={"method": "$capsule/result", "params": params})
                    self.trace.db.execute("INSERT INTO private_investigation_publications VALUES (?,?,?,?)",
                                          (binding["attempt_id"], binding["capsule_id"], record.seq, digest))
                self.trace.db.commit()
                return _publication(self.trace, binding)
            except Exception:
                self.trace.db.rollback()
                raise

    def run(self, attempt: Mapping[str, Any], context: Mapping[str, Any], update: Callable[..., None], *,
            on_event: Callable[..., None] | None = None) -> dict[str, Any]:
        store = None
        worker = None
        lease = None
        binding = None
        owned = None
        reason = "failed"
        owns_run = False
        try:
            self.reserve(attempt["id"])
            with self._lock:
                owned = self._owned.get(attempt["id"])
                if owned is not None:
                    if owned.started or owned.closed:
                        owned = None  # Duplicate calls may recover, but never share live control.
                    else:
                        owned.started = True
                        owns_run = True
            if owned is None:
                result = self.recover(attempt, context)
                if result is None:
                    raise PrivateEvidenceError("outcome-unknown")
                return result
            # A competing SQLite writer must not hold the cancellation lock.
            binding, claimed = self._claim(attempt, context)
            if not claimed:
                result = self.recover(attempt, context)
                if result is None:
                    raise PrivateEvidenceError("outcome-unknown")
                return result
            with self._lock:
                cancelled_before_launch = self._closed or owned.cancelled
                if not cancelled_before_launch:
                    store = self._store(binding, create=True)
                    lease = self._writer_lease(store)
                    if lease.fd is None:
                        raise PrivateEvidenceError("recording-in-progress")
                    worker = self._worker(store)
                    self._workers.add(worker)
                    owned.worker = worker
            if cancelled_before_launch:
                self._remember(attempt, context, {"closedBeforeLaunch": True})
                raise PrivateEvidenceError("cancelled")

            def remember(**fields: Any) -> None:
                nonlocal reason
                self._remember(attempt, context, fields)
                binding["state"]["attempt"].update({key: value for key, value in fields.items()
                                                  if key in {"source", "threadId", "turnId"}})
                # No raw private event/error is forwarded into public projections.
                public = {key: value for key, value in fields.items() if key in {"source", "threadId", "turnId", "status"}}
                lifecycle = fields.get("lifecycle")
                if lifecycle is not None:
                    if (not isinstance(lifecycle, dict) or lifecycle.keys() - {"phase", "stopReason"}
                            or lifecycle.get("phase") not in {"preparing", "awaiting-sign-in", "checking", "running", "closed"}
                            or ("stopReason" in lifecycle and lifecycle["stopReason"] not in
                                {"cancelled", "deadline", "failed", "completed", "owner-unavailable"})):
                        raise PrivateEvidenceError("invalid-lifecycle")
                    if lifecycle["phase"] == "closed":
                        reason = lifecycle.get("stopReason", "failed")
                    else:
                        public["lifecycle"] = dict(lifecycle)
                        store.append(source=binding["state"]["attempt"].get("source", "private-investigation"),
                                     direction="internal", message={"method": "$capsule/lifecycle", "params": lifecycle})
                if public:
                    update(**public)

            run_error = None
            try:
                worker.run(attempt, context, remember)
            except Exception as exc:
                run_error = exc
            if any(reader.is_alive() for reader in self._readers(worker)):
                raise PrivateEvidenceError("capture-still-closing")
            with self.trace._lock:
                binding = _binding(self.trace, attempt, context)
            # run's first recovery can precede late bytes accepted during its
            # finally cleanup. Publish only the closed incarnation's result.
            artifact = worker.recover(binding["state"]["attempt"], context)
            if artifact is None:
                if run_error is not None:
                    raise run_error
                raise PrivateEvidenceError("outcome-unknown")
            result = self._publish(binding, artifact)
            reason = "completed"
            return result
        except Exception as exc:
            reason = "cancelled" if owned is not None and owned.cancelled else (
                "deadline" if reason == "deadline" or getattr(exc, "stop_reason", None) == "deadline" else "failed")
            self._diagnose(store, binding["state"]["attempt"].get("source") if binding is not None else None, exc)
            if isinstance(exc, PrivateEvidenceError):
                raise
            raise PrivateEvidenceError("execution-stopped", status="failed" if getattr(exc, "status", None) == "failed" else "unknown") from None
        finally:
            if worker is not None:
                worker.close()
                with self._lock:
                    self._workers.discard(worker)
            if lease is not None:
                lease.finish(self._readers(worker))
            if owns_run:
                with self._lock:
                    owned.closed = True
                    owned.worker = None
                update(lifecycle={"phase": "closed", "stopReason": reason})

    def recover(self, attempt: Mapping[str, Any], context: Mapping[str, Any]) -> dict[str, Any] | None:
        store = None
        lease = None
        try:
            with self.trace._lock:
                binding = _binding(self.trace, attempt, context)
                if binding is None:
                    return self._legacy.recover(attempt, context)
                published = _publication(self.trace, binding)
                if binding["state"].get("closedBeforeLaunch") is True:
                    return None
            try:
                store = self._store(binding)
            except PrivateEvidenceError as exc:
                if published is not None and exc.reason == "unavailable":
                    return published  # Existing publication remains inspectable; resolver still requires proof.
                raise
            lease = self._writer_lease(store)
            if lease.fd is None:
                return None  # Another recorder/recovery still owns the transcript.
            artifact = self._worker(store).recover(binding["state"]["attempt"], context)
            if artifact is not None:
                # A crash may precede the metadata callback although exact
                # native evidence already establishes these identifiers.
                outputs = [store.get(seq) for seq in artifact["outputSeqs"]]
                recovered = {}
                for name, column in (("threadId", "thread_id"), ("turnId", "turn_id")):
                    values = {getattr(record, column) for record in outputs}
                    if len(values) == 1 and None not in values:
                        recovered[name] = values.pop()
                self._remember(attempt, context, recovered)
                with self.trace._lock:
                    binding = _binding(self.trace, attempt, context)
            elif published is not None:
                raise PrivateEvidenceError("publication-conflict", status="failed")
            return self._publish(binding, artifact) if artifact is not None else None
        except PrivateEvidenceError:
            raise
        except Exception as exc:
            self._diagnose(store, attempt.get("source"), exc)
            raise PrivateEvidenceError("recovery-unavailable", status="failed" if getattr(exc, "status", None) == "failed" else "unknown") from None
        finally:
            if lease is not None:
                lease.close()

    def resolve_result_evidence(self, attempt: Mapping[str, Any], context: Mapping[str, Any],
                               artifact: Mapping[str, Any]) -> dict[str, Any]:
        store = None
        lease = None
        try:
            with self.trace._lock:
                binding = _binding(self.trace, attempt, context)
                if binding is None:
                    raise PrivateEvidenceError("binding-unavailable")
                published = validate_publication(self.trace, attempt, context, artifact)
            store = self._store(binding)
            lease = self._writer_lease(store)
            if lease.fd is None:
                raise PrivateEvidenceError("recording-in-progress")
            original = self._worker(store).recover(binding["state"]["attempt"], context)
            if original is None or any(original[key] != published[key] for key in ("text", "executionEvidence", "citations", "unsupportedCitations")):
                raise PrivateEvidenceError("publication-conflict", status="failed")
            return {"kind": "private-capsule", "capsuleId": binding["capsule_id"], "trace": store,
                    "artifact": original, "attempt": dict(binding["state"]["attempt"])}
        except PrivateEvidenceError:
            raise
        except Exception as exc:
            self._diagnose(store, attempt.get("source"), exc)
            raise PrivateEvidenceError("recovery-unavailable") from None
        finally:
            if lease is not None:
                lease.close()

    def close(self) -> None:
        with self._lock:
            self._closed = True
            for owned in self._owned.values():
                if not owned.closed:
                    owned.cancelled = True
            workers = tuple(self._workers)
        for worker in workers:
            worker.close()
        self._legacy.close()

    def close_evidence(self) -> None:
        """Finalize storage after the controller joins all completion callbacks."""
        with self._lock:
            if self._workers:
                raise PrivateEvidenceError("worker-still-closing")
            _reap_writers()
            with _retired_lock:
                if any(lease.path.parent == Path(store.path).parent for lease, _ in _retired_writers
                       for store in self._stores.values()):
                    raise PrivateEvidenceError("capture-still-closing")
            for store in self._stores.values():
                store.close()
            self._stores.clear()
