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

The migration is not only duplicated persistence.

The meta-protocol Elaborator reconstructs a Cut from the ordinary Value bound to the Cut Name.

`admit_cut_elaboration` validates protocol/projection membership from Cut Values plus live Elaborator capability.

`actualize_observed` obtains reaction identity, input projection Names, output templates, cause cuts, and Actualizer identity from the Possibility Value.

The public semantic read APIs likewise overlay runtime facts such as live/spent disposition onto semantics recovered from named Values.

The old observer-specific SQL tables remain for:

- compatibility with the earlier experiments;
- efficient lookup / reverse indexes;
- mutable runtime/index state;

but they are no longer the semantic source of truth.

One pressure test deliberately corrupts semantic-looking columns in those tables and verifies that the interpreted Cut, Possibility, and Occurrence remain unchanged because the immutable named Values still carry the meaning.

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

The current observer subsystem still writes several specialized tables, but the direction is now clear.

The irreducible substrate is converging toward:

- permanent Names;
- generic immutable Value persistence;
- live/spent projection disposition and delegation;
- generic atomic authority-occurrence commit;
- durable occurrence provenance / indexing.

Cut, Possibility, Elaboration, Occurrence, and lens semantics belong above that substrate.

## Next pressure point

The next useful deletion experiment is not to invent another abstraction.

It is to pick one specialized semantic index at a time and prove it can be rebuilt or omitted because the named Values plus generic authority history contain enough information.

The best candidates are `cut_members`, `observed_possibility_cuts`, and `observed_reaction_outputs`, because the live execution paths now recover the corresponding semantics from Values instead.
