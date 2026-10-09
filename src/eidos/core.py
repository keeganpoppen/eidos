from __future__ import annotations

"""Executable experiment in the Eidos language nucleus.

The current runtime prototype begins with Frames and endpoint automata.  This
module asks a narrower language question: how much follows from persistent
values, nominal identity, situated Role bindings, authority-bearing Socket
continuations, and partial realization?

`perform` marks the point at which local realization requires relational
participation.  A Reaction resumes the captured continuation and explicitly
supplies both its result and any successor Socket.  Praxis never recursively
rewrites captured values to smuggle successor authority into a computation.
"""

from dataclasses import dataclass, fields, is_dataclass
from hashlib import sha256
import json
from typing import Any, Literal, TypeAlias


Scalar: TypeAlias = None | bool | int | float | str


# ---------------------------------------------------------------------------
# Form, identity, and situated interpretation


@dataclass(frozen=True, order=True)
class Name:
    """Permanent opaque identity; knowledge of a Name grants no authority."""

    value: str


@dataclass(frozen=True, order=True, init=False)
class Role:
    """A realization-local semantic parameter and namespace path."""

    path: tuple[str, ...]

    def __init__(self, *path: str) -> None:
        if not path or any(not part for part in path):
            raise ValueError("a Role requires one or more non-empty path segments")
        object.__setattr__(self, "path", tuple(path))

    def __str__(self) -> str:
        return "/".join(self.path)


@dataclass(frozen=True)
class Socket:
    """Description of a named authority-bearing relational continuation.

    Whether this occurrence is currently live is intentionally absent from the
    immutable value.  That disposition belongs to Trusted Machinery.
    """

    name: Name


@dataclass(frozen=True)
class RecordValue:
    fields: tuple[tuple[str, Any], ...]

    @classmethod
    def from_mapping(cls, values: dict[str, Any]) -> RecordValue:
        return cls(tuple(sorted(values.items())))

    def get(self, field: str) -> Any:
        for key, value in self.fields:
            if key == field:
                return value
        raise KeyError(field)

    def as_dict(self) -> dict[str, Any]:
        return dict(self.fields)


@dataclass(frozen=True)
class Binding:
    """Situated assignment of a Role to a value.

    A binding can itself receive a Name when independent addressability matters;
    ephemeral scoped bindings do not need one merely to exist.
    """

    role: Role
    value: Any
    name: Name | None = None


@dataclass(frozen=True)
class Bindings:
    entries: tuple[Binding, ...] = ()

    def lookup(self, role: Role) -> Any:
        for binding in reversed(self.entries):
            if binding.role == role:
                return binding.value
        raise KeyError(role)

    def bind(self, role: Role, value: Any, *, name: Name | None = None) -> Bindings:
        return Bindings(self.entries + (Binding(role=role, value=value, name=name),))


@dataclass(frozen=True)
class LexicalEnv:
    entries: tuple[tuple[str, Any], ...] = ()

    def lookup(self, name: str) -> Any:
        for key, value in reversed(self.entries):
            if key == name:
                return value
        raise KeyError(name)

    def bind(self, name: str, value: Any) -> LexicalEnv:
        return LexicalEnv(self.entries + ((name, value),))


# ---------------------------------------------------------------------------
# Eidos Core terms


class Term:
    pass


@dataclass(frozen=True)
class Lit(Term):
    value: Any


@dataclass(frozen=True)
class Var(Term):
    name: str


@dataclass(frozen=True)
class Need(Term):
    """Read whatever occupies a Role in this realization."""

    role: Role


@dataclass(frozen=True)
class Let(Term):
    name: str
    value: Term
    body: Term


@dataclass(frozen=True)
class Record(Term):
    fields: tuple[tuple[str, Term], ...]

    @classmethod
    def from_mapping(cls, values: dict[str, Term]) -> Record:
        return cls(tuple(values.items()))


@dataclass(frozen=True)
class Get(Term):
    record: Term
    field: str


Primitive = Literal["add", "concat", "eq"]


@dataclass(frozen=True)
class Prim(Term):
    """Closed primordial pure operators; no host-callable escape hatch."""

    operation: Primitive
    arguments: tuple[Term, ...]


@dataclass(frozen=True)
class Lambda(Term):
    """First-class Eidos code with lexical capture and situated Role lookup."""

    parameters: tuple[str, ...]
    body: Term


@dataclass(frozen=True)
class Apply(Term):
    function: Term
    arguments: tuple[Term, ...]


