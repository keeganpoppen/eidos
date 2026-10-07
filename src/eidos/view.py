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


def _bounds(events: list[TraceRecord]) -> tuple[int, int]:
    if not events:
        return (0, 0)
    return min(e.seq for e in events), max(e.seq for e in events)


def _delta_parts(item: ItemView, *, summary: bool) -> list[str]:
    parts: dict[int, str] = {}
    prefix = "item/reasoning/summary" if summary else "item/reasoning/text"
    for event in item.events:
        if not event.method or not event.method.startswith(prefix):
            continue
        params = event.message.get("params")
        if not isinstance(params, dict):
            continue
        index_key = "summaryIndex" if summary else "contentIndex"
        index = params.get(index_key)
        if not isinstance(index, int):
            continue
        parts.setdefault(index, "")
        delta = params.get("delta")
        if isinstance(delta, str):
            parts[index] += delta
    return [parts[i] for i in sorted(parts) if parts[i]]


def _reasoning_sections(item: ItemView) -> tuple[list[str], list[str]]:
    raw = item.final_item or {}
    final_summary = raw.get("summary")
    final_content = raw.get("content")
    summary = [str(x) for x in final_summary] if isinstance(final_summary, list) and final_summary else _delta_parts(item, summary=True)
    content = [str(x) for x in final_content] if isinstance(final_content, list) and final_content else _delta_parts(item, summary=False)
    return summary, content


def _render_item(item: ItemView) -> str:
    raw = item.final_item or {}
    kind = item.item_type or str(raw.get("type") or "item")
    title = kind
    body = ""
    if kind == "agentMessage":
        body = escape(str(raw.get("text", ""))).replace("\n", "<br>")
    elif kind == "reasoning":
        summary, content = _reasoning_sections(item)
        if summary:
            body += '<div class="reasoning-summary">' + "<br><br>".join(
                escape(x).replace("\n", "<br>") for x in summary
            ) + "</div>"
        if content:
            body += '<details class="reasoning-content"><summary>reasoning content</summary>' + "".join(
                f"<p>{escape(x).replace(chr(10), '<br>')}</p>" for x in content
            ) + "</details>"
        if not summary and not content:
            body = '<span class="muted">reasoning activity recorded; no text persisted</span>'
    elif kind == "commandExecution":
        command = escape(str(raw.get("command", "")))
        output = escape(str(raw.get("aggregatedOutput") or ""))
        body = f"<pre>$ {command}\n{output}</pre>"
    elif kind == "fileChange":
        changes = raw.get("changes") or []
        body = "<ul>" + "".join(
            f"<li>{escape(str(c.get('path', c)))}</li>" for c in changes if isinstance(c, dict)
        ) + "</ul>"
    elif kind in {"mcpToolCall", "dynamicToolCall", "collabAgentToolCall"}:
        tool = raw.get("tool") or raw.get("server") or kind
        body = (
            f"<strong>{escape(str(tool))}</strong>"
            f"<pre>{escape(json.dumps(raw, ensure_ascii=False, indent=2))}</pre>"
        )
    elif kind == "userMessage":
        content = raw.get("content") or []
        body = "<br>".join(escape(_input_text(x)) for x in content if isinstance(x, dict))
    else:
        body = f"<pre>{escape(json.dumps(raw, ensure_ascii=False, indent=2))}</pre>"
    lo, hi = _bounds(item.events)
    return (
        f'<article class="item trace-region {escape(kind)}" data-start="{lo}" data-end="{hi}">'
        f'<header>{escape(title)} <code>{escape(item.item_id)}</code></header>{body}</article>'
    )


