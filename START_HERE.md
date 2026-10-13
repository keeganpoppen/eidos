# Nema seed — start here

**Seed identity: NEMA-SEED-1.** This is a semantic checkpoint, not a password or capability. It exists so a fresh session can recover the destination without possessing the founding chat.

> Build a personal computational world in which understanding, acting, observing, and changing the machinery of work are themselves addressable activities.

Nema is the world/workbench. Eidos is the language and semantic substrate. Praxis performs local realization. Trusted Machinery (also, affectionately, TM) commits local authority transitions. Codex remains the initial native agent harness. These names organize responsibilities; they are not instructions to create four isolated services.

## Recover the intent before continuing the implementation

Read, in order:

1. [AGENTS.md](AGENTS.md): operational boundaries and collaboration.
2. [DESTINATION](docs/vision/DESTINATION.md): what the world should enable and why.
3. [V1](docs/roadmap/V1.md): the smallest *transformative whole*, its acceptance scenarios, and release gates.
4. [STATE](docs/roadmap/STATE.md): what the repository actually contains, the inspected base revision, and important unproven guarantees.
5. [WORKSTREAMS](docs/roadmap/WORKSTREAMS.md): coordinated parallel work, dependencies, and concrete deliveries.

Then load only relevant depth:

| Question | Canonical specification |
| --- | --- |
| What does the expression/continuation language mean? | [SEMANTICS](docs/vision/SEMANTICS.md) |
| What must the Codex membrane observe/control? | [MEMBRANE](docs/vision/MEMBRANE.md) |
| What should using this feel like? | [INTERACTION](docs/vision/INTERACTION.md) |
| How do knowledge, forks, and recursive improvement fit? | [REFLECTION](docs/vision/REFLECTION.md) |
| Why did we keep or reject particular ideas? | [DECISIONS](docs/roadmap/DECISIONS.md) |
| How should many agents collaborate? | [ORCHESTRATION](docs/agents/ORCHESTRATION.md) |
| What can I paste into a new session? | [BOOTSTRAP](docs/agents/BOOTSTRAP.md) |
| How do we keep this seed alive? | [CONTINUITY](docs/agents/CONTINUITY.md) |
| What is the continuing program learning? | [PROGRAM](docs/agents/PROGRAM.md) |
| Where did these commitments come from? | [SOURCES](docs/agents/SOURCES.md) |

## The recognition test

You understand the intended system if you can explain all three without hand-waving:

**The workbench:** a long real Codex conversation becomes a durable navigable world, not a chat scroll. A user can put its plan, changes, pending questions, original evidence, and alternative interpretations in different linked apertures; ask an agent to rearrange or investigate them; and resume the work without reconstructing context manually.

**The language:** a process is partly realized locally, with residual interaction made explicit and serializable. Roles select situated meanings without namespace collapse. Wrapping/rebinding changes interpretation while preserving references and causal provenance. A live Socket is not interchangeable with a copied description of one.

**The improvement loop:** use recorded work to propose a better lens, context projection, instruction, wrapper, or workflow; test it against history or an isolated fork; compare outcomes; admit a reviewed improvement; retain the old explanation. The auditors use the same workbench and their own operations are inspectable.

## Do not confuse the last experiment with the next priority

At the inspected base, discovery, observer-side processes, and a shared named-protocol `ProcessRuntime` already exist. Rebuilding them because an older document ends with “next: discovery” is wasted effort. Conversely, having a local protocol test does not mean the everyday workbench, complete context capture, secure remote capability transfer, or durable end-to-end orchestration is finished.

The recommended next cycle is **one integrated two-thread investigation**: stable references from actual trace evidence to semantic selections, a reviewable context packet, bounded delegated work, return-to-source navigation, and restartable progress. Use the existing runtime where it reduces the gap. Do not rewrite the stack to prove philosophical purity.

## Status and precedence

These vision documents consolidate endorsed aims from the founding collaboration and propose an implementation route. They are **not** claims that V1 is delivered or that the calculus has been formally proved. `STATE` is an as-of audit. Older top-level technical docs are valuable implementation checkpoints; `docs/experiments/` is archaeology. When a newer implementation contradicts this seed, report the difference, decide deliberately, and update the affected specification with rationale.

[IMPLEMENTATION.md](IMPLEMENTATION.md) preserves the pre-seed implementation overview. The seed is a usable reconstruction of the conversation's design trajectory, not a complete verbatim transcript. No future session should need the original chat to proceed, and no session should regard this text as beyond revision.
