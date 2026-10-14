"""Explicit local UTF-8 intake, separate from native observation and execution.

The ledger binds an immutable original file to one derived host record. Names
and copied envelopes alone do not establish that binding. Frozen descriptions
remain useful after the live source disappears, without restoring authority.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
import time
from typing import Any, Mapping
import uuid

from .trace import TraceRecord, TraceStore

FORMAT = "supplied-text/v1"
PARSER_VERSION = "supplied-text-admission/v1"
CLASSIFICATION = "local-owner-supplied"
METHOD = "$local/document"
ITEM_TYPE = "suppliedText"
GROUP_PREFIX = "local-document_"
MAX_FILE_BYTES = 64 * 1024
MAX_RECORD_BYTES = 64 * 1024
MAX_CONTEXT_RECORD_BYTES = 96 * 1024
MAX_RESPONSE_BYTES = 128 * 1024
MAX_UPLOAD_BYTES = 4 * ((MAX_FILE_BYTES + 2) // 3) + 4096


def _error(status: int, message: str):
    # The investigation projector uses this module too; do not form an import cycle.
    from .investigation import InvestigationError
    return InvestigationError(status, message)


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def bounded_response(value: dict[str, Any]) -> dict[str, Any]:
    if len(_json(value).encode("utf-8")) > MAX_RESPONSE_BYTES:
        raise _error(413, "supplied text response exceeds 128 KiB")
    return value


def ensure_schema(trace: TraceStore) -> None:
    """Called by every workbench TraceStore, including direct non-API users."""
    trace.require_workbench()
    with trace._lock:
        trace.db.execute("""CREATE TABLE IF NOT EXISTS supplied_text_files(
            id TEXT PRIMARY KEY, request_id TEXT UNIQUE NOT NULL, fingerprint TEXT NOT NULL,
            receipt_json TEXT NOT NULL, original_bytes BLOB NOT NULL,
            seq INTEGER UNIQUE NOT NULL, source TEXT NOT NULL, thread_id TEXT UNIQUE NOT NULL,
            host_record_sha256 TEXT NOT NULL)""")


def _name(value: Any) -> str:
    if not isinstance(value, str) or not value.replace("\ufeff", "").strip() or value in {".", ".."}:
        raise _error(400, "fileName must be a display basename")
    try:
        if (len(value.encode("utf-8")) > 255 or "/" in value or "\\" in value
                or any(ord(c) < 32 or ord(c) == 127 for c in value)):
            raise ValueError
    except (UnicodeError, ValueError):
        raise _error(400, "fileName must be a display basename of at most 255 UTF-8 bytes") from None
    return value


def _request(value: Any) -> str:
    if (not isinstance(value, str) or not value.strip() or not 1 <= len(value) <= 128
            or not value.isascii() or any(ord(c) < 32 or ord(c) == 127 for c in value)):
        raise _error(400, "requestId must be nonblank printable ASCII of at most 128 bytes")
    return value


def _identity(data: bytes, file_name: str, format: str) -> dict[str, Any]:
    if format != FORMAT:
        raise _error(400, "unsupported supplied text format")
    _name(file_name)
    if not isinstance(data, bytes):
        raise _error(400, "supplied text requires exact bytes")
    if len(data) > MAX_FILE_BYTES:
        raise _error(413, "supplied text file exceeds 64 KiB")
    return {"format": format, "fileName": file_name, "fileSha256": _sha(data), "byteLength": len(data)}


def _coordinates(identifier: str) -> dict[str, str]:
    suffix = identifier.removeprefix("file_")
    return {"id": identifier, "source": "supplied-text:" + identifier,
            "threadId": GROUP_PREFIX + suffix, "turnId": "local-document-turn_" + suffix,
            "itemId": "local-document-item_" + suffix}


def _envelope(identity: Mapping[str, Any], coordinates: Mapping[str, Any], text: str,
              parser: str) -> dict[str, Any]:
    return {"method": METHOD, "params": {"version": 1, "id": coordinates["id"],
        "threadId": coordinates["threadId"], "turnId": coordinates["turnId"], "item": {
            "id": coordinates["itemId"], "type": ITEM_TYPE, "text": text,
            **{key: identity[key] for key in ("fileName", "fileSha256", "byteLength")},
            "classification": CLASSIFICATION, "parserVersion": parser}}}


def descriptor(receipt: Mapping[str, Any]) -> dict[str, Any]:
    return {"kind": "supplied-text", "version": 1, **{key: receipt[key] for key in (
        "id", "fileName", "fileSha256", "byteLength", "classification", "parserVersion", "hostRecordSha256")}}


def context_record(record: TraceRecord, local: Mapping[str, Any] | None = None) -> dict[str, Any]:
    value = {"seq": record.seq, "threadId": record.thread_id, "source": record.source,
             "direction": record.direction, "method": record.method, "rawText": record.raw_text,
             "sha256": _sha(record.raw_text.encode("utf-8"))}
    if local is not None:
        value["localEvidence"] = dict(local)
    return value


def reserved_record(record: TraceRecord) -> bool:
    return (bool(record.method and record.method.startswith("$local/")) or record.item_type == ITEM_TYPE
            or bool(record.thread_id and record.thread_id.startswith(GROUP_PREFIX)))


def document_descriptor(trace: TraceStore, record: TraceRecord) -> dict[str, Any] | None:
    """Verify current admission, not just an envelope's self-description."""
    trace.require_workbench()
    if record.method != METHOD or record.direction != "internal":
        return None
    with trace._lock:
        row = trace.db.execute("SELECT * FROM supplied_text_files WHERE seq=?", (record.seq,)).fetchone()
    if row is None:
        return None
    try:
        receipt = json.loads(row["receipt_json"])
        data = bytes(row["original_bytes"])
        text = data.decode("utf-8")
        coords = _coordinates(row["id"])
        if (not re.fullmatch(r"file_[0-9a-f]{32}", row["id"])
                or receipt["format"] != FORMAT or receipt["parserVersion"] != "supplied-text-admission/v1"
                or receipt["classification"] != CLASSIFICATION
                or receipt["fileSha256"] != _sha(data) or type(receipt["byteLength"]) is not int
                or receipt["byteLength"] != len(data) or receipt["requestId"] != row["request_id"]
                or any(receipt[key] != value for key, value in coords.items())
                or receipt["seq"] != record.seq or type(receipt["seq"]) is not int
                or row["source"] != record.source or row["thread_id"] != record.thread_id
                or record.source != coords["source"] or record.thread_id != coords["threadId"]
                or record.turn_id != coords["turnId"] or record.item_id != coords["itemId"]
                or record.item_type != ITEM_TYPE or record.rpc_id is not None or record.response_to is not None
                or receipt["admittedAtMs"] != record.observed_at_ms):
            return None
        _name(receipt["fileName"])
        expected = _json(_envelope(receipt, coords, text, receipt["parserVersion"]))
        digest = _sha(expected.encode("utf-8"))
        if (record.raw_text != expected or receipt["hostRecordSha256"] != digest
                or row["host_record_sha256"] != digest):
            return None
        return descriptor(receipt)
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError):
        return None


