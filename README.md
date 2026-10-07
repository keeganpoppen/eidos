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

### Our conversation renderer

```bash
uv run eidos serve .eidos/traces.db
# open http://127.0.0.1:8765
```

The UI is driven entirely by Eidos-persisted data: user/assistant messages, command executions, file changes, tool calls, live reasoning deltas when Codex exposes them, and the native event spine. Imported old history and future live observations use the same renderer while retaining their different evidence sources.

### Semantic maps / shadow observers

A semantic map is a **versioned interpretation over the evidence**, not a replacement transcript. Nodes may overlap, nest, or cite several non-contiguous trace ranges. Several observers may maintain competing maps; the currently displayed map is selected by horizon plus confidence/reliability, while alternatives remain stored.

Run an ephemeral Codex fork as a semantic observer:

```bash
uv run eidos codex-observe .eidos/traces.db THREAD_ID \
  --target-records 220 \
  --overlap-records 32 \
  --max-windows 4
```

The deterministic window planner only decides where the observer should look. The model authors the semantic chunking, titles, summaries, and retrospective revisions. Each later window receives the observer's prior map and may split, merge, rename, or reconnect older nodes with hindsight.

Observer forks are tagged as internal and hidden from the normal thread list, but their raw native traces remain in the same evidence store for inspection.

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
- [`docs/V0_STATUS.md`](docs/V0_STATUS.md) — what survived first contact with implementation/Codex and what remains open.
