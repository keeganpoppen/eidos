# eidos

A tiny executable experiment in reflective continuations, persistent Frames, and the **Trusted Machinery** that prevents descriptions of authority from becoming forged authority.

The working idea is intentionally severe:

> **Name identifies. Socket authorizes. Frame records a local causal cut. Match advances compatible continuations.**

`eidos` is not yet an agent framework and it is not yet the Codex wrapper. It is the small substrate we want to understand *before* wrapping Codex/app-server with it.

## Current v0

The repository contains two layers:

- **Eidos / Praxis** — immutable Values and a tiny local evaluator that reduces pure computation until `perform`, returning a serializable suspended continuation.
- **Trusted Machinery** — a SQLite-backed authority substrate for fresh Names, immutable Frames, session sockets, atomic Frame publication, rendezvous Matches, durable receipts, and socket transfer.

The current semantic objects are deliberately few:

```text
Value
Name
Frame
Socket
Protocol
Match
```

A binding is ordinary immutable Frame data. Changing a binding means constructing a new Frame. A socket occurrence may survive unchanged across many Frames, but it may advance only once: a successful Match spends the old occurrence and creates freshly named successor occurrence(s).

## Try it

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
pytest
```

## What this is trying to prove

The first vertical slice asks whether we can make the following unambiguous across crashes:

1. Alice and Bob are durable participants.
2. A binary protocol yields complementary socket projections.
3. Each participant publishes a Frame containing a suspended operation.
4. Trusted Machinery durably matches the compatible offers.
5. Old socket occurrences are spent exactly once; successor occurrences are minted.
6. Both sides can later incorporate the same durable Match independently.
7. Historical Frames remain inspectable without reviving spent authority.

If this works cleanly, the next steps are delegation, historical evaluation with mocked effects, and then a `CodexPlace` adapter around app-server.

## Why this exists

The eventual target is a Nema meta-harness around Codex/app-server. A native Codex thread will initially remain partly opaque; Nema will wrap observable boundaries as named continuations and preserve both high-level harness traces and provider-bound request/response traces. The calculus should sharpen that recorder/controller, not postpone it.

See [`docs/SEMANTICS.md`](docs/SEMANTICS.md) for the current compact contract.
