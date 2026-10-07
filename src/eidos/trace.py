from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import sqlite3
import time
import threading
from typing import Any, Iterable, Iterator, Literal, Mapping

Direction = Literal["client_to_appserver", "appserver_to_client", "provider_request", "provider_response", "internal"]


def _json_id(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _nested_id(value: Any, key: str) -> str | None:
    if isinstance(value, Mapping):
        direct = value.get(key)
        if isinstance(direct, str):
            return direct
    return None


def _extract_coordinates(message: Mapping[str, Any]) -> tuple[str | None, str | None, str | None, str | None]:
    params = message.get("params")
    result = message.get("result")
    thread_id = turn_id = item_id = item_type = None

    if isinstance(params, Mapping):
        thread_id = _nested_id(params, "threadId") or _nested_id(params, "thread_id")
        turn_id = _nested_id(params, "turnId") or _nested_id(params, "turn_id")
        item_id = _nested_id(params, "itemId") or _nested_id(params, "item_id")
        item = params.get("item")
        if isinstance(item, Mapping):
            item_id = item_id or _nested_id(item, "id")
            value = item.get("type")
            item_type = str(value) if value is not None else None
        thread = params.get("thread")
        if isinstance(thread, Mapping):
            thread_id = thread_id or _nested_id(thread, "id")
        turn = params.get("turn")
        if isinstance(turn, Mapping):
            turn_id = turn_id or _nested_id(turn, "id")

    if isinstance(result, Mapping):
        thread = result.get("thread")
        if isinstance(thread, Mapping):
            thread_id = thread_id or _nested_id(thread, "id")
        turn = result.get("turn")
        if isinstance(turn, Mapping):
            turn_id = turn_id or _nested_id(turn, "id")

    return thread_id, turn_id, item_id, item_type


@dataclass(frozen=True)
class TraceRecord:
    seq: int
    source: str
    direction: str
    observed_at_ms: int
    emitted_at_ms: int | None
    rpc_id: str | None
    method: str | None
    response_to: str | None
    thread_id: str | None
    turn_id: str | None
    item_id: str | None
    item_type: str | None
    raw_text: str

    @property
    def message(self) -> dict[str, Any]:
        return json.loads(self.raw_text)


class TraceStore:
    """Append-only evidence store for native protocol boundaries.

    Raw JSONL is authoritative evidence. The extracted columns are intentionally
    disposable projections used for indexing and UI. Unknown fields and methods
    survive because the original record is never normalized away.
    """

    def __init__(self, path: str | Path = ":memory:") -> None:
        self.db = sqlite3.connect(str(path), isolation_level=None, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS trace_records(
              seq INTEGER PRIMARY KEY AUTOINCREMENT,
              source TEXT NOT NULL,
              direction TEXT NOT NULL,
              observed_at_ms INTEGER NOT NULL,
              emitted_at_ms INTEGER,
              rpc_id TEXT,
              method TEXT,
              response_to TEXT,
              thread_id TEXT,
              turn_id TEXT,
              item_id TEXT,
              item_type TEXT,
              raw_text TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS trace_thread_seq ON trace_records(thread_id, seq);
            CREATE INDEX IF NOT EXISTS trace_turn_seq ON trace_records(turn_id, seq);
            CREATE INDEX IF NOT EXISTS trace_item_seq ON trace_records(item_id, seq);
            CREATE INDEX IF NOT EXISTS trace_rpc ON trace_records(rpc_id, seq);
            """
        )

    def close(self) -> None:
        with self._lock:
            self.db.close()

    def append_line(
        self,
        *,
        source: str,
        direction: Direction,
        raw_text: str,
        observed_at_ms: int | None = None,
    ) -> TraceRecord:
        raw_text = raw_text.rstrip("\r\n")
        message = json.loads(raw_text)
        if not isinstance(message, dict):
            raise ValueError("JSON-RPC evidence must be a JSON object")
        return self.append(
            source=source,
            direction=direction,
            message=message,
            raw_text=raw_text,
            observed_at_ms=observed_at_ms,
        )

    def append(
        self,
        *,
        source: str,
        direction: Direction,
        message: Mapping[str, Any],
        raw_text: str | None = None,
        observed_at_ms: int | None = None,
    ) -> TraceRecord:
        observed = int(observed_at_ms if observed_at_ms is not None else time.time() * 1000)
        raw = raw_text if raw_text is not None else json.dumps(message, ensure_ascii=False, separators=(",", ":"))
        rpc_id = _json_id(message.get("id"))
        method_value = message.get("method")
        method = str(method_value) if method_value is not None else None
        thread_id, turn_id, item_id, item_type = _extract_coordinates(message)
        emitted = message.get("emittedAtMs")
        emitted_at_ms = int(emitted) if isinstance(emitted, (int, float)) else None
        with self._lock:
            response_to = None
            prior = None
            if method is None and rpc_id is not None:
                prior = self.db.execute(
                    "SELECT * FROM trace_records WHERE source=? AND rpc_id=? AND method IS NOT NULL "
                    "AND direction<>? ORDER BY seq DESC LIMIT 1",
                    (source, rpc_id, direction),
                ).fetchone()
                if prior is not None:
                    response_to = prior["method"]
                    thread_id = thread_id or prior["thread_id"]
                    turn_id = turn_id or prior["turn_id"]
                    item_id = item_id or prior["item_id"]
                    item_type = item_type or prior["item_type"]
            cur = self.db.execute(
                """
                INSERT INTO trace_records(
                  source,direction,observed_at_ms,emitted_at_ms,rpc_id,method,response_to,
                  thread_id,turn_id,item_id,item_type,raw_text
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    source,
                    direction,
                    observed,
                    emitted_at_ms,
                    rpc_id,
                    method,
                    response_to,
                    thread_id,
                    turn_id,
                    item_id,
                    item_type,
                    raw,
                ),
            )
            seq = int(cur.lastrowid)
            if prior is not None:
                self.db.execute(
                    "UPDATE trace_records SET "
                    "thread_id=COALESCE(thread_id,?), turn_id=COALESCE(turn_id,?), "
                    "item_id=COALESCE(item_id,?), item_type=COALESCE(item_type,?) WHERE seq=?",
                    (thread_id, turn_id, item_id, item_type, prior["seq"]),
                )
            row = self.db.execute("SELECT * FROM trace_records WHERE seq=?", (seq,)).fetchone()
            assert row is not None
            return TraceRecord(**dict(row))

    def get(self, seq: int) -> TraceRecord:
        with self._lock:
            row = self.db.execute("SELECT * FROM trace_records WHERE seq=?", (seq,)).fetchone()
            if row is None:
                raise KeyError(seq)
            return TraceRecord(**dict(row))

    def records(self, *, thread_id: str | None = None) -> list[TraceRecord]:
        with self._lock:
            if thread_id is None:
                rows = self.db.execute("SELECT * FROM trace_records ORDER BY seq").fetchall()
            else:
                rows = self.db.execute("SELECT * FROM trace_records WHERE thread_id=? ORDER BY seq", (thread_id,)).fetchall()
            return [TraceRecord(**dict(row)) for row in rows]

    def threads(self) -> list[dict[str, Any]]:
        with self._lock:
            return [
                dict(row)
                for row in self.db.execute(
                    """
                    SELECT thread_id, MIN(seq) AS first_seq, MAX(seq) AS last_seq,
                           COUNT(*) AS record_count,
                           COUNT(DISTINCT turn_id) AS turn_count
                    FROM trace_records
                    WHERE thread_id IS NOT NULL
                    GROUP BY thread_id
                    ORDER BY last_seq DESC
                    """
                ).fetchall()
            ]

    def import_jsonl(
        self,
        lines: Iterable[str],
        *,
        source: str = "codex-app-server",
        direction: Direction = "appserver_to_client",
    ) -> int:
        count = 0
        for line in lines:
            if not line.strip():
                continue
            self.append_line(source=source, direction=direction, raw_text=line)
            count += 1
        return count