@dataclass(frozen=True)
class Closure:
    """A serializable lexical closure.

    Only the lexical environment is captured. Role Bindings remain situated:
    applying the same Closure under a different realization can therefore
    specialize its open semantic parameters differently.
    """

    parameters: tuple[str, ...]
    body: Term
    lexical: LexicalEnv


@dataclass(frozen=True)
class With(Term):
    """Realize `body` under a persistent scoped Role binding."""

    role: Role
    value: Term
    body: Term
    binding_name: Name | None = None


@dataclass(frozen=True)
class Perform(Term):
    """Expose a relational continuation at the local causal frontier.

    On Reaction, `result_as` receives the payload and `successor_as` receives
    the successor Socket (or None).  Eidos code explicitly decides whether and
    where to rebind that successor.
    """

    socket: Term
    operation: Name
    argument: Term
    result_as: str
    successor_as: str
    then: Term


# ---------------------------------------------------------------------------
# Explicit abstract machine


@dataclass(frozen=True)
class Returned:
    value: Any


Control: TypeAlias = Term | Returned


class KontFrame:
    pass


@dataclass(frozen=True)
class LetValueFrame(KontFrame):
    name: str
    body: Term


@dataclass(frozen=True)
class RecordFrame(KontFrame):
    completed: tuple[tuple[str, Any], ...]
    current_name: str
    remaining: tuple[tuple[str, Term], ...]


@dataclass(frozen=True)
class GetFrame(KontFrame):
    field: str


@dataclass(frozen=True)
class PrimFrame(KontFrame):
    operation: Primitive
    completed: tuple[Any, ...]
    remaining: tuple[Term, ...]


@dataclass(frozen=True)
class ApplyFunctionFrame(KontFrame):
    arguments: tuple[Term, ...]


@dataclass(frozen=True)
class ApplyArgumentFrame(KontFrame):
    closure: Closure
    completed: tuple[Any, ...]
    remaining: tuple[Term, ...]


@dataclass(frozen=True)
class RestoreLexicalFrame(KontFrame):
    lexical: LexicalEnv


@dataclass(frozen=True)
class WithValueFrame(KontFrame):
    role: Role
    body: Term
    binding_name: Name | None


@dataclass(frozen=True)
class RestoreBindingsFrame(KontFrame):
    bindings: Bindings


@dataclass(frozen=True)
class PerformSocketFrame(KontFrame):
    operation: Name
    argument: Term
    result_as: str
    successor_as: str
    then: Term


@dataclass(frozen=True)
class PerformArgumentFrame(KontFrame):
    socket: Any
    operation: Name
    result_as: str
    successor_as: str
    then: Term


@dataclass(frozen=True)
class MachineState:
    control: Control
    lexical: LexicalEnv = LexicalEnv()
    bindings: Bindings = Bindings()
    stack: tuple[KontFrame, ...] = ()


@dataclass(frozen=True)
class Continuation:
    """Serializable residual local computation, not a Python closure."""

    result_as: str
    successor_as: str
    then: Term
    lexical: LexicalEnv
    bindings: Bindings
    stack: tuple[KontFrame, ...]


@dataclass(frozen=True)
class Done:
    value: Any
    bindings: Bindings


@dataclass(frozen=True)
class Open:
    """Realization is blocked only by an unbound semantic Role."""

    role: Role
    state: MachineState


@dataclass(frozen=True)
class Suspended:
    """Local computation exposed as a relational continuation."""

    socket: Socket
    operation: Name
    argument: Any
    continuation: Continuation


Realization: TypeAlias = Done | Open | Suspended


@dataclass(frozen=True)
class Reaction:
    """Authoritative causal occurrence supplied from outside Praxis.

    Praxis does not infer protocol legality or mint successor authority.  It
    verifies only that this occurrence discharges the suspension being resumed,
    then exposes the result to ordinary Eidos code.
    """

    name: Name
    consumed: Socket
    successor: Socket | None
    value: Any


class RealizationError(RuntimeError):
    pass


