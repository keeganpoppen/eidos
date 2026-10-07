# eidos

A small executable experiment in reflective continuations, persistent Frames, and the **Trusted Machinery** that prevents descriptions of authority from becoming forged authority.

The current working idea is intentionally severe:

> **Name identifies. Socket authorizes. Frame records a local causal cut. Match advances compatible continuations.**

`eidos` is not an agent framework. It is becoming the small semantic/runtime substrate for a Nema meta-harness around Codex/app-server.

## What exists

### Eidos / Praxis

An immutable value language plus a tiny local evaluator. Praxis reduces ordinary computation locally until it reaches:

```text
perform(socket, operation, value)
```

At that boundary it returns a serializable suspended continuation rather than executing the effect.

### Trusted Machinery

A SQLite/WAL-backed authority substrate providing:

- durable fresh Names;
- immutable Frames;
- binary protocol/session sockets;
- atomic Frame + offer publication;
- single-spend socket advancement;
- durable rendezvous Matches and receipts;
- live socket handoff;
- idempotent state-changing requests.

The end-to-end Runtime now runs a two-party program through `perform -> Frame -> Match -> receipt -> resume`, including restart after the Match is committed but before either side resumes.

### Codex boundary

`AppServerClient` is a traced JSONL client for `codex app-server`; `CodexPlace` treats one app-server process as one evaluator realm that may host many threads.

`TraceStore` preserves native JSON records and cheap indexing projections without normalizing unknown fields away.

Existing Codex threads can be hydrated into our store:

```bash
uv run eidos codex-sync .eidos/traces.db --recent 3
```

Future JSONL traffic can be recorded transparently:

```bash
uv run eidos codex-proxy .eidos/traces.db -- codex app-server --listen stdio://
```

### Live SvelteKit chat + trace surface

The primary UI is now a SvelteKit 3 / Svelte 5 client. It talks to a small Python API that owns the live Codex app-server process and projects only from persisted Eidos evidence.

The easiest development path is:

```bash
bash scripts/dev.sh
# -> Eidos UI: http://127.0.0.1:5173
```

Or run the two halves separately:

```bash
# terminal 1
uv run eidos serve .eidos/traces.db

# terminal 2
cd ui
bun install
bun run dev
```

The Vite dev server proxies `/api` to Eidos on `127.0.0.1:8765`.

From the UI you can start a native Codex thread, resume an imported thread, send messages, watch persisted agent/reasoning/tool activity appear live, run semantic observers, and navigate their non-contiguous support ranges. Obvious Markdown in user/assistant/reasoning text is rendered and sanitized.

The old Python-rendered trace pages remain available at `http://127.0.0.1:8765` as a fallback/debug surface.

The live UI is still driven entirely by Eidos-persisted data: user/assistant messages, command executions, file changes, tool calls, live reasoning deltas when Codex exposes them, and the native event spine. Imported old history and future live observations use the same projection path while retaining their different evidence sources.

### Retrospective semantic maps

A semantic map is a **versioned retrospective interpretation over the evidence**, not a replacement transcript. Eidos asks an ephemeral Codex fork to rewrite the history from the perspective of someone who already knows how it turned out.

The observer does **not** receive an egalitarian dump of raw events. Eidos first builds a weighted story substrate:

- user messages and final assistant answers form the default semantic spine;
- plans and reasoning summaries are intermediate evidence;
- repetitive command/tool/file activity is collapsed into low-prior execution-support episodes;
- those priors are defeasible when later consequences show that a tiny tool result actually mattered.

The output is normally a two-level tree: a few durable top-level arcs with specific episodes/subtopics beneath them. Importance should sharpen upward; roots should omit procedural mechanics unless the mechanics themselves became the point.

Run a full retrospective rewrite with:

```bash
uv run eidos codex-observe .eidos/traces.db THREAD_ID --max-windows 0
```

Each later horizon receives the prior map and may split, merge, rename, or reinterpret older nodes with hindsight. Old revisions remain stored, so the system can distinguish what an episode looked like earlier from what it later came to mean.

Leaf/window rewrites default to `low` reasoning effort. Eidos consults `model/list` and only switches to another model when the catalog clearly advertises it as a fast/small/efficient option that supports low effort; otherwise it safely inherits the source model. Set `EIDOS_SUMMARY_MODEL` to explicitly pin the summarizer model. The planned hierarchy reserves `medium` for synthesis and `high` for rare adjudication rather than routine summarization.

Nodes may overlap, nest, or cite several non-contiguous trace ranges. Observer forks are internal and hidden from the normal thread list, but their native traces remain in the evidence store.


## Develop / test

Eidos uses [uv](https://docs.astral.sh/uv/) for the Python environment, dependency resolution, and command execution. There is no manual virtualenv activation or pip workflow.

```bash
uv sync
uv run pytest
```

Run project commands through uv as well:

```bash
uv run eidos --help
```

## Current semantic vocabulary

```text
Value
Name
Frame
Socket
Protocol
Match
```

A binding is ordinary immutable Frame data. Changing a binding means constructing another Frame. A socket occurrence may survive unchanged across many Frames, but a successful rendezvous spends that occurrence and creates successor socket occurrence(s).

See:

- [`docs/SEMANTICS.md`](docs/SEMANTICS.md) — compact semantic contract;
- [`docs/V0_STATUS.md`](docs/V0_STATUS.md) — what survived first contact with implementation/Codex and what remains open;
- [`docs/SUMMARY_TREE.md`](docs/SUMMARY_TREE.md) — planned recursive semantic hierarchy, effort budget, and subagent/map-reduce strategy.