def _outline_html(store: TraceStore, thread_id: str) -> str:
    outline = store.semantic_outline(thread_id)
    alternatives = store.semantic_revisions(thread_id, lens="thread")
    if outline is None:
        return (
            '<aside class="outline"><div class="outline-head">semantic map</div>'
            '<div class="outline-empty">No semantic interpretation yet.<br><br>'
            'The native trace remains the source; this rail will hold versioned, '
            'overlapping episode lenses over it.</div></aside>'
        )

    by_id = {node["node_id"]: node for node in outline["nodes"]}

    def depth(node: dict[str, Any]) -> int:
        d = 0
        seen: set[str] = set()
        parent = node.get("parent_node_id")
        while parent and parent in by_id and parent not in seen and d < 8:
            seen.add(parent)
            d += 1
            parent = by_id[parent].get("parent_node_id")
        return d

    nodes = []
    for node in outline["nodes"]:
        spans = [[int(s["start"]), int(s["end"])] for s in node["support"]]
        encoded = escape(json.dumps(spans, separators=(",", ":")), quote=True)
        summary = escape(str(node.get("summary") or ""))
        support_label = (
            f'{len(spans)} region{"s" if len(spans) != 1 else ""}'
            if spans
            else "interpretive node"
        )
        nodes.append(
            f'<button class="outline-node" style="--depth:{depth(node)}" data-spans="{encoded}">'
            f'<span class="outline-title">{escape(str(node["title"]))}</span>'
            f'<span class="outline-summary">{summary}</span>'
            f'<span class="outline-meta">{support_label} · {float(node["confidence"]):.2f}</span>'
            "</button>"
        )

    alt_count = max(0, len(alternatives) - 1)
    header = (
        f'<div class="outline-head">semantic map '
        f'<button id="clear-focus" title="show all">all</button></div>'
        f'<div class="outline-provenance">{escape(str(outline["observer"]))} · '
        f'horizon {outline["horizon_seq"]} · score {float(outline["score"]):.2f}'
        + (f" · {alt_count} alternate" + ("s" if alt_count != 1 else "") if alt_count else "")
        + "</div>"
    )
    return f'<aside class="outline">{header}{"".join(nodes)}</aside>'


