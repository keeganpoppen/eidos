from __future__ import annotations

"""Value-level operation wrappers for the Eidos Core experiment.

A Facet is an ordinary immutable Eidos value: an inner target plus operation
clauses written in Eidos terms.  Performing against a Facet is still local
realization.  Only when the clauses eventually reach a terminal Socket does the
computation become a relational suspension.

This makes the earlier `refer -> wrap -> rebind` idea executable without a
privileged host-language handler stack.  A clause returns an explicit Step:
its result and the successor target visible to the caller.  If it forwards to
an inner Socket, `Rewrap` can construct the successor Facet around the successor
inner authority supplied by the Reaction.
"""

from dataclasses import dataclass, fields, is_dataclass
import json
from typing import Any

from . import core as _core
from .core import (
    Bindings,
    Continuation,
    Control,
    Done,
    GetFrame,
    LetValueFrame,
    LexicalEnv,
    MachineState,
    Name,
    Open,
    PerformArgumentFrame,
    PerformSocketFrame,
    PrimFrame,
    PraxisCore,
    Realization,
    RealizationError,
    RecordFrame,
    RecordValue,
    RestoreBindingsFrame,
    Returned,
    Socket,
    Suspended,
    Term,
    WithValueFrame,
)


@dataclass(frozen=True)
class Clause:
    """Eidos code that locally interprets one operation on a Facet.

    The clause runs in the Facet's captured lexical environment, extended with
    four explicit parameters.  Ambient Roles remain open to the realization in
    which the Facet is used.
    """

    operation: Name
    body: Term
    argument_as: str = "argument"
    self_as: str = "self"
    inner_as: str = "inner"
    state_as: str = "state"


@dataclass(frozen=True)
class Facet:
    """An immutable local interpreter around another operation target.

    Facets are not live authority by themselves.  They may contain or eventually
    resolve to a live Socket.  Nested Facets therefore compose local semantic
    layers while preserving a single terminal relational suspension.
    """

    inner: Any
    clauses: tuple[Clause, ...]
    state: Any = None
    lexical: LexicalEnv = LexicalEnv()

    def clause(self, operation: Name) -> Clause:
        for clause in self.clauses:
            if clause.operation == operation:
                return clause
        raise RealizationError(
            f"facet has no clause for operation {operation.value!r}"
        )


@dataclass(frozen=True)
class StepValue:
    """Result of a locally interpreted operation.

    `successor` is the target to expose to the caller after this operation.  It
    may be the same Facet, a reconstructed Facet around a successor inner
    Socket, a raw Socket, another value-level target, or None.
    """

    value: Any
    successor: Any


@dataclass(frozen=True)
class Step(Term):
    value: Term
    successor: Term


@dataclass(frozen=True)
class Rewrap(Term):
    """Rebuild a Facet with a new inner target and optional new state."""

    facet: Term
    inner: Term
    state: Term | None = None


# ---------------------------------------------------------------------------
# Additional abstract-machine frames


@dataclass(frozen=True)
class PerformTargetArgumentFrame(_core.KontFrame):
    target: Socket | Facet
    operation: Name
    result_as: str
    successor_as: str
    then: Term


@dataclass(frozen=True)
class CompleteFacetPerformFrame(_core.KontFrame):
    result_as: str
    successor_as: str
    then: Term
    outer_lexical: LexicalEnv
    outer_bindings: Bindings


@dataclass(frozen=True)
class StepValueFrame(_core.KontFrame):
    successor: Term


@dataclass(frozen=True)
class StepSuccessorFrame(_core.KontFrame):
    value: Any


@dataclass(frozen=True)
class RewrapFacetFrame(_core.KontFrame):
    inner: Term
    state: Term | None


@dataclass(frozen=True)
class RewrapInnerFrame(_core.KontFrame):
    facet: Facet
    state: Term | None


@dataclass(frozen=True)
class RewrapStateFrame(_core.KontFrame):
    facet: Facet
    inner: Any


