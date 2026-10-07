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

### Hindsight-first semantic tree

A semantic tree is a **versioned retrospective interpretation over the evidence**, not a replacement transcript. The current build pipeline is:

```text
raw trace
  ↓ deterministic weighted story substrate
global hindsight brief                     medium
  ↓
parallel retrospective leaf enrichment     low
  ↓
importance-weighted parallel rollups        medium
  ↓
final retrospective synthesis              medium
  ↓
provenance tree → raw support ranges
```

The deterministic substrate deliberately foregrounds user messages and final assistant answers and collapses routine command/tool/file churn. Leaf windows are planned by **semantic mass**, not raw record count, so a 500-record tool detour does not automatically earn five times the inference budget of a short conceptual exchange.

Every semantic region is still inspected. Leaf workers are historical forks truncated at local completed-turn cutoffs whenever possible, so they inherit the real native past while the global retro injects future knowledge. They may explicitly return no durable episode when a region has little to offer. Surviving nodes carry importance, confidence, and trace support; low-importance nodes pack more densely in reducer groups while important nodes receive more synthesis bandwidth. At every rollup the governing question is:

> Given the final state of the story, what information from these children is still necessary to understand this region at the next scale?

The result is a recursive tree, not merely a two-level outline. Importance should sharpen upward. The Svelte focus pane lets you descend through child nodes and back to their supporting transcript regions.

Run it with:

```bash
uv run eidos codex-observe .eidos/traces.db THREAD_ID
```

or use **REWRITE WITH HINDSIGHT** in the UI. Progress reports the current global/enrichment/reducer stage rather than an opaque spinner.

Leaf workers default to `low` reasoning effort; global and rollup synthesis use `medium`. Eidos only auto-selects another model when `model/list` clearly advertises a small/mini/efficient option that supports low effort; otherwise it uses the default/inherited model rather than guessing. Overrides:

```bash
EIDOS_SUMMARY_MODEL=<leaf-model>
EIDOS_SYNTHESIS_MODEL=<merge-model>
EIDOS_SUMMARY_CONCURRENCY=4
```

Concurrency is bounded to at most 8 workers. Semantic worker threads are ephemeral, read-only, hidden from the ordinary thread list, and still fully traced.

Old sequential retrospective/experimental maps remain queryable as legacy revisions, but the hindsight tree is the default semantic interpretation.



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
