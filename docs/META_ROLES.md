# Actualizer | Elaborator as ordinary protocol roles

This experiment removes the remaining special authority objects from observer-relative elaboration/actualization.

> **Elaborator and Actualizer are roles, and authority to occupy those roles is represented by ordinary live projection capabilities.**

The implementation uses the same `projections` table and the same live/spent discipline as ordinary participant authority.

## The loop

A newly observed cut carries an ordinary projection:

    role   = Elaborator
    state  = cut:<cut-name>
    holder = whoever currently occupies the Elaborator role

That projection may be delegated like any other live projection.

Successful elaboration consumes the participating Elaborator projections and, for each derived possibility, creates:

    role   = Actualizer
    state  = possibility:<possibility-name>
    holder = the Actualizer role binding chosen by that elaboration

Actualization consumes both:

- the ordinary participant projections required by the Reaction;
- the corresponding Actualizer projection.

It then produces the participant successors and, for each successor observer cut, a new ordinary Elaborator projection.

So the authority cycle is now:

    Elaborator projection
        | elaborate
        v
    Actualizer projection
        | actualize
        v
    successor Elaborator projection
        | ...

No bespoke elaboration-token kind is required in this observer-cut experiment.

## Delegation

Because meta-role authority is ordinary projection authority, it can move without changing the cut itself.

An observer may start with:

    Cut C
    Elaborator projection held by O

and delegate only the Elaborator projection:

    O -> specialist -> joint elaborator -> agent

while `C` and its world projections remain identical.

This gives a concrete interpretation of choosing how deeply to understand a situation: the observer can keep elaborating locally, or hand the same causal evidence to another role occupant with different models/context.

## Epistemic context is not authority

`CutElaboration` now records a set of knowledge/model references used in the derivation.

For example:

    shallow knowledge:
        night-sky:raw-observation

    deeper knowledge:
        night-sky:raw-observation
        astronomy:model
        catalog:stellar-objects

These inputs are part of the elaboration proof/provenance. They may eventually change which semantic possibilities a richer Elaborator can derive.

They do **not** create or duplicate live projection authority.

The current pressure test intentionally keeps the protocol derivation itself fixed, so richer knowledge changes the proof identity/provenance while leaving the same world projections and Reaction set. The next language-level model can let knowledge rules derive additional predicates without changing this authority boundary.

This encodes the principle:

> **Understanding changes what can be concluded from an observation; it does not by itself grant power over the observed world.**

## Joint elaboration

Joint elaboration becomes especially natural under this model.

Suppose:

    O1 owns Cut C1 and its Elaborator projection E1
    O2 owns Cut C2 and its Elaborator projection E2

Neither cut alone can derive some cross-cut Reaction.

O1 and O2 may delegate E1 and E2 to a joint Elaborator. The joint Elaborator now has:

- both observer-relative causal cuts;
- whatever contextual models it chooses to bring to bear;
- authority to elaborate from both cuts exactly once.

If it derives possibility R, admission consumes E1 and E2 and creates an Actualizer projection A_R.

Actualization of R consumes A_R plus the participant projection capabilities required by R.

The shared occurrence then extends each observer's causal history separately.

## Why this is closer to a meta-protocol

The distinction between ordinary and meta authority has narrowed substantially.

Participant:

    live projection -> Reaction -> successor projection

Meta:

    Elaborator projection -> elaboration -> Actualizer projection
    Actualizer projection -> occurrence -> Elaborator projection

Both are now expressed as named, role-bearing, linear projection authority.

Trusted Machinery still has dedicated host API methods for `admit_cut_elaboration` and `actualize_observed`, so the collapse is not complete. But the *authority objects* crossing those calls are no longer privileged token species.

## Next pressure point

The remaining specialness is operational rather than ontological:

> `admit_cut_elaboration` and `actualize_observed` are still hard-coded Trusted Machinery verbs.

The next experiment should represent those verbs themselves as ordinary Socket operations in an Eidos meta-protocol:

    Elaborator.perform(Elaborate(cuts, knowledge))
        -> Actualizer projection(s)

    Actualizer.perform(Actualize(possibility, observation))
        -> Occurrence + successor Elaborator projections

If that works, Trusted Machinery can approach a single generic operation:

> **atomically commit an occurrence over current linear capabilities.**

At that point Actualizer | Elaborator is not architecture surrounding Eidos. It is an Eidos protocol.