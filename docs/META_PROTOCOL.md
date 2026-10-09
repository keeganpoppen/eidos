# Elaborate / Actualize as an Eidos meta-protocol

This experiment moves the Actualizer | Elaborator cycle onto the ordinary Eidos `perform` boundary.

> **Elaborate and Actualize are now ordinary Socket operations over ordinary projection authority.**

The implementation lives in `src/eidos/meta_protocol.py`.

## Surface

An Elaborator role projection is surfaced as:

    Socket(Name(<projection-name>))

Eidos code may perform:

    perform elaborator.Elaborate {
        protocol_cid,
        cuts,
        authorities,
        knowledge,
        actualizer
    }

Praxis does nothing special for this operation. It realizes locally until the ordinary terminal Socket and returns `Suspended`.

The meta-protocol driver turns that suspension into the already-tested observer-cut elaboration transition and returns an authoritative `Reaction` to Praxis.

The result contains ordinary Eidos Values naming:

- the meta occurrence corresponding to the admitted elaboration;
- the proof/provenance identity;
- derived possibilities;
- one ordinary Actualizer Socket for each possibility.

Actualization is symmetric:

    perform actualizer.Actualize {
        possibility,
        observation
    }

Again Praxis merely suspends on the Socket. The driver commits the occurrence and resumes Praxis with:

- the application-world Occurrence;
- successor participant Sockets;
- successor observer cuts;
- successor Elaborator Sockets.

## Multi-Socket Reaction

Joint elaboration exposed an old lie in Eidos Core: `Reaction` assumed exactly one Socket was consumed.

That is no longer true.

`Reaction.consumed` may now contain several Sockets, and Praxis resumes a suspension when its target Socket is among the capabilities consumed by the occurrence.

This lets a joint Elaborate operation consume, for example:

    Elaborator(C1) + Elaborator(C2)

as one causal meta occurrence.

The same structure applies to Actualize:

    Actualizer(R)
    + participant Socket A
    + participant Socket B
    -> Occurrence R

Core no longer has to pretend that the Actualizer Socket was the only causal input.

## Placement is not semantics

The holder of an Elaborator projection may be realized by:

- the current model;
- a local subagent;
- a remote/virtual subagent;
- another process reached through exec/RPC;
- a human;
- a later implementation we have not imagined.

That changes placement and implementation of the role, not the Eidos protocol.

Delegating an Elaborator projection changes who may interpret the same cut without changing the cut or its world authority.

## Understanding

`CutElaboration` carries contextual knowledge/model references as provenance.

Thus the semantic shape is approximately:

    Elaborate(
        observer-relative cuts,
        models / contextual knowledge,
        attention / compute,
    )
    -> structured adjacent possibility

Knowledge can therefore affect elaboration without being conflated with authority.

The current executable protocol keeps inference deliberately simple, but the trust boundary is already correct:

> **epistemic enrichment changes the derivation; only live capabilities authorize causal change.**

## Generic authority commit

That collapse is now implemented.

Trusted Machinery exposes one generic projection-occurrence primitive:

    commit_projection_occurrence(
        kind,
        consumes,
        establishes,
        fact
    )

Its semantics are intentionally narrow:

1. at least one live projection capability must be consumed;
2. the same capability cannot be consumed twice;
3. all consumed capabilities must belong to one authority-local instance;
4. every consumed projection becomes spent atomically;
5. only the explicitly supplied successor projection templates are minted;
6. the occurrence, inputs, outputs, and opaque causal fact are persisted together.

The primitive knows nothing about cuts, observers, possibilities, protocols,
Elaborators, or Actualizers.

Both semantic adapters now use this same primitive inside their transactions:

    Elaborate
        semantic derivation / provenance
        -> generic authority occurrence
            consumes Elaborator projections
            establishes Actualizer projections

    Actualize
        selected application possibility / observation
        -> generic authority occurrence
            consumes Actualizer + participant projections
            establishes participant successors + Elaborator projections

The authoritative occurrence Praxis receives is the same generic occurrence
recorded by this substrate.

## What remains special

`MetaProtocolDriver` still has two semantic adapter branches because the two
operations do different semantic preparation:

- Elaborate computes a possibility-space from cuts, models, and protocol rules;
- Actualize interprets one already-derived possibility and updates observer-cut
  bookkeeping around its occurrence.

But neither branch implements its own authority transition anymore.

The remaining specialness is therefore above the Trusted Machinery nucleus:
semantic derivation and representation, not authority mechanics.

Trusted Machinery has reached the role we repeatedly wanted for it:

> **an atomic commit engine for occurrences over live linear authority.**

The next pressure point is whether the semantic bookkeeping now stored in
specialized tables can itself migrate upward into ordinary Eidos Values and
protocol code, leaving the substrate with little more than names, linear
projection disposition, and generic occurrence commit.