def render_thread_html(store: TraceStore, thread_id: str) -> str:
    view = project_thread(store, thread_id)
    nav = "".join(
        f'<a class="thread {"active" if t["thread_id"] == thread_id else ""}" '
        f'href="/thread/{escape(t["thread_id"])}">{escape(t["thread_id"])}'
        f'<small>{t["turn_count"]} turns · {t["record_count"]} records</small></a>'
        for t in store.threads()
    )
    turns: list[str] = []
    for turn in view.turns:
        inputs = "".join(f'<div class="user">{escape(_input_text(x))}</div>' for x in turn.inputs)
        items = "".join(_render_item(item) for item in turn.items.values())
        raw = "\n".join(
            f"{r.seq:06d} {r.direction:>19} {r.method or ('↩ '+str(r.response_to))}"
            for r in turn.events
        )
        lo, hi = _bounds(turn.events)
        turns.append(
            f'<section class="turn trace-region" data-start="{lo}" data-end="{hi}">'
            f'<h2>turn <code>{escape(turn.turn_id)}</code></h2>{inputs}{items}'
            f'<details><summary>native event spine · {len(turn.events)}</summary>'
            f'<pre>{escape(raw)}</pre></details></section>'
        )
    body = "".join(turns) or '<div class="empty">No turn-scoped events yet.</div>'
    outline = _outline_html(store, thread_id)
    return f'''<!doctype html>
<html><head><meta charset="utf-8"><title>Eidos · {escape(thread_id)}</title>
<style>
:root {{ color-scheme: dark; font-family: ui-monospace,SFMono-Regular,Menlo,monospace; background:#0d0d0d; color:#e8e8e8 }}
* {{ box-sizing:border-box }} body {{ margin:0 }}
.shell {{ display:grid; grid-template-columns:240px 300px minmax(0,1fr); min-height:100vh }}
nav {{ border-right:1px solid #333; padding:12px; position:sticky; top:0; height:100vh; overflow:auto }}
.brand {{ font-size:20px; font-weight:800; margin:4px 4px 16px }}
.thread {{ display:block; color:#aaa; text-decoration:none; padding:9px; border:1px solid transparent; overflow:hidden; text-overflow:ellipsis }}
.thread:hover,.thread.active {{ color:#fff; border-color:#555; background:#171717 }}
.thread small {{ display:block; color:#666; margin-top:3px }}
.outline {{ border-right:1px solid #333; padding:12px; position:sticky; top:0; height:100vh; overflow:auto; background:#0a0a0a }}
.outline-head {{ font-weight:800; font-size:12px; text-transform:uppercase; letter-spacing:.08em; margin:4px 4px 6px }}
.outline-head button {{ float:right; background:#151515; color:#888; border:1px solid #333; cursor:pointer }}
.outline-provenance,.outline-empty {{ color:#666; font-size:10px; line-height:1.5; margin:0 4px 14px }}
.outline-node {{ width:100%; display:block; text-align:left; border:0; border-left:1px solid #333; background:transparent; color:#ddd; cursor:pointer; padding:8px 8px 8px calc(8px + var(--depth) * 14px); margin:1px 0 }}
.outline-node:hover,.outline-node.active {{ background:#171717; border-left-color:#ddd }}
.outline-title {{ display:block; font-weight:700; font-size:12px; line-height:1.3 }}
.outline-summary {{ display:block; color:#888; font-family:system-ui,sans-serif; font-size:11px; line-height:1.35; margin-top:3px }}
.outline-meta {{ display:block; color:#555; font-size:9px; margin-top:5px }}
main {{ max-width:1100px; padding:24px 32px 80px }}
h1 {{ margin:0 0 28px; font-size:18px }} .turn {{ margin:0 0 42px; transition:opacity .15s,border-color .15s }}
.turn h2 {{ font-size:12px; color:#777; font-weight:400 }}
.user {{ border-left:4px solid #aaa; padding:12px 16px; margin:12px 0 18px; white-space:pre-wrap; font-family:system-ui,sans-serif; font-size:16px }}
.item {{ border:1px solid #333; margin:8px 0; padding:12px 14px; background:#111; transition:opacity .15s,border-color .15s }}
.item header {{ color:#888; font-size:11px; margin-bottom:10px; text-transform:uppercase }}
.item.agentMessage {{ border-color:#555; font-family:system-ui,sans-serif; line-height:1.5 }}
.item.commandExecution,.item.mcpToolCall,.item.dynamicToolCall {{ background:#090909 }}
.reasoning-summary {{ color:#aaa; font-family:system-ui,sans-serif; font-size:13px; line-height:1.45 }}
.reasoning-content {{ margin-top:10px; color:#777 }} .muted {{ color:#555; font-style:italic }}
pre {{ white-space:pre-wrap; overflow-wrap:anywhere; color:#bbb; font-size:12px }}
details {{ margin-top:9px; color:#666 }} summary {{ cursor:pointer; font-size:11px }} code {{ color:#bbb }}
.focus-dim {{ opacity:.13 }} .focus-hit {{ opacity:1!important; border-color:#666!important }}
</style></head><body><div class="shell"><nav><div class="brand">eidos / traces</div>{nav}</nav>{outline}<main>
<h1>{escape(thread_id)}</h1>{body}</main></div>
<script>
const regions=[...document.querySelectorAll('.trace-region')];
function clearFocus(){{
  regions.forEach(el=>el.classList.remove('focus-dim','focus-hit'));
  document.querySelectorAll('.outline-node').forEach(el=>el.classList.remove('active'));
}}
function overlaps(a,b,c,d){{ return a<=d && c<=b; }}
document.querySelectorAll('.outline-node').forEach(node=>node.addEventListener('click',()=>{{
  clearFocus();
  node.classList.add('active');
  const spans=JSON.parse(node.dataset.spans || '[]');
  if(!spans.length) return;
  let first=null;
  regions.forEach(el=>{{
    const a=Number(el.dataset.start), b=Number(el.dataset.end);
    const hit=spans.some(([c,d])=>overlaps(a,b,c,d));
    el.classList.add(hit?'focus-hit':'focus-dim');
    if(hit && !first) first=el;
  }});
  if(first) first.scrollIntoView({{behavior:'smooth',block:'center'}});
}}));
const clear=document.getElementById('clear-focus');
if(clear) clear.addEventListener('click', clearFocus);
</script></body></html>'''


def render_index_html(store: TraceStore) -> str:
    links = "".join(
        f'<li><a href="/thread/{escape(t["thread_id"])}">{escape(t["thread_id"])}</a> '
        f'<small>{t["turn_count"]} turns · {t["record_count"]} records</small></li>'
        for t in store.threads()
    ) or "<li>No persisted threads yet.</li>"
    return (
        "<!doctype html><meta charset='utf-8'><title>Eidos traces</title>"
        "<style>body{background:#0d0d0d;color:#eee;font:14px ui-monospace,monospace;padding:30px}"
        "a{color:#fff}li{margin:12px}</style><h1>eidos / traces</h1><ul>"
        + links
        + "</ul>"
    )
