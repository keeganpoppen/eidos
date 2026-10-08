# Eidos Core: language-nucleus experiment

This document freezes the current language hypothesis long enough to test it.
It does **not** replace the existing v0 authority runtime in
[`SEMANTICS.md`](SEMANTICS.md). The runtime began with the useful vocabulary
`Value / Name / Frame / Socket / Protocol / Match`; this experiment asks which
of those belong to the language itself and which are derived machine artifacts.

The current answer is:

> **Eidos partially realizes persistent Values under situated Role Bindings. A
> Name says which thing; a Socket is a named, authority-bearing relational
> continuation. When local realization cannot determine the next state alone,
> it suspends at `perform`. A Reaction may later supply a result and successor
> Socket, allowing realization to continue.**

The executable experiment lives in `src/eidos/core.py`.

## The three axes

### 1. Form

A **Value** is immutable inspectable form. Ordinary data, code, residual
continuations, binding environments, resolvers, and semantic descriptions can
all be represented as Values.

This does not mean they are semantically interchangeable. It means the
metalevel can move into the value level: Values can be named, inspected,
content-addressed, transmitted, wrapped, and partially realized.

### 2. Identity / situated interpretation

A **Name** answers *which one?* Names are nominal, permanent, and freely
copyable. Knowing a Name grants neither reachability nor authority.

A **Role** answers *what semantic position is being consumed here?* Roles are
local parameters, not global identities:

```text
executor
workspace
skills
resolver
```

A **Binding** assigns a Value to a Role for one realization:

```text
executor  -> Socket(#codex-k17)
workspace -> @workspace-42
```

This provides two important properties:

1. local names compose without collapsing into one global namespace;
2. ambient/dynamic dependencies are explicit persistent data rather than hidden
   mutable globals.

A lexical variable is an ordinary local computation name. A Role is an open
semantic parameter intended to be supplied, rebound, or left open across
realizations.

### 3. Continuation / relation

A **Socket** is a named, authority-bearing relational continuation occurrence.
It is an immutable description of one possible next interaction at one causal
instant. Its authoritative liveness is not contained in the copied Value;
Trusted Machinery maintains that separately.

The enduring relation may progress through successive Socket occurrences:

```text
K0 --Reaction R0--> K1 --Reaction R1--> K2
```

The old occurrence remains historical. The successor is explicit.

Not every transient evaluator continuation receives a Name. A continuation
becomes Socket-like when it survives to a relational causal frontier and its
advancement matters independently.

## Realization

The central evaluator operation is:

```text
realize(value, bindings)
```

Praxis specializes and evaluates as far as it can using only the local Value,
lexical environment, and Role Bindings.

The core experiment has three observable outcomes:

```text
Done(value)

Open(role, residual)

Suspended(socket, operation, argument, continuation)
```

`Open` means a Role remains unbound. Supplying it continues the same explicit
residual computation.

`Suspended` means realization reached a relational boundary. It is the value
form of:

```text
perform socket.operation(argument)
```

The continuation is serializable data, not a hidden Python closure.

## Reaction and explicit successor authority

A **Reaction** is a causal occurrence supplied from outside Praxis:

```text
Reaction {
    consumed  = Socket(#k0)
    successor = Socket(#k1)
    value     = result
}
```

Praxis verifies only that the Reaction discharges the Socket on which the local
computation suspended. It does not infer protocol legality or mint successor
authority.

The resumed program receives both:

```text
result
successor_socket
```

and must explicitly decide what the successor means locally. For example, it
may bind the `executor` Role to the successor for a nested realization.

This replaces the current runtime prototype's `_replace_name()` mechanism,
which recursively searches captured JSON for an old socket name and replaces
it with the successor. Successor authority should be language-visible, not
smuggled in as ambient mutation.

## Why this is not merely algebraic effects

`perform` resembles the request node of a free effect representation. That is a
useful implementation observation, not the organizing idea of Eidos.

The distinctive operation is situated partial realization:

```text
(code/value, persistent role bindings)
    -> more specialized value
    -> perhaps an open residual
    -> perhaps a relational suspension
```

