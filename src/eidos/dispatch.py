from __future__ import annotations

"""Structural local dispatch over ordinary Eidos Values.

This experiment pushes the Facet result one step further. A wrapper is no longer
an interpreter-specific Facet object. It is an ordinary RecordValue whose
"$dispatch" field contains operation Names mapped to first-class Eidos Closures.

PraxisDispatch recognizes only that structural convention. The behavior of every
method is Eidos code, wrapper state is ordinary record data, and successor
wrappers are constructed with ordinary Record terms. A terminal Socket remains
the only relational suspension.
"""

from typing import Any, Mapping

from .core import (
    Apply,
    Closure,
    Get,
    Let,
    Lit,
    MachineState,
    Name,
    PraxisCore,
    Realization,
    RealizationError,
    RecordValue,
    Socket,
    Term,
    Var,
)

DISPATCH_FIELD = "$dispatch"
INNER_FIELD = "inner"
STATE_FIELD = "state"
STEP_VALUE_FIELD = "value"
STEP_SUCCESSOR_FIELD = "successor"

_INTERNAL_STEP = "$eidos:dispatch-step"


def dispatch_table(methods: Mapping[Name, Closure]) -> RecordValue:
    """Build an immutable structural method table."""

    return RecordValue.from_mapping(
        {operation.value: closure for operation, closure in methods.items()}
    )


def wrapper(
    *,
    inner: Any,
    methods: Mapping[Name, Closure],
    state: Any = None,
    fields: Mapping[str, Any] | None = None,
) -> RecordValue:
    """Convenience constructor for a structurally dispatchable Value.

    This function is host-side sugar for tests/examples. The same Value can be
    constructed inside Eidos with ordinary Record terms.
    """

    values = dict(fields or {})
    values[DISPATCH_FIELD] = dispatch_table(methods)
    values[INNER_FIELD] = inner
    values[STATE_FIELD] = state
    return RecordValue.from_mapping(values)


def is_dispatchable(value: Any) -> bool:
    if not isinstance(value, RecordValue):
        return False
    try:
        return isinstance(value.get(DISPATCH_FIELD), RecordValue)
    except KeyError:
        return False


class PraxisDispatch(PraxisCore):
    """Praxis with one structural local-realization convention.

    A perform against a terminal Socket delegates to Eidos Core and therefore
    suspends relationally. A perform against a RecordValue with a "$dispatch"
    table applies the selected first-class Closure locally.

    The Closure must return an ordinary RecordValue with fields:

        value
        successor

    No Facet, Step, Rewrap, host callback, or handler stack is involved.
    """

    def _perform_target(
        self,
        *,
        state: MachineState,
        target: Any,
        operation: Name,
        argument: Any,
        result_as: str,
        successor_as: str,
        then: Term,
        rest: tuple[Any, ...],
    ) -> MachineState | Realization:
        if isinstance(target, Socket):
            return super()._perform_target(
                state=state,
                target=target,
                operation=operation,
                argument=argument,
                result_as=result_as,
                successor_as=successor_as,
                then=then,
                rest=rest,
            )

        if not is_dispatchable(target):
            raise RealizationError(
                "perform target must be a Socket or structurally dispatchable Value"
            )

        table = target.get(DISPATCH_FIELD)
        assert isinstance(table, RecordValue)
        try:
            method = table.get(operation.value)
        except KeyError as exc:
            raise RealizationError(
                f"target has no method for operation {operation.value!r}"
            ) from exc
        if not isinstance(method, Closure):
            raise RealizationError(
                f"dispatch entry {operation.value!r} is not an Eidos Closure"
            )

        # Local method application and the caller-facing result/successor binding
        # are expressed entirely with ordinary Eidos Core terms. The reserved
        # lexical name is scoped by Let and cannot leak into the caller's
        # enclosing continuation.
        control = Let(
            _INTERNAL_STEP,
            Apply(Lit(method), (Lit(target), Lit(argument))),
            Let(
                result_as,
                Get(Var(_INTERNAL_STEP), STEP_VALUE_FIELD),
                Let(
                    successor_as,
                    Get(Var(_INTERNAL_STEP), STEP_SUCCESSOR_FIELD),
                    then,
                ),
            ),
        )
        return MachineState(
            control=control,
            lexical=state.lexical,
            bindings=state.bindings,
            stack=rest,
        )
