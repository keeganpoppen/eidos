from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
import json
import os
import threading
from typing import Any, Callable, Iterable, Mapping, Sequence

from .codex import AppServerClient, CodexPlace
from .semantic import (
    CandidateWindow,
    LEAF_REASONING_EFFORT,
    SYNTHESIS_REASONING_EFFORT,
    build_story_beats,
    choose_leaf_model,
    format_story_window,
)
from .trace import TraceStore


ProgressCallback = Callable[[str, int, int, str], None]


GLOBAL_RETRO_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "confidence",
        "narrative",
        "durableArcs",
        "deadEnds",
        "surprises",
        "attentionGuidance",
    ],
    "properties": {
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "narrative": {"type": "string"},
        "durableArcs": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["id", "title", "summary", "importance"],
                "properties": {
                    "id": {"type": "string"},
                    "title": {"type": "string"},
                    "summary": {"type": "string"},
                    "importance": {"type": "number", "minimum": 0, "maximum": 1},
                },
            },
        },
        "deadEnds": {"type": "array", "items": {"type": "string"}},
        "surprises": {"type": "array", "items": {"type": "string"}},
        "attentionGuidance": {"type": "array", "items": {"type": "string"}},
    },
}


LEAF_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["signal", "assessment", "episodes"],
    "properties": {
        "signal": {"type": "number", "minimum": 0, "maximum": 1},
        "assessment": {"type": "string"},
        "episodes": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "id",
                    "title",
                    "summary",
                    "importance",
                    "confidence",
                    "support",
                    "arcHints",
                ],
                "properties": {
                    "id": {"type": "string"},
                    "title": {"type": "string"},
                    "summary": {"type": "string"},
                    "importance": {"type": "number", "minimum": 0, "maximum": 1},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "support": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["start", "end", "weight", "label"],
                            "properties": {
                                "start": {"type": "integer"},
                                "end": {"type": "integer"},
                                "weight": {"type": "number", "minimum": 0, "maximum": 1},
                                "label": {"type": ["string", "null"]},
                            },
                        },
                    },
                    "arcHints": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
    },
}


ROLLUP_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["narrative", "parents", "discarded"],
    "properties": {
        "narrative": {"type": "string"},
        "parents": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "id",
                    "title",
                    "summary",
                    "importance",
                    "confidence",
                    "children",
                ],
                "properties": {
                    "id": {"type": "string"},
                    "title": {"type": "string"},
                    "summary": {"type": "string"},
                    "importance": {"type": "number", "minimum": 0, "maximum": 1},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "children": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
        "discarded": {"type": "array", "items": {"type": "string"}},
    },
}


@dataclass(frozen=True)
class SemanticWindow:
    index: int
    start_seq: int
    end_seq: int
    beat_count: int
    semantic_mass: float


@dataclass
class TreeNode:
    node_id: str
    title: str
    summary: str
    importance: float
    confidence: float
    support: list[dict[str, Any]]
    children: list[str] = field(default_factory=list)
    level: int = 0

    @property
    def first_seq(self) -> int:
        if not self.support:
            return 0
        return min(int(span["start"]) for span in self.support)


@dataclass(frozen=True)
class TreeBuildResult:
    revision_id: str
    global_retro: dict[str, Any]
    leaf_windows: int
    leaf_episodes: int
    levels: int
    model: str | None
    leaf_effort: str
    synthesis_effort: str


def _full_window(store: TraceStore, thread_id: str) -> CandidateWindow:
    records = store.records(thread_id=thread_id)
    if not records:
        raise ValueError("thread has no persisted Eidos evidence")
    return CandidateWindow(
        thread_id=thread_id,
        start_seq=records[0].seq,
        end_seq=records[-1].seq,
        record_count=len(records),
    )


