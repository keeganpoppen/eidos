"""Bounded explicit-file imports. Receipts describe local writes, never authority.

Original bytes, raw records and their line mapping commit together. The public
byte path isolates correlation and refuses merging native thread identities;
the legacy iterable adapter deliberately retains its old correlation semantics.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass
import hashlib
import json
import math
import re
import sqlite3
import time
from typing import Any, Iterable
import uuid

from .evidence_discovery import EvidenceDiscovery, SCOPE
from .investigation import InvestigationError
from .trace import Direction, TraceStore

FORMAT = "appserver-jsonl/v1"
PARSER_VERSION = "history-import-parser/v1"
MAX_FILE_BYTES = 8 * 1024 * 1024
MAX_LINE_BYTES = 512 * 1024
MAX_LINES = 20_000
MAX_DEPTH = 64
MAX_RESPONSE_BYTES = 128 * 1024
MAX_UPLOAD_BYTES = 4 * ((MAX_FILE_BYTES + 2) // 3) + 4096
DIRECTIONS = frozenset({"appserver_to_client", "client_to_appserver", "provider_request", "provider_response", "internal"})
API_DIRECTIONS = frozenset({"appserver_to_client", "client_to_appserver"})


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def bounded_response(value: dict[str, Any]) -> dict[str, Any]:
    if len(_json(value).encode("utf-8")) > MAX_RESPONSE_BYTES:
        raise InvestigationError(413, "history import response exceeds 128 KiB")
    return value


def _text(value: Any, label: str, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvestigationError(400, f"invalid {label}")
    try:
        size = len(value.encode("utf-8"))
    except UnicodeError:
        raise InvestigationError(400, f"invalid {label}") from None
    if size > maximum or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise InvestigationError(400, f"invalid {label}")
    return value


def _request_id(value: Any) -> str:
    value = _text(value, "requestId", 128)
    if not value.isascii():
        raise InvestigationError(400, "requestId must be printable ASCII")
    return value


def _metadata(source: Any, direction: Any, file_name: Any, format: Any) -> None:
    if format != FORMAT:
        raise InvestigationError(400, "unsupported history import format")
    _text(source, "source", 256)
    _text(file_name, "fileName", 255)
    if "/" in file_name or "\\" in file_name or file_name in {".", ".."}:
        raise InvestigationError(400, "fileName must be a display basename")
    if not isinstance(direction, str) or direction not in DIRECTIONS:
        raise InvestigationError(400, "invalid history import direction")


def operation_identity(data: bytes, *, source: str, direction: str, format: str = FORMAT) -> dict[str, Any]:
    _metadata(source, direction, "history.jsonl", format)
    if not isinstance(data, bytes):
        raise InvestigationError(400, "history import requires exact file bytes")
    if len(data) > MAX_FILE_BYTES:
        raise InvestigationError(413, "history file exceeds 8 MiB")
    identity = {"format": format, "source": source, "direction": direction,
                "fileSha256": _hash(data), "byteLength": len(data)}
    return {**identity, "operationFingerprint": _hash(_json(identity).encode("utf-8"))}


@dataclass(frozen=True)
class _Line:
    number: int
    start: int
    content_end: int
    end: int
    raw: str
    message: dict[str, Any]


def _reject_constant(value: str) -> None:
    raise ValueError("nonfinite number")


def _validate_value(message: dict[str, Any]) -> None:
    stack: list[tuple[Any, int]] = [(message, 1)]
    while stack:
        value, depth = stack.pop()
        if isinstance(value, (dict, list)):
            if depth > MAX_DEPTH:
                raise ValueError("nesting exceeds 64")
            if isinstance(value, dict):
                for key, child in value.items():
                    key.encode("utf-8")
                    stack.append((child, depth + 1))
            else:
                stack.extend((child, depth + 1) for child in value)
        elif isinstance(value, str):
            value.encode("utf-8")
        elif isinstance(value, float) and not math.isfinite(value):
            raise ValueError("nonfinite number")
    emitted = message.get("emittedAtMs")
    if isinstance(emitted, (int, float)) and not -(2**63) <= int(emitted) < 2**63:
        raise ValueError("timestamp cannot be represented")


def _parse(data: bytes, *, reserved: bool = True, allow_empty: bool = False) -> tuple[list[_Line], int, int]:
    if len(data) > MAX_FILE_BYTES:
        raise InvestigationError(413, "history file exceeds 8 MiB")
    lines, physical, blanks = [], 0, 0
    for match in re.finditer(rb"([^\r\n]*)(\r\n|\r|\n|$)", data):
        if match.start() == match.end():
            continue
        physical += 1
        where = f" at line {physical}, byte {match.start()}"
        if physical > MAX_LINES:
            raise InvestigationError(413, "history exceeds 20000 physical lines" + where)
        if match.end() - match.start() > MAX_LINE_BYTES:
            raise InvestigationError(413, "history line exceeds 512 KiB" + where)
        content = match.group(1)
        if not content.strip(b" \t"):
            blanks += 1
            continue
        try:
            raw = content.decode("utf-8")
            message = json.loads(raw, parse_constant=_reject_constant)
            if not isinstance(message, dict):
                raise ValueError("object required")
            _validate_value(message)
        except (ValueError, TypeError, UnicodeError, RecursionError, OverflowError):
            raise InvestigationError(400, "invalid or unrepresentable JSON object" + where) from None
        if reserved:
            method = message.get("method")
            params = message.get("params")
            item = params.get("item") if isinstance(params, dict) else None
            if ((isinstance(method, str) and method.startswith("$capsule/")) or
                    (isinstance(item, dict) and item.get("type") == "privateResultPublication")):
                raise InvestigationError(400, "reserved host publication shape" + where)
        lines.append(_Line(physical, match.start(), match.end(1), match.end(), raw, message))
    if not lines and not allow_empty:
        raise InvestigationError(400, "history file contains no JSON objects")
    return lines, physical, blanks


def _append(trace: TraceStore, lines: list[_Line], source: str, direction: Direction) -> list[int]:
    return [trace.append(source=source, direction=direction, message=line.message, raw_text=line.raw).seq
            for line in lines]


def import_legacy_lines(trace: TraceStore, lines: Iterable[str], *, source: str, direction: Direction) -> int:
    """Atomic compatibility adapter; text iteration cannot prove original bytes."""
    _metadata(source, direction, "history.jsonl", FORMAT)
    chunks, size, physical = [], 0, 0
    for line in lines:
        if not isinstance(line, str):
            raise InvestigationError(400, "history lines must be text")
        try:
            # Iterable entries were historically individual lines, even without
            # a terminator. Insert one only in this non-archival compatibility path.
            chunk = (line if line.endswith(("\r", "\n")) else line + "\n").encode("utf-8")
        except UnicodeError:
            raise InvestigationError(400, "history line is not valid Unicode") from None
        size += len(chunk)
        if size > MAX_FILE_BYTES:
            raise InvestigationError(413, "history exceeds 8 MiB")
        physical += sum(1 for _ in re.finditer(rb"\r\n|\r|\n", chunk))
        if physical > MAX_LINES:
            raise InvestigationError(413, "history exceeds 20000 physical lines")
        chunks.append(chunk)
    parsed, _, _ = _parse(b"".join(chunks), reserved=False, allow_empty=True)
    with trace._lock:
        nested = trace.db.in_transaction
        savepoint = "history_import_" + uuid.uuid4().hex
        trace.db.execute(f"SAVEPOINT {savepoint}" if nested else "BEGIN IMMEDIATE")
        try:
            _append(trace, parsed, source, direction)
            trace.db.execute(f"RELEASE {savepoint}" if nested else "COMMIT")
        except BaseException:
            if nested:
                trace.db.execute(f"ROLLBACK TO {savepoint}")
                trace.db.execute(f"RELEASE {savepoint}")
            else:
                trace.db.execute("ROLLBACK")
            raise
    return len(parsed)


class HistoryImports:
    def __init__(self, trace: TraceStore) -> None:
        trace.require_workbench()
        self.trace = trace
        with trace._lock:
            if trace.db.in_transaction:
                raise InvestigationError(409, "initialize history imports outside a transaction")
            trace.db.executescript("""
                CREATE TABLE IF NOT EXISTS history_imports(
                    id TEXT PRIMARY KEY, request_id TEXT UNIQUE NOT NULL,
                    operation_fingerprint TEXT NOT NULL, receipt_json TEXT NOT NULL,
                    original_bytes BLOB NOT NULL);
                CREATE TABLE IF NOT EXISTS history_import_lines(
                    import_id TEXT NOT NULL REFERENCES history_imports(id), ordinal INTEGER NOT NULL,
                    line INTEGER NOT NULL, byte_start INTEGER NOT NULL, content_byte_end INTEGER NOT NULL,
                    byte_end INTEGER NOT NULL, seq INTEGER NOT NULL, raw_sha256 TEXT NOT NULL,
                    PRIMARY KEY(import_id,ordinal));
            """)

    @staticmethod
    def _prepare(data: bytes, identity: dict[str, Any]) -> tuple[dict[str, Any], list[_Line], set[str]]:
        lines, physical, blanks = _parse(data)
        # Run the same recorded-field projector over this file only. No target
        # database source lookup, annotation, RPC hydration or index mutation.
        scratch = TraceStore()
        try:
            _append(scratch, lines, "history-import-preview", identity["direction"])
            records = scratch.records()
            discovery = EvidenceDiscovery(scratch)
            discovery.rebuild()
            thread_ids = {r.thread_id for r in records if r.thread_id is not None}
            fields = scratch.db.execute("SELECT COUNT(*) FROM evidence_discovery_fields").fetchone()[0]
            turns = scratch.db.execute("SELECT COUNT(*) FROM (SELECT DISTINCT thread_id,turn_id FROM trace_records "
                                       "WHERE thread_id IS NOT NULL AND turn_id IS NOT NULL)").fetchone()[0]
            summary = {"threadCount": len(thread_ids), "turnCount": turns,
                       "unscopedRecordCount": sum(r.thread_id is None or r.turn_id is None for r in records),
                       "discoverableFieldCount": fields}
        except (ValueError, TypeError, UnicodeError, RecursionError, OverflowError, sqlite3.DataError):
            raise InvestigationError(400, "history fields cannot be represented by the public projection") from None
        finally:
            scratch.close()
        warnings = ["file-local-preview", "single-direction-capture"]
        if summary["unscopedRecordCount"]:
            warnings.append("unscoped-records")
        if not fields:
            warnings.append("no-discoverable-history")
        preview = {key: identity[key] for key in ("format", "fileSha256", "byteLength", "operationFingerprint")}
        preview.update(parserVersion=PARSER_VERSION, discoveryScope=SCOPE, recordCount=len(lines),
                       blankLineCount=blanks, physicalLineCount=physical, summary=summary, warnings=warnings,
                       committable=bool(fields), reason=None if fields else "no-discoverable-history")
        preview["previewFingerprint"] = _hash(_json(preview).encode("utf-8"))
        bounded_response({"preview": preview})
        return preview, lines, thread_ids

    def preview(self, data: bytes, *, source: str = "codex-app-server", direction: Direction = "appserver_to_client",
                file_name: str = "history.jsonl", format: str = FORMAT) -> dict[str, Any]:
        self.trace.require_workbench()
        _metadata(source, direction, file_name, format)
        identity = operation_identity(data, source=source, direction=direction, format=format)
        return self._prepare(data, identity)[0]

    def commit(self, data: bytes, *, request_id: str, preview_fingerprint: str,
               source: str = "codex-app-server", direction: Direction = "appserver_to_client",
               file_name: str = "history.jsonl", format: str = FORMAT,
               require_discoverable: bool = True) -> tuple[dict[str, Any], bool]:
        self.trace.require_workbench()
        _metadata(source, direction, file_name, format)
        request_id = _request_id(request_id)
        identity = operation_identity(data, source=source, direction=direction, format=format)
        with self.trace._lock:
            if self.trace.db.in_transaction:
                raise InvestigationError(409, "history import requires its own durable transaction")
            self.trace.db.execute("BEGIN IMMEDIATE")
            try:
                previous = self.trace.db.execute("SELECT operation_fingerprint,receipt_json FROM history_imports WHERE request_id=?",
                                                 (request_id,)).fetchone()
                if previous is not None:
                    if previous["operation_fingerprint"] != identity["operationFingerprint"]:
                        raise InvestigationError(409, "requestId already belongs to a different history import")
                    receipt = json.loads(previous["receipt_json"])
                    bounded_response({"receipt": receipt})
                    self.trace.db.execute("COMMIT")
                    return receipt, False
                preview, lines, threads = self._prepare(data, identity)
                if preview_fingerprint != preview["previewFingerprint"]:
                    raise InvestigationError(409, "history preview changed; review this exact file again")
                if require_discoverable and not preview["committable"]:
                    raise InvestigationError(422, "history file has no discoverable public history")
                for thread_id in threads:
                    if self.trace.db.execute("SELECT 1 FROM trace_records WHERE thread_id=? "
                            "UNION ALL SELECT 1 FROM thread_annotations WHERE thread_id=? "
                            "UNION ALL SELECT 1 FROM semantic_revisions WHERE thread_id=? LIMIT 1",
                            (thread_id, thread_id, thread_id)).fetchone() is not None:
                        raise InvestigationError(409, "history thread already exists; merging imports is not supported")
                identifier = "import_" + uuid.uuid4().hex
                capture_source = "history-import:" + identifier
                if self.trace.db.execute("SELECT 1 FROM trace_records WHERE source=? "
                        "UNION ALL SELECT 1 FROM history_imports WHERE id=? LIMIT 1", (capture_source, identifier)).fetchone():
                    raise InvestigationError(409, "history capture source already exists")
                receipt = {key: value for key, value in preview.items() if key not in {"committable", "reason"}}
                receipt.update(id=identifier, requestId=request_id, fileName=file_name, source=source,
                               captureSource=capture_source, direction=direction, createdAtMs=int(time.time() * 1000))
                bounded_response({"receipt": receipt})
                seqs = _append(self.trace, lines, capture_source, direction)
                self.trace.db.execute("INSERT INTO history_imports VALUES(?,?,?,?,?)",
                    (identifier, request_id, identity["operationFingerprint"], _json(receipt), data))
                self.trace.db.executemany("INSERT INTO history_import_lines VALUES(?,?,?,?,?,?,?,?)",
                    ((identifier, ordinal, line.number, line.start, line.content_end, line.end, seq, _hash(line.raw.encode("utf-8")))
                     for ordinal, (line, seq) in enumerate(zip(lines, seqs))))
                self.trace.db.execute("COMMIT")
                return receipt, True
            except BaseException:
                self.trace.db.execute("ROLLBACK")
                raise

    def get_request(self, request_id: str) -> dict[str, Any]:
        self.trace.require_workbench()
        _request_id(request_id)
        with self.trace._lock:
            row = self.trace.db.execute("SELECT receipt_json FROM history_imports WHERE request_id=?", (request_id,)).fetchone()
            if row is None:
                raise InvestigationError(404, "history import receipt not found")
            receipt = json.loads(row[0])
            bounded_response({"receipt": receipt})
            return receipt

    def records(self, import_id: str, *, limit: int = 100, cursor: str | None = None) -> dict[str, Any]:
        self.trace.require_workbench()
        _text(import_id, "import id", 128)
        if type(limit) is not int or not 1 <= limit <= 100:
            raise InvestigationError(400, "history mapping limit must be between 1 and 100")
        after = -1
        if cursor is not None:
            try:
                if not isinstance(cursor, str) or not 1 <= len(cursor) <= 2048:
                    raise ValueError
                value = json.loads(base64.b64decode(cursor, altchars=b"-_", validate=True))
                if (not isinstance(value, dict) or set(value) != {"importId", "after", "version"} or
                        value["importId"] != import_id or type(value["version"]) is not int or value["version"] != 1 or
                        type(value["after"]) is not int or not 0 <= value["after"] < MAX_LINES):
                    raise ValueError
                after = value["after"]
            except (ValueError, TypeError, UnicodeError, RecursionError):
                raise InvestigationError(400, "invalid history mapping cursor") from None
        with self.trace._lock:
            if not self.trace.db.execute("SELECT 1 FROM history_imports WHERE id=?", (import_id,)).fetchone():
                raise InvestigationError(404, "history import not found")
            rows = self.trace.db.execute("SELECT * FROM history_import_lines WHERE import_id=? AND ordinal>? ORDER BY ordinal LIMIT ?",
                                         (import_id, after, limit + 1)).fetchall()
        records = [{"line": r["line"], "byteStart": r["byte_start"], "contentByteEnd": r["content_byte_end"],
                    "byteEnd": r["byte_end"], "seq": r["seq"], "rawSha256": r["raw_sha256"]} for r in rows[:limit]]
        following = None
        if len(rows) > limit:
            following = base64.urlsafe_b64encode(_json({"version": 1, "importId": import_id, "after": rows[limit - 1]["ordinal"]}).encode()).decode()
        return bounded_response({"importId": import_id, "records": records, "nextCursor": following})


def upload_body(handler: Any, *, commit: bool) -> dict[str, Any]:
    """This route alone accepts bounded base64 uploads; no text conversion."""
    fields = {"format", "source", "direction", "fileName", "contentBase64"}
    if commit:
        fields |= {"requestId", "previewFingerprint"}
    try:
        headers = handler.headers
        lengths = headers.get_all("Content-Length", []) if hasattr(headers, "get_all") else [headers.get("Content-Length", "")]
        if len(lengths) != 1 or not isinstance(lengths[0], str) or not lengths[0].isascii() or not lengths[0].isdecimal():
            raise ValueError
        length = int(lengths[0])
        if headers.get("Transfer-Encoding") is not None or headers.get("Content-Encoding") is not None:
            raise ValueError
        if length > MAX_UPLOAD_BYTES:
            raise InvestigationError(413, "history upload body exceeds its byte limit")
        raw = handler.rfile.read(length)
        if len(raw) != length:
            raise ValueError
        def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
            result: dict[str, Any] = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError
                result[key] = value
            return result
        body = json.loads(raw, object_pairs_hook=unique, parse_constant=_reject_constant)
        if not isinstance(body, dict) or set(body) != fields:
            raise ValueError
        _metadata(body["source"], body["direction"], body["fileName"], body["format"])
        if body["direction"] not in API_DIRECTIONS:
            raise ValueError
        encoded = body.pop("contentBase64")
        if not isinstance(encoded, str) or len(encoded) > 4 * ((MAX_FILE_BYTES + 2) // 3):
            raise ValueError
        data = base64.b64decode(encoded, validate=True)
        if len(data) > MAX_FILE_BYTES:
            raise InvestigationError(413, "history file exceeds 8 MiB")
        if commit:
            _request_id(body["requestId"])
            if not isinstance(body["previewFingerprint"], str) or not re.fullmatch(r"[0-9a-f]{64}", body["previewFingerprint"]):
                raise ValueError
        return {**body, "data": data}
    except InvestigationError:
        raise
    except (ValueError, TypeError, UnicodeError, RecursionError, OverflowError):
        raise InvestigationError(400, "invalid history upload envelope") from None
