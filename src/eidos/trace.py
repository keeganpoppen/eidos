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

    method = message.get("method")
    if item_type is None and isinstance(method, str):
        if method.startswith("item/reasoning/"):
            item_type = "reasoning"
        elif method.startswith("item/agentMessage/"):
            item_type = "agentMessage"
        elif method.startswith("item/commandExecution/"):
            item_type = "commandExecution"
        elif method.startswith("item/fileChange/"):
            item_type = "fileChange"
        elif method.startswith("item/mcpToolCall/"):
            item_type = "mcpToolCall"

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
        if str(path) != ":memory:":
            Path(path).expanduser().parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path), isolation_level=None, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self.db.execute("PRAGMA foreign_keys=ON")
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

            CREATE TABLE IF NOT EXISTS thread_annotations(
              thread_id TEXT PRIMARY KEY,
              kind TEXT NOT NULL,
              parent_thread_id TEXT,
              metadata_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS semantic_observers(
              name TEXT PRIMARY KEY,
              lens TEXT NOT NULL,
              reliability REAL NOT NULL DEFAULT 1.0,
              prompt TEXT
            );
            CREATE TABLE IF NOT EXISTS semantic_revisions(
              revision_id TEXT PRIMARY KEY,
              thread_id TEXT NOT NULL,
              lens TEXT NOT NULL,
              observer TEXT NOT NULL,
              horizon_seq INTEGER NOT NULL,
              parent_revision TEXT,
              confidence REAL NOT NULL,
              created_at_ms INTEGER NOT NULL,
              note TEXT
            );
            CREATE INDEX IF NOT EXISTS semantic_revision_thread
              ON semantic_revisions(thread_id, lens, horizon_seq);
            CREATE TABLE IF NOT EXISTS semantic_nodes(
              revision_id TEXT NOT NULL,
              node_id TEXT NOT NULL,
              parent_node_id TEXT,
              ordinal INTEGER NOT NULL,
              title TEXT NOT NULL,
              summary TEXT NOT NULL,
              confidence REAL NOT NULL,
              PRIMARY KEY(revision_id, node_id),
              FOREIGN KEY(revision_id) REFERENCES semantic_revisions(revision_id)
            );
            CREATE TABLE IF NOT EXISTS semantic_support(
              revision_id TEXT NOT NULL,
              node_id TEXT NOT NULL,
              ordinal INTEGER NOT NULL,
              start_seq INTEGER NOT NULL,
              end_seq INTEGER NOT NULL,
              weight REAL NOT NULL,
              label TEXT,
              PRIMARY KEY(revision_id, node_id, ordinal),
              FOREIGN KEY(revision_id, node_id)
                REFERENCES semantic_nodes(revision_id, node_id)
            );
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

    def annotate_thread(
        self,
        thread_id: str,
        *,
        kind: str,
        parent_thread_id: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        with self._lock:
            self.db.execute(
                """
                INSERT INTO thread_annotations(thread_id,kind,parent_thread_id,metadata_json)
                VALUES (?,?,?,?)
                ON CONFLICT(thread_id) DO UPDATE SET
                  kind=excluded.kind,
                  parent_thread_id=excluded.parent_thread_id,
                  metadata_json=excluded.metadata_json
                """,
                (
                    thread_id,
                    kind,
                    parent_thread_id,
                    json.dumps(dict(metadata or {}), sort_keys=True, separators=(",", ":")),
                ),
            )

    def threads(self, *, include_internal: bool = False) -> list[dict[str, Any]]:
        with self._lock:
            internal_clause = "" if include_internal else "AND a.thread_id IS NULL"
            rows = self.db.execute(
                f"""
                SELECT r.thread_id, MIN(r.seq) AS first_seq, MAX(r.seq) AS last_seq,
                       COUNT(*) AS record_count,
                       COUNT(DISTINCT r.turn_id) AS turn_count
                FROM trace_records r
                LEFT JOIN thread_annotations a ON a.thread_id=r.thread_id
                WHERE r.thread_id IS NOT NULL {internal_clause}
                GROUP BY r.thread_id
                ORDER BY last_seq DESC
                """
            ).fetchall()
            return [dict(row) for row in rows]

    def register_semantic_observer(
        self,
        *,
        name: str,
        lens: str,
        reliability: float = 1.0,
        prompt: str | None = None,
    ) -> None:
        with self._lock:
            self.db.execute(
                """
                INSERT INTO semantic_observers(name,lens,reliability,prompt)
                VALUES (?,?,?,?)
                ON CONFLICT(name) DO UPDATE SET
                  lens=excluded.lens,
                  reliability=excluded.reliability,
                  prompt=excluded.prompt
                """,
                (name, lens, float(reliability), prompt),
            )

    def put_semantic_revision(
        self,
        *,
        thread_id: str,
        lens: str,
        observer: str,
        horizon_seq: int,
        nodes: Iterable[Mapping[str, Any]],
        confidence: float = 1.0,
        parent_revision: str | None = None,
        note: str | None = None,
        revision_id: str | None = None,
        created_at_ms: int | None = None,
    ) -> str:
        """Persist one immutable semantic interpretation of a thread.

        A revision is a proposal, not truth. Several observers may publish
        competing or overlapping revisions for the same lens and horizon.
        Support is represented as one or more trace ranges per node, so a
        semantic node may be non-contiguous in the native transcript.
        """

        import uuid

        revision_id = revision_id or f"sem_{uuid.uuid4().hex}"
        created = int(created_at_ms if created_at_ms is not None else time.time() * 1000)
        node_values = [dict(node) for node in nodes]
        with self._lock:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                self.db.execute(
                    """
                    INSERT INTO semantic_revisions(
                      revision_id,thread_id,lens,observer,horizon_seq,parent_revision,
                      confidence,created_at_ms,note
                    ) VALUES (?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        revision_id,
                        thread_id,
                        lens,
                        observer,
                        int(horizon_seq),
                        parent_revision,
                        float(confidence),
                        created,
                        note,
                    ),
                )
                for ordinal, node in enumerate(node_values):
                    node_id = str(node.get("id") or f"node-{ordinal}")
                    self.db.execute(
                        """
                        INSERT INTO semantic_nodes(
                          revision_id,node_id,parent_node_id,ordinal,title,summary,confidence
                        ) VALUES (?,?,?,?,?,?,?)
                        """,
                        (
                            revision_id,
                            node_id,
                            node.get("parent"),
                            int(node.get("ordinal", ordinal)),
                            str(node.get("title") or "Untitled"),
                            str(node.get("summary") or ""),
                            float(node.get("confidence", 1.0)),
                        ),
                    )
                    for support_ordinal, span in enumerate(node.get("support") or []):
                        start = int(span["start"])
                        end = int(span.get("end", start))
                        if start > end:
                            raise ValueError(f"semantic support starts after it ends: {start}>{end}")
                        self.db.execute(
                            """
                            INSERT INTO semantic_support(
                              revision_id,node_id,ordinal,start_seq,end_seq,weight,label
                            ) VALUES (?,?,?,?,?,?,?)
                            """,
                            (
                                revision_id,
                                node_id,
                                support_ordinal,
                                start,
                                end,
                                float(span.get("weight", 1.0)),
                                span.get("label"),
                            ),
                        )
                self.db.execute("COMMIT")
            except Exception:
                self.db.execute("ROLLBACK")
                raise
        return revision_id

    def semantic_revisions(
        self,
        thread_id: str,
        *,
        lens: str | None = None,
    ) -> list[dict[str, Any]]:
        with self._lock:
            sql = """
                SELECT r.*, COALESCE(o.reliability,1.0) AS reliability,
                       r.confidence * COALESCE(o.reliability,1.0) AS score
                FROM semantic_revisions r
                LEFT JOIN semantic_observers o ON o.name=r.observer
                WHERE r.thread_id=?
            """
            args: list[Any] = [thread_id]
            if lens is not None:
                sql += " AND r.lens=?"
                args.append(lens)
            sql += " ORDER BY r.horizon_seq DESC, r.created_at_ms DESC"
            return [dict(row) for row in self.db.execute(sql, args).fetchall()]

    def semantic_outline(
        self,
        thread_id: str,
        *,
        lens: str = "thread",
        revision_id: str | None = None,
    ) -> dict[str, Any] | None:
        """Return one selected semantic revision plus its nodes/support.

        Selection is intentionally simple in v0: among revisions at the most
        recent horizon, prefer the current retrospective lineage when present,
        then observer confidence weighted by its reliability prior. Historical
        experimental lineages remain queryable.
        """

        with self._lock:
            if revision_id is None:
                row = self.db.execute(
                    """
                    WITH horizon AS (
                      SELECT MAX(horizon_seq) AS h
                      FROM semantic_revisions
                      WHERE thread_id=? AND lens=?
                    )
                    SELECT r.*, COALESCE(o.reliability,1.0) AS reliability,
                           r.confidence * COALESCE(o.reliability,1.0) AS score
                    FROM semantic_revisions r
                    LEFT JOIN semantic_observers o ON o.name=r.observer
                    JOIN horizon ON r.horizon_seq=horizon.h
                    WHERE r.thread_id=? AND r.lens=?
                    ORDER BY
                      CASE
                        WHEN r.observer='retrospective-tree' THEN 2
                        WHEN r.observer='retrospective' THEN 1
                        ELSE 0
                      END DESC,
                      score DESC,
                      r.created_at_ms DESC
                    LIMIT 1
                    """,
                    (thread_id, lens, thread_id, lens),
                ).fetchone()
            else:
                row = self.db.execute(
                    """
                    SELECT r.*, COALESCE(o.reliability,1.0) AS reliability,
                           r.confidence * COALESCE(o.reliability,1.0) AS score
                    FROM semantic_revisions r
                    LEFT JOIN semantic_observers o ON o.name=r.observer
                    WHERE r.revision_id=? AND r.thread_id=?
                    """,
                    (revision_id, thread_id),
                ).fetchone()
            if row is None:
                return None
            revision = dict(row)
            nodes = []
            node_rows = self.db.execute(
                "SELECT * FROM semantic_nodes WHERE revision_id=? ORDER BY ordinal,node_id",
                (revision["revision_id"],),
            ).fetchall()
            for node_row in node_rows:
                node = dict(node_row)
                supports = [
                    {
                        "start": support["start_seq"],
                        "end": support["end_seq"],
                        "weight": support["weight"],
                        "label": support["label"],
                    }
                    for support in self.db.execute(
                        """
                        SELECT * FROM semantic_support
                        WHERE revision_id=? AND node_id=?
                        ORDER BY ordinal
                        """,
                        (revision["revision_id"], node["node_id"]),
                    ).fetchall()
                ]
                node["support"] = supports
                nodes.append(node)
            revision["nodes"] = nodes
            return revision

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
