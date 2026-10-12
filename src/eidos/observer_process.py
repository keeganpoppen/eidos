from __future__ import annotations

"""A responding observer as a resumable Eidos process.

The responder runs an ordinary Eidos Closure under the live InquiryResponder
Socket already authorized by DiscoveryAccept. Its Inspect/Consult steps consume
and re-establish that SAME source-domain linear responder authority; Defer,
Offer, and Refuse are ordinary Eidos perform operations interpreted through
the existing source-domain discovery decisions.

No second responder authority is minted. A requesting Model's process remains
in its own domain and may remain suspended while this observer deliberates.
"""

from dataclasses import dataclass
from typing import Any, Callable, Mapping

from .authority import ProjectionGrant
from .core import (
    Apply, Bindings, Closure, Done, Lit, Name, PraxisCore, Reaction, RecordValue,
    Role, Socket, Suspended, canonical_bytes, content_id, to_data,
)
from .discovery import (
    DiscoveryError, _inquiry, _responder_in_lineage,
    accept_inquiry, decide_inquiry, poll_inquiry,
)
from .epistemics import admitted_inspection_scope, _require_kind
from .model_execution import ModelAdapter, ModelExecutionError
from .semantic_values import projection_value
from .trusted import TrustedMachinery
from .process_runtime import (
    ProcessRuntime, ProcessRuntimeError, ProcessReaction, ProcessPending,
    ProcessContinuation, ProcessState, operation_value, protocol_value,
)


OBSERVER_SOCKET_ROLE = Role("discovery", "responder-socket")
OBSERVER_CONTEXT_ROLE = Role("discovery", "context")
OBSERVER_INQUIRY_ROLE = Role("discovery", "inquiry")

OBSERVER_INSPECT = Name("observer:Inspect")
OBSERVER_CONSULT = Name("observer:Consult")
OBSERVER_DEFER = Name("observer:Defer")
OBSERVER_OFFER = Name("observer:Offer")
OBSERVER_REFUSE = Name("observer:Refuse")


def defer_request(reason: str = "") -> RecordValue:
    return RecordValue.from_mapping({
        "$kind": "ObserverDeferRequest",
        "reason": reason,
    })


def offer_request(cut: Name | str) -> RecordValue:
    return RecordValue.from_mapping({
        "$kind": "ObserverOfferRequest",
        "cut": cut if isinstance(cut, Name) else Name(cut),
    })


def refuse_request(reason: str = "") -> RecordValue:
    return RecordValue.from_mapping({
        "$kind": "ObserverRefuseRequest",
        "reason": reason,
    })


def observer_advice(
    context: Name | str,
    *,
    recommendation: str,
    cut: Name | str | None = None,
    receipt: Any = None,
) -> RecordValue:
    if recommendation not in ("offer", "refuse", "defer"):
        raise ModelExecutionError("observer recommendation must be offer/refuse/defer")
    return RecordValue.from_mapping({
        "$kind": "ObserverAdvice",
        "context": context if isinstance(context, Name) else Name(context),
        "recommendation": recommendation,
        "cut": None if cut is None else (
            cut if isinstance(cut, Name) else Name(cut)
        ),
        "receipt": receipt,
    })


@dataclass(frozen=True)
class ObserverProgress:
    process: str
    inquiry: str
    checkpoint: str | None = None
    outcome: str | None = None
    occurrence: str | None = None