class PraxisFacets(PraxisCore):
    """Praxis Core extended with value-level operation interpretation.

    `Perform` is no longer assumed to suspend immediately.  Its target may be a
    Facet, in which case the matching clause is realized locally.  Clauses can
    answer locally, transform the operation, or forward through arbitrarily
    many nested Facets.  Only a terminal Socket creates `Suspended`.
    """

    def _run(self, initial: MachineState) -> Realization:
        state = initial
        while True:
            if isinstance(state.control, Term):
                reduced = self._reduce_term(state, state.control)
                if isinstance(reduced, Open):
                    return reduced
                state = reduced
                continue

            if not state.stack:
                return Done(state.control.value, state.bindings)

            value = state.control.value
            frame, rest = state.stack[-1], state.stack[:-1]

            match frame:
                case LetValueFrame(name, body):
                    state = self._state(
                        state,
                        body,
                        rest,
                        lexical=state.lexical.bind(name, value),
                    )
                case RecordFrame(completed, current_name, remaining):
                    completed += ((current_name, value),)
                    if remaining:
                        next_name, next_term = remaining[0]
                        state = self._state(
                            state,
                            next_term,
                            rest
                            + (
                                RecordFrame(
                                    completed, next_name, remaining[1:]
                                ),
                            ),
                        )
                    else:
                        state = self._state(
                            state, Returned(RecordValue(completed)), rest
                        )
                case GetFrame(field):
                    if not isinstance(value, RecordValue):
                        raise RealizationError("Get expects a RecordValue")
                    state = self._state(state, Returned(value.get(field)), rest)
                case PrimFrame(operation, completed, remaining):
                    completed += (value,)
                    if remaining:
                        state = self._state(
                            state,
                            remaining[0],
                            rest
                            + (
                                PrimFrame(operation, completed, remaining[1:]),
                            ),
                        )
                    else:
                        state = self._state(
                            state,
                            Returned(self._primitive(operation, completed)),
                            rest,
                        )
                case WithValueFrame(role, body, binding_name):
                    outer = state.bindings
                    state = self._state(
                        state,
                        body,
                        rest + (RestoreBindingsFrame(outer),),
                        bindings=outer.bind(role, value, name=binding_name),
                    )
                case RestoreBindingsFrame(bindings):
                    state = self._state(
                        state, Returned(value), rest, bindings=bindings
                    )
                case PerformSocketFrame(
                    operation, argument, result_as, successor_as, then
                ):
                    if not isinstance(value, (Socket, Facet)):
                        raise RealizationError(
                            "perform target must realize to a Socket or Facet"
                        )
                    state = self._state(
                        state,
                        argument,
                        rest
                        + (
                            PerformTargetArgumentFrame(
                                value, operation, result_as, successor_as, then
                            ),
                        ),
                    )
                case PerformArgumentFrame(
                    socket, operation, result_as, successor_as, then
                ):
                    # Compatibility with continuations produced by PraxisCore.
                    return Suspended(
                        socket=socket,
                        operation=operation,
                        argument=value,
                        continuation=Continuation(
                            result_as=result_as,
                            successor_as=successor_as,
                            then=then,
                            lexical=state.lexical,
                            bindings=state.bindings,
                            stack=rest,
                        ),
                    )
                case PerformTargetArgumentFrame(
                    target, operation, result_as, successor_as, then
                ):
                    if isinstance(target, Socket):
                        return Suspended(
                            socket=target,
                            operation=operation,
                            argument=value,
                            continuation=Continuation(
                                result_as=result_as,
                                successor_as=successor_as,
                                then=then,
                                lexical=state.lexical,
                                bindings=state.bindings,
                                stack=rest,
                            ),
                        )

                    clause = target.clause(operation)
                    method_lexical = (
                        target.lexical
                        .bind(clause.self_as, target)
                        .bind(clause.inner_as, target.inner)
                        .bind(clause.state_as, target.state)
                        .bind(clause.argument_as, value)
                    )
                    state = MachineState(
                        control=clause.body,
                        lexical=method_lexical,
                        bindings=state.bindings,
                        stack=rest
                        + (
                            CompleteFacetPerformFrame(
                                result_as=result_as,
                                successor_as=successor_as,
                                then=then,
                                outer_lexical=state.lexical,
                                outer_bindings=state.bindings,
                            ),
                        ),
                    )
                case CompleteFacetPerformFrame(
                    result_as,
                    successor_as,
                    then,
                    outer_lexical,
                    outer_bindings,
                ):
                    if not isinstance(value, StepValue):
                        raise RealizationError(
                            "a Facet clause must realize to StepValue"
                        )
                    state = MachineState(
                        control=then,
                        lexical=(
                            outer_lexical
                            .bind(result_as, value.value)
                            .bind(successor_as, value.successor)
                        ),
                        bindings=outer_bindings,
                        stack=rest,
                    )
                case StepValueFrame(successor):
                    state = self._state(
                        state,
                        successor,
                        rest + (StepSuccessorFrame(value),),
                    )
                case StepSuccessorFrame(step_value):
                    state = self._state(
                        state,
                        Returned(StepValue(step_value, value)),
                        rest,
                    )
                case RewrapFacetFrame(inner, state_term):
                    if not isinstance(value, Facet):
                        raise RealizationError("Rewrap expects a Facet")
                    state = self._state(
                        state,
                        inner,
                        rest + (RewrapInnerFrame(value, state_term),),
                    )
                case RewrapInnerFrame(facet, state_term):
                    if state_term is None:
                        state = self._state(
                            state,
                            Returned(
                                Facet(
                                    inner=value,
                                    clauses=facet.clauses,
                                    state=facet.state,
                                    lexical=facet.lexical,
                                )
                            ),
                            rest,
                        )
                    else:
                        state = self._state(
                            state,
                            state_term,
                            rest + (RewrapStateFrame(facet, value),),
                        )
                case RewrapStateFrame(facet, inner):
                    state = self._state(
                        state,
                        Returned(
                            Facet(
                                inner=inner,
                                clauses=facet.clauses,
                                state=value,
                                lexical=facet.lexical,
                            )
                        ),
                        rest,
                    )
                case _:
                    raise TypeError(frame)

    def _reduce_term(
        self, state: MachineState, term: Term
    ) -> MachineState | Open:
        match term:
            case Step(value, successor):
                return self._state(
                    state,
                    value,
                    state.stack + (StepValueFrame(successor),),
                )
            case Rewrap(facet, inner, state_term):
                return self._state(
                    state,
                    facet,
                    state.stack + (RewrapFacetFrame(inner, state_term),),
                )
            case _:
                return super()._reduce_term(state, term)