def verified_documents(trace: TraceStore, records: list[TraceRecord]) -> dict[int, dict[str, Any]]:
    return {record.seq: value for record in records if reserved_record(record)
            and (value := document_descriptor(trace, record)) is not None}


def group_metadata(trace: TraceStore, thread_id: str) -> dict[str, Any]:
    trace.require_workbench()
    if not thread_id.startswith(GROUP_PREFIX):
        return {}
    with trace._lock:
        row = trace.db.execute("SELECT seq FROM supplied_text_files WHERE thread_id=?", (thread_id,)).fetchone()
        if row is None:
            return {}
        try:
            record = trace.get(row["seq"])
        except KeyError:
            return {}
        value = document_descriptor(trace, record)
    return {"sourceKind": "supplied-text", "sourceOnly": True, "preview": value["fileName"]} if value else {}


class SuppliedText:
    def __init__(self, trace: TraceStore) -> None:
        trace.require_workbench()
        self.trace = trace
        ensure_schema(trace)

    @staticmethod
    def _prepare(data: bytes, identity: dict[str, Any]) -> tuple[dict[str, Any], str]:
        try:
            text = data.decode("utf-8")
        except UnicodeError:
            raise _error(400, "supplied file must contain strict UTF-8 text") from None
        preview = {**identity, "parserVersion": PARSER_VERSION, "classification": CLASSIFICATION,
                   "textExcerpt": text[:480], "truncated": len(text) > 480,
                   "discoverableFieldCount": int(bool(text.strip()))}
        preview["previewFingerprint"] = _sha(_json(preview).encode("utf-8"))
        # Fixed-width host IDs and the largest public sequence bound make this
        # stateless preflight conservative for every actual committed record.
        coords = _coordinates("file_" + "0" * 32)
        raw = _json(_envelope(identity, coords, text, PARSER_VERSION))
        proof = {**preview, **coords, "hostRecordSha256": _sha(raw.encode("utf-8"))}
        record = TraceRecord(2**53 - 1, coords["source"], "internal", 0, None, None, METHOD, None,
                            coords["threadId"], coords["turnId"], coords["itemId"], ITEM_TYPE, raw)
        if len(raw.encode("utf-8")) > MAX_RECORD_BYTES:
            raise _error(413, "supplied text generated envelope exceeds 64 KiB")
        if len(_json(context_record(record, descriptor(proof))).encode("utf-8")) > MAX_CONTEXT_RECORD_BYTES:
            raise _error(413, "supplied text frozen record exceeds 96 KiB")
        bounded_response({"preview": preview})
        return preview, text

    def preview(self, data: bytes, *, file_name: str, format: str = FORMAT) -> dict[str, Any]:
        self.trace.require_workbench()
        return self._prepare(data, _identity(data, file_name, format))[0]

    def commit(self, data: bytes, *, request_id: str, preview_fingerprint: str,
               file_name: str, format: str = FORMAT) -> tuple[dict[str, Any], bool]:
        self.trace.require_workbench()
        request_id = _request(request_id)
        identity = _identity(data, file_name, format)
        fingerprint = _sha(_json(identity).encode("utf-8"))
        with self.trace._lock:
            if self.trace.db.in_transaction:
                raise _error(409, "supplied text requires its own durable transaction")
            self.trace.db.execute("BEGIN IMMEDIATE")
            try:
                prior = self.trace.db.execute("SELECT fingerprint,receipt_json FROM supplied_text_files WHERE request_id=?",
                                              (request_id,)).fetchone()
                if prior is not None:
                    if prior["fingerprint"] != fingerprint:
                        raise _error(409, "requestId already belongs to different supplied text")
                    receipt = json.loads(prior["receipt_json"])
                    if preview_fingerprint != receipt["previewFingerprint"]:
                        raise _error(409, "requestId already belongs to a different supplied text preview")
                    bounded_response({"receipt": receipt})
                    self.trace.db.execute("COMMIT")
                    return receipt, False
                preview, text = self._prepare(data, identity)
                if preview_fingerprint != preview["previewFingerprint"]:
                    raise _error(409, "supplied text preview changed; review this exact file again")
                coords = _coordinates("file_" + uuid.uuid4().hex)
                raw = _json(_envelope(identity, coords, text, PARSER_VERSION))
                digest = _sha(raw.encode("utf-8"))
                admitted = int(time.time() * 1000)
                record = self.trace.append(source=coords["source"], direction="internal",
                    message=json.loads(raw), raw_text=raw, observed_at_ms=admitted)
                if not 1 <= record.seq <= 2**53 - 1:
                    raise _error(413, "supplied text sequence exceeds the public reference bound")
                receipt = {**preview, **coords, "requestId": request_id, "admittedAtMs": admitted,
                           "seq": record.seq, "hostRecordSha256": digest}
                bounded_response({"receipt": receipt})
                bounded_response({"receipt": receipt, "contentBase64": base64.b64encode(data).decode("ascii")})
                self.trace.db.execute("INSERT INTO supplied_text_files VALUES(?,?,?,?,?,?,?,?,?)", (
                    coords["id"], request_id, fingerprint, _json(receipt), data, record.seq, coords["source"],
                    coords["threadId"], digest))
                self.trace.db.execute("COMMIT")
                return receipt, True
            except BaseException:
                self.trace.db.execute("ROLLBACK")
                raise

    def get_request(self, request_id: str) -> dict[str, Any]:
        self.trace.require_workbench()
        _request(request_id)
        with self.trace._lock:
            row = self.trace.db.execute("SELECT receipt_json FROM supplied_text_files WHERE request_id=?", (request_id,)).fetchone()
        if row is None:
            raise _error(404, "supplied text receipt not found")
        receipt = json.loads(row[0])
        bounded_response({"receipt": receipt})
        return receipt

    def get(self, identifier: str) -> dict[str, Any]:
        self.trace.require_workbench()
        with self.trace._lock:
            row = self.trace.db.execute("SELECT receipt_json,original_bytes FROM supplied_text_files WHERE id=?", (identifier,)).fetchone()
        if row is None:
            raise _error(404, "supplied text file not found")
        receipt, data = json.loads(row[0]), bytes(row[1])
        if receipt["fileSha256"] != _sha(data) or receipt["byteLength"] != len(data):
            raise _error(409, "supplied text original bytes do not match the receipt")
        return bounded_response({"receipt": receipt, "contentBase64": base64.b64encode(data).decode("ascii")})