def plan_semantic_windows(
    store: TraceStore,
    thread_id: str,
    *,
    target_mass: float = 8.0,
    overlap_beats: int = 2,
    max_beats: int = 18,
) -> list[SemanticWindow]:
    """Partition history by semantic mass rather than raw event count.

    Every raw record is consumed by build_story_beats, but model attention is
    allocated over the resulting weighted beats. Long routine execution bursts
    therefore do not automatically receive more leaf workers merely because
    they emitted more protocol traffic.
    """

    whole = _full_window(store, thread_id)
    beats = build_story_beats(store, whole)
    if not beats:
        return [
            SemanticWindow(
                index=0,
                start_seq=whole.start_seq,
                end_seq=whole.end_seq,
                beat_count=0,
                semantic_mass=0.0,
            )
        ]

    target_mass = max(2.0, float(target_mass))
    overlap_beats = max(0, int(overlap_beats))
    max_beats = max(4, int(max_beats))

    windows: list[SemanticWindow] = []
    start = 0
    while start < len(beats):
        mass = 0.0
        end = start
        while end < len(beats):
            beat = beats[end]
            beat_mass = max(0.12, float(beat.importance))
            would_exceed = mass + beat_mass > target_mass
            too_many = end - start >= max_beats
            if end > start and (would_exceed or too_many):
                break
            mass += beat_mass
            end += 1

        selected = beats[start:end]
        if not selected:
            selected = [beats[start]]
            end = start + 1
            mass = max(0.12, float(selected[0].importance))

        windows.append(
            SemanticWindow(
                index=len(windows),
                start_seq=selected[0].start_seq,
                end_seq=selected[-1].end_seq,
                beat_count=len(selected),
                semantic_mass=mass,
            )
        )

        if end >= len(beats):
            break
        start = max(start + 1, end - overlap_beats)

    return windows


def pack_nodes_by_mass(
    nodes: Sequence[TreeNode],
    *,
    target_mass: float = 4.5,
    max_items: int = 10,
) -> list[list[TreeNode]]:
    """Pack low-value nodes densely and give important nodes more reducer space."""

    ordered = sorted(nodes, key=lambda node: (node.first_seq, node.node_id))
    groups: list[list[TreeNode]] = []
    current: list[TreeNode] = []
    mass = 0.0
    for node in ordered:
        weight = max(0.15, float(node.importance))
        if current and (
            (mass + weight > target_mass and len(current) >= 2)
            or len(current) >= max_items
        ):
            groups.append(current)
            current = []
            mass = 0.0
        current.append(node)
        mass += weight
    if current:
        groups.append(current)
    return groups


def _merge_support(nodes: Iterable[TreeNode]) -> list[dict[str, Any]]:
    spans: list[tuple[int, int, float]] = []
    for node in nodes:
        for span in node.support:
            spans.append(
                (
                    int(span["start"]),
                    int(span.get("end", span["start"])),
                    float(span.get("weight", 1.0)),
                )
            )
    if not spans:
        return []
    spans.sort()
    merged: list[dict[str, Any]] = []
    start, end, weight = spans[0]
    for next_start, next_end, next_weight in spans[1:]:
        if next_start <= end + 1:
            end = max(end, next_end)
            weight = max(weight, next_weight)
        else:
            merged.append({"start": start, "end": end, "weight": weight, "label": None})
            start, end, weight = next_start, next_end, next_weight
    merged.append({"start": start, "end": end, "weight": weight, "label": None})
    return merged


def _latest_completed_turn(store: TraceStore, thread_id: str, horizon_seq: int) -> str | None:
    latest: str | None = None
    for record in store.records(thread_id=thread_id):
        if record.seq > horizon_seq:
            break
        if record.method in {"turn/completed", "$history/turn"} and record.turn_id:
            latest = record.turn_id
    return latest


def _extract_structured_message(
    store: TraceStore,
    *,
    thread_id: str,
    turn_id: str,
) -> dict[str, Any]:
    messages: list[Mapping[str, Any]] = []
    for record in store.records(thread_id=thread_id):
        if record.turn_id != turn_id or record.method != "item/completed":
            continue
        params = record.message.get("params")
        if not isinstance(params, Mapping):
            continue
        item = params.get("item")
        if isinstance(item, Mapping) and item.get("type") == "agentMessage":
            messages.append(item)
    if not messages:
        raise ValueError(f"semantic worker {thread_id} produced no traced agentMessage")
    final = next(
        (item for item in reversed(messages) if item.get("phase") in {"final", "final_answer"}),
        messages[-1],
    )
    text = final.get("text")
    if not isinstance(text, str):
        raise ValueError("semantic worker final message has no text")
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError("semantic worker output is not an object")
    return value


