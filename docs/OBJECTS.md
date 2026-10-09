# Objects as a Core library

This experiment follows [`DISPATCH.md`](DISPATCH.md) and removes the remaining
structural-dispatch hook from the evaluator.

The result is stronger than the Facet experiment:

> **Local objects, wrappers, and message dispatch can be expressed as an Eidos
> Core library convention. Praxis Core does not need to know they exist.**

The implementation lives in [`src/eidos/objects.py`](../src/eidos/objects.py).

## Representation

An operation target is an ordinary `RecordValue`:

```text
{
    "$methods": {
        operation-name: Closure(...)
    },
    ... ordinary fields ...
}
```

Methods are first-class Eidos Closures.

A message send with a statically named operation compiles to ordinary Core
terms:

```text
let target = ...
let step =
    apply target.$methods[Operation] (target, argument)

let result = step.value
let next   = step.successor

...
```

There is no evaluator branch for "object", "Facet", or "$dispatch".

## Terminal endpoints

A terminal relational endpoint is also an ordinary object.

Its method eventually executes Core:

```text
perform self.$socket.Operation(argument)
```

and therefore reaches a relational `Suspended` state.

When a Reaction supplies the successor Socket, ordinary Eidos code constructs
the successor endpoint record.

This means Core needs to understand only the terminal Socket continuation. The
entire locally programmable membrane above that Socket is library structure.

## Wrapping

A forwarding wrapper is an ordinary object with fields such as:

```text
{
    "$methods": ...,
    "inner": ...,
    "state": ...
}
```

Its method can call the inner object with the same library expansion, transform
arguments/results, and construct a successor wrapper with ordinary `Record`
expressions.

Nested values such as:

```text
Audit(
    Sandbox(
        Terminal(Socket K0)
    )
)
```

therefore reduce in unmodified `PraxisCore` to exactly one terminal suspension
on `K0`.

After a Reaction establishes `K1`, ordinary local realization constructs the
successor stack around `K1`.

## Why this matters

The progression has been:

```text
privileged effect handler?
    ↓
Facet special object
    ↓
structural-dispatch evaluator convention
    ↓
ordinary records + first-class closures + Core perform
```

The object/metaobject flavor was not merely decoration around algebraic effects.

Eidos can move operation interpretation into Values themselves while preserving
the stronger distinction that only a terminal Socket crosses the relational
membrane.

The generic evaluator still has no host callback registry. Wrapper code remains
inspectable, serializable, content-addressable, open on Roles, and suitable for
partial realization elsewhere.

## Lexical capture versus situated Roles

First-class Closure support deliberately captures only lexical values.

Role Bindings remain supplied by the current realization.

Thus one immutable method Closure can be used under different:

```text
executor
policy
resolver
workspace
```

bindings without becoming a different code value.

This sharpens the original Role distinction:

> a lexical variable belongs to the computation's local expression structure;
> a Role is an open semantic parameter of the realization.

## What remains in Core

This experiment strengthens the current nucleus rather than adding another one.

Core currently needs:

```text
persistent Values
Names
Roles / Bindings
first-class code / Closures
Socket descriptions
local partial realization
terminal perform
```

Objects are derived.

Facet is derived.

Local handler composition is derived.

Static operation dispatch is derived.

## The next real question

There are now two particularly informative boundaries to attack.

### Dynamic operation selection

The current message-send expansion assumes that the operation Name is static in
the Eidos term. Dynamic operation values require ordinary map/pattern lookup in
the value language.

That looks like a mundane language-expressiveness problem, not evidence for a
new effect primitive.

### Reaction authority

The much deeper unresolved question remains outside local realization:

> What is the minimal authority/witness structure by which suspended Socket
> continuations may participate in a Reaction and establish successor live
> authority without turning Trusted Machinery into the rich protocol
> interpreter?

That is where the next *semantic* work should concentrate.

## Practical consequence

The Codex bridge can now be modeled with a terminal endpoint object whose method
performs against a Socket representing an observable native continuation. Audit,
sandbox, context projection, replay, and mock layers can be ordinary wrappers
above it.

That gives a concrete route back to the recorder/controller while preserving the
language experiment:

> **The calculus should sharpen the recorder/controller, not postpone it.**
