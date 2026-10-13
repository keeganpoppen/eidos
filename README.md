# Eidos / Nema

**A personal computational world for working with agents—and working on the way you work with them.**

Nema's first realization is a reflective workspace around native Codex/app-server. It preserves real execution evidence, makes context and continuations inspectable, and lets people and agents compose many views, delegate investigations, explore alternatives, and improve the machinery without erasing its history.

Eidos is the expression/continuation language beneath that ambition. It is not a replacement for Codex's agent loop, and the project is not finished when one more small calculus example passes.

> Semantic structure lives in Values. Names make it addressable. Capabilities carry causal authority. Occurrences make history.

## New session?

Read **[START_HERE.md](START_HERE.md)**. This repository is the durable continuation artifact of its founding design conversation.

The short path is [destination](docs/vision/DESTINATION.md) → [transformative V1](docs/roadmap/V1.md) → [current state](docs/roadmap/STATE.md) → [parallel workstreams](docs/roadmap/WORKSTREAMS.md). [AGENTS.md](AGENTS.md) supplies operational guidance; [the bootstrap prompt](docs/agents/BOOTSTRAP.md) starts a fresh high-effort session. Optional repository skills are in `.agents/skills/`.

## The experience we are trying to make possible

Open months of prior work without rereading months of chat. Move from a claim to its evidence, from a pending question to the continuation it blocks, from a proposed change to its actual diff. Place different interpretations alongside one another. Give a specialist exactly the context and authority its task requires. Fork a historical question without accidentally replaying live effects. Resume after interruption. Turn a discovered improvement into a tested, reviewable change to the environment itself.

The user, their agents, processes, terminal sessions, browser surfaces, and local or remote executors should inhabit one addressable semantic medium, rather than independent conversations with lossy handoffs.

## What exists today

There are two substantial bodies of implementation to connect deliberately:

- A Codex JSONL client/proxy, trace persistence/import, a live Python API and SvelteKit UI, and a hindsight-oriented semantic tree over recorded conversation evidence.
- An experimental Eidos evaluator and linear-authority substrate: Values, Names, situated Roles/Bindings, Closures, Sockets, multi-input Reactions, observer-relative Cuts, executable Models, context acquisition/discovery, and a generic named-protocol continuation runtime.

The [implementation overview](IMPLEMENTATION.md) and existing [runtime checkpoint](docs/PROCESS_RUNTIME.md) describe these in more detail. The [state audit](docs/roadmap/STATE.md) distinguishes local demonstrations from production guarantees. In particular, host registration and holder strings are not a secure remote capability system; generic commit is a privileged interface, not permission for arbitrary clients to mint successors.

The first integrated investigation slice now connects two-thread evidence selection, immutable context preview/revisions, one native worker attempt, recovery from recorded completion, and source-linked conclusion adoption. Try the [synthetic workflow and acceptance report](docs/evidence/INVESTIGATION_CYCLE_A.md); its fake worker consumes no account resources. Real-native verification and the resumable disclosure-question loop remain open.

## Develop

```bash
uv sync
uv run pytest
uv run eidos --help
```

```bash
cd ui
bun install
bun run check
bun run build
```

To run the local development workspace:

```bash
bash scripts/dev.sh
```

The existing dev setup serves the UI on loopback port 5173 and the Python API on 8765. Inspect [scripts/dev.sh](scripts/dev.sh) and the current CLI before changing launch behavior. Native Codex use requires the user's authorized local installation and consumes real resources. Keep auth material and personal traces out of this public repository.

## Architecture in one breath

**Preserve before interpreting. Name what matters. Realize locally until interaction is required. Commit only admitted live authority. Keep evidence, interpretation, and power separate. Present meaningful continuations, not just data. Let the same machinery inspect and improve itself.**

The strong language in those sentences describes design commitments, not proof of complete implementation. The next success is a reliable, coherent everyday workflow, not a larger catalogue of abstractions.
