from __future__ import annotations

from dataclasses import dataclass, field
from html import escape
import json
from typing import Any

from .trace import TraceRecord, TraceStore


@dataclass
class ItemView:
    item_id: str
    item_type: str | None = None
    final_item: dict[str, Any] | None = None
    events: list[TraceRecord] = field(default_factory=list)


@dataclass
class TurnView:
    turn_id: str
    inputs: list[dict[str, Any]] = field(default_factory=list)
    items: dict[str, ItemView] = field(default_factory=dict)
    events: list[TraceRecord] = field(default_factory=list)


@dataclass
class ThreadView:
    thread_id: str
    turns: list[TurnView]
    unscoped: list[TraceRecord]


def project_thread(store: TraceStore, thread_id: str) -> ThreadView:
    records = store.records(thread_id=thread_id)
    turns: dict[str, TurnView] = {}
    turn_order: list[str] = []
    unscoped: list[TraceRecord] = []

    def ensure_turn(turn_id: str) -> TurnView:
        if turn_id not in turns:
            turns[turn_id] = TurnView(turn_id=turn_id)
            turn_order.append(turn_id)
        return turns[turn_id]

    for record in records:
        message = record.message
        params = message.get("params") if isinstance(message, dict) else None
        if record.method == "turn/start" and isinstance(params, dict):
            tid = record.turn_id or f"pending@{record.seq}"
            turn = ensure_turn(tid)
            inputs = params.get("input")
            if isinstance(inputs, list):
                turn.inputs.extend(x for x in inputs if isinstance(x, dict))
        if record.turn_id is None:
            unscoped.append(record)
            continue
        turn = ensure_turn(record.turn_id)
        turn.events.append(record)
        if record.item_id is not None:
            item = turn.items.setdefault(record.item_id, ItemView(record.item_id, record.item_type))
            item.events.append(record)
            item.item_type = record.item_type or item.item_type
            if record.method in {"item/completed", "item/started", "$history/item"} and isinstance(params, dict):
                raw_item = params.get("item")
                if isinstance(raw_item, dict):
                    if record.method in {"item/completed", "$history/item"} or item.final_item is None:
                        item.final_item = raw_item
    return ThreadView(thread_id=thread_id, turns=[turns[t] for t in turn_order], unscoped=unscoped)


def _input_text(value: dict[str, Any]) -> str:
    kind = value.get("type")
    if kind == "text":
        return str(value.get("text", ""))
    if kind == "skill":
        return f"$skill {value.get('name', '')} ({value.get('path', '')})"
    if kind == "mention":
        return f"@{value.get('name', '')} ({value.get('path', '')})"
    if kind == "localImage":
        return f"[image] {value.get('path', '')}"
    return json.dumps(value, ensure_ascii=False, indent=2)


def _render_item(item: ItemView) -> str:
    raw = item.final_item or {}
    kind = item.item_type or str(raw.get("type") or "item")
    title = kind
    body = ""
    if kind == "agentMessage":
        body = escape(str(raw.get("text", ""))).replace("\n", "<br>")
    elif kind == "reasoning":
        summary = raw.get("summary") or []
        body = "<br>".join(escape(str(x)) for x in summary)
    elif kind == "commandExecution":
        command = escape(str(raw.get("command", "")))
        output = escape(str(raw.get("aggregatedOutput") or ""))
        body = f"<pre>$ {command}\n{output}</pre>"
    elif kind == "fileChange":
        changes = raw.get("changes") or []
        body = "<ul>" + "".join(f"<li>{escape(str(c.get('path', c)))}</li>" for c in changes if isinstance(c, dict)) + "</ul>"
    elif kind in {"mcpToolCall", "dynamicToolCall", "collabAgentToolCall"}:
        tool = raw.get("tool") or raw.get("server") or kind
        body = f"<strong>{escape(str(tool))}</strong><pre>{escape(json.dumps(raw, ensure_ascii=False, indent=2))}</pre>"
    elif kind == "userMessage":
        content = raw.get("content") or []
        body = "<br>".join(escape(_input_text(x)) for x in content if isinstance(x, dict))
    else:
        body = f"<pre>{escape(json.dumps(raw, ensure_ascii=False, indent=2))}</pre>"
    return f'<article class="item {escape(kind)}"><header>{escape(title)} <code>{escape(item.item_id)}</code></header>{body}</article>'


