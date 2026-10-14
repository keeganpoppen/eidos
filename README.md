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

The integrated investigation connects two-thread evidence selection, immutable context manifests and request pins, bounded attempts, evidence-only recovery, and comparison of exact artifact versions. Evidence inquiries can defer, reload, offer or refuse evidence while retaining the original context and receipt. Recorded-text search finds evidence across threads and exposes its exact source records before selection. Exact result discovery supports inspecting and reusing earlier work. Historical input previews can start a new question from their exact frozen evidence while preserving the current draft. Authored findings can become reusable results without a native attempt. Result provenance shows which saved contexts directly included a result and the exact snapshot each received. Try the [synthetic workflow](docs/evidence/INTEGRATION_CYCLE_B.md) or the [managed-attempt acceptance](docs/evidence/MANAGED_ATTEMPT_INTEGRATION.md); their authored workers consume no account resources. Real subscription-backed service availability and answer quality remain unverified.

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

Use **Import history** in the workbench to review an explicitly chosen app-server
JSONL file, then commit its records and exact original bytes together. The supported
format is UTF-8 JSON objects with one recorded direction for the entire file; other
Codex export formats are not inferred. Imports use isolated capture identities and
refuse thread IDs already present in the workbench. After a lost reply, check the
retained receipt or reselect the exact file to retry the same operation.

The CLI uses the same importer. Repeating the same file, origin label and direction
recovers its receipt instead of appending duplicates:

```bash
uv run eidos import-jsonl .eidos/traces.db supplied-history.jsonl --preview --json
uv run eidos import-jsonl .eidos/traces.db supplied-history.jsonl
```

File review and import do not start native work. The importer retains unknown fields
and repeated lines; its [contract](docs/agents/HISTORY_IMPORT_TASK.md) documents
bounds, exact line mappings and the distinct legacy iterable API behavior.

Use **Add text evidence** for a local UTF-8 file such as test output or a code
excerpt. Preview and save it, then open or search its literal text and add it to
a context. Original bytes can be downloaded from the receipt. Files are limited
to 64 KiB, with additional encoding limits shown on refusal. A lost reply retains
the exact request for receipt lookup or file reselection. This records supplied
contents; it does not certify their origin or run them as commands.
[Contract and recovery](docs/agents/SUPPLIED_TEXT_TASK.md).

From a saved context, choose **Write finding** to retain a conclusion and open
questions without starting a specialist. The finding keeps that exact context,
appears in result search, and can become an input to another question. Citations
identify supplied sources; uncited hypotheses are labelled. A lost save reply can
be recovered with **Check finding receipt** or an exact retry. The
[contract](docs/agents/AUTHORED_FINDING_TASK.md) describes its attribution and recovery.

Beside a cited result input, choose **Compare with this supplied result** to review
the exact supplied result alongside the finding that used it. Apply the arrangement,
then save it to reopen the same versions later. An unavailable original leaves the
frozen input readable through provenance. Authored demonstrations live under
**Examples** in the comparison view.

Managed attempts are explicitly enabled when starting the API:

```bash
uv run eidos serve .eidos/traces.db --managed-native
```

Start an attempt from its reviewed context in the UI. Each attempt requires fresh
ChatGPT Plus or Pro sign-in, with three minutes for setup/sign-in and two minutes
for work, and uses that account's model allowance. Stop targets the current owned
attempt; reopening history restores no login or automatic execution. Initial
support requires Linux/aarch64, the pinned Codex0.154.0 executable, bubblewrap,
system Python, a C compiler and public system certificate roots. The
[acceptance evidence](docs/evidence/MANAGED_ATTEMPT_INTEGRATION.md) distinguishes
offline verification from unobserved real service behavior. Ordinary startup
leaves native execution closed.

## Architecture in one breath

**Preserve before interpreting. Name what matters. Realize locally until interaction is required. Commit only admitted live authority. Keep evidence, interpretation, and power separate. Present meaningful continuations, not just data. Let the same machinery inspect and improve itself.**

The strong language in those sentences describes design commitments, not proof of complete implementation. The next success is a reliable, coherent everyday workflow, not a larger catalogue of abstractions.
