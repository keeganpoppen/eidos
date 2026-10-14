"""Disposable discovery over explicit displayed public-history text fields.

Hot queries parse no source JSON. Cold/dirty thread projection and literal text
scans scale with corpus size; result limits are not CPU, memory or database quotas.
Names locate recorded data, never confer authority or private-store access.
"""
from __future__ import annotations

import base64
from contextlib import contextmanager
import hashlib
import json
import sqlite3
from typing import Any, Iterator, Mapping
import uuid

from .history_projection import TextField, item_text_fields
from .investigation import InvestigationError, MAX_PROMPT_BYTES, MAX_RECORDS, _json, _text
from .investigation_reads import InvestigationReads
from .trace import TraceRecord, TraceStore
from .view import project_records

SCOPE = "displayed-history-text/v1"
INDEX_VERSION = "evidence-discovery-index/v1"
METHODS = (
    "turn/start", "item/started", "item/completed", "$history/item",
    "item/agentMessage/delta", "item/commandExecution/outputDelta",
    "item/reasoning/summaryTextDelta", "item/reasoning/textDelta",
)
DIRECTIONS = ("internal", "client_to_appserver", "appserver_to_client")


def _hash(value: Any) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _raw_hash(record: TraceRecord) -> str:
    return hashlib.sha256(record.raw_text.encode("utf-8")).hexdigest()


