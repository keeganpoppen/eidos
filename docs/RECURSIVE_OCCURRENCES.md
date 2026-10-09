# Recursive occurrence semantics

This experiment extends the first possibility/occurrence model across multiple protocol generations.

> **Elaboration proposes the next possible world; Trusted Machinery commits one occurrence within it.**

## The dual

The implementation now has two deliberately different responsibilities.

### Semantic elaborator

Given:

- an immutable recursive protocol description;
- one authoritative frontier;
- the concrete live projections at that frontier;
- the occurrence that produced it;

the elaborator derives the next set of latent Reaction possibilities.

It knows protocol semantics.

### Trusted Machinery™

TM does not interpret those rules. It owns:

- durable identities;
- linear projection disposition;
- one-shot elaboration authority;
- atomic occurrence commit;
- crash-safe causal history.

This gives a useful duality:

    elaborate: authoritative frontier -> possible next occurrences
    commit:    one admitted possibility -> authoritative occurrence

## Frontier identity is not frontier authority

A protocol frontier has a stable Name that may appear freely in historical Values.

That Name does not authorize elaboration.

When an occurrence creates a successor frontier, TM also creates a distinct opaque one-shot elaboration authority. The semantic elaborator must present that authority when admitting its proof-shaped FrontierBlueprint.

The authority is consumed by successful admission.

So:

    frontier Name        = which frontier?
    elaboration authority = may define this frontier's possibility space once

This preserves the broader Eidos rule:

> **Name identifies; capability authorizes.**

## Protocol commitment

A RecursiveProtocol has a content-derived protocol commitment.

Generation zero installs that commitment with the instance. Every later FrontierBlueprint must name exactly the same commitment.

TM still does not prove that the blueprint semantically follows from the protocol. In this experiment, possession of the one-shot elaboration authority designates the semantic dual trusted to produce that proof.

The blueprint is itself content-addressable and its proof digest is persisted with the frontier admission. That gives explicit provenance without pretending a hash proves semantics.

## Recursive flow

Generation zero:

    RecursiveProtocol
          | elaborate_genesis
          v
    initial projections + latent possibilities
          | install
          v
    frontier F0 [elaborated]

Occurrence:

    F0 + selected possibility + observation
          | atomic commit
          v
    occurrence R0
    frontier F1 [open]
    one-shot elaboration authority E1

Recursive elaboration:

    (protocol, F1 projections, R0)
          | elaborate_frontier
          v
    FrontierBlueprint B1
          | admit with E1
          v
    frontier F1 [elaborated]
    latent possibilities P1

Then the cycle repeats.

## What the tests establish

The recursive test runs a protocol through two generations:

    ready
      | yes / no
      v
    after-yes
      | ack-yes
      v
    done

After YES occurs, only ACK-YES is semantically enabled at the next frontier. RECOVER-NO exists in the immutable protocol description but is not elaborated there because its required projection states are absent.

The second occurrence creates a terminal frontier whose elaboration yields no possible Reactions.

The tests also establish:

- a blueprint naming a different protocol commitment is rejected;
- a blueprint omitting an authoritative live projection is rejected;
- the frontier Name itself cannot substitute for elaboration authority;
- elaboration authority is one-shot;
- the previous frontier becomes historical/spent when an occurrence advances it.

## A useful interpretation of authority genesis

At genesis, some act must admit the protocol description itself.

After genesis, the experiment no longer needs ambient authority to invent each next possibility space. The previous occurrence produces a successor frontier and a capability to elaborate exactly that frontier once.

That makes the semantic elaborator look like the constructive dual of TM:

- TM turns possibility into historical fact;
- the elaborator turns historical fact back into structured possibility.

Or, more suggestively:

    possibility --TM--> occurrence --elaboration--> possibility --TM--> ...

This is a feedback loop, not a one-way pipeline.

## Relation to a nema

A recursive protocol instance now has the shape of a process that repeatedly:

1. exposes a frontier of possible interaction;
2. has one possibility become an occurrence;
3. uses the new causal state to elaborate its next possible frontier.

For the identity/meta protocol, the projected object being successively elaborated can be the process's own description.

That is the first implementation-level route from the occurrence calculus back to:

> **a nema is a self-realizing process.**

Autopoiesis is no longer required as a separate mechanism; it can be a protocol whose successor frontier describes the next possible realizations of self.

## Deliberate limitation

The current frontier capability is globally linear for one protocol generation: one occurrence spends the whole frontier generation and precludes its sibling possibilities.

That is appropriate for this lockstep experiment but is not yet a general model of independent concurrent events. A future version may split frontier/elaboration authority so causally independent subfrontiers can advance without imposing a false total order.

That is now the most important caveat.

## Next pressure point

The next question is no longer whether elaboration can recurse. It can.

The next question is:

> **Can the protocol/elaboration authority itself be represented as an ordinary Eidos capability/projection, so the apparent duality between semantic elaborator and Trusted Machinery becomes another protocol rather than a privileged runtime split?**

If yes, the meta protocol really does begin to eat the architecture.