An Eidos residual should be inspectable and transformable. One should be able
to rebind an open Role, substitute a resolver, pin or replace a Socket, transmit
the partially realized residue, and continue under another situated
interpretation.

Explicit effect-handler syntax may become useful. It is not assumed to be
primitive. The earlier `refer -> wrap -> rebind` pattern may express much of
handler composition through ordinary Values and realization.

## What is derived

The following concepts remain important without being primitive language
forms.

### Frame

A Frame is a persistent snapshot or causal cut of an evaluator configuration:
Bindings, runnable residues, and suspended interactions. Frames are excellent
persistence and debugger objects. The language need not be fundamentally
Frame-shaped.

### Protocol

A Protocol describes or proves possible Socket evolution. Endpoint automata,
session types, choreographies, structural interfaces, and dependent contracts
may all compile to whatever evidence the authority substrate ultimately needs.

### Match

A binary send/receive Match is one kind of Reaction. Reaction is the more
general causal idea: suspended relational continuations jointly advance and
produce successor continuations.

### Nema

A nema is a **self-realizing process**. Its own represented state participates
in producing the next realization of that same process. Trusted Machinery does
not need a `Nema` class, and Eidos does not need a `nema` keyword for the pattern
to emerge.

### Surface

A Surface is a realized presentation of Values together with the continuations
available through that presentation. Terminal, web, filesystem-like, and Codex
surfaces can project the same semantic substrate differently.

## Trusted Machinery™

Trusted Machinery is not an oracle for reality and should not become the
language's protocol interpreter. It is the substrate whose bookkeeping the
system accepts as authoritative for a deliberately narrow set of machine facts:

- fresh identity allocation;
- current linear authority disposition;
- atomic durable publication;
- consumption/transfer of authority without duplication;
- durable causal occurrences;
- crash-safe retry against stale state.

The unresolved boundary question is:

> What minimum authorization or witness must accompany a proposed Reaction so
> Trusted Machinery can atomically establish it without itself understanding
> the rich protocol language?

The core experiment does not answer that question. It keeps Reaction outside
Praxis so the boundary remains visible.

## What the executable experiment demonstrates

`src/eidos/core.py` currently demonstrates:

1. Names and Roles are distinct value forms.
2. Bindings are persistent and scoped; rebinding leaves the old environment
   intact.
3. An unbound Role produces an explicit resumable `Open` residual.
4. `perform` produces a serializable `Suspended` continuation.
5. Reaction supplies result and successor Socket explicitly.
6. Eidos code—not Praxis magic—chooses whether to rebind the successor.
7. An old program can be re-realized with a mock Socket to produce a distinct
   situated suspension while sharing the same code residue.
8. The primordial pure operators are closed and explicit; there is no arbitrary
   registered Python callable hidden inside the semantics.

The experiment deliberately does **not** yet provide:

- lambdas or a source parser;
- local handlers/wrappers;
- multiple simultaneous residual fibers;
- Trusted-Machinery integration;
- static linear or session typing;
- a general namespace/ref language;
- fresh Name generation from inside Praxis;
- a proof that Frame and Protocol can remain derived at every layer.

## Next pressure tests

The next useful tests should be semantic, not ornamental:

1. Express a local wrapper that can observe, transform, answer, or forward a
   `perform` without privileged host callbacks.
2. Represent multiple open Roles and independently reducible residual branches
   without forcing a single first-missing-role suspension.
3. Compile the existing binary protocol runtime into explicit Reaction values
   consumed by Eidos Core.
4. Map one Codex app-server boundary to a Socket suspension and resume it with an
   explicit successor continuation—while preserving opaque native state where
   it is genuinely opaque.
5. Determine the smallest Reaction witness Trusted Machinery must validate.

The target remains practical:

> **The calculus should sharpen the recorder/controller, not postpone it.**

A useful debugger picture survives all of these demotions:

> A persistent cut records local organization. Sockets are the continuation
> edges crossing its membrane. Reactions move the cut.
