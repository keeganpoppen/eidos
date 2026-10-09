# Observer-relative causal cuts

This pressure test replaces the idea of one global protocol frontier with observer-relative causal cuts.

> **A causal cut is not the edge of the universe. It is the edge of what a particular observer can presently make addressable within that universe.**

The implementation lives in `src/eidos/cuts.py` and the corresponding Trusted Machinery experiment.

## Cut

A cut contains:

- one observer identity;
- one protocol commitment;
- a set of concrete projection capabilities visible at that cut;
- optional ancestry to a prior cut and occurrence.

A cut is a historical/semantic object, not a global clock.

Different observers may have cuts that are disjoint, overlapping, stale with respect to one another, or later joined by a shared occurrence.

## Elaborator and Actualizer

`Elaborator` and `Actualizer` are modeled as roles attached to a derivation, not singleton daemons.

An elaboration records:

    observer cut(s)
    + protocol
    + Elaborator role
    + Actualizer role
    -> latent possibilities

The Actualizer role named by that elaboration is the role expected to commit one of those possibilities as an occurrence.

The current experiment represents role occupants by names such as `elaborator:left` or `actualizer:joint`; authority behind those role bindings is deliberately left for the next layer.

## No global generation

The central test creates two observer cuts:

    O1 sees A,B
    O2 sees C,D

with independent reactions:

    LEFT  consumes A,B
    RIGHT consumes C,D

O1 elaborates LEFT. O2 elaborates RIGHT.

Actualizing LEFT does not advance or spend O2's cut. RIGHT remains actualizable afterward.

Thus:

    LEFT || RIGHT

is represented as genuine causal independence rather than two arbitrarily ordered generations of one global frontier.

Linear projection authority still prevents contradictory reuse of A, B, C, or D.

## Joining observer worlds

After LEFT and RIGHT, each observer receives a successor cut:

    O1: A1,B1
    O2: C1,D1

Neither cut alone can elaborate a later JOIN reaction requiring B1 and D1.

A joint elaboration over both cuts can:

    O1 cut ---\
               +--- Elaborator:joint ---> JOIN
    O2 cut ---/

When JOIN actualizes, its occurrence record names both causal cuts as causes.

Trusted Machinery then creates one successor cut for each observer, and both successor cuts name the same occurrence as their immediate causal parent.

So their histories meet without collapsing into one canonical history:

    O1 history ---\
                   Occurrence JOIN
    O2 history ---/
          |                 |
          v                 v
       O1 cut'           O2 cut'

The occurrence is shared. The cuts remain observer-relative.

## The wild frontier

If a required projection is outside every cut supplied to an elaboration, that reaction is simply not derivable there.

This does not assert that the unseen entity is unreal.

It says only that the relation is not yet part of the elaborator's addressable causal world.

When another cut carrying the missing causal relation is joined, a possibility that previously could not be expressed may become derivable.

This is the computational version of the distinction:

> something can exist outside an observer's addressable causal world without yet being meaningfully assertable from that world.

## Authority

Cut identity and elaboration authority remain distinct.

    Cut Name     = which observed causal cut?
    capability   = may elaborate from this cut

An elaboration spanning several cuts requires the elaboration capability for each cut.

Projection capabilities, not cut identity, authorize the eventual occurrence itself.

Thus observer cuts constrain what can be derived while live projections constrain what can actually be consumed.

## Historical cuts can become stale

Only cuts that causally participate in an occurrence automatically receive successor cuts in this experiment.

Another observer may still retain a cut containing a projection that has since been spent globally.

That cut remains a valid historical representation of what the observer knew. Any attempt to actualize an old possibility from it fails mechanically because the underlying projection authority is no longer live.

A future `observe occurrence` / reconciliation protocol can advance such an observer ex post.

## What this supersedes

The earlier `RECURSIVE_OCCURRENCES.md` experiment used one globally linear frontier per protocol generation.

That experiment remains useful for lockstep protocols, but it is no longer the preferred general picture.

The observer-relative experiment removes the accidental total order while preserving:

- recursive elaboration;
- linear projection authority;
- durable occurrences;
- protocol commitments;
- distinct Names and capabilities.

## Next pressure point

The most interesting remaining privilege is now visible:

> **Elaborator and Actualizer are roles semantically, but their authority is still represented by special Trusted Machinery APIs/tokens.**

The next experiment should express those roles as ordinary Eidos projections/Sockets of a meta-protocol.

If successful, the architecture becomes recursively uniform:

    ordinary protocol possibility
        <-> Actualizer / Elaborator meta-protocol
        <-> identity/self-realization protocol

with Trusted Machinery reduced further toward a generic atomic authority substrate.