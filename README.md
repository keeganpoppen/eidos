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
eidos codex-sync .eidos/traces.db --recent 3
```

Future JSONL traffic can be recorded transparently:

```bash
eidos codex-proxy .eidos/traces.db -- codex app-server --listen stdio://
```

### Our conversation renderer

```bash
eidos serve .eidos/traces.db
# open http://127.0.0.1:8765
```

The UI is driven entirely by Eidos-persisted data: user/assistant messages, command executions, file changes, tool calls, and the native event spine. Imported old history and future live observations use the same renderer while retaining their different evidence sources.

## Install / test

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
pytest
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