def _start_worker_thread(
    place: CodexPlace,
    store: TraceStore,
    *,
    source_thread_id: str,
    stage: str,
    metadata: Mapping[str, Any],
    model: str | None,
) -> str:
    params: dict[str, Any] = {
        "cwd": os.getcwd(),
        "approvalPolicy": "never",
        "sandbox": "read-only",
        "ephemeral": True,
        "threadSource": f"eidos-semantic-{stage}",
    }
    if model is not None:
        params["model"] = model
    thread_id = place.start_thread(**params)
    store.annotate_thread(
        thread_id,
        kind=f"semantic-{stage}",
        parent_thread_id=source_thread_id,
        metadata=dict(metadata),
    )
    return thread_id


def _run_fresh_worker(
    *,
    command: Sequence[str],
    store: TraceStore,
    source_thread_id: str,
    stage: str,
    metadata: Mapping[str, Any],
    prompt: str,
    schema: Mapping[str, Any],
    model: str | None,
    effort: str,
    timeout: float = 120.0,
) -> dict[str, Any]:
    client = AppServerClient(
        command,
        trace=store,
        source=f"codex-semantic-{stage}",
    )
    with client:
        place = CodexPlace(stage, client).start()
        thread_id = _start_worker_thread(
            place,
            store,
            source_thread_id=source_thread_id,
            stage=stage,
            metadata=metadata,
            model=model,
        )
        started = client.turn_start_text(
            thread_id,
            prompt,
            effort=effort,
            outputSchema=dict(schema),
            turnTrigger=f"eidos-semantic-{stage}",
        )
        turn = started.get("turn")
        if not isinstance(turn, Mapping) or not isinstance(turn.get("id"), str):
            raise ValueError(f"{stage} turn/start returned no turn id: {started!r}")
        turn_id = str(turn["id"])
        client.wait_for("turn/completed", thread_id=thread_id, timeout=timeout)
        return _extract_structured_message(store, thread_id=thread_id, turn_id=turn_id)


def _global_story_scaffold(store: TraceStore, thread_id: str) -> str:
    whole = _full_window(store, thread_id)
    beats = build_story_beats(store, whole)
    rendered: list[str] = []
    for beat in beats:
        if beat.kind == "user":
            label = "USER"
            limit = 1800
        elif beat.kind == "assistant-final":
            label = "ASSISTANT FINAL"
            limit = 1800
        elif beat.kind == "execution-support":
            label = "EXECUTION SUPPORT"
            limit = 650
        elif beat.kind == "reasoning-summary":
            label = "REASONING SUMMARY"
            limit = 700
        else:
            label = beat.kind.upper()
            limit = 700
        span = str(beat.start_seq) if beat.start_seq == beat.end_seq else f"{beat.start_seq}-{beat.end_seq}"
        rendered.append(f"[{label} seq {span}]\n{beat.text[:limit]}")
    text = "\n\n".join(rendered)
    # This is only an attention scaffold. The fork still inherits native history.
    return text[:80000]


def _global_prompt(store: TraceStore, thread_id: str, horizon_seq: int) -> str:
    return f"""You are preparing the global hindsight brief for an Eidos semantic tree.

You have inherited the native Codex history through trace horizon {horizon_seq}.
Read it as someone who already knows how the movie ends. Do NOT create the final
outline yet. Produce a compact prior that independent local workers can use to
reinterpret their own regions without needing the entire future transcript.

Identify:
- what ultimately became the durable story;
- likely durable arcs and concepts;
- dead ends or busy-looking activity that turned out not to matter;
- small/surprising moments whose later consequences made them important;
- attention guidance for local workers.

The deterministic scaffold below foregrounds dialogue and compresses routine
execution. It is an attention hint, not a substitute for the inherited history.

{_global_story_scaffold(store, thread_id)}

Return only the structured value required by the output schema.
"""


def _leaf_prompt(
    store: TraceStore,
    thread_id: str,
    window: SemanticWindow,
    global_retro: Mapping[str, Any],
) -> str:
    local = CandidateWindow(
        thread_id=thread_id,
        start_seq=window.start_seq,
        end_seq=window.end_seq,
        record_count=0,
    )
    return f"""You are one parallel retrospective enrichment worker.

GLOBAL HINDSIGHT BRIEF:
{json.dumps(global_retro, ensure_ascii=False, separators=(",", ":"))}

Your local evidence covers Eidos trace seq {window.start_seq}..{window.end_seq}.
Interpret this region knowing the ending summarized above.

Important:
- READ the whole supplied local substrate, but do not assume this region deserves
  equal narrative weight merely because it occupies a window.
- It is correct to return signal near 0 and episodes=[] when little survives at
  the larger scale.
- User messages and final assistant answers are the default semantic spine.
- Routine commands/tools are supporting evidence unless their consequences made
  them important later.
- Rescue surprises the global brief underestimated. The global brief is a prior,
  not an oracle.
- Episodes should say what the activity TURNED OUT TO MEAN, not narrate commands.
- Titles: 3-7 words. Summary: one terse sentence.
- Support ranges must lie inside {window.start_seq}..{window.end_seq}.
- Non-contiguous support is allowed.
- Do not call tools.

LOCAL WEIGHTED STORY SUBSTRATE:
{format_story_window(store, local)}

Return only the structured value required by the output schema.
"""