def _excerpt(text: str, term: str) -> tuple[str, int, int]:
    """Original Unicode offsets, including casefold expansions such as ß → ss."""
    found = text.casefold().find(term)
    if found < 0:
        raise InvestigationError(409, "source field no longer matches this query; refresh search")
    folded, start, end = 0, 0, len(text)
    for index, character in enumerate(text):
        following = folded + len(character.casefold())
        if folded <= found < following:
            start = index
        if following >= found + len(term):
            end = index + 1
            break
        folded = following
    left = max(0, start - max(0, 238 - (end - start)) // 2)
    right = min(len(text), left + 238)
    left = max(0, right - 238)
    return ("…" if left else "") + text[left:right] + ("…" if right < len(text) else ""), left, right


class EvidenceDiscovery:
    def __init__(self, trace: TraceStore) -> None:
        trace.require_workbench()
        self.trace = trace
        with trace._lock:
            trace.db.executescript("""
                CREATE TABLE IF NOT EXISTS evidence_discovery_meta(
                    id INTEGER PRIMARY KEY CHECK(id=1), schema_version TEXT NOT NULL,
                    epoch TEXT NOT NULL, generation INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS evidence_discovery_dirty(thread_id TEXT PRIMARY KEY);
                CREATE TABLE IF NOT EXISTS evidence_discovery_fields(
                    id TEXT PRIMARY KEY, thread_id TEXT NOT NULL, turn_id TEXT NOT NULL,
                    item_id TEXT, field TEXT NOT NULL, order_seq INTEGER NOT NULL,
                    version TEXT NOT NULL, text_value TEXT NOT NULL, search_text TEXT NOT NULL,
                    segments_json TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS evidence_discovery_order
                    ON evidence_discovery_fields(order_seq,id);
                CREATE INDEX IF NOT EXISTS evidence_discovery_thread
                    ON evidence_discovery_fields(thread_id);
                CREATE TRIGGER IF NOT EXISTS evidence_discovery_insert AFTER INSERT ON trace_records BEGIN
                    INSERT OR IGNORE INTO evidence_discovery_dirty SELECT NEW.thread_id WHERE NEW.thread_id IS NOT NULL;
                    UPDATE evidence_discovery_meta SET generation=generation+1 WHERE id=1;
                END;
                CREATE TRIGGER IF NOT EXISTS evidence_discovery_delete AFTER DELETE ON trace_records BEGIN
                    INSERT OR IGNORE INTO evidence_discovery_dirty SELECT OLD.thread_id WHERE OLD.thread_id IS NOT NULL;
                    UPDATE evidence_discovery_meta SET generation=generation+1 WHERE id=1;
                END;
                CREATE TRIGGER IF NOT EXISTS evidence_discovery_update AFTER UPDATE ON trace_records BEGIN
                    INSERT OR IGNORE INTO evidence_discovery_dirty SELECT OLD.thread_id WHERE OLD.thread_id IS NOT NULL;
                    INSERT OR IGNORE INTO evidence_discovery_dirty SELECT NEW.thread_id WHERE NEW.thread_id IS NOT NULL;
                    UPDATE evidence_discovery_meta SET generation=generation+1 WHERE id=1;
                END;
                CREATE TRIGGER IF NOT EXISTS evidence_discovery_annotation_insert AFTER INSERT ON thread_annotations BEGIN
                    INSERT OR IGNORE INTO evidence_discovery_dirty VALUES(NEW.thread_id);
                    UPDATE evidence_discovery_meta SET generation=generation+1 WHERE id=1;
                END;
                CREATE TRIGGER IF NOT EXISTS evidence_discovery_annotation_delete AFTER DELETE ON thread_annotations BEGIN
                    INSERT OR IGNORE INTO evidence_discovery_dirty VALUES(OLD.thread_id);
                    UPDATE evidence_discovery_meta SET generation=generation+1 WHERE id=1;
                END;
                CREATE TRIGGER IF NOT EXISTS evidence_discovery_annotation_update AFTER UPDATE ON thread_annotations BEGIN
                    INSERT OR IGNORE INTO evidence_discovery_dirty VALUES(OLD.thread_id);
                    INSERT OR IGNORE INTO evidence_discovery_dirty VALUES(NEW.thread_id);
                    UPDATE evidence_discovery_meta SET generation=generation+1 WHERE id=1;
                END;
            """)
        with self._snapshot():
            row = trace.db.execute("SELECT schema_version FROM evidence_discovery_meta WHERE id=1").fetchone()
            if row is None or row[0] != INDEX_VERSION:
                self._reset()

    @contextmanager
    def _snapshot(self) -> Iterator[None]:
        self.trace.require_workbench()
        with self.trace._lock:
            self.trace.db.execute("BEGIN IMMEDIATE")
            try:
                yield
                self.trace.db.execute("COMMIT")
            except BaseException:
                self.trace.db.execute("ROLLBACK")
                raise

    def _reset(self) -> None:
        self.trace.db.execute("DELETE FROM evidence_discovery_fields")
        self.trace.db.execute("DELETE FROM evidence_discovery_dirty")
        self.trace.db.execute("INSERT INTO evidence_discovery_dirty SELECT DISTINCT thread_id FROM trace_records WHERE thread_id IS NOT NULL")
        self.trace.db.execute("INSERT OR REPLACE INTO evidence_discovery_meta VALUES(1,?,?,0)",
                              (INDEX_VERSION, uuid.uuid4().hex))

    def rebuild(self) -> None:
        """Replace only the derived index, invalidating existing cursors and hits."""
        with self._snapshot():
            self._reset()
            self._refresh()

    def _refresh(self) -> None:
        epoch = self._generation()[0]
        threads = self.trace.db.execute("SELECT thread_id FROM evidence_discovery_dirty ORDER BY thread_id").fetchall()
        for row in threads:
            thread_id = row[0]
            self.trace.db.execute("DELETE FROM evidence_discovery_fields WHERE thread_id=?", (thread_id,))
            hidden = self.trace.db.execute("SELECT 1 FROM thread_annotations WHERE thread_id=?", (thread_id,)).fetchone()
            if hidden is None:
                sql = ("SELECT * FROM trace_records WHERE thread_id=? AND direction IN (?,?,?) "
                       f"AND method IN ({','.join('?' for _ in METHODS)}) ORDER BY seq")
                records = [TraceRecord(**dict(record)) for record in self.trace.db.execute(sql, (thread_id, *DIRECTIONS, *METHODS))]
                for turn in project_records(thread_id, records).turns:
                    for item in turn.items.values():
                        first = min(record.seq for record in item.events)
                        for field in item_text_fields(item):
                            self._index_field(thread_id, turn.turn_id, item.item_id, first, field, epoch)
                    # Exactly the renderer's user-input fallback, over eligible history.
                    if not any(item.item_type == "userMessage" for item in turn.items.values()):
                        for record in turn.events:
                            if record.method != "turn/start":
                                continue
                            params = record.message.get("params")
                            inputs = params.get("input") if isinstance(params, dict) else None
                            if isinstance(inputs, list):
                                for index, value in enumerate(inputs):
                                    if isinstance(value, dict) and value.get("type") == "text" and isinstance(value.get("text"), str):
                                        self._index_field(thread_id, turn.turn_id, None, record.seq,
                                            TextField(f"turn.input/{index}/text", [(value["text"], record)]), epoch)
            self.trace.db.execute("DELETE FROM evidence_discovery_dirty WHERE thread_id=?", (thread_id,))

    def _index_field(self, thread_id: str, turn_id: str, item_id: str | None,
                     first: int, field: TextField, epoch: str) -> None:
        text = field.text
        if not text:
            return
        segments, offset = [], 0
        identities = []
        for chunk, record in field.segments:
            if not chunk:
                continue
            if record is None:
                raise ValueError("displayed text has no recorded source")
            digest = _raw_hash(record)
            segments.append({"start": offset, "end": offset + len(chunk), "seq": record.seq, "sha256": digest})
            identities.append([record.seq, digest, record.thread_id, record.turn_id, record.item_id,
                               record.source, record.direction, record.method])
            offset += len(chunk)
        identifier = "ef1_" + _hash([thread_id, first, field.field])
        version = "efv1_" + _hash([INDEX_VERSION, epoch, thread_id, turn_id, item_id, field.field, text, identities])
        self.trace.db.execute("INSERT INTO evidence_discovery_fields VALUES(?,?,?,?,?,?,?,?,?,?)", (
            identifier, thread_id, turn_id, item_id, field.field, first, version, text, text.casefold(), _json(segments)))

    def _generation(self) -> list[Any]:
        row = self.trace.db.execute("SELECT epoch,generation FROM evidence_discovery_meta WHERE id=1").fetchone()
        return [row[0], row[1]]

    @staticmethod
    def _params(query: Mapping[str, list[str]], allowed: set[str]) -> tuple[dict[str, str], str]:
        params = InvestigationReads._params(query, allowed)
        raw = params.get("q")
        term = _text(raw.strip() if isinstance(raw, str) else raw, "q", 200).casefold()
        return params, term

    @staticmethod
    def _cursor(value: Mapping[str, Any]) -> str:
        return base64.urlsafe_b64encode(_json(value).encode()).decode().rstrip("=")

    @staticmethod
    def _after(value: str, scope: list[Any], generation: list[Any]) -> list[Any]:
        _text(value, "cursor", 2048)
        try:
            decoded = json.loads(base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True))
            after = decoded["after"]
            if (not isinstance(decoded, dict) or set(decoded) != {"scope", "generation", "after"}
                    or decoded["scope"] != scope or not isinstance(after, list) or len(after) != 2
                    or type(after[0]) is not int or not 1 <= after[0] <= 2**63 - 1
                    or not isinstance(after[1], str) or not after[1].startswith("ef1_") or len(after[1]) != 68):
                raise ValueError
        except (ValueError, TypeError, KeyError, UnicodeError, RecursionError):
            raise InvestigationError(400, "cursor does not match this evidence query") from None
        if decoded["generation"] != generation:
            raise InvestigationError(409, "source history changed; refresh search before continuing")
        return after

    @staticmethod
    def _hit(row: sqlite3.Row, term: str) -> dict[str, Any]:
        excerpt, left, right = _excerpt(row["text_value"], term)
        seqs = sorted({segment["seq"] for segment in json.loads(row["segments_json"])
                       if segment["start"] < right and segment["end"] > left})
        if not 1 <= len(seqs) <= MAX_RECORDS:
            raise InvestigationError(413, "source excerpt exceeds 256 contributing records")
        return {"id": row["id"], "version": row["version"], "threadId": row["thread_id"],
                "turnId": row["turn_id"], "itemId": row["item_id"], "field": row["field"],
                "anchorSeq": seqs[0], "recordSeqs": seqs, "excerpt": excerpt}

    def search(self, query: Mapping[str, list[str]]) -> dict[str, Any]:
        params, term = self._params(query, {"q", "threadId", "limit", "cursor", "knownVersion"})
        raw_limit = params.get("limit", "20")
        if (len(raw_limit) > 3 or not raw_limit.isascii() or not raw_limit.isdecimal()
                or not 1 <= int(raw_limit) <= 40):
            raise InvestigationError(400, "search limit must be between 1 and 40")
        limit = int(raw_limit)
        thread = params.get("threadId")
        if thread is not None:
            _text(thread, "threadId", 200)
        known = params.get("knownVersion")
        if known is not None:
            _text(known, "knownVersion", 200)
        scope = [SCOPE, term, thread, limit]
        with self._snapshot():
            self._refresh()
            generation = self._generation()
            after = self._after(params["cursor"], scope, generation) if "cursor" in params else None
            version = "es1_" + _hash([scope, generation, after])
            if known == version:
                return {"scope": SCOPE, "version": version, "unchanged": True}
            clauses, args = ["instr(search_text,?)>0"], [term]
            if thread is not None:
                clauses.append("thread_id=?")
                args.append(thread)
            if after:
                clauses.append("(order_seq>? OR (order_seq=? AND id>?))")
                args.extend([after[0], after[0], after[1]])
            rows = self.trace.db.execute("SELECT * FROM evidence_discovery_fields WHERE " + " AND ".join(clauses)
                + " ORDER BY order_seq,id LIMIT ?", (*args, limit + 1)).fetchall()
            hits = [self._hit(row, term) for row in rows[:limit]]
            cursor = None
            if len(rows) > limit:
                last = rows[limit - 1]
                cursor = self._cursor({"scope": scope, "generation": generation, "after": [last["order_seq"], last["id"]]})
            response = {"scope": SCOPE, "version": version, "unchanged": False, "hits": hits, "nextCursor": cursor}
            # Imported coordinates have no legacy length bound. Bound the whole
            # wire envelope, not just excerpts, without hiding matching records.
            if len(_json(response).encode()) > MAX_PROMPT_BYTES:
                raise InvestigationError(413, "search response exceeds 128 KiB; narrow the query")
            return response

    def inspect(self, identifier: str, query: Mapping[str, list[str]]) -> dict[str, Any]:
        params, term = self._params(query, {"q", "version"})
        version = _text(params.get("version"), "version", 200)
        _text(identifier, "hit id", 200)
        with self._snapshot():
            self._refresh()
            row = self.trace.db.execute("SELECT * FROM evidence_discovery_fields WHERE id=?", (identifier,)).fetchone()
            if row is None:
                raise InvestigationError(404, "source field is missing or no longer visible")
            if row["version"] != version:
                raise InvestigationError(409, "source field changed; refresh search before inspecting")
            hit = self._hit(row, term)
            seqs = hit["recordSeqs"]
            marks = ",".join("?" for _ in seqs)
            size = self.trace.db.execute(f"SELECT SUM(length(CAST(raw_text AS BLOB))) FROM trace_records WHERE seq IN ({marks})", seqs).fetchone()[0]
            if size is not None and size > MAX_PROMPT_BYTES:
                raise InvestigationError(413, "exact source inspection exceeds 128 KiB")
            rows = self.trace.db.execute(f"SELECT * FROM trace_records WHERE seq IN ({marks}) ORDER BY seq", seqs).fetchall()
            if len(rows) != len(seqs):
                raise InvestigationError(404, "source records are missing")
            records = [{"seq": value["seq"], "threadId": value["thread_id"], "source": value["source"],
                        "direction": value["direction"], "method": value["method"], "rawText": value["raw_text"],
                        "sha256": hashlib.sha256(value["raw_text"].encode()).hexdigest()} for value in rows]
            response = {"scope": SCOPE, "hit": hit, "records": records}
            # Same compact UTF-8 JSON serialization as the HTTP server, including envelopes.
            if len(_json(response).encode()) > MAX_PROMPT_BYTES:
                raise InvestigationError(413, "exact source inspection exceeds 128 KiB")
            return response
