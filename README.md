# eidos

A small executable experiment in reflective computation, observer-relative causal structure, and **Trusted Machinery™** for linear authority.

The current working thesis is:

> **Semantic structure lives in Values. Names make it addressable. Capabilities carry causal authority. Occurrences make history.**

And the Trusted Machinery underneath them is intentionally boring:

> **atomically commit an occurrence over live linear authority.**

`eidos` is not an agent framework. It is becoming the semantic/runtime substrate for a Nema meta-harness around Codex/app-server.

## What exists

### Eidos / Praxis

Eidos Core is a persistent value language with Names, Roles/Bindings, first-class closures, ordinary structural Values, and authority-bearing Sockets.

Praxis realizes ordinary computation locally until it reaches:

```text
perform socket.Operation(argument)
```

At that boundary it returns a serializable suspended continuation. `perform` is not a special case for agents, tools, Elaborators, or Actualizers: all of those are ordinary Socket operations.

A Reaction may jointly consume several Sockets. A local continuation resumes when its Socket is among the capabilities consumed by the authoritative occurrence.

### Observer-relative semantics

There is no privileged global frontier.

A **Cut** is an ordinary immutable Eidos Value describing one observer-relative causal boundary. Several Cuts can be elaborated jointly, letting a richer observer/specialist/subagent relate facts that no one Cut could expose alone.

```text
Cut C1 ---\
           +-- Elaborator --> Possibility R
Cut C2 ---/
```

Knowledge and models enrich elaboration without granting authority. Historical Cuts remain meaningful after their capabilities are spent, so later reasoning can improve an old model without resurrecting the old world's causal power.

`Elaborator` and `Actualizer` are ordinary roles backed by ordinary projection capabilities:

```text
Elaborator projections
        |
      Elaborate
        v
Possibilities + Actualizer projections
        |
      Actualize
        v
Occurrence + successor projections + successor Elaborators
```

Elaboration and actualization differ semantically, not mechanically.

### Trusted Machinery™

The current observer-relative path uses a deliberately narrow SQLite/WAL-backed substrate:

- durable fresh Names;
- immutable content-addressed Eidos Values and immutable Name→Value bindings;
- identity-only authority domains;
- projection authority facts: domain, holder, live/spent disposition;
- generic atomic authority occurrences over consumed/established projections;
- delegation, idempotency, and durable causal history.

A projection's **role/state/key are not machine columns**. They live in the immutable `Projection` Value bound to the projection Name. Holder and live/spent disposition remain machine authority facts.

Genesis is explicitly separate: an authority domain and its initial projections are admitted once. Normal occurrence commit cannot mint authority from nothing.

Cut, Elaboration, Possibility, Occurrence, protocol meaning, and semantic indexes are all ordinary Values / library conventions above this substrate.

### Derived semantic lenses

Addressable semantic context is traversable without a privileged ontology.

`walk_named_values(..., depth=N)` follows Names embedded in Values, so an observer can progressively expand from an Occurrence into its Possibility, Elaboration, Cuts, projection descriptions, and further context.

`SemanticIndex` is explicitly disposable and rebuildable from the canonical Name→Value relation. Indexes accelerate interpretation; they never become the source of truth.

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
Role / Binding
Projection / Socket
Cut
Elaborator
Possibility
Actualizer
Reaction / Occurrence
Trusted Machinery™
```

A Name identifies; knowing one grants no authority. A projection capability may be semantically inspectable through the immutable Value bound to its Name while its holder/live-spent status remains separate authority state.

A Cut is observer-relative, not a global world state. Elaboration expands an addressable causal situation into adjacent possibility; Actualization resolves one such possibility into authoritative history through the generic occurrence substrate.

See:

- [`docs/CORE.md`](docs/CORE.md) — executable Core language nucleus;
- [`docs/OBSERVER_CUTS.md`](docs/OBSERVER_CUTS.md) — observer-relative causal cuts and joint elaboration;
- [`docs/META_PROTOCOL.md`](docs/META_PROTOCOL.md) — Elaborate / Actualize as ordinary Eidos Socket operations;
- [`docs/SEMANTIC_VALUES.md`](docs/SEMANTIC_VALUES.md) — tableless semantic objects, addressable provenance, and lenses;
- [`docs/SUMMARY_TREE.md`](docs/SUMMARY_TREE.md) — hindsight-first semantic tree over Codex evidence;
- [`experiments/README.md`](experiments/README.md) — archived pressure tests that shaped the current model.