def upload_body(handler: Any, *, commit: bool) -> dict[str, Any]:
    from .investigation import InvestigationError
    fields = {"format", "fileName", "contentBase64"} | ({"requestId", "previewFingerprint"} if commit else set())
    try:
        headers = handler.headers
        lengths = headers.get_all("Content-Length", []) if hasattr(headers, "get_all") else [headers.get("Content-Length", "")]
        if (len(lengths) != 1 or not isinstance(lengths[0], str) or not lengths[0].isascii()
                or not lengths[0].isdecimal() or headers.get("Transfer-Encoding") is not None
                or headers.get("Content-Encoding") is not None):
            raise ValueError
        length = int(lengths[0])
        if length > MAX_UPLOAD_BYTES:
            raise _error(413, "supplied text upload exceeds its byte limit")
        raw = handler.rfile.read(length)
        if len(raw) != length:
            raise ValueError
        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError
                result[key] = value
            return result
        def no_constant(_):
            raise ValueError
        body = json.loads(raw, object_pairs_hook=unique, parse_constant=no_constant)
        if not isinstance(body, dict) or set(body) != fields:
            raise ValueError
        encoded = body.pop("contentBase64")
        if not isinstance(encoded, str) or len(encoded) > 4 * ((MAX_FILE_BYTES + 2) // 3):
            raise ValueError
        data = base64.b64decode(encoded, validate=True)
        if base64.b64encode(data).decode("ascii") != encoded:
            raise ValueError
        _identity(data, body["fileName"], body["format"])
        if commit:
            _request(body["requestId"])
            if not isinstance(body["previewFingerprint"], str) or not re.fullmatch(r"[0-9a-f]{64}", body["previewFingerprint"]):
                raise ValueError
        return {**body, "data": data}
    except InvestigationError:
        raise
    except (ValueError, TypeError, UnicodeError, RecursionError, OverflowError):
        raise _error(400, "invalid supplied text upload envelope") from None