class PraxisCore:
    """Small-step partial realization of Eidos values under Role bindings."""

    def realize(
        self,
        term: Term,
        *,
        lexical: LexicalEnv | None = None,
        bindings: Bindings | None = None,
    ) -> Realization:
        return self._run(
            MachineState(
                control=term,
                lexical=lexical or LexicalEnv(),
                bindings=bindings or Bindings(),
            )
        )

    def supply(
        self,
        open_: Open,
        value: Any,
        *,
        binding_name: Name | None = None,
    ) -> Realization:
        """Continue after supplying one previously open Role."""

        state = open_.state
        return self._run(
            MachineState(
                control=state.control,
                lexical=state.lexical,
                bindings=state.bindings.bind(open_.role, value, name=binding_name),
                stack=state.stack,
            )
        )

    def resume(self, suspended: Suspended, reaction: Reaction) -> Realization:
        """Resume with the explicit result and successor established by Reaction."""

        if reaction.consumed != suspended.socket:
            raise RealizationError(
                f"reaction consumes {reaction.consumed.name.value!r}, "
                f"not suspended socket {suspended.socket.name.value!r}"
            )
        k = suspended.continuation
        lexical = k.lexical.bind(k.result_as, reaction.value).bind(
            k.successor_as, reaction.successor
        )
        return self._run(
            MachineState(
                control=k.then,
                lexical=lexical,
                bindings=k.bindings,
                stack=k.stack,
            )
        )

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
                        rest + (RestoreLexicalFrame(state.lexical),),
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
                case ApplyFunctionFrame(arguments):
                    if not isinstance(value, Closure):
                        raise RealizationError("Apply expects a Closure")
                    if len(arguments) != len(value.parameters):
                        raise RealizationError(
                            f"closure expects {len(value.parameters)} arguments, "
                            f"got {len(arguments)}"
                        )
                    if not arguments:
                        state = self._state(
                            state,
                            value.body,
                            rest + (RestoreLexicalFrame(state.lexical),),
                            lexical=value.lexical,
                        )
                    else:
                        state = self._state(
                            state,
                            arguments[0],
                            rest
                            + (
                                ApplyArgumentFrame(
                                    value, (), arguments[1:]
                                ),
                            ),
                        )
                case ApplyArgumentFrame(closure, completed, remaining):
                    completed += (value,)
                    if remaining:
                        state = self._state(
                            state,
                            remaining[0],
                            rest
                            + (
                                ApplyArgumentFrame(
                                    closure, completed, remaining[1:]
                                ),
                            ),
                        )
                    else:
                        lexical = closure.lexical
                        for parameter, argument in zip(
                            closure.parameters, completed, strict=True
                        ):
                            lexical = lexical.bind(parameter, argument)
                        state = self._state(
                            state,
                            closure.body,
                            rest + (RestoreLexicalFrame(state.lexical),),
                            lexical=lexical,
                        )
                case RestoreLexicalFrame(lexical):
                    state = self._state(
                        state, Returned(value), rest, lexical=lexical
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
                    state = self._state(
                        state,
                        argument,
                        rest
                        + (
                            PerformArgumentFrame(
                                value, operation, result_as, successor_as, then
                            ),
                        ),
                    )
                case PerformArgumentFrame(
                    socket, operation, result_as, successor_as, then
                ):
                    outcome = self._perform_target(
                        state=state,
                        target=socket,
                        operation=operation,
                        argument=value,
                        result_as=result_as,
                        successor_as=successor_as,
                        then=then,
                        rest=rest,
                    )
                    if isinstance(outcome, MachineState):
                        state = outcome
                    else:
                        return outcome
                case _:
                    raise TypeError(frame)

    def _reduce_term(self, state: MachineState, term: Term) -> MachineState | Open:
        match term:
            case Lit(value):
                return self._state(state, Returned(value))
            case Var(name):
                return self._state(state, Returned(state.lexical.lookup(name)))
            case Need(role):
                try:
                    return self._state(
                        state, Returned(state.bindings.lookup(role))
                    )
                except KeyError:
                    return Open(role=role, state=state)
            case Let(name, value, body):
                return self._state(
                    state, value, state.stack + (LetValueFrame(name, body),)
                )
            case Record(term_fields):
                if not term_fields:
                    return self._state(state, Returned(RecordValue(())))
                first_name, first_term = term_fields[0]
                return self._state(
                    state,
                    first_term,
                    state.stack
                    + (
                        RecordFrame((), first_name, term_fields[1:]),
                    ),
                )
            case Get(record, field):
                return self._state(
                    state, record, state.stack + (GetFrame(field),)
                )
            case Prim(operation, arguments):
                if not arguments:
                    return self._state(
                        state, Returned(self._primitive(operation, ()))
                    )
                return self._state(
                    state,
                    arguments[0],
                    state.stack + (PrimFrame(operation, (), arguments[1:]),),
                )
            case Lambda(parameters, body):
                return self._state(
                    state, Returned(Closure(parameters, body, state.lexical))
                )
            case Apply(function, arguments):
                return self._state(
                    state,
                    function,
                    state.stack + (ApplyFunctionFrame(arguments),),
                )
            case With(role, value, body, binding_name):
                return self._state(
                    state,
                    value,
                    state.stack
                    + (WithValueFrame(role, body, binding_name),),
                )
            case Perform(
                socket, operation, argument, result_as, successor_as, then
            ):
                return self._state(
                    state,
                    socket,
                    state.stack
                    + (
                        PerformSocketFrame(
                            operation, argument, result_as, successor_as, then
                        ),
                    ),
                )
            case _:
                raise TypeError(term)

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
        rest: tuple[KontFrame, ...],
    ) -> MachineState | Realization:
        """Interpret the terminal target of perform.

        Core recognizes only live relational Socket descriptions. Derived
        realizers may override this hook to keep interpreting richer ordinary
        Values locally before eventually delegating a terminal Socket here.
        """

        if not isinstance(target, Socket):
            raise RealizationError(
                "perform target must realize to a Socket in Eidos Core"
            )
        return Suspended(
            socket=target,
            operation=operation,
            argument=argument,
            continuation=Continuation(
                result_as=result_as,
                successor_as=successor_as,
                then=then,
                lexical=state.lexical,
                bindings=state.bindings,
                stack=rest,
            ),
        )

    @staticmethod
    def _state(
        old: MachineState,
        control: Control,
        stack: tuple[KontFrame, ...] | None = None,
        *,
        lexical: LexicalEnv | None = None,
        bindings: Bindings | None = None,
    ) -> MachineState:
        return MachineState(
            control=control,
            lexical=old.lexical if lexical is None else lexical,
            bindings=old.bindings if bindings is None else bindings,
            stack=old.stack if stack is None else stack,
        )

    @staticmethod
    def _primitive(operation: Primitive, arguments: tuple[Any, ...]) -> Any:
        if len(arguments) != 2:
            raise RealizationError(f"{operation} expects two arguments")
        match operation:
            case "add":
                return arguments[0] + arguments[1]
            case "concat":
                return str(arguments[0]) + str(arguments[1])
            case "eq":
                return arguments[0] == arguments[1]
            case _:
                raise RealizationError(f"unknown primitive {operation!r}")


