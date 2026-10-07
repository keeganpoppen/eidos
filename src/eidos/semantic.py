from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Iterable, Mapping

from .codex import CodexPlace
from .trace import TraceRecord, TraceStore


# Deliberate reasoning-effort policy for semantic derivation.
#
# Leaf/window work is numerous and structurally constrained, so keep it cheap.
# Higher synthesis levels see already-condensed Values and earn more reasoning.
# "high" is reserved for explicit adjudication/instability, not routine summaries.
LEAF_REASONING_EFFORT = "low"
SYNTHESIS_REASONING_EFFORT = "medium"
ADJUDICATION_REASONING_EFFORT = "high"


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
    effort: str = LEAF_REASONING_EFFORT
    timeout: float = 120.0


RETROSPECTIVE_ANGLE = (
    "Rewrite the thread retrospectively from the perspective of someone who knows how it "
    "turned out. Identify the few semantic arcs that ultimately mattered, how their meaning "
    "changed with later evidence, and the specific episodes that support them."
)

OBSERVER_PRESETS: dict[str, tuple[str, float]] = {
    "retrospective": (RETROSPECTIVE_ANGLE, 1.0),
}


def observer_preset(name: str = "retrospective", *, effort: str = LEAF_REASONING_EFFORT, lens: str = "thread") -> ObserverSpec:
    angle, reliability = OBSERVER_PRESETS[name]
    return ObserverSpec(
        name=name,
        angle=angle,
        lens=lens,
        reliability=reliability,
        effort=effort,
    )


