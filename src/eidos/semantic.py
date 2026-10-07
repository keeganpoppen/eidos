from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Iterable, Mapping

from .codex import CodexPlace
from .trace import TraceRecord, TraceStore


@dataclass(frozen=True)
class CandidateWindow:
    thread_id: str
    start_seq: int
    end_seq: int
    record_count: int
    signals: tuple[str, ...] = ()


@dataclass(frozen=True)
class ObserverSpec:
    name: str
    angle: str
    lens: str = "thread"
    reliability: float = 1.0
    effort: str = "low"
    timeout: float = 120.0


OUTLINE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["confidence", "nodes"],
    "properties": {
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "note": {"type": "string"},
        "nodes": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["id", "title", "summary", "confidence", "support"],
                "properties": {
                    "id": {"type": "string"},
                    "parent": {"type": ["string", "null"]},
                    "ordinal": {"type": "integer"},
                    "title": {"type": "string"},
                    "summary": {"type": "string"},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "support": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["start", "end", "weight"],
                            "properties": {
                                "start": {"type": "integer"},
                                "end": {"type": "integer"},
                                "weight": {"type": "number", "minimum": 0, "maximum": 1},
                                "label": {"type": ["string", "null"]},
                            },
                        },
                    },
                },
            },
        },
    },
}


_BOUNDARY_METHODS = {
    "turn/completed",
    "thread/compacted",
    "$history/turn",
}


