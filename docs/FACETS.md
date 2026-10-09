# Facets: value-level interpretation around Sockets

This experiment answers the first pressure test from [`CORE.md`](CORE.md):

> Can an ordinary Eidos Value observe, transform, answer, or forward an
> operation without a privileged `handle` construct or a host-language callback?

The answer is **yes, provisionally**.

The executable experiment lives in [`src/eidos/facets.py`](../src/eidos/facets.py).
It extends the Eidos Core abstract machine without changing Trusted Machinery or
the existing Frame/Protocol runtime.

## The claim

`perform` does not necessarily cross the relational membrane immediately.

```text
perform target.Op(argument)
```

first realizes `target` locally.  A terminal `Socket` suspends.  A `Facet`
interprets the operation with ordinary Eidos code.

A Facet is an immutable Value:

```text
Facet {
    inner
    clauses
    state
    captured lexical environment
}
```

Each clause names one operation and contains an Eidos term.  The term receives
explicit lexical parameters for:

```text
self
inner
state
argument
```

It must produce:

```text
Step {
    value
    successor
}
```

The caller receives both fields exactly as it would after a relational
Reaction.  This means local interpretation and external suspension share one
continuation shape without becoming the same causal event.

## Answer locally

A clause can answer without touching its inner target:

```text
Ping(argument) =>
    Step(
        value = "pong:" + argument,
        successor = self,
    )
```

No Socket is exposed.  Trusted Machinery is not involved.  The same Facet
remains available as the successor because the contained live authority was not
spent.

## Transform and forward

A clause can transform an operation, forward it, transform the result, and
reconstruct itself around the successor inner authority:

```text
Turn(argument) =>
    perform inner.Turn("request:" + argument)
        as (inner_reply, inner_successor)
    in
        Step(
            value = "reply:" + inner_reply,
            successor = rewrap(
                self,
                inner = inner_successor,
                state = state + 1,
            ),
        )
```

The terminal inner Socket is the only relational suspension.

When a Reaction supplies the successor inner Socket, ordinary Eidos code uses
`Rewrap` to build the successor Facet.  Praxis does not recursively replace old
Socket names in captured state.

## Composition

Facets nest:

```text
Audit(
    Sandbox(
        CodexSocket
    )
)
```

An operation proceeds through the outer Facet, then the inner Facet, then the
terminal Socket.  One terminal suspension captures the entire local wrapper
stack as serializable continuation data.

After the Reaction:

1. the innermost clause receives the successor terminal Socket;
2. it rewraps that Socket in the successor inner Facet;
3. the outer clause receives that Facet as its successor target;
4. it rewraps again;
5. the original caller receives the reconstructed outer Facet.

So the relation evolves as:

```text
Outer0(Inner0(K0))
    --Reaction consuming K0-->
Outer1(Inner1(K1))
```

The wrappers are immutable Values.  The Socket is live relational authority.
The Reaction advances only the terminal Socket occurrence; local realization
reconstructs the surrounding semantic membrane.

## Why this is not a privileged effect-handler stack

The evaluator does know one generic rule:

```text
Perform target.Op(arg)

if target is Facet:
    realize the matching clause locally

if target is Socket:
    suspend relationally
```

But the behavior of the layer is not a Python callback or hidden runtime table.
It is Eidos data:

- operation Names;
- clause terms;
- captured lexical Values;
- immutable local state;
- explicit successor construction.

A Facet can be serialized, inspected, nested, content-addressed, transmitted,
and partially realized.  Its clause can itself remain open on Roles.  That is
the Smalltalk/metaobject strand we wanted to preserve: language machinery
migrates into inspectable Values.

An explicit `handle` syntax may still become useful.  It is no longer required
to explain local interception and composition.

## Refer, wrap, rebind

The earlier pattern is now concrete:

```text
refer
    acquire or resolve some target Value

wrap
    construct a Facet around it

rebind
    assign that Facet to a Role in a new situated environment
```

For example:

```text
executor -> CodexSocket
```

may become:

```text
executor -> Audit(Sandbox(CodexSocket))
```

without changing behavior written against the `executor` Role.

This is why Roles and Bindings remain central.  They provide stable semantic
slots through which locally reconstructed interaction surfaces can be
substituted cheaply.

## What this establishes

The tests demonstrate that:

1. a Facet can answer an operation locally without exposing a Socket;
2. a Facet can transform and forward an operation to its inner target;
3. a Reaction result can be transformed on the way back out;
4. successor Socket authority is rewrapped explicitly;
5. immutable Facet state can evolve through reconstruction;
6. nested Facets collapse into one terminal Socket suspension;
7. the complete wrapper stack round-trips as serializable data;
8. a clause may remain open on an ambient Role and continue after specialization;
9. unknown operations are not silently forwarded;
10. every clause must explicitly return both result and successor.

## What it does not establish

This is not yet a complete object or effect system.

It does not provide:

- lambdas or general user-defined functions;
- wildcard or structural operation dispatch;
- private nominal object identity;
- multiple simultaneous residual fibers;
- multi-shot resumptions;
- static authority or session typing;
- Trusted-Machinery validation of Reactions;
- a general state lens/update calculus;
- cross-process execution of Facets;
- automatic attenuation proofs for wrapped capabilities.

`Facet` may ultimately be library sugar over a more general first-class
realizer/metaobject mechanism.  The experiment intentionally chooses a concrete
shape first.

## Revised membrane picture

The result sharpens the biological metaphor:

```text
local Eidos realization
    |
    | Facet / Facet / Facet
    | locally interpretable membrane layers
    v
terminal Socket
    |
    | relational suspension
    v
Reaction
```

A Facet is membrane structure.  A Socket is the named relational continuation
crossing the membrane.  A Reaction is the lightning bolt that consumes the
current Socket occurrence and establishes its successor.

The next pressure test is no longer whether wrapping is possible.  It is:

> Can Facets become fully ordinary constructed Values—with general functions,
> structural dispatch, and explicit state lenses—without turning Praxis into a
> special-purpose object interpreter?

That is now a concrete language-design problem rather than an analogy.