def _rollup_prompt(
    *,
    global_retro: Mapping[str, Any],
    nodes: Sequence[TreeNode],
    level: int,
    final: bool,
) -> str:
    payload = [
        {
            "id": node.node_id,
            "title": node.title,
            "summary": node.summary,
            "importance": node.importance,
            "confidence": node.confidence,
            "support": node.support,
        }
        for node in nodes
    ]
    scale = "final thread scale" if final else f"semantic level {level}"
    return f"""You are an Eidos retrospective reducer at {scale}.

GLOBAL HINDSIGHT BRIEF:
{json.dumps(global_retro, ensure_ascii=False, separators=(",", ":"))}

CHILD SEMANTIC VALUES:
{json.dumps(payload, ensure_ascii=False, separators=(",", ":"))}

Reduce these children with ex-post wisdom.

The question is NOT "summarize each child." Ask:
  Given the final state of the story, what information from these children is
  still necessary to understand this region at the next scale?

Rules:
- IMPORTANCE MUST SHARPEN UPWARD.
- Low-value children may be listed in discarded and disappear entirely from the
  parent narrative. Reading everything does not imply sampling everything evenly.
- Important children deserve finer distinctions; routine siblings may collapse
  together or vanish.
- Each parent must name one or more child ids from the supplied set.
- Do not invent support ranges; Eidos derives parent support from children.
- Parent titles: 3-7 words. Summaries: one terse sentence.
- The global brief is a prior. Correct it when child evidence reveals something
  the global pass underestimated.
- Prefer a few durable parents to exhaustive coverage.
- Do not call tools.

Return only the structured value required by the output schema.
"""


