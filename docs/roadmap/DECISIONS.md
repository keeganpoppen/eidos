# Decision register and preserved design rationale

This is a reconstruction of the collaboration's important turns, not a verbatim transcript. **Accepted direction** records endorsed intent. **Provisional realization** records a current engineering choice. **Open obligation** identifies what still needs proof or implementation. **Deferred exploration** preserves an idea without making it a prerequisite. Source provenance is in [SOURCES](../agents/SOURCES.md).

## Endorsed direction

### D01 — Codex is the harness; build a meta-harness

The native subscription-backed agent loop is the initial evaluator. Nema adds durable observation, context/topology control, reflection, and presentation. Replacing the agent loop would distract from the distinct value and user constraint. Other executors remain possible later.

### D02 — A personal authority-local world, not a cloud dashboard

Persistence, control, and execution should feel owned by the user. A web app is a peer observation/intention surface. Remote execution is compatible with locality when admitted explicitly; cloud centralization is not a conceptual requirement.

### D03 — Preserve more than the first interpreter understands

Retain raw operational evidence and unknown native information. Normalize/index for utility without destroying source distinctions. Derive deeper models later from corresponding harness/provider observations. A perfect middle ontology is not needed before recording useful evidence.

### D04 — Names, roles, bindings, references, addresses, and holders differ

Names preserve identity; Roles are namespaced semantic positions; Bindings connect code to situated values/references. Binding identity differs from its address and target. Lexical closure capture differs from role binding at realization. This is the answer to namespace collapse and implicit dynamic environment, not just naming style.

### D05 — `perform` is the ordinary interaction boundary

Local reduction can construct new values without external effects. External suspensions expose continuation structure. Resolution may be ordinary local interpretation until it needs a remote interaction. There is no necessary universal `resolve` networking primitive.

### D06 — Derive the Smalltalk-like object world

Facet/structural-dispatch experiments showed wrappers and method dispatch can live in ordinary Records and Closures above Core. Keep reflective object/metaobject behavior without requiring a dedicated evaluator branch for every semantic noun. The surviving pattern is refer → wrap → rebind.

### D07 — Frame/cut is a useful reified view, not an absolute global state

Keep frame-content identity separate from event/occurrence identity. A persistent self need not literally embed its entire predecessor chain; named structural sharing and provenance express the relation more cleanly. Cuts across independent continuations need not all advance together.

### D08 — Sockets carry current relational continuation and authority

The intended socket is an authorized local projection of a named session relation, carrying its current continuation. Successor sockets make progress explicit. A copied historical frame or socket description does not duplicate live authority. Endpoint roles need not be tied permanently to participant identity.

### D09 — Multi-party Reaction, domain-local occurrence

A reaction can join several suspended computations, not one privileged sender. Its occurrence is the causal fact connecting histories. Atomic commitment does not imply simultaneous remote observation. A notification, an observer's incorporation, and a real external effect are different causal steps.

### D10 — Actualizer and Elaborator are roles

Elaboration interprets the actual into structured possible futures; actualization admits one occurrence. They differ semantically, not necessarily mechanically. Both can be ordinary Socket operations above shared authority mechanics. Neither must be a singleton daemon.

### D11 — Understanding is not authority

Two cuts, a better model, or more attention can reveal a new possibility. It does not grant world authority. Specialists may be closures, subagents, remote/virtual agents, subprocesses, humans, or compositions. Their placement does not define their semantic role.

### D12 — Historical reinterpretation is a first-class capability of the product

Later understanding can improve a model of an old world without reviving old authority. Keep original reports, derived interpretations, and counterfactual experiments distinct. Recompilation or replay under mocked effects requires an explicit new realization, not pretending the original live continuation survived unchanged.

### D13 — Many surfaces and many theories of attention

Surface, Lens, Focus, and Aperture capture the shared world and different ways of encountering it. The renderer is not the owner of meaning. Prompts and UIs can be alternative lowerings of an interaction. Preserve domain-native artifacts, not just textual summaries or JSON views.

### D14 — Reflection should apply to the apparatus itself

Record and inspect context construction, orchestration, presentation, and improvement sessions with the same tools used for ordinary tasks. Adoption should be tested, versioned, attributable, and reversible. Recursive self-improvement is an evidence loop, not unbounded autonomous rewriting.

### D15 — The coherent useful whole outranks another minimal novelty

The current seed explicitly elevates the reflective Codex workbench and complete two-thread investigation loop. Minimality is valuable when it enables composition and delivery. Kernel exploration must not indefinitely postpone the recorder/controller and lived experience.

## Provisional realizations and open obligations

### D16 — One-shot local authority and explicit genesis

