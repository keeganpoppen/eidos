# From possibility to occurrence

This experiment records the current reaction-side hypothesis in executable form.

> **Possibility is semantic. Occurrence is causal. Commit is mechanical.**

It is intentionally narrower than a complete protocol language or distributed consensus design.

## The split

The semantic layer describes a current protocol frontier as participant-relative projection templates plus a finite set of possible next Reactions. For each Reaction it records the exact current projections it would consume and the exact successor projection templates it would establish if it occurred.

The semantic elaborator produces an InstanceBlueprint.

Trusted Machinery then installs that blueprint mechanically. At installation time it assigns durable Names to the protocol instance, current live projection capabilities, and latent Reaction possibilities.

Successor projection Names do not exist yet. Their templates do.

Thus:

    possible successor authority != live successor authority

The former is latent in the possibility space. The latter exists only after a particular Reaction becomes an occurrence.

## A/B/O branching example

The executable test protocol begins with:

    A : ready
    B : ready
    O : watching

and two latent Reaction possibilities:

    YES:
        consumes A + B + O
        establishes A:after-yes, B:after-yes, O:recorded-yes

    NO:
        consumes A + B + O
        establishes A:after-no, B:after-no, O:recorded-no

Before observation, YES and NO are both possible and neither has occurred.

The observer eventually recognizes a condition and selects the corresponding already-elaborated possibility. Trusted Machinery does not inspect what that condition means.

It atomically:

1. verifies that the selected possibility is still open;
2. verifies that its predeclared input projections are still live;
3. consumes those projection capabilities;
4. records one durable Occurrence;
5. materializes only the successor templates already attached to that possibility;
6. precludes competing possibilities that depended on any consumed projection.

The caller cannot supply an arbitrary successor set to commit_occurrence.

## Possibility versus occurrence

A Reaction possibility is intensional: it belongs to the protocol's current space of possible evolution.

An Occurrence is extensional: it is the durable causal fact that one such possibility became actual for particular current projections and a particular observation record.

This lets us stop using one overloaded word such as Match to mean compatibility, attempted rendezvous, matcher result, and committed historical event.

## Projection capability

For this experiment, the occurrence subsystem calls the current participant frontier objects projections rather than reusing the existing runtime Socket table.

Conceptually they test the same claim:

> **A Socket is a live capability corresponding to one participant's current projection at the protocol frontier.**

The existing v0 Socket/Protocol/Match runtime remains intact while this experiment tests the cleaner factoring.

## Trusted Machinery™

The important API is deliberately boring:

    install_occurrence_blueprint(blueprint)
    commit_occurrence(possibility, observation)

The install step is the trust boundary at which an already-elaborated semantic possibility space becomes authoritative machine state.

The commit step knows no protocol rules. It sees only preinstalled causal structure and current linear authority.

Its job is best described as:

> **atomic commit of occurrence**

That includes single-consumption, fresh output Names, durable history, and crash-safe idempotence.

## Observer semantics

The observer in the A/B/O test is constitutive because its current projection is one of the capabilities consumed by both candidate Reactions.

The observation payload itself is opaque to Trusted Machinery.

Responsibility is divided cleanly:

- the protocol says that an observation role participates;
- the observer decides which condition it has recognized;
- semantic elaboration maps that condition to one already-possible Reaction;
- Trusted Machinery atomically commits the selected occurrence.

Ambient observers remain separate: they may inspect the durable occurrence later without being one of its consumed projections.

## Competing branches

YES and NO consume the same current frontier. Once YES occurs:

    A0, B0, O0 -> spent
    YES -> occurred
    NO  -> precluded

TM does not need to know that YES and NO are logical opposites. NO becomes impossible mechanically because the authority it would require has already been consumed.

## Crash semantics

An Occurrence is durable before any participant must locally incorporate it.

After restart the system can still observe the occurrence record, its observation payload, the spent historical input projections, and the live successor projections.

This preserves the earlier distinction between:

    the Reaction happened

and:

    a participant has incorporated that fact into a later local cut

No simultaneous remote observation is assumed.

## What this does not solve

It does not yet solve recursive multi-frontier elaboration, distributed occurrence commit, cryptographic lineage proofs, Interval Tree Clock integration, ambient observer subscription, static session typing, or how an observer acquires trustworthy evidence from the external world.

The current experiment establishes only this factoring:

    Protocol semantics
        |
        v
    latent possibility space
        |
    observation selects one
        |
        v
    Trusted Machinery
    atomic commit of occurrence
        |
        v
    new live projected frontier

## Recursive elaboration

That pressure test is now implemented. See [`RECURSIVE_OCCURRENCES.md`](RECURSIVE_OCCURRENCES.md).

A committed Occurrence now exposes a successor frontier plus a distinct one-shot elaboration authority. The semantic elaborator derives the next possibility space from the protocol commitment and authoritative successor projections; Trusted Machinery admits that proof-shaped blueprint once and then returns to mechanical occurrence commit.

The current loop is:

    possibility
        -> atomic occurrence
        -> open successor frontier
        -> semantic elaboration
        -> admitted possibility
        -> ...

The next pressure point is whether the elaboration authority itself can become an ordinary Eidos capability/projection of a meta protocol, rather than remaining a privileged seam between the semantic dual and Trusted Machinery.
