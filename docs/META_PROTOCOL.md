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

## What remains special

`MetaProtocolDriver` still has two adapter branches:

    Elaborate -> admit_cut_elaboration
    Actualize -> actualize_observed

These are implementation bridges into the current Trusted Machinery experiment.

They are no longer:

- Eidos syntax primitives;
- special authority species;
- special Praxis continuation forms.

So the remaining privilege is narrow and mechanical.

## Next collapse

The next serious pressure test is to replace those two driver branches with one generic Trusted Machinery operation of roughly this shape:

    commit occurrence(
        consumed live capabilities,
        established capability templates,
        causal record / proof
    )

Then Elaborate and Actualize would differ only in the protocol-described occurrence they ask that substrate to commit.

If that survives, Trusted Machinery approaches the role we have repeatedly wanted for it:

> **an atomic commit engine for occurrences over live linear authority.**

At that point Actualizer | Elaborator is simply an Eidos meta-protocol realized over the same causal substrate as ordinary application protocols.