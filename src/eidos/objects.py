from __future__ import annotations

"""Object/message conventions derived entirely from Eidos Core.

Unlike eidos.dispatch, this module adds no Praxis subclass and no evaluator
semantics. An operation target is an ordinary RecordValue containing a method
table of first-class Closures. Message send is an AST expansion into Get +
Apply. A terminal endpoint is merely an object whose method eventually reaches
Core Perform on a contained Socket.

The point of this module is experimental: if useful wrapper/object semantics can
be expressed this way, Facet and structural dispatch belong above the language
nucleus rather than inside Praxis.
"""

from typing import Any, Mapping

from .core import (
    Apply,
    Closure,
    Get,
    Let,
    Name,
    RecordValue,
    Term,
    Var,
)

METHODS_FIELD = "$methods"
SOCKET_FIELD = "$socket"
INNER_FIELD = "inner"
STATE_FIELD = "state"
STEP_VALUE_FIELD = "value"
STEP_SUCCESSOR_FIELD = "successor"

_TARGET_VAR = "$eidos:invoke-target"
_STEP_VAR = "$eidos:invoke-step"


def method_table(methods: Mapping[Name, Closure]) -> RecordValue:
    return RecordValue.from_mapping(
        {operation.value: closure for operation, closure in methods.items()}
    )


def object_value(
    *,
    methods: Mapping[Name, Closure],
    fields: Mapping[str, Any] | None = None,
) -> RecordValue:
    values = dict(fields or {})
    values[METHODS_FIELD] = method_table(methods)
    return RecordValue.from_mapping(values)


def invoke(
    target: Term,
    operation: Name,
    argument: Term,
    *,
    result_as: str,
    successor_as: str,
    then: Term,
) -> Term:
    """Compile one message send into ordinary Eidos Core terms.

    Operations are statically named in the current Core syntax, so selecting the
    corresponding Closure requires no evaluator hook. A later dynamic-operation
    language can derive lookup from ordinary map/pattern facilities.
    """

    return Let(
        _TARGET_VAR,
        target,
        Let(
            _STEP_VAR,
            Apply(
                Get(
                    Get(Var(_TARGET_VAR), METHODS_FIELD),
                    operation.value,
                ),
                (
                    Var(_TARGET_VAR),
                    argument,
                ),
            ),
            Let(
                result_as,
                Get(Var(_STEP_VAR), STEP_VALUE_FIELD),
                Let(
                    successor_as,
                    Get(Var(_STEP_VAR), STEP_SUCCESSOR_FIELD),
                    then,
                ),
            ),
        ),
    )