def plan_candidate_windows(
    store: TraceStore,
    thread_id: str,
    *,
    target_records: int = 220,
    overlap_records: int = 32,
    boundary_slop: int = 48,
    max_windows: int | None = None,
) -> list[CandidateWindow]:
    """Produce cheap structural windows without pretending to author episodes.

    Windows are merely attention hints for a semantic observer. They overlap,
    prefer nearby native turn/compaction boundaries, and carry the structural
    signals that caused a cut. The observer remains free to create nodes whose
    support is non-contiguous or crosses these window boundaries.
    """

    records = store.records(thread_id=thread_id)
    if not records:
        return []
    target_records = max(16, target_records)
    overlap_records = max(0, min(overlap_records, target_records // 2))
    windows: list[CandidateWindow] = []
    start = 0

    while start < len(records):
        if max_windows is not None and len(windows) >= max_windows:
            break
        nominal = min(len(records) - 1, start + target_records - 1)
        if nominal == len(records) - 1:
            end = nominal
        else:
            lo = max(start, nominal - boundary_slop)
            hi = min(len(records) - 1, nominal + boundary_slop)
            candidates = [
                i
                for i in range(lo, hi + 1)
                if records[i].method in _BOUNDARY_METHODS
            ]
            end = min(candidates, key=lambda i: abs(i - nominal)) if candidates else nominal

        selected = records[start : end + 1]
        signals = tuple(
            sorted(
                {
                    str(record.method)
                    for record in selected
                    if record.method in _BOUNDARY_METHODS
                }
            )
        )
        windows.append(
            CandidateWindow(
                thread_id=thread_id,
                start_seq=selected[0].seq,
                end_seq=selected[-1].seq,
                record_count=len(selected),
                signals=signals,
            )
        )
        if end >= len(records) - 1:
            break
        next_start = max(start + 1, end + 1 - overlap_records)
        start = next_start
    return windows


def _compact_item(item: Mapping[str, Any]) -> str:
    kind = str(item.get("type") or "item")
    if kind == "userMessage":
        content = item.get("content") or []
        text = " ".join(
            str(x.get("text"))
            for x in content
            if isinstance(x, Mapping) and x.get("type") == "text" and x.get("text")
        )
        return f"user: {text[:4000]}"
    if kind == "agentMessage":
        return "agent: " + str(item.get("text") or "")[:4000]
    if kind == "commandExecution":
        command = str(item.get("command") or "")
        output = str(item.get("aggregatedOutput") or "")
        return f"command: {command[:1200]}\noutput: {output[-1800:]}"
    if kind == "fileChange":
        paths = [
            str(change.get("path"))
            for change in item.get("changes") or []
            if isinstance(change, Mapping) and change.get("path")
        ]
        return "file changes: " + ", ".join(paths[:40])
    if kind == "reasoning":
        summary = item.get("summary") or []
        content = item.get("content") or []
        text = "\n".join(str(x) for x in (summary or content))
        return "reasoning: " + text[:2400]
    if kind in {"mcpToolCall", "dynamicToolCall", "collabAgentToolCall"}:
        return kind + ": " + json.dumps(item, ensure_ascii=False, separators=(",", ":"))[:2200]
    return kind + ": " + json.dumps(item, ensure_ascii=False, separators=(",", ":"))[:1800]


def format_trace_window(store: TraceStore, window: CandidateWindow) -> str:
    records = [
        record
        for record in store.records(thread_id=window.thread_id)
        if window.start_seq <= record.seq <= window.end_seq
    ]
    lines: list[str] = []
    for record in records:
        message = record.message
        params = message.get("params") if isinstance(message, Mapping) else None
        detail = ""
        if record.method in {"item/completed", "$history/item"} and isinstance(params, Mapping):
            item = params.get("item")
            if isinstance(item, Mapping):
                detail = _compact_item(item)
        elif record.method == "turn/start" and isinstance(params, Mapping):
            inputs = params.get("input") or []
            texts = [
                str(x.get("text"))
                for x in inputs
                if isinstance(x, Mapping) and x.get("type") == "text" and x.get("text")
            ]
            detail = "user input: " + "\n".join(texts)[:4000]
        elif record.method and record.method.startswith("item/reasoning/") and isinstance(params, Mapping):
            delta = params.get("delta")
            if isinstance(delta, str) and delta:
                detail = "reasoning delta: " + delta[:1000]
        elif record.method == "thread/compacted":
            detail = "context compaction boundary"
        method = record.method or (f"response:{record.response_to}" if record.response_to else "record")
        prefix = f"[{record.seq}] {method}"
        if record.item_type:
            prefix += f" <{record.item_type}>"
        lines.append(prefix + (f"\n{detail}" if detail else ""))
    return "\n\n".join(lines)


def _latest_completed_turn(store: TraceStore, thread_id: str, horizon_seq: int) -> str | None:
    latest: str | None = None
    for record in store.records(thread_id=thread_id):
        if record.seq > horizon_seq:
            break
        if record.method in {"turn/completed", "$history/turn"} and record.turn_id:
            latest = record.turn_id
    return latest


def _previous_outline(
    store: TraceStore,
    thread_id: str,
    spec: ObserverSpec,
) -> dict[str, Any] | None:
    for revision in store.semantic_revisions(thread_id, lens=spec.lens):
        if revision["observer"] == spec.name:
            return store.semantic_outline(
                thread_id,
                lens=spec.lens,
                revision_id=revision["revision_id"],
            )
    return None


def _observer_prompt(
    store: TraceStore,
    window: CandidateWindow,
    spec: ObserverSpec,
    previous: dict[str, Any] | None,
) -> str:
    previous_nodes = previous["nodes"] if previous is not None else []
    return f"""You are an Eidos shadow semantic observer.

Your job is semantic chunking and navigational interpretation, not transcript
compression. Produce a COMPLETE semantic map of the source thread through trace
sequence {window.end_seq}. You may revise, split, merge, rename, nest, or retain
older nodes in light of later evidence.

Angle for this observer:
{spec.angle}

Rules:
- Use natural titles. Do NOT force nodes into categories such as finding,
  decision, artifact, or task.
- A node may cite multiple disjoint support ranges. This is important: ideas and
  episodes may disappear and recur later.
- Support ranges are inclusive Eidos trace sequence numbers and must not exceed
  the current horizon ({window.end_seq}).
- Prefer semantically meaningful episodes/threads of development over native
  Codex turn boundaries.
- Tool-call bursts are evidence. Describe what they were *for* and what became
  important, rather than narrating every command.
- Preserve genuinely useful older nodes even when the current window is about
  something else.
- Use confidence to express uncertainty. Do not manufacture support.
- Do not call tools. The inherited thread context and the supplied Eidos trace
  window are the complete evidence for this observer turn.

Previous map by this observer:
{json.dumps(previous_nodes, ensure_ascii=False, separators=(",", ":"))}

Current candidate window (plumbing only; its edges are NOT presumed episode
boundaries):
{format_trace_window(store, window)}

Return only the structured value required by the output schema.
"""


class CodexShadowObserver:
    """Uses an ephemeral Codex fork as one semantic observer over Eidos evidence."""

    def __init__(self, place: CodexPlace, store: TraceStore) -> None:
        self.place = place
        self.store = store

    def observe_window(
        self,
        *,
        source_thread_id: str,
        window: CandidateWindow,
        spec: ObserverSpec,
    ) -> str:
        if source_thread_id != window.thread_id:
            raise ValueError("window belongs to a different source thread")
        self.store.register_semantic_observer(
            name=spec.name,
            lens=spec.lens,
            reliability=spec.reliability,
            prompt=spec.angle,
        )
        previous = _previous_outline(self.store, source_thread_id, spec)
        last_turn_id = _latest_completed_turn(self.store, source_thread_id, window.end_seq)
        fork_args: dict[str, Any] = {
            "ephemeral": True,
            "threadSource": "eidos-semantic-observer",
        }
        if last_turn_id is not None:
            fork_args["lastTurnId"] = last_turn_id
        fork_thread = self.place.fork_thread(source_thread_id, **fork_args)
        self.store.annotate_thread(
            fork_thread,
            kind="semantic-observer",
            parent_thread_id=source_thread_id,
            metadata={
                "observer": spec.name,
                "lens": spec.lens,
                "horizon_seq": window.end_seq,
            },
        )
        prompt = _observer_prompt(self.store, window, spec, previous)
        started = self.place.client.turn_start_text(
            fork_thread,
            prompt,
            effort=spec.effort,
            outputSchema=OUTLINE_SCHEMA,
            turnTrigger="eidos-semantic-observer",
        )
        turn = started.get("turn")
        if not isinstance(turn, Mapping) or not isinstance(turn.get("id"), str):
            raise ValueError(f"observer turn/start returned no turn id: {started!r}")
        turn_id = str(turn["id"])
        self.place.client.wait_for(
            "turn/completed",
            thread_id=fork_thread,
            timeout=spec.timeout,
        )
        page = self.place.client.thread_items_list(
            fork_thread,
            turn_id=turn_id,
            limit=200,
            sort_direction="asc",
        )
        messages = []
        for entry in page.get("data") or []:
            if not isinstance(entry, Mapping):
                continue
            item = entry.get("item")
            if isinstance(item, Mapping) and item.get("type") == "agentMessage":
                messages.append(item)
        if not messages:
            raise ValueError("shadow observer produced no agentMessage")
        final = next(
            (item for item in reversed(messages) if item.get("phase") == "final"),
            messages[-1],
        )
        raw_text = final.get("text")
        if not isinstance(raw_text, str):
            raise ValueError("shadow observer final message has no text")
        proposal = json.loads(raw_text)
        if not isinstance(proposal, Mapping):
            raise ValueError("shadow observer output is not an object")
        nodes = proposal.get("nodes")
        if not isinstance(nodes, list):
            raise ValueError("shadow observer output has no nodes")

        normalized: list[dict[str, Any]] = []
        for ordinal, raw_node in enumerate(nodes):
            if not isinstance(raw_node, Mapping):
                continue
            support: list[dict[str, Any]] = []
            for raw_span in raw_node.get("support") or []:
                if not isinstance(raw_span, Mapping):
                    continue
                start = int(raw_span["start"])
                end = int(raw_span["end"])
                if start < 1 or end < start or end > window.end_seq:
                    raise ValueError(
                        f"observer emitted invalid support range {start}..{end} "
                        f"for horizon {window.end_seq}"
                    )
                support.append(
                    {
                        "start": start,
                        "end": end,
                        "weight": float(raw_span.get("weight", 1.0)),
                        "label": raw_span.get("label"),
                    }
                )
            normalized.append(
                {
                    "id": str(raw_node.get("id") or f"node-{ordinal}"),
                    "parent": raw_node.get("parent"),
                    "ordinal": int(raw_node.get("ordinal", ordinal)),
                    "title": str(raw_node.get("title") or "Untitled"),
                    "summary": str(raw_node.get("summary") or ""),
                    "confidence": float(raw_node.get("confidence", 1.0)),
                    "support": support,
                }
            )

        parent_revision = previous["revision_id"] if previous is not None else None
        return self.store.put_semantic_revision(
            thread_id=source_thread_id,
            lens=spec.lens,
            observer=spec.name,
            horizon_seq=window.end_seq,
            nodes=normalized,
            confidence=float(proposal.get("confidence", 1.0)),
            parent_revision=parent_revision,
            note=str(proposal.get("note") or ""),
        )

    def observe_windows(
        self,
        *,
        source_thread_id: str,
        windows: Iterable[CandidateWindow],
        spec: ObserverSpec,
    ) -> list[str]:
        revisions = []
        for window in windows:
            revisions.append(
                self.observe_window(
                    source_thread_id=source_thread_id,
                    window=window,
                    spec=spec,
                )
            )
        return revisions
