# Semantic contract: the distinctions worth carrying forward

**Status:** endorsed direction plus explicit open design obligations. Existing Python classes are executable experiments, not a frozen language standard. See [DECISIONS](../roadmap/DECISIONS.md) for the history and [STATE](../roadmap/STATE.md) for implementation limits.

## S1. A language of situated, persistent computation

The desired expression language spans descriptions of work, context, process, and presentation. It can be partly interpreted locally, leave unresolved roles or external interactions explicit, and pass that residue elsewhere without flattening meaning into an opaque prompt.

Its important seam is:

```text
immutable description + lexical environment + situated bindings
    -> local realization / partial evaluation
    -> value, unresolved interpretation, or suspended external interaction
    -> admitted occurrence
    -> successor local realization
```

Not every step must execute in the same language. Eidos can describe the boundary of a native Codex computation whose internals remain opaque. We own the local evaluator and representation, not the provider's hidden continuation.

A serialized residual computation needs code identity, lexical data, binding provenance, expected protocol position, and a realization/version contract. Arbitrary live Python stacks, OS handles, native Codex internal stacks, and authority are not magically made serializable by putting their names in a record.

## S2. Value, Name, reference, address, binding, authority

A **Value** is immutable semantic content. Content identity enables deduplication and sharing. Equal content may participate in distinct causal histories.

A **Name** is durable identity. A fresh name must be reserved with the persistence guarantee the computation relies on *before* reasoning or external publication depends on its uniqueness. Deterministic names still need a persisted namespace/counter/seed; deterministic spelling does not remove the allocation obligation.

A **reference** is a description for denoting or locating something. Distinguish inline value, content reference, and entity/name reference where their behavior differs. A name can remain the same as placement changes; a content reference identifies the old content. Neither grants access by default.

An **address/path** is a route to interpretation in a context. Identity is not a filesystem path, subdomain, array position, or current socket address. A resolver can itself be a bound, inspectable interpreter. Pure local resolution is not a kernel-wide networking effect; a resolution that must ask another world crosses an ordinary interaction boundary.

A **Role** is the namespaced semantic position a piece of behavior was written to consume. A **Binding** connects that role to a situated value/reference. A binding may itself need a Name, independently of its role, target, and location. Preserve the difference between updating a binding, renaming an address, and replacing its referent.

A **capability** is live authority to participate, not merely a copyable descriptive object. The intended Socket is an authorized local projection of a named session relation, carrying its current continuation. Whether implementation uses opaque handles, authenticated domain-local references, or another mechanism is a realization choice. Publicly readable identifiers plus self-asserted holder strings do not implement unforgeability.

## S3. Lexical capture is not situated binding

Closures capture the lexical values needed by code. Roles stay open to the realization unless deliberately closed by a value-level operation. Reusing the same immutable closure under another resolver, workspace, model, attention budget, or executor should not require modifying its code identity.

This addresses both namespace collapse and the dynamic-variable problem: caller, wrapper, callee, and resumed computation need explicit rules for which environment supplies each role. Do not let ambient process globals silently decide. A closure/delegation/handoff test must distinguish captured lexical values, late-bound roles, and intentionally snapshotted roles. This is a semantic issue, not just dependency-injection syntax.

Binding changes construct a new Value; that construction is not automatically a world effect. Admitting that value as a live process's successor state is a separate causal operation.

## S4. Derive objects and handlers where possible

Objects, facets, wrappers, method tables, and local handler composition have been demonstrated as library conventions over Records, Closures, lookup, Apply, and terminal `perform`. Their meaning lives in inspectable Values, not a privileged host callback registry inside the evaluator.

The productive composition pattern is **refer → wrap → rebind**. An audit wrapper can transform inputs/outputs around a sandbox wrapper around a terminal native endpoint. Ordinary computation reduces through the wrappers until a terminal Socket suspends; after the occurrence, ordinary computation reconstructs successor wrappers around successor authority.

This retains the desired Smalltalk/metaobject flavor without making every concept primitive. Algebraic effects explain an important part of the boundary, but “everything is just effects” omits persistent identity, situated interpretation, resumable state, addressable history, and presentation. Conversely, adding special effect-handler syntax is not justified solely by analogy. Test the composition you need.

## S5. Frames, cuts, relations, and occurrences

A **frame/cut** is a reified view of a causal situation across relevant continuations. It need not be a primitive in the language or an absolute global state. Frame-content identity and causal occurrence identity must remain separate: two histories can yield equal semantic content without being the same event.

A Socket can be understood as the live local continuation at a relational boundary. Successive Socket occurrences account for progress; a static snapshot does not imply a static process. “Socket = continuation” is an illuminating correspondence, not permission to confuse a whole participant's computation, its protocol endpoint, and every capability it holds.

A **Reaction** establishes a relation among suspended computations and yields successor states. It may consume several complementary projections; it is not intrinsically unary or requester/responder-shaped. A **committed occurrence** is the durable causal fact, distinct from a candidate match, an enabled possibility, the matcher algorithm, or a downstream notification.

