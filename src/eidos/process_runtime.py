from __future__ import annotations

"""One continuation machine for any named Eidos process protocol.

The machine doesn't know whether the current participant is requesting or
responding. It understands a named ProcessProtocol Value, a saved Eidos
continuation, one authority-bearing Socket, and an operation interpreter.
The interpreter supplies a Reaction backed by Trusted Machinery; the machine
verifies it, resumes Praxis, and records the successor checkpoint or outcome.

Protocol-specific effects (such as looking up a Cut or deciding an Inquiry)
remain ordinary libraries above the machine. No new authority substrate and
no global inter-domain transaction are introduced.
"""

from dataclasses import dataclass
from typing import Any, Callable, Iterable

from .core import (
    Done, Name, PraxisCore, Reaction, RecordValue, Socket, Suspended,
    content_id,
)
from .trusted import TrustedMachinery


class ProcessRuntimeError(ValueError):
    pass


def operation_value(
    name: Name | str,
    *,
    terminal: bool = False,
) -> RecordValue:
    return RecordValue.from_mapping({
        "$kind": "ProtocolOperation",
        "name": name if isinstance(name, Name) else Name(name),
        "terminal": terminal,
    })


def protocol_value(
    *,
    role: str,
    operations: Iterable[RecordValue],
) -> RecordValue:
    """An inspectable semantic description of legal local continuations."""

    if not role:
        raise ValueError("a protocol needs a projection role")
    entries = tuple(operations)
    seen: set[Name] = set()
    for entry in entries:
        if not isinstance(entry, RecordValue) or entry.get("$kind") != "ProtocolOperation":
            raise ValueError("protocol operations must be ordinary ProtocolOperation Values")
        name = entry.get("name")
        terminal = entry.get("terminal")
        if not isinstance(name, Name) or not isinstance(terminal, bool):
            raise ValueError("operation requires a Name and terminal flag")
        if name in seen:
            raise ValueError("duplicate protocol operation")
        seen.add(name)
    if not entries:
        raise ValueError("a process protocol cannot have an empty operation frontier")
    return RecordValue.from_mapping({
        "$kind": "ProcessProtocol",
        "projection_role": role,
        "operations": entries,
    })


@dataclass(frozen=True)
class ProcessState:
    """One located, inspectable suspended continuation."""

    checkpoint: str
    process: str
    descriptor: RecordValue
    protocol: RecordValue
    suspended: Suspended
    step: int
    holder: str
    domain: str
    extras: tuple[tuple[str, Any], ...]

    def get(self, key: str, default: Any = None) -> Any:
        return dict(self.extras).get(key, default)


@dataclass(frozen=True)
class ProcessPending:
    """Pending semantic input; no capability has been consumed."""

    reference: str


@dataclass(frozen=True)
class ProcessReaction:
    """A protocol interpreter has committed a supported causal occurrence."""

    reaction: Reaction
    # The semantic interpreter may update the situated Context or holder.
    extras: tuple[tuple[str, Any], ...] = ()
    handoff_to: str | None = None


@dataclass(frozen=True)
class ProcessResult:
    process: str
    checkpoint: str | None = None
    outcome: str | None = None
    occurrence: str | None = None
    pending: str | None = None
    handoff_to: str | None = None


@dataclass(frozen=True)
class ProcessContinuation:
    """Receipt shared by all Roles at the point Praxis has resumed."""

    state: ProcessState
    transition: ProcessReaction
    resumed: Done | Suspended
    checkpoints: tuple[str, ...]
    occurrences: tuple[str, ...]
    extras: tuple[tuple[str, Any], ...]


Interpreter = Callable[[ProcessState], ProcessPending | ProcessReaction]
Finisher = Callable[[ProcessContinuation], str]