# ---------------------------------------------------------------------------
# Extended explicit representation


_FACET_CLASSES: tuple[type[Any], ...] = (
    Clause,
    Facet,
    StepValue,
    Step,
    Rewrap,
    PerformTargetArgumentFrame,
    CompleteFacetPerformFrame,
    StepValueFrame,
    StepSuccessorFrame,
    RewrapFacetFrame,
    RewrapInnerFrame,
    RewrapStateFrame,
)
_ALL_CLASSES = _core._CORE_CLASSES + _FACET_CLASSES
_CLASS_BY_TAG: dict[str, type[Any]] = {
    cls.__name__: cls for cls in _ALL_CLASSES
}


def to_data(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, tuple):
        return {"$": "tuple", "items": [to_data(item) for item in value]}
    if isinstance(value, list):
        return {"$": "list", "items": [to_data(item) for item in value]}
    if isinstance(value, dict):
        return {
            "$": "map",
            "items": [
                [str(key), to_data(item)]
                for key, item in sorted(value.items())
            ],
        }
    if is_dataclass(value) and type(value) in _ALL_CLASSES:
        return {
            "$": type(value).__name__,
            **{
                field.name: to_data(getattr(value, field.name))
                for field in fields(value)
            },
        }
    raise TypeError(f"not an Eidos Facet value: {type(value)!r}")


def from_data(data: Any) -> Any:
    if data is None or isinstance(data, (bool, int, float, str)):
        return data
    if not isinstance(data, dict) or "$" not in data:
        raise TypeError(f"not encoded Eidos Facet data: {data!r}")

    tag = data["$"]
    if tag in {"tuple", "list"}:
        items = [from_data(item) for item in data["items"]]
        return tuple(items) if tag == "tuple" else items
    if tag == "map":
        return {key: from_data(item) for key, item in data["items"]}

    cls = _CLASS_BY_TAG.get(tag)
    if cls is None:
        raise ValueError(f"unknown Eidos Facet tag: {tag!r}")
    kwargs = {
        field.name: from_data(data[field.name])
        for field in fields(cls)
    }
    if cls is _core.Role:
        return _core.Role(*kwargs["path"])
    return cls(**kwargs)


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        to_data(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