Local atomicity means a domain admits the relevant consumption, successor authority, and occurrence together or not at all. It does not mean distant observers resume simultaneously. Notification, incorporation into a new local cut, and outward effects have their own causal histories.

## S6. Protocols describe possibility; they are not necessarily kernel types

A protocol is an intensional description of roles and possible interactions. A session instance is situated relational history under such a description. A realized trace is one actual path; it is not interchangeable with the general protocol. Choreography can describe global coordination, but a trace should not be called the only meaning of choreography. Preserve the distinction rather than litigating borrowed terminology.

Common instantiation/projection explains complementarity: participating endpoints are related, not arbitrary unrelated things that accidentally have equal tags. Where peers compose previously independent local protocols, compatibility and admission need an explicit contract; shared names or a common hash are not proofs of compatibility.

Some protocols have constitutive witness/observer roles. An ambient auditor need not participate in an event merely because it later cares about it. If observation is required for admission, give it a real role/capability; do not make all logging a global barrier.

## S7. Actualizer | Elaborator

An **Elaborator** interprets a situated causal world and produces structured possibilities. An **Actualizer** participates in admitting one possibility as an occurrence. These are roles, not singleton services or ontologically special species.

```text
Cut(s) + Knowledge + Models + Attention
    -- Elaborator --> possibilities with inspectable derivations
    -- Actualizer + required live authority --> occurrence
    --> successor Cut(s), bindings, and continuations
```

Elaboration and actualization differ semantically, not mechanically: both can cross ordinary Socket protocols and commit ordinary local occurrences when they change admitted state. Purely thinking about an old cut is not itself an authority-consuming action. Independent retrospective interpretations should not need exclusive possession of the historical world.

Joint elaboration can relate two cuts in a way neither observer can alone. Models can be declarative rules, closures, delegated executors, or persistent processes that ask questions, wait, inspect, consult, acquire evidence, and hand off. Attention affects what is explored and at what cost. More knowledge may justify new conclusions; it does not manufacture authority over a newly understood entity.

## S8. Trusted Machinery and the unresolved admission obligation

The intended TM nucleus is **an atomic commit engine for occurrences over live linear authority**. It supplies durable names, local single-consumption, successor allocation, provenance, and replay of command results. Genesis is an explicitly admitted act, not an ordinary reaction from nothing.

But factoring semantic checking out of TM does not make it unnecessary. There must be a protected path by which a semantic possibility and its outputs become admitted. A trusted interpreter, constrained transition capability, or checkable witness may implement that path. The commitment is narrow mechanism plus explicit trust—not arbitrary caller-supplied output grants with a decorative proof digest.

**Conservation means conservation of authorized transitions, not token count.** One live low-privilege input exchanged for arbitrary high-privilege outputs is still escalation. A capability identifies what transformation is admitted, not merely something available to burn. The current trusted-host prototype leaves this obligation above its generic API; do not expose that API as an untrusted network endpoint.

Likewise, a hash establishes content identity, not that a conclusion follows from premises, that a caller holds authority, or that a remote domain agreed. Linear clocks, causal DAGs, routing tags, and logs do not independently prevent double spending.

## S9. Pending, delegation, discovery, and handoff

A pending continuation is not failure and not an event invented to satisfy a polling loop. The source may defer, refuse, or offer evidence in its own history; the receiver incorporates a decision through a separate local occurrence. Absence of an answer is not proof of refusal or non-occurrence. Cancellation, timeout, terminal refusal, transport failure, and unknown external outcome need distinct values.

A disclosed Cut is evidence, not transfer of its participant authority. Its source occurrence and recipient incorporation are causally linked; there is no assumed atomic commit across domains. A useful Cut may be discovered through an open question without its Name being known initially.

Handoff transfers one live local projection/continuation to a new admitted holder. The old holder cannot advance the successor, while copied checkpoints remain inspectable. Resumption after migration must preserve the code/Context actually used, relevant binding choices, pending questions, and effect uncertainty. Naming the same holder on another machine is not authentication.

## S10. Semantics across surfaces

A surface, prompt, context packet, terminal view, and agent-facing interaction can be different lowerings of the same meaningful interaction description. Preserve identity, source links, proposed affordances, selected focus, and authority preconditions through those lowerings. Pixel or widget equality is not required; semantic continuity is.

A future language must express both “what is this?” and “what can happen here?” without requiring a special primitive for every UI component. [INTERACTION](INTERACTION.md) specifies the experiential consequences.

## The test of a fundamental concept

Keep a concept in the nucleus only when removing it loses an invariant that cannot be derived cleanly. Keep a derived convention when it gives users or agents a meaningful new composition. Preserve uncertainty when a claim has only passed a narrow test. No analogy, theorem-sounding sentence, or green suite closes obligations that the suite does not exercise.