class ProcessRuntime:
    """Durable causal progression without a requester/responder special case."""

    def __init__(self, trusted: TrustedMachinery, *, max_steps: int = 16) -> None:
        if max_steps <= 0:
            raise ValueError("max_steps must be positive")
        self.trusted = trusted
        self.max_steps = max_steps

    def load(self, checkpoint: str, *, identity: str | None = None) -> ProcessState:
        state = self.trusted.named_eidos_value(checkpoint)["value"]
        if not isinstance(state, RecordValue):
            raise ProcessRuntimeError("process checkpoint must be an Eidos Value")
        process = self._field(state, "process")
        suspended = self._field(state, "suspension")
        step = self._field(state, "step")
        if not isinstance(process, Name) or not isinstance(suspended, Suspended):
            raise ProcessRuntimeError("checkpoint must name a process and suspension")
        if isinstance(step, bool) or not isinstance(step, int) or not 0 <= step < self.max_steps:
            raise ProcessRuntimeError("process step budget exceeded")

        descriptor = self.trusted.named_eidos_value(process.value)["value"]
        if not isinstance(descriptor, RecordValue):
            raise ProcessRuntimeError("process description is not an Eidos Value")
        protocol_name = self._field(descriptor, "protocol")
        if not isinstance(protocol_name, Name):
            raise ProcessRuntimeError("process description must bind a ProcessProtocol Name")
        protocol = self.trusted.named_eidos_value(protocol_name.value)["value"]
        if not isinstance(protocol, RecordValue) or protocol.get("$kind") != "ProcessProtocol":
            raise ProcessRuntimeError("process protocol Name does not resolve")

        domain_ref = self._field(descriptor, "authority_domain")
        domain = process.value if domain_ref is None else domain_ref.value
        if domain_ref is not None and not isinstance(domain_ref, Name):
            raise ProcessRuntimeError("authority_domain must be a Name")
        projection = self.trusted.projection(suspended.socket.name.value)
        if (
            projection["domain_name"] != domain
            or projection.get("role") != protocol.get("projection_role")
        ):
            raise ProcessRuntimeError("Socket violates local protocol authority")
        if identity is not None and projection["holder"] != identity:
            raise ProcessRuntimeError("continuation belongs to another holder")

        self.operation(protocol, suspended.operation)
        return ProcessState(
            checkpoint=checkpoint,
            process=process.value,
            descriptor=descriptor,
            protocol=protocol,
            suspended=suspended,
            step=step,
            holder=projection["holder"],
            domain=domain,
            extras=tuple(
                (key, value)
                for key, value in state.fields
                if key not in ("$kind", "process", "step", "suspension")
            ),
        )

    @staticmethod
    def _field(value: RecordValue, key: str) -> Any:
        try:
            return value.get(key)
        except KeyError:
            return None

    @staticmethod
    def operation(protocol: RecordValue, name: Name) -> RecordValue:
        for operation in protocol.get("operations"):
            if operation.get("name") == name:
                return operation
        raise ProcessRuntimeError(
            f"{name.value!r} is not legal for this local ProcessProtocol"
        )

    def validate_successor(
        self,
        state: ProcessState,
        suspended: Suspended,
        *,
        expected_socket: str,
        identity: str | None = None,
    ) -> None:
        if suspended.socket.name.value != expected_socket:
            raise ProcessRuntimeError("continuation changed Socket without a Reaction")
        projection = self.trusted.projection(expected_socket)
        if (
            projection["domain_name"] != state.domain
            or projection.get("role") != state.protocol.get("projection_role")
        ):
            raise ProcessRuntimeError("successor Socket violates local protocol")
        if identity is not None and projection["holder"] != identity:
            raise ProcessRuntimeError("successor Socket belongs to another holder")
        self.operation(state.protocol, suspended.operation)

    def advance(
        self,
        checkpoint: str,
        *,
        interpret: Interpreter,
        finish: Finisher,
        identity: str | None = None,
        validate: Callable[[ProcessState], None] | None = None,
    ) -> ProcessResult:
        """Interpret one operation, resume, and persist exactly one successor cut."""

        state = self.load(checkpoint, identity=identity)
        if validate is not None:
            validate(state)

        transition = interpret(state)
        if isinstance(transition, ProcessPending):
            return ProcessResult(
                process=state.process,
                checkpoint=checkpoint,
                pending=transition.reference,
            )
        if not isinstance(transition, ProcessReaction):
            raise ProcessRuntimeError("protocol interpretation must yield Reaction or Pending")
        reaction = transition.reaction
        if state.suspended.socket not in reaction.consumed_sockets:
            raise ProcessRuntimeError("Reaction did not consume the suspended Socket")
        authorized = self.trusted.authority_occurrence(reaction.name.value)
        if (
            authorized["domain_name"] != state.domain
            or state.suspended.socket.name.value not in authorized["inputs"]
        ):
            raise ProcessRuntimeError("Reaction does not have source-domain authority")
        # Check the entire declared Socket set; a semantic interpreter cannot
        # slip a new participant into Praxis's Reaction by merely naming it.
        if {
            socket.name.value for socket in reaction.consumed_sockets
        } != set(authorized["inputs"]):
            raise ProcessRuntimeError("Reaction Socket set contradicts causal inputs")

        successor = reaction.successor
        expected_terminal = self.operation(
            state.protocol, state.suspended.operation
        ).get("terminal")
        if expected_terminal != (successor is None):
            raise ProcessRuntimeError("Reaction successor violates the operation protocol")
        if successor is not None and successor.name.value not in authorized["outputs"].values():
            raise ProcessRuntimeError("Reaction successor lacks established authority")
        resumed = PraxisCore().resume(state.suspended, reaction)

        checkpoints = self.lineage(checkpoint)
        occurrences = self.occurred_lineage(checkpoints) + (reaction.name.value,)
        extras = dict(state.extras)
        extras.update(dict(transition.extras))
        continuation = ProcessContinuation(
            state=state, transition=transition, resumed=resumed,
            checkpoints=checkpoints, occurrences=occurrences,
            extras=tuple(extras.items()),
        )
        if isinstance(resumed, Done):
            outcome = finish(continuation)
            return ProcessResult(
                process=state.process, outcome=outcome,
                occurrence=reaction.name.value,
            )
        if not isinstance(resumed, Suspended):
            raise ProcessRuntimeError("process continuation is neither Done nor Suspended")
        if successor is None:
            raise ProcessRuntimeError("terminal protocol operation cannot leave suspended code")
        # Handoff is represented by the holder of the *successor* capability.
        # Only the recipient may progress it, but the previous holder can
        # still reconstruct this already-committed historical transition.
        next_identity = transition.handoff_to or identity
        self.validate_successor(
            state, resumed,
            expected_socket=successor.name.value,
            identity=next_identity,
        )
        next_checkpoint = self.checkpoint(
            previous=checkpoint,
            process=state.process,
            step=state.step + 1,
            suspended=resumed,
            parent_occurrence=reaction.name.value,
            extras=extras,
        )
        return ProcessResult(
            process=state.process,
            checkpoint=next_checkpoint,
            occurrence=reaction.name.value,
            handoff_to=transition.handoff_to,
        )

    def checkpoint(
        self,
        *,
        previous: str | None,
        process: str,
        step: int,
        suspended: Suspended,
        parent_occurrence: str | None,
        extras: dict[str, Any],
        request_id: str | None = None,
    ) -> str:
        """Persist an ordinary residual computation independent of local Role."""

        # One universal checkpoint schema. Compatibility wrappers may add their
        # old field aliases, but the machine only reads these common fields.
        value = RecordValue.from_mapping({
            "$kind": "ProcessCheckpoint",
            "process": Name(process),
            "step": step,
            "suspension": suspended,
            "previous": None if previous is None else Name(previous),
            "parent_occurrence": (
                None if parent_occurrence is None else Name(parent_occurrence)
            ),
            **extras,
        })
        identity = (
            request_id or
            f"{process}:{previous if previous is not None else 'initial'}:next-checkpoint"
        )
        return self.persist(
            kind="process-checkpoint", value=value, request_id=identity
        )

    def persist(self, *, kind: str, value: RecordValue, request_id: str) -> str:
        name = self.trusted.reserve_name(
            kind=kind, request_id=f"{request_id}:reserve"
        )
        self.trusted.bind_eidos_value(
            name=name, value=value, request_id=f"{request_id}:bind"
        )
        return name

    def lineage(self, checkpoint: str) -> tuple[str, ...]:
        result: list[str] = []
        visited: set[str] = set()
        cursor: str | None = checkpoint
        while cursor is not None:
            if cursor in visited:
                raise ProcessRuntimeError("cyclic process checkpoint history")
            visited.add(cursor)
            result.append(cursor)
            value = self.trusted.named_eidos_value(cursor)["value"]
            previous = value.get("previous")
            if previous is not None and not isinstance(previous, Name):
                raise ProcessRuntimeError("checkpoint previous must be a Name")
            cursor = None if previous is None else previous.value
        return tuple(reversed(result))

    def occurred_lineage(self, checkpoints: tuple[str, ...]) -> tuple[str, ...]:
        events: list[str] = []
        for checkpoint in checkpoints:
            value = self.trusted.named_eidos_value(checkpoint)["value"]
            parent = value.get("parent_occurrence")
            if parent is not None and not isinstance(parent, Name):
                raise ProcessRuntimeError("checkpoint parent_occurrence must be a Name")
            if isinstance(parent, Name):
                events.append(parent.value)
        return tuple(events)