# ---------------------------------------------------------------------------
# Explicit JSON representation: residual computation is ordinary data.


_CORE_CLASSES: tuple[type[Any], ...] = (
    Name,
    Role,
    Socket,
    RecordValue,
    Binding,
    Bindings,
    LexicalEnv,
    Lit,
    Var,
    Need,
    Let,
    Record,
    Get,
    Prim,
    Lambda,
    Apply,
    Closure,
    With,
    Perform,
    Returned,
    LetValueFrame,
    RecordFrame,
    GetFrame,
    PrimFrame,
    ApplyFunctionFrame,
    ApplyArgumentFrame,
    RestoreLexicalFrame,
    WithValueFrame,
    RestoreBindingsFrame,
    PerformSocketFrame,
    PerformArgumentFrame,
    MachineState,
    Continuation,
    Done,
    Open,
    Suspended,
    Reaction,
)
_CLASS_BY_TAG: dict[str, type[Any]] = {cls.__name__: cls for cls in _CORE_CLASSES}


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
            "items": [[str(key), to_data(item)] for key, item in sorted(value.items())],
        }
    if is_dataclass(value) and type(value) in _CORE_CLASSES:
        return {
            "$": type(value).__name__,
            **{field.name: to_data(getattr(value, field.name)) for field in fields(value)},
        }
    raise TypeError(f"not an Eidos Core value: {type(value)!r}")


def from_data(data: Any) -> Any:
    if data is None or isinstance(data, (bool, int, float, str)):
        return data
    if not isinstance(data, dict) or "$" not in data:
        raise TypeError(f"not encoded Eidos Core data: {data!r}")

    tag = data["$"]
    if tag in {"tuple", "list"}:
        items = [from_data(item) for item in data["items"]]
        return tuple(items) if tag == "tuple" else items
    if tag == "map":
        return {key: from_data(item) for key, item in data["items"]}

    cls = _CLASS_BY_TAG.get(tag)
    if cls is None:
        raise ValueError(f"unknown Eidos Core tag: {tag!r}")
    kwargs = {
        field.name: from_data(data[field.name])
        for field in fields(cls)
    }
    if cls is Role:
        return Role(*kwargs["path"])
    return cls(**kwargs)


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        to_data(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def content_id(value: Any) -> str:
    return "sha256:" + sha256(canonical_bytes(value)).hexdigest()