class SemanticTreeBuilder:
    def __init__(
        self,
        store: TraceStore,
        *,
        command: Sequence[str] = ("codex", "app-server", "--listen", "stdio://"),
        max_workers: int | None = None,
    ) -> None:
        self.store = store
        self.command = tuple(command)
        configured = int(os.environ.get("EIDOS_SUMMARY_CONCURRENCY", "4"))
        self.max_workers = max(1, min(8, max_workers or configured))

    def _global_retro(
        self,
        thread_id: str,
        *,
        model: str | None,
        progress: ProgressCallback,
    ) -> dict[str, Any]:
        whole = _full_window(self.store, thread_id)
        progress(
            "global",
            0,
            1,
            f"global hindsight · {model or 'inherited model'} / {SYNTHESIS_REASONING_EFFORT}",
        )
        client = AppServerClient(
            self.command,
            trace=self.store,
            source="codex-semantic-global",
        )
        with client:
            place = CodexPlace("semantic-global", client).start()
            last_turn = _latest_completed_turn(self.store, thread_id, whole.end_seq)
            if last_turn is not None:
                args: dict[str, Any] = {
                    "lastTurnId": last_turn,
                    "ephemeral": True,
                    "threadSource": "eidos-semantic-global",
                    "sandbox": "read-only",
                    "approvalPolicy": "never",
                }
                if model is not None:
                    args["model"] = model
                worker_thread = place.fork_thread(thread_id, **args)
            else:
                worker_thread = _start_worker_thread(
                    place,
                    self.store,
                    source_thread_id=thread_id,
                    stage="global",
                    metadata={"horizon_seq": whole.end_seq},
                    model=model,
                )
            self.store.annotate_thread(
                worker_thread,
                kind="semantic-global",
                parent_thread_id=thread_id,
                metadata={"horizon_seq": whole.end_seq},
            )
            started = client.turn_start_text(
                worker_thread,
                _global_prompt(self.store, thread_id, whole.end_seq),
                effort=SYNTHESIS_REASONING_EFFORT,
                outputSchema=GLOBAL_RETRO_SCHEMA,
                turnTrigger="eidos-semantic-global",
            )
            turn = started.get("turn")
            if not isinstance(turn, Mapping) or not isinstance(turn.get("id"), str):
                raise ValueError(f"global hindsight turn/start returned no turn id: {started!r}")
            turn_id = str(turn["id"])
            client.wait_for("turn/completed", thread_id=worker_thread, timeout=180.0)
            value = _extract_structured_message(
                self.store,
                thread_id=worker_thread,
                turn_id=turn_id,
            )
        progress("global", 1, 1, "global hindsight committed")
        return value

    def _enrich_one(
        self,
        thread_id: str,
        window: SemanticWindow,
        global_retro: Mapping[str, Any],
        *,
        model: str | None,
    ) -> tuple[SemanticWindow, dict[str, Any]]:
        value = _run_fresh_worker(
            command=self.command,
            store=self.store,
            source_thread_id=thread_id,
            stage="leaf",
            metadata={
                "window_index": window.index,
                "start_seq": window.start_seq,
                "end_seq": window.end_seq,
                "semantic_mass": window.semantic_mass,
            },
            prompt=_leaf_prompt(self.store, thread_id, window, global_retro),
            schema=LEAF_SCHEMA,
            model=model,
            effort=LEAF_REASONING_EFFORT,
            timeout=150.0,
        )
        return window, value

    def _normalize_leaf(
        self,
        window: SemanticWindow,
        value: Mapping[str, Any],
    ) -> list[TreeNode]:
        out: list[TreeNode] = []
        for ordinal, raw in enumerate(value.get("episodes") or []):
            if not isinstance(raw, Mapping):
                continue
            support: list[dict[str, Any]] = []
            for span in raw.get("support") or []:
                if not isinstance(span, Mapping):
                    continue
                start = int(span["start"])
                end = int(span.get("end", start))
                if (
                    start < window.start_seq
                    or end > window.end_seq
                    or end < start
                ):
                    raise ValueError(
                        f"leaf worker emitted invalid support {start}..{end} "
                        f"outside {window.start_seq}..{window.end_seq}"
                    )
                support.append(
                    {
                        "start": start,
                        "end": end,
                        "weight": float(span.get("weight", 1.0)),
                        "label": span.get("label"),
                    }
                )
            if not support:
                continue
            local_id = str(raw.get("id") or f"episode-{ordinal}")
            out.append(
                TreeNode(
                    node_id=f"leaf-{window.index}-{local_id}",
                    title=str(raw.get("title") or "Untitled episode"),
                    summary=str(raw.get("summary") or ""),
                    importance=float(raw.get("importance", value.get("signal", 0.5))),
                    confidence=float(raw.get("confidence", 1.0)),
                    support=support,
                    children=[],
                    level=0,
                )
            )
        return out

    def _reduce_group(
        self,
        thread_id: str,
        global_retro: Mapping[str, Any],
        nodes: Sequence[TreeNode],
        *,
        model: str | None,
        level: int,
        group_index: int,
        final: bool,
    ) -> tuple[dict[str, Any], Sequence[TreeNode]]:
        value = _run_fresh_worker(
            command=self.command,
            store=self.store,
            source_thread_id=thread_id,
            stage="reduce",
            metadata={
                "level": level,
                "group": group_index,
                "child_count": len(nodes),
                "final": final,
            },
            prompt=_rollup_prompt(
                global_retro=global_retro,
                nodes=nodes,
                level=level,
                final=final,
            ),
            schema=ROLLUP_SCHEMA,
            model=model,
            effort=SYNTHESIS_REASONING_EFFORT,
            timeout=150.0,
        )
        return value, nodes

    def _normalize_rollup(
        self,
        value: Mapping[str, Any],
        children: Sequence[TreeNode],
        *,
        level: int,
        group_index: int,
    ) -> list[TreeNode]:
        by_id = {child.node_id: child for child in children}
        used: set[str] = set()
        parents: list[TreeNode] = []
        for ordinal, raw in enumerate(value.get("parents") or []):
            if not isinstance(raw, Mapping):
                continue
            child_ids = [
                str(child_id)
                for child_id in raw.get("children") or []
                if str(child_id) in by_id and str(child_id) not in used
            ]
            if not child_ids:
                continue
            used.update(child_ids)
            child_nodes = [by_id[child_id] for child_id in child_ids]
            local_id = str(raw.get("id") or f"parent-{ordinal}")
            parents.append(
                TreeNode(
                    node_id=f"roll-{level}-{group_index}-{local_id}",
                    title=str(raw.get("title") or "Untitled arc"),
                    summary=str(raw.get("summary") or ""),
                    importance=float(raw.get("importance", max(node.importance for node in child_nodes))),
                    confidence=float(raw.get("confidence", min(node.confidence for node in child_nodes))),
                    support=_merge_support(child_nodes),
                    children=child_ids,
                    level=level,
                )
            )
        return parents

    def _persist_tree(
        self,
        thread_id: str,
        *,
        global_retro: Mapping[str, Any],
        all_nodes: Mapping[str, TreeNode],
        roots: Sequence[TreeNode],
        final_narrative: str,
    ) -> str:
        parent_of: dict[str, str] = {}
        for node in all_nodes.values():
            for child_id in node.children:
                parent_of[child_id] = node.node_id

        reachable: set[str] = set()
        stack = [node.node_id for node in roots]
        while stack:
            node_id = stack.pop()
            if node_id in reachable:
                continue
            node = all_nodes.get(node_id)
            if node is None:
                continue
            reachable.add(node_id)
            stack.extend(node.children)

        ordered = sorted(
            (all_nodes[node_id] for node_id in reachable),
            key=lambda node: (-node.level, node.first_seq, node.node_id),
        )
        values: list[dict[str, Any]] = []
        for ordinal, node in enumerate(ordered):
            values.append(
                {
                    "id": node.node_id,
                    "parent": parent_of.get(node.node_id),
                    "ordinal": ordinal,
                    "title": node.title,
                    "summary": node.summary,
                    "confidence": node.confidence,
                    "support": node.support,
                }
            )

        self.store.register_semantic_observer(
            name="retrospective-tree",
            lens="thread",
            reliability=1.0,
            prompt="global hindsight -> parallel retrospective enrichment -> recursive reducer",
        )
        whole = _full_window(self.store, thread_id)
        previous = next(
            (
                revision
                for revision in self.store.semantic_revisions(thread_id, lens="thread")
                if revision.get("observer") == "retrospective-tree"
            ),
            None,
        )
        note = final_narrative or str(global_retro.get("narrative") or "")
        return self.store.put_semantic_revision(
            thread_id=thread_id,
            lens="thread",
            observer="retrospective-tree",
            horizon_seq=whole.end_seq,
            nodes=values,
            confidence=float(global_retro.get("confidence", 1.0)),
            parent_revision=previous.get("revision_id") if previous else None,
            note=note,
        )

    def build(
        self,
        thread_id: str,
        *,
        progress: ProgressCallback | None = None,
    ) -> TreeBuildResult:
        progress = progress or (lambda stage, current, total, detail: None)

        discovery = AppServerClient(
            self.command,
            trace=self.store,
            source="codex-semantic-discovery",
        )
        with discovery:
            CodexPlace("semantic-discovery", discovery).start()
            leaf_model = choose_leaf_model(discovery)

        synthesis_model = os.environ.get("EIDOS_SYNTHESIS_MODEL") or leaf_model
        global_retro = self._global_retro(
            thread_id,
            model=synthesis_model,
            progress=progress,
        )

        windows = plan_semantic_windows(self.store, thread_id)
        progress(
            "enrich",
            0,
            len(windows),
            f"parallel retrospective enrichment · {len(windows)} semantic windows · "
            f"{leaf_model or 'default model'} / {LEAF_REASONING_EFFORT} · "
            f"concurrency {self.max_workers}",
        )

        leaf_values: dict[int, dict[str, Any]] = {}
        completed = 0
        completed_lock = threading.Lock()
        with ThreadPoolExecutor(max_workers=min(self.max_workers, len(windows) or 1)) as executor:
            futures = {
                executor.submit(
                    self._enrich_one,
                    thread_id,
                    window,
                    global_retro,
                    model=leaf_model,
                ): window
                for window in windows
            }
            for future in as_completed(futures):
                window, value = future.result()
                leaf_values[window.index] = value
                with completed_lock:
                    completed += 1
                    progress(
                        "enrich",
                        completed,
                        len(windows),
                        f"enriched {completed}/{len(windows)} · "
                        f"window {window.index + 1} signal {float(value.get('signal', 0.0)):.2f}",
                    )

        leaves: list[TreeNode] = []
        all_nodes: dict[str, TreeNode] = {}
        for window in windows:
            for node in self._normalize_leaf(window, leaf_values.get(window.index, {})):
                leaves.append(node)
                all_nodes[node.node_id] = node

        if not leaves:
            revision = self._persist_tree(
                thread_id,
                global_retro=global_retro,
                all_nodes={},
                roots=[],
                final_narrative=str(global_retro.get("narrative") or ""),
            )
            return TreeBuildResult(
                revision_id=revision,
                global_retro=global_retro,
                leaf_windows=len(windows),
                leaf_episodes=0,
                levels=0,
                model=leaf_model,
                leaf_effort=LEAF_REASONING_EFFORT,
                synthesis_effort=SYNTHESIS_REASONING_EFFORT,
            )

        current = sorted(leaves, key=lambda node: (node.first_seq, node.node_id))
        level = 1
        final_narrative = str(global_retro.get("narrative") or "")

        # Repeatedly reduce importance-weighted groups. Low-value nodes pack more
        # densely; important nodes consume more of a reducer group's semantic mass.
        while len(current) > 6 and level <= 4:
            groups = pack_nodes_by_mass(current)
            progress(
                "reduce",
                0,
                len(groups),
                f"rollup level {level} · {len(current)} children -> {len(groups)} reducer groups · "
                f"{synthesis_model or 'default model'} / {SYNTHESIS_REASONING_EFFORT}",
            )
            next_level: list[TreeNode] = []
            completed = 0
            with ThreadPoolExecutor(max_workers=min(self.max_workers, len(groups) or 1)) as executor:
                futures = {
                    executor.submit(
                        self._reduce_group,
                        thread_id,
                        global_retro,
                        group,
                        model=synthesis_model,
                        level=level,
                        group_index=group_index,
                        final=False,
                    ): (group_index, group)
                    for group_index, group in enumerate(groups)
                }
                for future in as_completed(futures):
                    group_index, _group = futures[future]
                    value, children = future.result()
                    parents = self._normalize_rollup(
                        value,
                        children,
                        level=level,
                        group_index=group_index,
                    )
                    for parent in parents:
                        all_nodes[parent.node_id] = parent
                    next_level.extend(parents)
                    completed += 1
                    progress(
                        "reduce",
                        completed,
                        len(groups),
                        f"rollup level {level} · group {completed}/{len(groups)} committed",
                    )
            if not next_level:
                break
            if len(next_level) >= len(current):
                # The reducer preserved too many distinctions to make this level
                # useful. Stop recursing and let the final synthesis adjudicate
                # the remaining semantic Values in one pass.
                current = sorted(next_level, key=lambda node: (node.first_seq, node.node_id))
                level += 1
                break
            current = sorted(next_level, key=lambda node: (node.first_seq, node.node_id))
            level += 1

        # Always do a final ex-post synthesis, even when there are only a few
        # surviving leaves. This is where the thread-level narrative is authored.
        progress(
            "final",
            0,
            1,
            f"final retrospective synthesis · {len(current)} candidates · "
            f"{synthesis_model or 'default model'} / {SYNTHESIS_REASONING_EFFORT}",
        )
        final_value, final_children = self._reduce_group(
            thread_id,
            global_retro,
            current,
            model=synthesis_model,
            level=level,
            group_index=0,
            final=True,
        )
        roots = self._normalize_rollup(
            final_value,
            final_children,
            level=level,
            group_index=0,
        )
        for root in roots:
            all_nodes[root.node_id] = root
        if roots:
            current = roots
        final_narrative = str(final_value.get("narrative") or final_narrative)
        progress("final", 1, 1, "final retrospective narrative committed")

        revision = self._persist_tree(
            thread_id,
            global_retro=global_retro,
            all_nodes=all_nodes,
            roots=current,
            final_narrative=final_narrative,
        )
        return TreeBuildResult(
            revision_id=revision,
            global_retro=global_retro,
            leaf_windows=len(windows),
            leaf_episodes=len(leaves),
            levels=level,
            model=leaf_model,
            leaf_effort=LEAF_REASONING_EFFORT,
            synthesis_effort=SYNTHESIS_REASONING_EFFORT,
        )
