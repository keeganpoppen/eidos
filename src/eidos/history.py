"""Read-only, turn-bounded history windows over authoritative trace evidence.

Anchors are first evidence sequence numbers, never array offsets. Index queries
may inspect the whole thread, but only selected turns' raw records are loaded and
projected. This is not a byte bound: one turn or semantic outline can be large.
"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
from typing import Any, Iterator

from .trace import TraceRecord, TraceStore


PAGE_SIZE = 40
# Bump when the wire projection changes so an older client-held page cannot
# suppress fetching the new representation after a server upgrade.
PROJECTION_VERSION = "thread-window-v1"
_TURNS = """
    WITH turns AS (
        SELECT turn_id, MIN(seq) AS first_seq, MAX(seq) AS last_seq,
               COUNT(*) AS record_count
        FROM trace_records WHERE thread_id=?
          AND (turn_id IS NOT NULL OR method='turn/start')
        GROUP BY turn_id, CASE WHEN turn_id IS NULL THEN seq ELSE 0 END
    )
"""


class SourceRecordNotFound(ValueError):
    pass


@contextmanager
def history_snapshot(store: TraceStore) -> Iterator[None]:
    """Keep metadata, projection and version in the same SQLite read snapshot."""
    with store._lock:
        store.db.execute("SAVEPOINT history_read")
        try:
            yield
        except BaseException:
            store.db.execute("ROLLBACK TO history_read")
            raise
        finally:
            store.db.execute("RELEASE history_read")


def thread_preview(store: TraceStore, thread_id: str) -> str:
    # Fetch one candidate at a time instead of materializing the entire trace.
    with store._lock:
        candidates = store.db.execute(
            "SELECT raw_text FROM trace_records WHERE thread_id=? AND "
            "(method='turn/start' OR (method IN ('item/completed', '$history/item') "
            "AND item_type='userMessage')) ORDER BY seq", (thread_id,),
        )
        for row in candidates:
            message = json.loads(row[0])
            params = message.get("params")
            if not isinstance(params, dict):
                continue
            item = params.get("item")
            values = params.get("input") if message.get("method") == "turn/start" else (
                item.get("content") if isinstance(item, dict) else None)
            if not isinstance(values, list):
                continue
            for value in values:
                if isinstance(value, dict) and value.get("type") == "text" and value.get("text"):
                    return str(value["text"])[:100]
    return thread_id


def history_window(
    store: TraceStore, thread_id: str, *, anchor_seq: int | None = None,
    around_seq: int | None = None, limit: int = PAGE_SIZE,
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, int]]:
    """Select complete turns by their first record, including pending sends.

    Caller holds history_snapshot through projection. A source jump validates
    exact membership before seeking; interleaved threads cannot match by range.
    """
    if not 1 <= limit <= PAGE_SIZE:
        raise ValueError(f"limit must be between 1 and {PAGE_SIZE}")
    if anchor_seq is not None and around_seq is not None:
        raise ValueError("anchorSeq and aroundSeq are mutually exclusive")
    if any(value is not None and value < 1 for value in (anchor_seq, around_seq)):
        raise ValueError("source anchors must be positive sequence numbers")
    db = store.db
    summary = db.execute(
        "SELECT COUNT(*) AS recordCount, COALESCE(MAX(seq),0) AS lastSeq "
        "FROM trace_records WHERE thread_id=?", (thread_id,),
    ).fetchone()
    total = db.execute(_TURNS + "SELECT COUNT(*) FROM turns", (thread_id,)).fetchone()[0]
    target_seq = around_seq if around_seq is not None else anchor_seq
    if target_seq is not None:
        target = db.execute(
            "SELECT turn_id, method FROM trace_records WHERE seq=? AND thread_id=?",
            (target_seq, thread_id),
        ).fetchone()
        if target is None:
            raise SourceRecordNotFound("That source record does not belong to this thread.")
        if target["turn_id"] is None:
            if target["method"] != "turn/start":
                raise SourceRecordNotFound("That source record has no conversation turn.")
            first = target_seq
        else:
            first = db.execute(
                "SELECT MIN(seq) FROM trace_records WHERE thread_id=? AND turn_id=?",
                (thread_id, target["turn_id"]),
            ).fetchone()[0]
        # A delayed native acknowledgement can merge an earlier pending send
        # into this turn. Follow the saved record, not its old first-seq value.
        anchor_seq = first
        if around_seq is not None:
            position = db.execute(
                _TURNS + "SELECT COUNT(*) FROM turns WHERE first_seq<?", (thread_id, first),
            ).fetchone()[0]
            anchor_seq = db.execute(
                _TURNS + "SELECT first_seq FROM turns ORDER BY first_seq LIMIT 1 OFFSET ?",
                (thread_id, position // limit * limit),
            ).fetchone()[0]
    rows = db.execute(
        _TURNS + "SELECT * FROM turns WHERE first_seq>=? ORDER BY first_seq LIMIT ?",
        (thread_id, anchor_seq or 0, limit + 1),
    ).fetchall()
    if not rows and total:
        # A saved anchor beyond the current trace is stale, not a new identity.
        raise SourceRecordNotFound("The saved source anchor is outside this thread.")
    selected = [dict(row) for row in rows[:limit]]
    first_seq = selected[0]["first_seq"] if selected else None
    earlier = db.execute(
        _TURNS + "SELECT first_seq FROM turns WHERE first_seq<? ORDER BY first_seq DESC LIMIT ?",
        (thread_id, first_seq or 0, limit),
    ).fetchall()
    start_index = db.execute(
        _TURNS + "SELECT COUNT(*) FROM turns WHERE first_seq<?", (thread_id, first_seq or 0),
    ).fetchone()[0]
    window = {
        "anchorSeq": first_seq, "startSeq": first_seq,
        "endSeq": max((row["last_seq"] for row in selected), default=None),
        "startIndex": start_index, "totalTurns": total,
        "hasEarlier": bool(earlier), "hasLater": len(rows) > limit,
        "previousAnchorSeq": earlier[-1][0] if earlier else None,
        "nextAnchorSeq": rows[limit]["first_seq"] if len(rows) > limit else None,
    }
    return selected, window, dict(summary)


def window_records(store: TraceStore, thread_id: str, turns: list[dict[str, Any]]) -> list[TraceRecord]:
    records: list[TraceRecord] = []
    for turn in turns:
        if turn["turn_id"] is None:
            rows = store.db.execute("SELECT * FROM trace_records WHERE seq=?", (turn["first_seq"],))
        else:
            rows = store.db.execute(
                "SELECT * FROM trace_records WHERE thread_id=? AND turn_id=? ORDER BY seq",
                (thread_id, turn["turn_id"]),
            )
        records.extend(TraceRecord(**dict(row)) for row in rows)
    records.sort(key=lambda record: record.seq)
    return records


def history_version(*values: Any) -> str:
    return hashlib.sha256(json.dumps((PROJECTION_VERSION, *values), sort_keys=True, separators=(",", ":")).encode()).hexdigest()
