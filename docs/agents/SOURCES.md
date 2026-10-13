# Source provenance and external verification

## What this seed is based on

The vision documents consolidate the retained founding conversation and retrieved project-specific memory, cross-checked against the default repository revision `6963a0c8d9530005a7998e71aa53e30fe13ea3da` on 2026-10-12. They are a reconstruction of the endorsed trajectory, not a complete transcript or a claim to recover messages unavailable at the context boundary.

The user explicitly requested that the repository become the final continuation artifact for future Codex/ChatGPT sessions, including persistent agent instructions, optional skills, and ambitious parallel work toward a transformative minimum viable product.

The major recovered threads were:

| Thread | Preserved in |
| --- | --- |
| Personal authority-local Cell/world; equal observation/intention peers | DESTINATION, INTERACTION, D02 |
| Codex subscription constraint; meta-harness rather than replacement loop | MEMBRANE, D01, V1 |
| Dual traces and progressively explained runtime context | MEMBRANE M3–M5, W1/W2 |
| Persistent context, structural sharing, request-time availability | MEMBRANE M4–M5, SEMANTICS |
| Partial realization; name/role/binding; wrappers and continuations | SEMANTICS, D04–D08 |
| Actualizer/Elaborator, multi-party occurrences, observer-relative cuts | SEMANTICS, D09–D12 |
| Multiple surfaces/lenses/focus/apertures and reflective compositor | INTERACTION, V1-03/10 |
| Forking, hindsight, alternate interpretations, recursive improvement | REFLECTION, V1-08/11 |
| Knowledge/attention/executors/discovery/handoff | SEMANTICS, STATE, runtime checkpoint docs |
| Candid selective collaboration, effort management, agent coordination | AGENTS, ORCHESTRATION, CONTINUITY |

## Repository evidence checked

The root tree had no AGENTS.md or repository skill directory at the audited base. The baseline README is preserved byte-for-byte as [IMPLEMENTATION.md](../../IMPLEMENTATION.md). Source/README references confirmed the trace/UI and semantic-runtime paths. The [ProcessRuntime checkpoint](../PROCESS_RUNTIME.md) and [Discovery checkpoint](../DISCOVERY.md) establish that later changes had advanced beyond the last visible excerpt's “next: discovery.”

The generic commit implementation was inspected directly in [trusted.py](../../src/eidos/trusted.py), particularly the local liveness/domain checks and caller-supplied output grants. The admission caveats in STATE are deliberately stronger than some historical completion reports.

The baseline workflow [.github/workflows/test.yml](../../.github/workflows/test.yml) runs `uv sync`, `uv run pytest`, and Bun install/check/build. Run `38240774514` passed for the audited base. No live-native or UI usability guarantee follows from that fact.

## Host conventions verified against official documentation

These links were checked on 2026-10-12. They are references, not vendored permanent API contracts; follow current redirects and revalidate against the installed client when behavior matters.

- [AGENTS.md discovery](https://developers.openai.com/codex/guides/agents-md): project instructions are layered by directory; keep the root entry small and direct deeper reading explicitly.
- [Repository skills](https://developers.openai.com/codex/skills): local skills use `.agents/skills/<name>/SKILL.md`, with name/description metadata and progressive disclosure.
- [Subagents](https://developers.openai.com/codex/multi-agent): consult actual host support rather than assuming a particular model, agent count, or configuration field.
- [App-server](https://developers.openai.com/codex/app-server): native client integration reference; verify the installed schema/version.
- [App-server architectural overview](https://openai.com/index/unlocking-the-codex-harness/): background for retaining Codex's native harness rather than replacing it.

The skill files added by this seed are instruction-only. They reference canonical project documents and do not install tools, change global host configuration, or grant external execution permissions.

## Intellectual influences versus dependencies

Frames/metaclass systems, Smalltalk/Lisp-like reflection, algebraic effects, session protocols, capability systems, typed roles, causal event structures, and partial evaluation helped ask productive questions. Earlier storage/transport/language explorations included Flix, semantic databases, message streams, and local operating-system primitives. None is declared a theorem proving Nema correct or a mandatory dependency of V1.

The biology, astronomy, glacier, arrow, routing, and seed-crystal metaphors are remembered as explanatory devices. They carry no physical or distributed-systems guarantees. DECISIONS records their useful implications and where the analogy stops.