def render_thread_html(store: TraceStore, thread_id: str) -> str:
    view = project_thread(store, thread_id)
    nav = "".join(
        f'<a class="thread {"active" if t["thread_id"] == thread_id else ""}" href="/thread/{escape(t["thread_id"])}">'
        f'{escape(t["thread_id"])}<small>{t["turn_count"]} turns · {t["record_count"]} records</small></a>'
        for t in store.threads()
    )
    turns: list[str] = []
    for turn in view.turns:
        inputs = "".join(f'<div class="user">{escape(_input_text(x))}</div>' for x in turn.inputs)
        items = "".join(_render_item(item) for item in turn.items.values())
        raw = "\n".join(f"{r.seq:06d} {r.direction:>19} {r.method or ('↩ '+str(r.response_to))}" for r in turn.events)
        turns.append(
            f'<section class="turn"><h2>turn <code>{escape(turn.turn_id)}</code></h2>{inputs}{items}'
            f'<details><summary>native event spine · {len(turn.events)}</summary><pre>{escape(raw)}</pre></details></section>'
        )
    body = "".join(turns) or '<div class="empty">No turn-scoped events yet.</div>'
    return f'''<!doctype html>
<html><head><meta charset="utf-8"><title>Eidos · {escape(thread_id)}</title>
<style>
:root {{ color-scheme: dark; font-family: ui-monospace,SFMono-Regular,Menlo,monospace; background:#0d0d0d; color:#e8e8e8 }}
* {{ box-sizing:border-box }} body {{ margin:0 }}
.shell {{ display:grid; grid-template-columns:280px minmax(0,1fr); min-height:100vh }}
nav {{ border-right:1px solid #333; padding:12px; position:sticky; top:0; height:100vh; overflow:auto }}
.brand {{ font-size:20px; font-weight:800; margin:4px 4px 16px }}
.thread {{ display:block; color:#aaa; text-decoration:none; padding:9px; border:1px solid transparent; overflow:hidden; text-overflow:ellipsis }}
.thread:hover,.thread.active {{ color:#fff; border-color:#555; background:#171717 }}
.thread small {{ display:block; color:#666; margin-top:3px }}
main {{ max-width:1100px; padding:24px 32px 80px }}
h1 {{ margin:0 0 28px; font-size:18px }} .turn {{ margin:0 0 42px }} .turn h2 {{ font-size:12px; color:#777; font-weight:400 }}
.user {{ border-left:4px solid #aaa; padding:12px 16px; margin:12px 0 18px; white-space:pre-wrap; font-family:system-ui,sans-serif; font-size:16px }}
.item {{ border:1px solid #333; margin:8px 0; padding:12px 14px; background:#111 }}
.item header {{ color:#888; font-size:11px; margin-bottom:10px; text-transform:uppercase }}
.item.agentMessage {{ border-color:#555; font-family:system-ui,sans-serif; line-height:1.5 }}
.item.commandExecution,.item.mcpToolCall,.item.dynamicToolCall {{ background:#090909 }}
pre {{ white-space:pre-wrap; overflow-wrap:anywhere; color:#bbb; font-size:12px }}
details {{ margin-top:9px; color:#666 }} summary {{ cursor:pointer; font-size:11px }} code {{ color:#bbb }}
</style></head><body><div class="shell"><nav><div class="brand">eidos / traces</div>{nav}</nav><main>
<h1>{escape(thread_id)}</h1>{body}</main></div></body></html>'''


def render_index_html(store: TraceStore) -> str:
    links = "".join(
        f'<li><a href="/thread/{escape(t["thread_id"])}">{escape(t["thread_id"])}</a> '
        f'<small>{t["turn_count"]} turns · {t["record_count"]} records</small></li>'
        for t in store.threads()
    ) or "<li>No persisted threads yet.</li>"
    return f"<!doctype html><meta charset='utf-8'><title>Eidos traces</title><style>body{{background:#0d0d0d;color:#eee;font:14px ui-monospace,monospace;padding:30px}}a{{color:#fff}}li{{margin:12px}}</style><h1>eidos / traces</h1><ul>{links}</ul>"
