# Structural dispatch: Facet without Facet

This experiment follows [`FACETS.md`](FACETS.md) and asks whether the local
wrapper itself must remain a special evaluator object.

The answer is now **mostly no**.

## Result

Eidos Core now has first-class lexical closures:

```text
Lambda(parameters, body)
    -> Closure(parameters, body, captured_lexical)
```

Closures capture ordinary lexical values but **not** Role Bindings. Roles remain
situated parameters of the realization in which the Closure is later applied.

A locally intercepting wrapper can therefore be represented as an ordinary
`RecordValue`:

```text
{
    "$dispatch": {
        operation: Closure(...)
    },
    "inner": ...,
    "state": ...
}
```

There is no `Facet` class in this representation.

The Closure receives only:

```text
self
argument
```

Everything else is ordinary structure reached from `self` or from ambient
Roles.

A method returns an ordinary record:

```text
{
    "value": result,
    "successor": next_target
}
```

Successor wrappers are built with ordinary `Record` expressions. There is no
special `Step` or `Rewrap` form.

## Local interpretation

`PraxisDispatch` interprets:

```text
perform target.Op(argument)
```

as follows.

If `target` is a terminal `Socket`, Core semantics apply and realization
returns `Suspended`.

If `target` is a record containing a structural `"$dispatch"` table, the
selected Closure is applied locally. Its returned `value` and `successor`
are bound to the caller's explicit continuation variables and local realization
continues.

Nested wrappers therefore reduce:

```text
Outer(
    Inner(
        Socket K0
    )
)
```

to exactly one relational suspension on `K0`.

After a Reaction establishes successor Socket `K1`, ordinary Eidos code
reconstructs:

```text
Outer'(
    Inner'(
        Socket K1
    )
)
```

No Socket-name search-and-replace occurs.

## Why first-class Closure matters

A wrapper method is now an inspectable, serializable Value rather than a body
whose parameter environment Praxis fabricates specially.

This separates two forms of context deliberately:

- lexical capture belongs to the Closure;
- Role Bindings remain supplied by the current realization.

The same Closure can therefore be realized under different `executor`,
`policy`, `resolver`, or other Roles without changing its code value.

This is the intended distinction between ordinary lexical scope and situated
semantic parameters.

## What remains special

One special rule remains:

> a RecordValue containing `"$dispatch"` is treated as a local operation
> interpreter by `PraxisDispatch`.

That is now the pressure point.

The wrapper itself is ordinary data. Its methods are ordinary Eidos code. Its
state is ordinary data. Its successor construction is ordinary code.

But operation dispatch is still selected by evaluator convention.

There are two serious possibilities:

1. **Structural dispatch is itself part of realization.**
   The convention is analogous to Smalltalk message lookup: sufficiently basic
   to deserve language semantics, while the objects/methods remain ordinary
   Values.

2. **Dispatch should itself be supplied through a Role/Binding.**
   In that design, Core knows only how to realize a target, while something like
   `realizer` or `dispatcher` determines how an operation is interpreted.
   Rebinding that Role changes the metaobject protocol itself.

The next experiment should discriminate between these rather than merely hiding
the convention behind another helper.

## Incidental correction

Adding first-class closures exposed that the original Core `Let` implementation
did not restore the outer lexical environment when its body returned to an
enclosing continuation. That is now fixed. Lexical variables and Roles therefore
have the intended distinct scoping semantics.

## Current pressure-test ladder

The progression is now:

```text
Facet class
    |
    v
ordinary RecordValue
+ first-class Closure methods
+ ordinary record successor construction
    |
    v
? structural dispatch semantics
  or
? Role-bound realizer / metaobject protocol
```

The next question is not whether wrappers can be Values. They can.

The question is:

> **Who interprets the relationship between an operation and the Value it is
> performed against?**

That is the next place where "fundamental" versus "derived" becomes substantive.