OUTLINE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["confidence", "note", "nodes"],
    "properties": {
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "note": {"type": "string"},
        "nodes": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["id", "parent", "ordinal", "title", "summary", "confidence", "support"],
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
                            "required": ["start", "end", "weight", "label"],
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


@dataclass(frozen=True)
class StoryBeat:
    start_seq: int
    end_seq: int
    kind: str
    importance: float
    text: str


def _input_text(values: Any) -> str:
    if not isinstance(values, list):
        return ""
    return "\n".join(
        str(value.get("text"))
        for value in values
        if isinstance(value, Mapping)
        and value.get("type") == "text"
        and value.get("text")
    )


def _salient_output(output: str) -> str:
    if not output:
        return ""
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    if not lines:
        return ""
    needles = (
        "error",
        "failed",
        "failure",
        "traceback",
        "passed",
        "success",
        "warning",
        "assert",
    )
    interesting = [
        line
        for line in lines
        if any(needle in line.lower() for needle in needles)
    ]
    selected = interesting[-6:] if interesting else lines[-2:]
    return " | ".join(selected)[:900]


def _execution_fragment(item: Mapping[str, Any]) -> tuple[str, str, bool]:
    kind = str(item.get("type") or "item")
    if kind == "commandExecution":
        command = str(item.get("command") or "").strip().replace("\n", " ")
        output = str(item.get("aggregatedOutput") or "")
        salient = _salient_output(output)
        text = f"command: {command[:420]}" if command else "command execution"
        if salient:
            text += f" => {salient}"
        important = any(
            needle in salient.lower()
            for needle in ("error", "failed", "failure", "traceback", "assert")
        )
        return "command", text, important
    if kind == "fileChange":
        paths = [
            str(change.get("path"))
            for change in item.get("changes") or []
            if isinstance(change, Mapping) and change.get("path")
        ]
        return "file", "changed: " + ", ".join(paths[:12]), bool(paths)
    if kind in {"mcpToolCall", "dynamicToolCall", "collabAgentToolCall", "functionCallOutput", "webSearch"}:
        name = item.get("tool") or item.get("name") or item.get("server") or kind
        return "tool", f"{kind}: {name}", False
    return "tool", kind, False


def build_story_beats(store: TraceStore, window: CandidateWindow) -> list[StoryBeat]:
    """Compose a weighted story substrate from raw evidence.

    The raw trace remains egalitarian. This projection intentionally does not:
    dialogue and final answers form the semantic spine, while routine execution
    churn is collapsed into support episodes. These are priors, not truth; later
    consequences may make a tiny tool result more important than a long message.
    """

    records = [
        record
        for record in store.records(thread_id=window.thread_id)
        if window.start_seq <= record.seq <= window.end_seq
    ]
    if not records:
        return []

    user_item_turns: set[str] = set()
    for record in records:
        if record.method not in {"item/completed", "$history/item"}:
            continue
        params = record.message.get("params")
        item = params.get("item") if isinstance(params, Mapping) else None
        if isinstance(item, Mapping) and item.get("type") == "userMessage" and record.turn_id:
            user_item_turns.add(record.turn_id)

    beats: list[StoryBeat] = []
    execution: list[tuple[int, str, str, bool]] = []
    seen_items: set[str] = set()

    def flush_execution() -> None:
        nonlocal execution
        if not execution:
            return
        start = execution[0][0]
        end = execution[-1][0]
        count = len(execution)
        commands = [text for _, kind, text, _ in execution if kind == "command"][:5]
        files = [text for _, kind, text, _ in execution if kind == "file"][:4]
        tools = [text for _, kind, text, _ in execution if kind == "tool"][:5]
        important = any(flag for *_, flag in execution)
        parts = [f"{count} execution item{'s' if count != 1 else ''}"]
        if commands:
            parts.append("commands: " + " ; ".join(commands))
        if files:
            parts.append("files: " + " ; ".join(files))
        if tools:
            parts.append("tools: " + " ; ".join(tools))
        beats.append(
            StoryBeat(
                start_seq=start,
                end_seq=end,
                kind="execution-support",
                importance=0.45 if important else 0.20,
                text="\n".join(parts),
            )
        )
        execution = []

    for record in records:
        message = record.message
        params = message.get("params") if isinstance(message, Mapping) else None

        if record.method == "turn/start" and isinstance(params, Mapping):
            if record.turn_id not in user_item_turns:
                text = _input_text(params.get("input"))
                if text:
                    flush_execution()
                    beats.append(
                        StoryBeat(record.seq, record.seq, "user", 1.0, text[:7000])
                    )
            continue

        if record.method in {"item/completed", "$history/item"} and isinstance(params, Mapping):
            item = params.get("item")
            if not isinstance(item, Mapping):
                continue
            item_id = str(item.get("id") or record.item_id or "")
            if item_id and item_id in seen_items:
                continue
            if item_id:
                seen_items.add(item_id)
            kind = str(item.get("type") or "")

            if kind == "userMessage":
                text = _input_text(item.get("content"))
                if text:
                    flush_execution()
                    beats.append(
                        StoryBeat(record.seq, record.seq, "user", 1.0, text[:7000])
                    )
                continue

            if kind == "agentMessage":
                text = str(item.get("text") or "").strip()
                phase = item.get("phase")
                if text:
                    flush_execution()
                    beats.append(
                        StoryBeat(
                            record.seq,
                            record.seq,
                            "assistant-final" if phase in {None, "final"} else "assistant-intermediate",
                            0.95 if phase in {None, "final"} else 0.55,
                            text[:7000],
                        )
                    )
                continue

            if kind == "plan":
                text = str(item.get("text") or "").strip()
                if text:
                    flush_execution()
                    beats.append(StoryBeat(record.seq, record.seq, "plan", 0.62, text[:3500]))
                continue

            if kind == "reasoning":
                summary = item.get("summary") or []
                text = "\n".join(str(value) for value in summary if value)
                if text:
                    flush_execution()
                    beats.append(
                        StoryBeat(record.seq, record.seq, "reasoning-summary", 0.52, text[:3000])
                    )
                continue

            if kind in {
                "commandExecution",
                "fileChange",
                "mcpToolCall",
                "dynamicToolCall",
                "collabAgentToolCall",
                "functionCallOutput",
                "webSearch",
            }:
                ekind, text, important = _execution_fragment(item)
                execution.append((record.seq, ekind, text, important))
                continue

        if record.method == "thread/compacted":
            flush_execution()
            beats.append(
                StoryBeat(record.seq, record.seq, "compaction-boundary", 0.12, "context compaction")
            )

    flush_execution()
    return beats


def format_story_window(store: TraceStore, window: CandidateWindow) -> str:
    beats = build_story_beats(store, window)
    rendered: list[str] = []
    for beat in beats:
        if beat.kind == "user":
            label = "SPINE · USER"
        elif beat.kind == "assistant-final":
            label = "SPINE · ASSISTANT FINAL"
        elif beat.kind == "assistant-intermediate":
            label = "ASSISTANT INTERMEDIATE"
        elif beat.kind == "execution-support":
            label = "EXECUTION SUPPORT"
        elif beat.kind == "reasoning-summary":
            label = "REASONING SUMMARY"
        elif beat.kind == "plan":
            label = "PLAN"
        else:
            label = beat.kind.upper()
        span = str(beat.start_seq) if beat.start_seq == beat.end_seq else f"{beat.start_seq}-{beat.end_seq}"
        rendered.append(
            f"[{label} | seq {span} | prior {beat.importance:.2f}]\n{beat.text}"
        )
    return "\n\n".join(rendered)


# Backwards-compatible name for callers/tests while the story projection settles.
format_trace_window = format_story_window


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
    story = format_story_window(store, window)
    return f"""You are Eidos's retrospective narrator.

You inherit the native Codex thread through trace horizon {window.end_seq}. Write
the semantic map as someone who already knows how this part of the movie ends.
Your job is not to describe the log. It is to rewrite the history around what
eventually mattered.

The supplied story substrate is an ATTENTION SCAFFOLD, not ground truth:
- USER messages and FINAL ASSISTANT answers are the default semantic spine.
- Plans and reasoning summaries are useful intermediate evidence.
- Routine tool/command/file activity is collapsed into EXECUTION SUPPORT and has
  a deliberately low prior.
- Those priors are defeasible. A one-line test failure or tool result can become
  central if later events show that it changed the direction of the work.

Perspective:
{spec.angle}

Rules:
- Retrospective importance is the organizing principle. Prefer "what this turned
  out to mean" over "what happened next."
- Use natural titles; never expose categories like finding/decision/artifact.
- Titles should usually be 3-7 words. Summaries are ONE terse sentence, normally
  under 150 characters.
- Produce a TWO-LEVEL tree. Roots are durable arcs/topics; direct children are
  the specific episodes, recurrences, or turns of thought that made those arcs.
- IMPORTANCE MUST SHARPEN UPWARD. A root should be more selective and abstract
  than its children. Do not mention grep/sed/cat/build chatter or tool names in
  roots unless that mechanism itself became conceptually important.
- Prefer roughly 3-8 roots. Omit procedural churn and dead ends unless knowing
  they were dead ends is itself important to understanding the history.
- A node may cite multiple disjoint support ranges; this is expected for ideas
  that disappear and recur.
- Support ranges are inclusive Eidos trace sequence numbers and cannot exceed
  horizon {window.end_seq}.
- Rewrite older nodes when later evidence changes their meaning. Preserve them
  only when they remain useful from the current endpoint.
- Use confidence for epistemic uncertainty, not importance.
- Do not call tools.

Previous retrospective map (produced at an earlier horizon):
{json.dumps(previous_nodes, ensure_ascii=False, separators=(",", ":"))}

Current weighted story substrate. Its boundaries are scheduling hints, NOT
semantic episode boundaries:
{story}

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
            "sandbox": "read-only",
            "approvalPolicy": "never",
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

        # Do not re-read the observer turn through thread/items/list. Some local
        # app-server/history modes intentionally do not support that RPC, and we
        # already own the authoritative live evidence: item/completed was traced
        # before turn/completed. Read the observer result from TraceStore.
        messages: list[Mapping[str, Any]] = []
        for record in self.store.records(thread_id=fork_thread):
            if record.turn_id != turn_id or record.method != "item/completed":
                continue
            params = record.message.get("params")
            if not isinstance(params, Mapping):
                continue
            item = params.get("item")
            if isinstance(item, Mapping) and item.get("type") == "agentMessage":
                messages.append(item)
        if not messages:
            raise ValueError(
                "shadow observer completed without a traced agentMessage; "
                "inspect the internal observer thread evidence"
            )
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
