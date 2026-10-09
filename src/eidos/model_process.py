from __future__ import annotations

"""Resumable epistemic processes made of ordinary Eidos continuations.

A ModelProcess runs a Closure until it suspends on its own linear Socket.
Inspect and Consult are ordinary perform operations interpreted by an explicit
host-side responder. Their generic Trusted Machinery occurrences consume only
the ModelProcess projection, NEVER a world projection from an observed Cut.

Every suspension is captured in an immutable named ModelCheckpoint. Replies
are saved as immutable ModelPreparedSteps before authority is consumed, so
recovery after a commit but before local resume can reconstruct the same next
continuation without rerunning a prepared external consultation.

This adapter is a local authority-domain experiment, not an isolated runtime:
a configured external consultation is NOT sandboxed or exactly-once.
"""

from dataclasses import dataclass
from typing import Any, Callable, Mapping
from uuid import uuid4

from .authority import ProjectionGrant
from .core import (
    Apply, Bindings, Closure, Done, Lit, Name, PraxisCore, Reaction,
    RecordValue, Role, Socket, Suspended, canonical_bytes, content_id, to_data,
)
from .epistemics import _require_kind, context_value
from .lenses import walk_named_values
from .cut_exchange import cut_request, validate_disclosure
from .model_execution import (
    MODEL_CONTEXT_ROLE, MODEL_INPUT_ROLE, MODEL_ROLE,
    ModelAdapter, ModelExecutionError,
)
from .semantic_values import projection_value
from .trusted import TrustedMachinery


PROCESS_SOCKET_ROLE = Role("elaboration", "process-socket")
INSPECT = Name("model:Inspect")
CONSULT = Name("model:Consult")
ACQUIRE = Name("model:Acquire")
HANDOFF = Name("model:Handoff")
PROCESS_ROLE = "ModelProcess"


def acquisition_request(provider: Name | str, cut: Name | str) -> RecordValue:
    return cut_request(provider, cut)


def handoff_request(target: str) -> RecordValue:
    if not target:
        raise ModelExecutionError("handoff target must be nonempty")
    return RecordValue.from_mapping({
        "$kind": "HandoffRequest",
        "target": target,
    })


def cut_provider_value(label: str) -> RecordValue:
    if not label:
        raise ModelExecutionError("CutProvider label must be nonempty")
    return RecordValue.from_mapping({
        "$kind": "CutProvider",
        "label": label,
    })


@dataclass(frozen=True)
class ProcessProgress:
    """Pointer to an immutable checkpoint or completed outcome."""

    run: str
    checkpoint: str | None = None
    outcome: str | None = None
    occurrence: str | None = None
    handoff_to: str | None = None


def inspection_request(target: Name | str) -> RecordValue:
    return RecordValue.from_mapping({
        "$kind": "InspectRequest",
        "target": target if isinstance(target, Name) else Name(target),
    })


def consultation_request(
    executor: Name | str,
    *,
    question: str,
) -> RecordValue:
    if not question:
        raise ModelExecutionError("consultation question must be nonempty")
    return RecordValue.from_mapping({
        "$kind": "ConsultRequest",
        "executor": executor if isinstance(executor, Name) else Name(executor),
        "question": question,
    })