class ObserverProcessRunner:
    """Realize one source observer's InquiryResponder protocol incrementally."""

    def __init__(
        self,
        trusted: TrustedMachinery,
        *,
        executors: Mapping[str, ModelAdapter] | None = None,
        identity: str | None = None,
        max_steps: int = 16,
        max_scope_nodes: int = 256,
    ) -> None:
        if max_steps <= 0 or max_scope_nodes <= 0:
            raise ValueError("observer process budgets must be positive")
        self.trusted = trusted
        self.machine = ProcessRuntime(trusted, max_steps=max_steps)
        self.executors = dict(executors or {})
        self.identity = identity
        self.max_steps = max_steps
        self.max_scope_nodes = max_scope_nodes

    def start(
        self,
        *,
        inquiry: str,
        discloser_projection: str,
        context: str,
        program: Closure,
        allowed_executors: tuple[str, ...] = (),
        request_id: str,
    ) -> ObserverProgress:
        """Accept the inquiry and bind one observer Closure to its responder."""

        if not isinstance(program, Closure):
            raise ModelExecutionError("observer program must be an Eidos Closure")
        question, provider = _inquiry(self.trusted, inquiry)
        source_domain = provider.get("source_domain").value
        observer = provider.get("observer")
        if self.identity is not None and self.identity != observer:
            raise ModelExecutionError("observer runner identity does not match provider")

        own_context = _require_kind(
            self.trusted.named_eidos_value(context)["value"], "ElaborationContext"
        )
        own_cuts = own_context.get("cuts")
        if not isinstance(own_cuts, tuple) or not own_cuts:
            raise ModelExecutionError("observer Context must contain its own Cuts")
        for reference in own_cuts:
            if not isinstance(reference, Name):
                raise ModelExecutionError("observer Cut must be a Name")
            cut = self.trusted.causal_cut(reference.value)
            if (
                cut["instance_name"] != source_domain
                or cut["observer"] != observer
            ):
                raise ModelExecutionError("observer Context cannot contain foreign Cuts")

        if len(set(allowed_executors)) != len(allowed_executors):
            raise ModelExecutionError("duplicate observer executor admission")
        for executor in allowed_executors:
            if executor not in self.executors:
                raise ModelExecutionError("observer executor must be registered")
            descriptor = _require_kind(
                self.trusted.named_eidos_value(executor)["value"],
                "ModelExecutor",
            )

        protocol = self.machine.persist(
            kind="process-protocol",
            request_id=f"{request_id}:protocol",
            value=protocol_value(
                role="InquiryResponder",
                operations=(
                    operation_value(OBSERVER_INSPECT),
                    operation_value(OBSERVER_CONSULT),
                    operation_value(OBSERVER_DEFER),
                    operation_value(OBSERVER_OFFER, terminal=True),
                    operation_value(OBSERVER_REFUSE, terminal=True),
                ),
                checkpoint_kind="ObserverCheckpoint",
                process_alias="observer_process",
            ),
        )
        accepted = accept_inquiry(
            self.trusted,
            inquiry=inquiry,
            discloser_projection=discloser_projection,
            request_id=f"{request_id}:accept",
        )
        process = self._persist(
            kind="observer-process",
            request_id=f"{request_id}:process",
            value=RecordValue.from_mapping({
                "$kind": "ObserverProcess",
                "protocol": Name(protocol),
                "authority_domain": Name(source_domain),
                "inquiry": Name(inquiry),
                "provider": question.get("provider"),
                "observer": observer,
                "source_domain": Name(source_domain),
                "context": Name(context),
                "acceptance": Name(accepted["acceptance"]),
                "program": program,
                "allowed_executors": tuple(Name(executor) for executor in allowed_executors),
            }),
        )
        responder = accepted["responder"]
        process_input = RecordValue.from_mapping({
            "$kind": "ObserverInput",
            "inquiry": Name(inquiry),
            "question": question.get("question"),
            "provider": question.get("provider"),
            "context": Name(context),
        })
        bindings = (
            Bindings()
            .bind(OBSERVER_SOCKET_ROLE, Socket(Name(responder)))
            .bind(OBSERVER_CONTEXT_ROLE, Name(context))
            .bind(OBSERVER_INQUIRY_ROLE, Name(inquiry))
        )
        realized = PraxisCore().realize(
            Apply(Lit(program), (Lit(process_input),)),
            bindings=bindings,
        )
        if not isinstance(realized, Suspended):
            raise ModelExecutionError("observer program must suspend on responder Socket")
        self._check_suspension(
            realized, inquiry=inquiry, responder=responder, observer=observer
        )
        checkpoint = self._checkpoint(
            process=process, inquiry=inquiry, step=0,
            suspended=realized, previous=None, parent_occurrence=None,
            request_id=f"{process}:checkpoint:0",
        )
        return ObserverProgress(
            process=process, inquiry=inquiry, checkpoint=checkpoint
        )

    def advance(self, checkpoint: str) -> ObserverProgress:
        """Advance one ordinary ProcessProtocol step through the shared machine."""

        try:
            progressed = self.machine.advance(
                checkpoint,
                interpret=self._interpret_step,
                finish=self._finish_continuation,
                validate=self._validate_process_state,
                identity=self.identity,
            )
        except ProcessRuntimeError as exc:
            raise ModelExecutionError(str(exc)) from exc
        descriptor = _require_kind(
            self.trusted.named_eidos_value(progressed.process)["value"],
            "ObserverProcess",
        )
        return ObserverProgress(
            process=progressed.process,
            inquiry=descriptor.get("inquiry").value,
            checkpoint=progressed.checkpoint,
            outcome=progressed.outcome,
            occurrence=progressed.occurrence,
        )

    def _validate_process_state(self, state: ProcessState) -> None:
        descriptor = _require_kind(state.descriptor, "ObserverProcess")
        inquiry = descriptor.get("inquiry")
        if not isinstance(inquiry, Name) or state.get("inquiry") != inquiry:
            raise ModelExecutionError("observer checkpoint has wrong Inquiry")
        self._check_suspension(
            state.suspended,
            inquiry=inquiry.value,
            responder=state.suspended.socket.name.value,
            observer=descriptor.get("observer"),
        )

    def _interpret_step(self, state: ProcessState) -> ProcessReaction:
        process, checkpoint = state.process, state.checkpoint
        descriptor = state.descriptor
        inquiry_ref = descriptor.get("inquiry")
        inquiry = inquiry_ref.value
        suspended = state.suspended
        observer = descriptor.get("observer")

        if suspended.operation in (OBSERVER_INSPECT, OBSERVER_CONSULT):
            prepared_name, prepared = self._prepare(
                process=process, checkpoint=checkpoint,
                descriptor=descriptor, suspended=suspended,
            )
            response = prepared.get("response")
            current = suspended.socket.name.value
            event = self.trusted.commit_projection_occurrence(
                kind={
                    OBSERVER_INSPECT: "ObserverInspect",
                    OBSERVER_CONSULT: "ObserverConsult",
                }[suspended.operation],
                consumes=(current,),
                establishes=(
                    ProjectionGrant(
                        key="next:responder",
                        holder=observer,
                        description=self.trusted.named_eidos_value(current)["value"],
                    ),
                ),
                fact={
                    "inquiry": inquiry,
                    "observer_process": process,
                    "checkpoint": checkpoint,
                    "operation": suspended.operation.value,
                    "prepared": prepared_name,
                    "response_cid": content_id(response),
                },
                request_id=f"{process}:{checkpoint}:step",
            )
            next_responder = event["established"]["next:responder"]
            occurrence = event["occurrence"]
            self.trusted.bind_eidos_value(
                name=occurrence,
                value=RecordValue.from_mapping({
                    "$kind": "ObserverInteraction",
                    "inquiry": inquiry_ref,
                    "observer_process": Name(process),
                    "checkpoint": Name(checkpoint),
                    "operation": suspended.operation,
                    "prepared": Name(prepared_name),
                    "request": suspended.argument,
                    "response": response,
                    "responder": suspended.socket.name,
                    "next_responder": Name(next_responder),
                }),
                request_id=f"{process}:{checkpoint}:occurrence",
            )
        else:
            # Interpretation of inquiry decisions belongs to this protocol,
            # not to the process machine's generic continuation loop.
            argument = suspended.argument
            if not isinstance(argument, RecordValue):
                raise ModelExecutionError("observer decision must be an Eidos Value")
            decision, cut = self._decision(suspended.operation, argument, descriptor)
            result = decide_inquiry(
                self.trusted,
                inquiry=inquiry,
                responder_projection=suspended.socket.name.value,
                decision=decision,
                cut=cut,
                request_id=f"{process}:{checkpoint}:decision",
            )
            occurrence = result["occurrence"]
            next_responder = result["responder"]
            response = RecordValue.from_mapping({
                "$kind": "ObserverDecisionResult",
                "inquiry": inquiry_ref,
                "decision": decision,
                "occurrence": Name(occurrence),
                "cut": None if cut is None else Name(cut),
            })

        return ProcessReaction(
            reaction=Reaction(
                name=Name(occurrence),
                consumed=suspended.socket,
                successor=(
                    None if next_responder is None else Socket(Name(next_responder))
                ),
                value=response,
            ),
        )

    def _finish_continuation(self, completed: ProcessContinuation) -> str:
        state = completed.state
        if state.suspended.operation not in (OBSERVER_OFFER, OBSERVER_REFUSE):
            raise ModelExecutionError(
                "observer process cannot finish without Offer or Refuse"
            )
        if not isinstance(completed.resumed, Done):
            raise ModelExecutionError("observer did not complete its continuation")
        descriptor = state.descriptor
        inquiry = descriptor.get("inquiry")
        occurrence = completed.transition.reaction.name.value
        return self._persist(
            kind="observer-outcome",
            request_id=f"{state.process}:{state.checkpoint}:outcome",
            value=RecordValue.from_mapping({
                "$kind": "ObserverOutcome",
                "observer_process": Name(state.process),
                "inquiry": inquiry,
                "context": descriptor.get("context"),
                "decision": Name(occurrence),
                "result": completed.resumed.value,
                "checkpoints": tuple(
                    Name(name) for name in completed.checkpoints
                ),
                "occurrences": tuple(
                    Name(name) for name in completed.occurrences
                ),
            }),
        )

    def _decision(
        self,
        operation: Name,
        argument: RecordValue,
        descriptor: RecordValue,
    ) -> tuple[str, str | None]:
        if operation == OBSERVER_DEFER:
            _require_kind(argument, "ObserverDeferRequest")
            return "defer", None
        if operation == OBSERVER_REFUSE:
            _require_kind(argument, "ObserverRefuseRequest")
            return "refuse", None
        if operation == OBSERVER_OFFER:
            _require_kind(argument, "ObserverOfferRequest")
            cut = argument.get("cut")
            if not isinstance(cut, Name):
                raise ModelExecutionError("ObserverOffer requires Cut Name")
            context = _require_kind(
                self.trusted.named_eidos_value(descriptor.get("context").value)["value"],
                "ElaborationContext",
            )
            if cut not in context.get("cuts"):
                raise ModelExecutionError(
                    "ObserverOffer requires a Cut explicitly in observer Context"
                )
            return "offer", cut.value
        raise ModelExecutionError("unsupported observer decision")

    def _prepare(
        self,
        *,
        process: str,
        checkpoint: str,
        descriptor: RecordValue,
        suspended: Suspended,
    ) -> tuple[str, RecordValue]:
        for name, value in self.trusted.named_values():
            if (
                isinstance(value, RecordValue)
                and _field(value, "$kind") == "ObserverPreparedStep"
                and _field(value, "checkpoint") == Name(checkpoint)
                and _field(value, "observer_process") == Name(process)
            ):
                return name, value

        response = self._respond(descriptor=descriptor, suspended=suspended)
        canonical_bytes(response)
        prepared = RecordValue.from_mapping({
            "$kind": "ObserverPreparedStep",
            "observer_process": Name(process),
            "checkpoint": Name(checkpoint),
            "request": suspended.argument,
            "operation": suspended.operation,
            "response": response,
        })
        name = self._persist(
            kind="observer-prepared",
            request_id=f"{process}:{checkpoint}:prepared",
            value=prepared,
        )
        return name, prepared

    def _respond(
        self, *, descriptor: RecordValue, suspended: Suspended,
    ) -> RecordValue:
        request = suspended.argument
        if not isinstance(request, RecordValue):
            raise ModelExecutionError("observer step requires RecordValue argument")
        context = descriptor.get("context")
        if not isinstance(context, Name):
            raise ModelExecutionError("observer process has no Context")
        inquiry = descriptor.get("inquiry")
        if not isinstance(inquiry, Name):
            raise ModelExecutionError("observer process lacks Inquiry")

        if suspended.operation == OBSERVER_INSPECT:
            _require_kind(request, "InspectRequest")
            target = request.get("target")
            if not isinstance(target, Name):
                raise ModelExecutionError("ObserverInspect target must be a Name")
            scope = admitted_inspection_scope(
                context,
                resolve=lambda name: self.trusted.named_eidos_value(name)["value"],
                max_nodes=self.max_scope_nodes,
            )
            scope.add(inquiry.value)
            if target.value not in scope:
                raise ModelExecutionError("ObserverInspect target outside scoped Context")
            return RecordValue.from_mapping({
                "$kind": "InspectedValue",
                "target": target,
                "value": self.trusted.named_eidos_value(target.value)["value"],
                "context": context,
            })

        if suspended.operation == OBSERVER_CONSULT:
            _require_kind(request, "ConsultRequest")
            executor = request.get("executor")
            if (
                not isinstance(executor, Name)
                or executor not in descriptor.get("allowed_executors")
                or executor.value not in self.executors
            ):
                raise ModelExecutionError(
                    "ObserverConsult requires an explicitly admitted executor"
                )
            _require_kind(
                self.trusted.named_eidos_value(executor.value)["value"],
                "ModelExecutor",
            )
            question = request.get("question")
            if not isinstance(question, str) or not question:
                raise ModelExecutionError("ObserverConsult requires a question")
            consultation = RecordValue.from_mapping({
                "$kind": "ObserverConsultation",
                "inquiry": inquiry,
                "context": context,
                "observer": descriptor.get("observer"),
                "question": question,
                "executor": executor,
            })
            response = self.executors[executor.value](consultation)
            _require_kind(response, "ObserverAdvice")
            if response.get("context") != context:
                raise ModelExecutionError("ObserverAdvice names wrong Context")
            return response

        raise ModelExecutionError("not an informational observer operation")

    def _check_suspension(
        self,
        suspended: Suspended,
        *,
        inquiry: str,
        responder: str,
        observer: str,
    ) -> None:
        if suspended.socket.name.value != responder:
            raise ModelExecutionError("observer performed on a foreign Socket")
        if suspended.operation not in (
            OBSERVER_INSPECT, OBSERVER_CONSULT,
            OBSERVER_DEFER, OBSERVER_OFFER, OBSERVER_REFUSE,
        ):
            raise ModelExecutionError("observer attempted inadmissible operation")
        row = self.trusted.projection(responder)
        _, provider = _inquiry(self.trusted, inquiry)
        if (
            row.get("role") != "InquiryResponder"
            or row.get("protocol_state") != f"inquiry:{inquiry}"
            or row["domain_name"] != provider.get("source_domain").value
            or row["holder"] != observer
            or observer != provider.get("observer")
        ):
            raise ModelExecutionError("observer has no live responder authority")
        if self.identity is not None and self.identity != observer:
            raise ModelExecutionError("observer process holder mismatch")
        if not _responder_in_lineage(self.trusted, inquiry, responder):
            raise ModelExecutionError(
                "observer responder Socket has no admitted causal lineage"
            )

    def _checkpoint(
        self,
        *,
        process: str,
        inquiry: str,
        step: int,
        suspended: Suspended,
        previous: str | None,
        parent_occurrence: str | None,
        request_id: str,
    ) -> str:
        return self._persist(
            kind="observer-checkpoint",
            request_id=request_id,
            value=RecordValue.from_mapping({
                "$kind": "ObserverCheckpoint",
                "observer_process": Name(process),
                "inquiry": Name(inquiry),
                "step": step,
                "suspension": suspended,
                "previous": None if previous is None else Name(previous),
                "parent_occurrence": (
                    None if parent_occurrence is None else Name(parent_occurrence)
                ),
            }),
        )

    def _lineage(self, checkpoint: str) -> tuple[str, ...]:
        result: list[str] = []
        seen: set[str] = set()
        cursor: str | None = checkpoint
        while cursor is not None:
            if cursor in seen:
                raise ModelExecutionError("cyclic observer checkpoint lineage")
            seen.add(cursor)
            result.append(cursor)
            value = _require_kind(
                self.trusted.named_eidos_value(cursor)["value"], "ObserverCheckpoint"
            )
            previous = value.get("previous")
            cursor = None if previous is None else previous.value
        return tuple(reversed(result))

    def _occurred_lineage(self, lineage: tuple[str, ...]) -> tuple[str, ...]:
        events: list[str] = []
        for checkpoint in lineage:
            value = _require_kind(
                self.trusted.named_eidos_value(checkpoint)["value"], "ObserverCheckpoint"
            )
            parent = value.get("parent_occurrence")
            if isinstance(parent, Name):
                events.append(parent.value)
        return tuple(events)

    def _persist(
        self,
        *,
        kind: str,
        value: RecordValue,
        request_id: str,
    ) -> str:
        name = self.trusted.reserve_name(
            kind=kind, request_id=f"{request_id}:reserve"
        )
        self.trusted.bind_eidos_value(
            name=name, value=value, request_id=f"{request_id}:bind"
        )
        return name


def _field(value: Any, key: str) -> Any:
    if isinstance(value, RecordValue):
        try:
            return value.get(key)
        except KeyError:
            return None
    return None
