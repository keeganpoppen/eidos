# Semantic objects as ordinary named Eidos Values

This checkpoint moves the observer/occurrence ontology out of Trusted Machinery's specialized tables and into ordinary immutable Eidos Core Values.

> **Names provide addressability. Values provide semantics. Trusted Machinery provides authority facts and atomic occurrence commit.**

## Generic persistence

Trusted Machinery now has a schema-agnostic immutable Value store:

    put_eidos_value(value) -> content id
    bind_eidos_value(name, value)
    named_eidos_value(name) -> value

The store uses the existing Eidos Core canonical serialization for `RecordValue`, `Name`, `Socket`, closures, continuations, and other Core Values.

Trusted Machinery does not inspect the schema of these Values.

A permanent Name is immutably bound to one content-addressed Value.

## Semantic library conventions

`src/eidos/semantic_values.py` currently provides library constructors for:

- Cut
- ProjectionTemplate
- Elaboration
- Possibility
- Occurrence

These are ordinary `RecordValue`s distinguished only by a conventional `$kind` field.

They are not new Core dataclasses or Trusted Machinery entities.

## Addressable provenance chain

The observer-relative path now produces an addressable graph:

    Cut C0
       |
       v
    Elaboration E
       |
       v
    Possibility P
       |
       v
    Occurrence O
       |
       v
    Cut C1

with additional Name references to:

- participant projection capabilities;
- Actualizer / Elaborator projections;
- multiple cause cuts for joint elaboration/actualization;
- multiple successor cuts;
- the protocol commitment;
- proof/model provenance.

A Possibility explicitly names the Elaboration occurrence that produced it.

An Occurrence explicitly names its Possibility, cause cuts, successor cuts, consumed capabilities, and established capabilities.

## Values are now canonical semantics

The migration is no longer duplicated persistence.

The observer-relative execution path has **no observer-specific ontology tables**.
In particular, Trusted Machinery no longer has tables for:

- causal cuts;
- cut membership;
- elaboration admissions;
- observer possibilities or their input/output mirrors;
- observer occurrences or their cut/input/output mirrors.

The meta-protocol reconstructs a Cut from the ordinary Value bound to the Cut
Name. Admission validates that Value against live Elaborator capability.
Actualization obtains the Reaction, required projections, output templates,
cause cuts, and Actualizer from the named Possibility Value.

Lifecycle state is derived rather than stored:

    Cut:
        live Elaborator projection -> open
        spent Elaborator projection -> elaborated
        named Occurrence cites it as a cause -> historical

    Possibility:
        live Actualizer + live inputs -> open
        Actualizer consumed by matching Actualize -> occurred
        Actualizer consumed by Preclude, or stale inputs -> precluded

Competing possibilities are precluded by an ordinary generic authority
occurrence that consumes the competing Actualizer projection. There is no
special preclusion table or flag that carries causal authority.

The public semantic APIs are therefore projections over:

    immutable named Eidos Values
    + live/spent projection facts
    + generic authority-occurrence history

The older lockstep/frontier and v0 Match experiments still retain their own
specialized tables alongside this path. They are historical experiments, not
dependencies of the observer-relative semantics.

## Stale knowledge remains knowledge

A subtle correction fell out of this migration.

A Cut Value continues to reference a projection even if that projection's live authority was subsequently spent.

That is correct:

> **epistemic history is not erased when authority advances.**

An observer may still reason from an old cut.

If it derives an old possibility and later tries to actualize it, Trusted Machinery rejects the occurrence because the required projection authority is no longer live.

Thus:

    semantic visibility != current authority

which is exactly the distinction the observer-relative model needs.

## Generic semantic lenses

`src/eidos/lenses.py` adds the first schema-agnostic lens over this world.

`referenced_names(value)` finds permanent Names structurally embedded anywhere in an Eidos Value.

`walk_named_values(roots, depth=N)` then expands the addressable neighborhood by resolving those Names to Values.

Unbound Names are retained as edges but are not errors.

This matters because a semantic Value may reference a live capability Name without that capability itself needing to denote a semantic Value.

## Progressive understanding

The depth walk makes the earlier intuition executable.

Starting from an Occurrence:

    depth 0:
        the Occurrence itself

    depth 1:
        its Possibility
        its cause Cut(s)
        its successor Cut(s)

    depth 2:
        the Elaboration that produced the Possibility
        further addressable context behind those Cuts

and so on.

No special Occurrence traversal algorithm is needed. The graph is a consequence of addressable Names embedded in ordinary Values.

This gives a primitive form of:

    understand(
        observations / cuts,
        contextual models,
        attention / traversal depth
    )

without conflating deeper understanding with greater causal authority.

## What remains in Trusted Machinery

For the observer-relative path, the durable substrate has collapsed to a much
smaller set of generic machinery:

- permanent Names;
- content-addressed immutable Eidos Values and immutable Name bindings;
- projection capabilities with authority-local instance, role/state/holder, and
  live/spent disposition;
- generic authority occurrences with consumed and established projections;
- command idempotency and the generic event log.

Cut, Elaboration, Possibility, Occurrence, observer-relative history, and
semantic lenses are all library-level Value conventions above that substrate.

This is now tested structurally: the test suite asserts that the old
observer-specific tables do not exist at all while the complete
Cut -> Elaboration -> Possibility -> Occurrence -> Cut lifecycle continues to
work.

## Stale knowledge and counterfactual elaboration

Historical semantic Cuts remain inspectable even after their projection
authority is spent.

A pure Elaborator may still ask:

    "what possibilities were visible from this old cut,
     perhaps using a better model I have now?"

and derive those possibilities retrospectively.

What it cannot do is turn that retrospective derivation into present authority:
the original Elaborator or Actualizer projections are spent, and Trusted
Machinery rejects their reuse.

That gives the desired asymmetry:

> **later understanding may improve the model of an old world; it does not
> resurrect the authority that world once contained.**

## Next pressure point

The semantic ontology itself is no longer the obvious target.

The remaining candidate reductions are lower-level:

1. decide whether an authority-local instance needs any semantic payload at all,
   or whether it should be only an identity/domain boundary whose description
   is another named Value;
2. decide how much of a projection's role/state description belongs in the
   generic authority substrate versus an ordinary capability Value;
3. replace linear scans over named Values with derived indexes/lenses that are
   explicitly disposable and rebuildable.

Those are optimization/substrate questions. The conceptual result of this
experiment is already sharper:

> **semantic structure lives in Values; causal power lives in capabilities;
> actual history lives in generic occurrences.**