class ModelProcessRunner:
    """Drive a Model Closure across durable, linear epistemic interactions."""

    def __init__(
        self,
        trusted: TrustedMachinery,
        *,
        executors: Mapping[str, ModelAdapter] | None = None,
        providers: Mapping[str, Callable[[RecordValue], str]] | None = None,
        identity: str | None = None,
        max_steps: int = 8,
        max_scope_nodes: int = 256,
    ) -> None:
        if max_steps <= 0 or max_scope_nodes <= 0:
            raise ValueError("process budgets must be positive")
        self.trusted = trusted
        self.executors = dict(executors or {})
        self.consultations: dict[str, set[str]] = {}
        self.providers = dict(providers or {})
        self.acquisitions: dict[str, set[str]] = {}
        self.handoffs: dict[str, set[str]] = {}
        self.identity = identity
        self.max_steps = max_steps
        self.max_scope_nodes = max_scope_nodes

    def authorize_consultation(self, *, model: str, executor: str) -> None:
        """Admit one Model -> Executor delegation on the host side.

        An executor's Name and mere registration do not authorize all Models
        to invoke it. The admitted list is captured in each process genesis
        description so it remains inspectable after the process is handed off.
        """

        if executor not in self.executors:
            raise ModelExecutionError("executor must be explicitly registered")
        _require_kind(
            self.trusted.named_eidos_value(executor)["value"], "ModelExecutor"
        )
        named_model = _require_kind(
            self.trusted.named_eidos_value(model)["value"], "Model"
        )
        if named_model.get("engine") != "process":
            raise ModelExecutionError(
                "consultation admission requires a process Model"
            )
        self.consultations.setdefault(model, set()).add(executor)

    def authorize_cut_acquisition(self, *, model: str, provider: str) -> None:
        """Admit which provider a given process Model may request new Cuts from."""

        if provider not in self.providers:
            raise ModelExecutionError("CutProvider must be explicitly registered")
        _require_kind(
            self.trusted.named_eidos_value(provider)["value"], "CutProvider"
        )
        self._require_process_model(model)
        self.acquisitions.setdefault(model, set()).add(provider)

    def authorize_handoff(self, *, model: str, target: str) -> None:
        """Admit a target holder for linear process continuation transfer."""

        if not target:
            raise ModelExecutionError("handoff target must be nonempty")
        self._require_process_model(model)
        self.handoffs.setdefault(model, set()).add(target)

    def _require_process_model(self, model: str) -> RecordValue:
        named = _require_kind(
            self.trusted.named_eidos_value(model)["value"], "Model"
        )
        if named.get("engine") != "process":
            raise ModelExecutionError("epistemic operation requires a process Model")
        return named

    def start(
        self,
        *,
        name: str,
        program: Closure,
        request: RecordValue,
        request_id: str | None = None,
    ) -> ProcessProgress:
        """Admit a separate epistemic authority domain and checkpoint its process."""

        _require_kind(request, "ModelInput")
        context = request.get("context")
        if not isinstance(context, Name):
            raise ModelExecutionError("ModelInput context must be a Name")
        if not isinstance(program, Closure):
            raise ModelExecutionError("ModelProcess requires a Closure")
        declared = _require_kind(
            self.trusted.named_eidos_value(name)["value"], "Model"
        )
        if (
            declared.get("engine") != "process"
            or declared.get("implementation") != program
        ):
            raise ModelExecutionError(
                "process program must match the immutable named Model"
            )
        if request.get("model") != Name(name):
            raise ModelExecutionError(
                "ModelInput must name the executable Model"
            )
        invocation = request_id or f"process:{uuid4().hex}"
        allowed_executors = tuple(
            Name(executor) for executor in sorted(self.consultations.get(name, ()))
        )
        allowed_providers = tuple(
            Name(provider) for provider in sorted(self.acquisitions.get(name, ()))
        )
        allowed_handoffs = tuple(sorted(self.handoffs.get(name, ())))
        owner = self.identity or name
        domain = self.trusted.admit_authority_domain(
            description=RecordValue.from_mapping({
                "$kind": "ModelProcess",
                "model": Name(name),
                "context": context,
                "input": request,
                "program": program,
                "allowed_executors": allowed_executors,
                "allowed_providers": allowed_providers,
                "allowed_handoffs": allowed_handoffs,
            }),
            establishes=(
                ProjectionGrant(
                    key="step:0",
                    holder=owner,
                    description=projection_value(
                        key="model-process:step:0",
                        role=PROCESS_ROLE,
                        state="step:0",
                    ),
                ),
            ),
            request_id=f"{invocation}:genesis",
        )
        run = domain["domain"]
        socket = Socket(Name(domain["projections"]["step:0"]))
        bindings = (
            Bindings()
            .bind(MODEL_ROLE, Name(name))
            .bind(MODEL_INPUT_ROLE, request)
            .bind(MODEL_CONTEXT_ROLE, context)
            .bind(PROCESS_SOCKET_ROLE, socket)
        )
        result = PraxisCore().realize(
            Apply(Lit(program), (Lit(request),)),
            bindings=bindings,
        )
        if isinstance(result, Done):
            return self._finish(
                run=run,
                projection=socket.name.value,
                proposal=result.value,
                events=(),
                checkpoints=(),
                parent=None,
                context=context,
                request_id=f"{run}:initial-finish",
            )
        if not isinstance(result, Suspended):
            raise ModelExecutionError("Model process must suspend or complete")
        self._check_suspension(result, socket.name.value)
        checkpoint = self._checkpoint(
            run=run,
            step=0,
            suspended=result,
            previous=None,
            parent_occurrence=None,
            context=context,
            request_id=f"{run}:checkpoint:0",
        )
        return ProcessProgress(run=run, checkpoint=checkpoint)

    def advance(self, checkpoint: str) -> ProcessProgress:
        """Commit one process interaction; recover deterministically on retry."""

        state = _require_kind(
            self.trusted.named_eidos_value(checkpoint)["value"],
            "ModelCheckpoint",
        )
        run_ref = state.get("run")
        suspended = state.get("suspension")
        step = state.get("step")
        if not isinstance(run_ref, Name) or not isinstance(suspended, Suspended):
            raise ModelExecutionError("malformed ModelCheckpoint")
        if not isinstance(step, int) or step < 0 or step >= self.max_steps:
            raise ModelExecutionError("model process step budget exceeded")
        run = run_ref.value
        descriptor = _require_kind(
            self.trusted.named_eidos_value(run)["value"], "ModelProcess"
        )
        context = state.get("context")
        if not isinstance(context, Name):
            # Backward compatible with checkpoints created by older experiments.
            context = descriptor.get("context")
        if not isinstance(context, Name):
            raise ModelExecutionError("process checkpoint lacks a Context Name")

        self._check_suspension(suspended, suspended.socket.name.value)
        holder = self._check_projection(run, suspended.socket.name.value)
        prepared_name, prepared = self._prepare(
            run=run, checkpoint=checkpoint, context=context,
            suspended=suspended, descriptor=descriptor,
        )
        response = prepared.get("response")
        next_context = context
        source_occurrence: Name | None = None
        if suspended.operation == ACQUIRE:
            if _field(response, "$kind") != "AcquiredContext":
                raise ModelExecutionError("Acquire must return AcquiredContext")
            next_context = response.get("context")
            source_occurrence = response.get("disclosure")
            if not isinstance(next_context, Name) or not isinstance(source_occurrence, Name):
                raise ModelExecutionError("acquisition lacks named Context or causal source")

        target_holder = holder
        if suspended.operation == HANDOFF:
            if _field(response, "$kind") != "HandoffAccepted":
                raise ModelExecutionError("Handoff must return HandoffAccepted")
            target_holder = response.get("target")
            if not isinstance(target_holder, str) or not target_holder:
                raise ModelExecutionError("handoff target must be nonempty")

        grant_key = f"step:{step + 1}"
        commit = self.trusted.commit_projection_occurrence(
            kind="ModelInteraction",
            consumes=(suspended.socket.name.value,),
            establishes=(
                ProjectionGrant(
                    key=grant_key,
                    holder=target_holder,
                    description=projection_value(
                        key=f"model-process:{grant_key}",
                        role=PROCESS_ROLE,
                        state=grant_key,
                    ),
                ),
            ),
            fact={
                "run": run,
                "checkpoint": checkpoint,
                "prepared": prepared_name,
                "operation": suspended.operation.value,
                "request": to_data(suspended.argument),
                "response_cid": content_id(response),
                "context": context.value,
                "next_context": next_context.value,
                "causal_source": (
                    None if source_occurrence is None else source_occurrence.value
                ),
                "next_holder": target_holder,
            },
            request_id=f"{run}:{checkpoint}:interact",
        )
        next_socket = commit["established"][grant_key]
        occurrence = commit["occurrence"]
        self._bind(
            name=occurrence,
            value=RecordValue.from_mapping({
                "$kind": "ModelInteraction",
                "run": Name(run),
                "checkpoint": Name(checkpoint),
                "prepared": Name(prepared_name),
                "operation": suspended.operation,
                "request": suspended.argument,
                "response": response,
                "context": context,
                "next_context": next_context,
                "causal_source": source_occurrence,
                "consumed": suspended.socket.name,
                "successor": Name(next_socket),
                "next_holder": target_holder,
            }),
            request_id=f"{run}:{checkpoint}:occurrence-value",
        )
        resumed = PraxisCore().resume(
            suspended,
            Reaction(
                name=Name(occurrence),
                consumed=suspended.socket,
                successor=Socket(Name(next_socket)),
                value=response,
            ),
        )
        checkpoints = self._checkpoint_lineage(checkpoint)
        events = self._occurred_lineage(checkpoints) + (occurrence,)
        if isinstance(resumed, Done):
            if target_holder != holder:
                raise ModelExecutionError("Handoff must produce a resumable continuation")
            return self._finish(
                run=run,
                projection=next_socket,
                proposal=resumed.value,
                events=events,
                checkpoints=checkpoints,
                parent=occurrence,
                context=next_context,
                request_id=f"{run}:{checkpoint}:finish",
            )
        if not isinstance(resumed, Suspended):
            raise ModelExecutionError("resumed Model must suspend or complete")
        self._check_suspension(resumed, next_socket)
        next_checkpoint = self._checkpoint(
            run=run,
            step=step + 1,
            suspended=resumed,
            previous=checkpoint,
            parent_occurrence=occurrence,
            context=next_context,
            request_id=f"{run}:{checkpoint}:next-checkpoint",
        )
        return ProcessProgress(
            run=run,
            checkpoint=next_checkpoint,
            occurrence=occurrence,
            handoff_to=target_holder if target_holder != holder else None,
        )

    def execute(
        self,
        *,
        name: str,
        program: Closure,
        request: RecordValue,
    ) -> tuple[RecordValue, Name]:
        """Drive a Model process to completion, preserving all intermediate steps."""

        progress = self.start(name=name, program=program, request=request)
        while progress.checkpoint is not None:
            progress = self.advance(progress.checkpoint)
        if progress.outcome is None:
            raise ModelExecutionError("Model process did not produce an outcome")
        outcome = _require_kind(
            self.trusted.named_eidos_value(progress.outcome)["value"],
            "ModelProcessOutcome",
        )
        return _require_kind(outcome.get("proposal"), "ModelProposal"), Name(progress.outcome)

    def _prepare(
        self,
        *,
        run: str,
        checkpoint: str,
        suspended: Suspended,
        descriptor: RecordValue,
    ) -> tuple[str, RecordValue]:
        for name, value in self.trusted.named_values():
            if (
                isinstance(value, RecordValue)
                and _field(value, "$kind") == "ModelPreparedStep"
                and value.get("checkpoint") == Name(checkpoint)
            ):
                return name, value

        response = self._respond(
            descriptor=descriptor,
            suspended=suspended,
        )
        canonical_bytes(response)
        prepared = RecordValue.from_mapping({
            "$kind": "ModelPreparedStep",
            "run": Name(run),
            "checkpoint": Name(checkpoint),
            "request": suspended.argument,
            "operation": suspended.operation,
            "response": response,
        })
        name = self._persist(
            kind="model-prepared", value=prepared,
            request_id=f"{run}:{checkpoint}:prepared",
        )
        return name, prepared

    def _respond(self, *, descriptor: RecordValue, suspended: Suspended) -> RecordValue:
        request = suspended.argument
        if not isinstance(request, RecordValue):
            raise ModelExecutionError("epistemic operation requires a RecordValue")

        model_input = _require_kind(descriptor.get("input"), "ModelInput")
        context = model_input.get("context")
        if suspended.operation == INSPECT:
            _require_kind(request, "InspectRequest")
            target = request.get("target")
            if not isinstance(target, Name):
                raise ModelExecutionError("Inspect target must be a Name")
            roots = (context, *model_input.get("cuts"))
            neighborhood = walk_named_values(
                roots,
                resolve=lambda name: self.trusted.named_eidos_value(name)["value"],
                depth=12,
            )
            if len(neighborhood.nodes) > self.max_scope_nodes:
                raise ModelExecutionError("inspection exceeds scoped context limit")
            if target.value not in neighborhood.by_name():
                raise ModelExecutionError("Inspect target is outside scoped Context")
            return RecordValue.from_mapping({
                "$kind": "InspectedValue",
                "target": target,
                "value": self.trusted.named_eidos_value(target.value)["value"],
            })

        if suspended.operation == CONSULT:
            _require_kind(request, "ConsultRequest")
            executor = request.get("executor")
            if (
                not isinstance(executor, Name)
                or executor not in descriptor.get("allowed_executors")
            ):
                raise ModelExecutionError("Consult requires explicitly delegated executor authority")
            if executor.value not in self.executors:
                raise ModelExecutionError("Consult requires a registered executor")
            desc = _require_kind(
                self.trusted.named_eidos_value(executor.value)["value"],
                "ModelExecutor",
            )
            if not isinstance(request.get("question"), str):
                raise ModelExecutionError("Consult requires a textual question")
            consultation = RecordValue.from_mapping({
                "$kind": "ModelConsultation",
                "context": context,
                "model": descriptor.get("model"),
                "cuts": model_input.get("cuts"),
                "facts": model_input.get("facts"),
                "question": request.get("question"),
                "executor": executor,
            })
            reply = self.executors[executor.value](consultation)
            _require_kind(reply, "ModelProposal")
            if reply.get("context") != context:
                raise ModelExecutionError("consultation reply names the wrong Context")
            canonical_bytes(reply)
            return reply

        raise ModelExecutionError(
            f"operation {suspended.operation.value!r} is not an epistemic interaction"
        )

    def _finish(
        self,
        *,
        run: str,
        projection: str,
        proposal: Any,
        events: tuple[str, ...],
        checkpoints: tuple[str, ...],
        parent: str | None,
        request_id: str,
    ) -> ProcessProgress:
        _require_kind(proposal, "ModelProposal")
        domain = _require_kind(
            self.trusted.named_eidos_value(run)["value"], "ModelProcess"
        )
        if proposal.get("context") != domain.get("context"):
            raise ModelExecutionError("process proposal names the wrong Context")
        canonical_bytes(proposal)
        committed = self.trusted.commit_projection_occurrence(
            kind="ModelProcessFinish",
            consumes=(projection,),
            establishes=(),
            fact={
                "run": run,
                "proposal_cid": content_id(proposal),
                "parent": parent,
                "events": list(events),
            },
            request_id=request_id,
        )
        outcome = committed["occurrence"]
        self._bind(
            name=outcome,
            value=RecordValue.from_mapping({
                "$kind": "ModelProcessOutcome",
                "run": Name(run),
                "proposal": proposal,
                "events": tuple(Name(event) for event in events),
                "checkpoints": tuple(Name(name) for name in checkpoints),
                "parent": None if parent is None else Name(parent),
            }),
            request_id=f"{run}:{outcome}:outcome-value",
        )
        return ProcessProgress(run=run, outcome=outcome, occurrence=outcome)

    def _check_projection(self, run: str, projection: str) -> None:
        row = self.trusted.projection(projection)
        if (
            row["domain_name"] != run or row.get("role") != PROCESS_ROLE
        ):
            raise ModelExecutionError("process Socket is outside its epistemic domain")
        # A spent projection is allowed here only for idempotent step recovery;
        # the TM command still checks/replays the original commit.

    def _check_suspension(self, suspended: Suspended, expected: str) -> None:
        if suspended.socket.name.value != expected:
            raise ModelExecutionError(
                "Model attempted perform against a Socket outside its own continuation"
            )
        if suspended.operation not in (INSPECT, CONSULT):
            raise ModelExecutionError("Model attempted an inadmissible operation")

    def _checkpoint(
        self,
        *,
        run: str,
        step: int,
        suspended: Suspended,
        previous: str | None,
        parent_occurrence: str | None,
        request_id: str,
    ) -> str:
        return self._persist(
            kind="model-checkpoint",
            value=RecordValue.from_mapping({
                "$kind": "ModelCheckpoint",
                "run": Name(run),
                "step": step,
                "suspension": suspended,
                "previous": None if previous is None else Name(previous),
                "parent_occurrence": (
                    None if parent_occurrence is None else Name(parent_occurrence)
                ),
            }),
            request_id=request_id,
        )

    def _checkpoint_lineage(self, checkpoint: str) -> tuple[str, ...]:
        result: list[str] = []
        visited: set[str] = set()
        cursor: str | None = checkpoint
        while cursor is not None:
            if cursor in visited:
                raise ModelExecutionError("cyclic model checkpoint history")
            visited.add(cursor)
            result.append(cursor)
            row = _require_kind(
                self.trusted.named_eidos_value(cursor)["value"],
                "ModelCheckpoint",
            )
            previous = row.get("previous")
            cursor = None if previous is None else previous.value
        return tuple(reversed(result))

    def _occurred_lineage(self, checkpoints: tuple[str, ...]) -> tuple[str, ...]:
        events: list[str] = []
        for checkpoint in checkpoints:
            row = _require_kind(
                self.trusted.named_eidos_value(checkpoint)["value"],
                "ModelCheckpoint",
            )
            parent = row.get("parent_occurrence")
            if isinstance(parent, Name):
                events.append(parent.value)
        return tuple(events)

    def _persist(self, *, kind: str, value: RecordValue, request_id: str) -> str:
        name = self.trusted.reserve_name(
            kind=kind, request_id=f"{request_id}:reserve"
        )
        self._bind(
            name=name, value=value,
            request_id=f"{request_id}:bind",
        )
        return name

    def _bind(self, *, name: str, value: RecordValue, request_id: str) -> None:
        self.trusted.bind_eidos_value(
            name=name, value=value, request_id=request_id
        )


def _field(value: RecordValue, key: str) -> Any:
    try:
        return value.get(key)
    except KeyError:
        return None