The prototype uses live/spent projections and a separately admitted genesis. Keep single-consumption as the starting discipline. Multi-shot exploration is possible through explicit new branches/authority, not copying a live token. Open: scope, admission, scheduling, and safe garbage collection of orphaned/abandoned projections.

### D17 — Generic TM with protected semantic admission

Accepted aim: narrow atomic local commit, no universal rich protocol interpreter in TM. Current realization: trusted Python adapters supply successor descriptions. Open obligation: who may submit such a transition, and what constrains those outputs? Burning any token is not sufficient proof. A hash labelled proof does not close this gap. Do not let prior celebration of “generic commit” conceal it.

### D18 — Python/uv plus current UI is the delivery substrate, not metaphysics

Earlier Flix/effects/CSP/Datalog work remains influential. The present repository is Python and Bun/Svelte. A replacement language or storage engine must justify a concrete benefit and migration path. Preserve semantic interfaces and native capabilities rather than restarting implementation to fit a favorite tool.

### D19 — Semantic tables may be removed; interpretation still exists

Canonical named Values and generic authority history replaced much bespoke observer storage. Derived indexes can be discarded/rebuilt. This does not establish that every schema convention is fundamental or that the host contains no semantic code. Keep archival experiments where useful; do not treat all old documents as simultaneous law.

### D20 — Disclosure and graph traversal are distinct

A generic lens may discover references within code. A scoped process cannot infer permission to inspect from reachability. Source disclosure and receiver incorporation are separate domain-local occurrences. Local holder/registration checks model this distinction; authenticated remote transport is not yet established.

### D21 — Requester/responder are positions in a protocol, not species

The newer implementation has one named-protocol ProcessRuntime. Pending, terminal, and continuing operations are locally described and checked; semantic handlers remain situated. Do not recreate duplicated engines for every participant type. Open: robust outer orchestration, resources, actual distributed placement, and handler composition driven by use cases.

**Provisional realization, 2026-10-13 (D01/D15/D21):** the first integrated investigation persists a pre-send native attempt beside TraceStore. Reusing `ModelProcessRunner.Consult` alone would still leave the external-completion-before-prepare window open, so this slice does not force a kernel adapter around the same unsafe seam. Repeated dispatch returns the existing attempt, recorded terminal evidence can recover its result, and missing evidence remains unknown. The calculus remains the intended continuation substrate; connecting visible offer/refuse/defer inquiry state to this durable outer identity is still an open delivery obligation. See the [contract](../agents/INVESTIGATION_CONTRACT.md) and [tested limits](../evidence/INVESTIGATION_CYCLE_A.md).

## Deferred explorations, kept for their potential

### D22 — Names, routing, locality, and leases

The DNS/routing/subdomain intuition aimed at composable names and movable computation: bind a remote participant locally, route through admitted places, and preserve identity when residency changes. Systemd/process trees and namespace/tun/tap ideas similarly suggested a personally controllable execution fabric.

Do not implement a 20 ms DNS lease system or bounded 255-slot routing scheme as a prerequisite. Ordinary cached DNS does not give simultaneous authoritative observation; leases need explicit clocks/fencing/renewal semantics. Durable identity reservation is not the same as a lease on current residency or authority. Prototype a real handoff/locality need before choosing network machinery.

### D23 — ITCs, causal DAGs, ledgers, and rendezvous tags

Dynamic causal clocks may be useful for split/join history; DAGs avoid an unnecessary global total order. They are not by themselves capability systems, anti-double-spend mechanisms, or distributed agreement. A common rendezvous tag shows a naming relation, not that peers hold complementary unforgeable authority. Prefer the smallest local substrate until cross-domain work demands more.

### D24 — Types, kinds, protocol projection, and unification

Role subtyping, dependent descriptions, session types, proof witnesses, and unification may sharpen admissible continuations. Keep them as research directions with executable counterexamples. Do not infer a complete type theory from a few typed records. The expression language needs to serve real composition across surfaces and places before type machinery becomes a new product gate.

### D25 — Natural metaphors are guides, not premises

Cells, membranes, receptors, catalysts, impulses, the arrow at rest, forests, astronomy, glaciers, and seed crystals helped articulate boundaries, latent possibilities, and evidence. Preserve their explanatory value. No requirement depends on a claim about quantum observers creating reality, biology proving a runtime rule, or the absence of an observer preventing an actual event.

## How to change a decision

Create a short amendment naming the decision ID, concrete pressure/counterexample, alternatives, chosen revision, impact on tests/data/migration, and evidence of review. Mark supersession instead of erasing the reason the old decision existed. A fresh session should inherit judgment, not be imprisoned by slogans.
