"""Shared displayed item projection and exact textual contributors.

API values stay compatible; source discovery admits only explicit text fields.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .trace import TraceRecord
from .view import ItemView


def _item_bounds(item: ItemView) -> tuple[int, int]:
    if not item.events:
        return (0, 0)
    return min(event.seq for event in item.events), max(event.seq for event in item.events)


def _join_deltas(item: ItemView, method: str) -> str:
    return "".join(text for text, _ in _delta_segments(item, method))


def _delta_segments(item: ItemView, method: str) -> list[tuple[str, TraceRecord]]:
    chunks: list[tuple[str, TraceRecord]] = []
    for event in item.events:
        if event.method != method:
            continue
        params = event.message.get("params")
        if isinstance(params, Mapping) and isinstance(params.get("delta"), str):
            chunks.append((params["delta"], event))
    return chunks


def _text_segments(item: ItemView, key: str, method: str) -> list[tuple[str, TraceRecord | None]]:
    text = (item.final_item or {}).get(key)
    if isinstance(text, str) and text:
        return [(text, item.final_event)]
    return _delta_segments(item, method)


def _reasoning_parts(item: ItemView, *, summary: bool) -> list[str]:
    return [part.text for part in _reasoning_fields(item, summary=summary)]


def _reasoning_fields(item: ItemView, *, summary: bool) -> list[TextField]:
    raw = item.final_item or {}
    key = "summary" if summary else "content"
    final = raw.get(key)
    if isinstance(final, list) and final:
        return [TextField(f"reasoning.{key}/{index}", [(str(value), item.final_event)],
                          searchable=isinstance(value, str)) for index, value in enumerate(final)]

    prefix = "item/reasoning/summary" if summary else "item/reasoning/text"
    index_key = "summaryIndex" if summary else "contentIndex"
    parts: dict[int, list[tuple[str, TraceRecord | None]]] = {}
    for event in item.events:
        if not event.method or not event.method.startswith(prefix):
            continue
        params = event.message.get("params")
        if not isinstance(params, Mapping) or not isinstance(params.get(index_key), int):
            continue
        index = int(params[index_key])
        parts.setdefault(index, [])
        if isinstance(params.get("delta"), str):
            parts[index].append((params["delta"], event))
    return [TextField(f"reasoning.{key}/{index}", parts[index])
            for index in sorted(parts) if any(text for text, _ in parts[index])]


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
        projected["text"] = "".join(text for text, _ in _text_segments(item, "text", "item/agentMessage/delta"))
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
        projected["output"] = "".join(text for text, _ in _text_segments(item, "aggregatedOutput", "item/commandExecution/outputDelta"))
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


@dataclass
class TextField:
    field: str
    segments: list[tuple[str, TraceRecord | None]]
    searchable: bool = True

    @property
    def text(self) -> str:
        return "".join(text for text, _ in self.segments)


def item_text_fields(item: ItemView) -> list[TextField]:
    """Only typed displayed text, with the renderer's final/fallback precedence."""
    raw = item.final_item or {}
    kind = item.item_type or raw.get("type")
    event = item.final_event
    if kind == "agentMessage":
        return [TextField("agentMessage.text", _text_segments(item, "text", "item/agentMessage/delta"))]
    if kind == "reasoning":
        return [field for summary in (True, False) for field in _reasoning_fields(item, summary=summary)
                if field.searchable]
    if kind == "commandExecution":
        fields = [TextField("commandExecution.output", _text_segments(item, "aggregatedOutput", "item/commandExecution/outputDelta"))]
        if isinstance(raw.get("command"), str):
            fields.append(TextField("commandExecution.command", [(raw["command"], event)]))
        return fields
    if kind == "userMessage" and isinstance(raw.get("content"), list):
        return [TextField(f"userMessage.content/{index}/text", [(part["text"], event)])
                for index, part in enumerate(raw["content"])
                if isinstance(part, dict) and part.get("type") == "text" and isinstance(part.get("text"), str)]
    if kind == "fileChange" and isinstance(raw.get("changes"), list):
        return [TextField(f"fileChange.changes/{index}/path", [(part["path"], event)])
                for index, part in enumerate(raw["changes"])
                if isinstance(part, dict) and isinstance(part.get("path"), str)]
    return []
