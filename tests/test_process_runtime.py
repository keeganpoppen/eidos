import pytest

from eidos.authority import ProjectionGrant
from eidos.core import (
    Apply, Done, Get, Lambda, Lit, Name, Need, Perform, PraxisCore,
    Reaction, Record, RecordValue, Socket, Suspended, Var,
)
from eidos.discovery import discover_request, discovery_provider_value
from eidos.epistemics import context_value, model_value
from eidos.genesis import admit_genesis
from eidos.model_execution import model_input
from eidos.model_process import (
    AWAIT_DISCOVERY, DISCOVER, PROCESS_SOCKET_ROLE, ModelProcessRunner,
)
from eidos.observer_process import (
    OBSERVER_REFUSE, OBSERVER_SOCKET_ROLE, ObserverProcessRunner, refuse_request,
)
from eidos.occurrence import ProjectionTemplate, RecursiveProtocol
from eidos.process_runtime import (
    ProcessPending, ProcessReaction, ProcessRuntime, ProcessRuntimeError,
    operation_value, protocol_value,
)
from eidos.semantic_values import projection_value
from eidos.trusted import TrustedMachinery


def named(machine, kind, value, key):
    return machine.persist(kind=kind, value=value, request_id=key)


def test_a_third_role_needs_no_requester_or_responder_runtime():
    tm = TrustedMachinery()
    machine = ProcessRuntime(tm)
    op = Name("echo:Reply")
    protocol = named(
        machine, "process-protocol",
        protocol_value(role="Echo", operations=(operation_value(op, terminal=True),)),
        "echo:protocol",
    )
    domain = tm.admit_authority_domain(
        description=RecordValue.from_mapping({"$kind": "EchoDomain"}),
        establishes=(
            ProjectionGrant(
                key="speaker",
                holder="actor:echo",
                description=projection_value(key="echo:0", role="Echo", state="ready"),
            ),
        ),
        request_id="echo:genesis",
    )
    process = named(
        machine, "process",
        RecordValue.from_mapping({
            "$kind": "EchoParticipant",
            "protocol": Name(protocol),
            "authority_domain": Name(domain["domain"]),
        }),
        "echo:participant",
    )
    socket = Socket(Name(domain["projections"]["speaker"]))
    suspended = PraxisCore().realize(
        Perform(
            socket=Lit(socket),
            operation=op,
            argument=Lit("hello"),
            result_as="reply",
            successor_as="next",
            then=Var("reply"),
        )
    )
    assert isinstance(suspended, Suspended)
    checkpoint = machine.checkpoint(
        process=process,
        step=0,
        suspended=suspended,
        previous=None,
        parent_occurrence=None,
        extras={},
        request_id="echo:checkpoint",
    )

    invoked = []
    def interpret(state):
        invoked.append(state.suspended.operation)
        outcome = tm.commit_projection_occurrence(
            kind="EchoReply",
            consumes=(state.suspended.socket.name.value,),
            establishes=(),
            fact={"utterance": state.suspended.argument},
            request_id=f"{state.process}:{state.checkpoint}:echo",
        )
        return ProcessReaction(Reaction(
            name=Name(outcome["occurrence"]),
            consumed=state.suspended.socket,
            successor=None,
            value="hello back",
        ))

    def finish(done):
        assert isinstance(done.resumed, Done)
        assert done.resumed.value == "hello back"
        name = done.transition.reaction.name.value
        tm.bind_eidos_value(
            name=name,
            value=RecordValue.from_mapping({
                "$kind": "EchoOutcome",
                "value": done.resumed.value,
                "checkpoints": tuple(Name(n) for n in done.checkpoints),
            }),
            request_id="echo:outcome",
        )
        return name

    with pytest.raises(ProcessRuntimeError, match="no interpreter registered"):
        machine.advance_registered(checkpoint)

    machine.register_protocol(
        protocol,
        interpret=lambda state: ProcessPending("some-unrelated-question"),
        finish=finish,
        identity="actor:echo",
    )
    with pytest.raises(ProcessRuntimeError, match="may not remain pending"):
        machine.advance_registered(checkpoint)
    assert tm.projection(socket.name.value)["disposition"] == "live"

    machine.register_protocol(
        protocol, interpret=interpret, finish=finish, identity="actor:echo",
    )
    completed = machine.advance_registered(checkpoint)
    assert completed.outcome
    assert invoked == [op]
    assert tm.named_eidos_value(completed.outcome)["value"].get("$kind") == "EchoOutcome"
    assert tm.projection(socket.name.value)["disposition"] == "spent"

    # Recovery uses exactly the same idempotent causal occurrence.
    assert machine.advance_registered(checkpoint) == completed


def test_protocol_value_controls_operations_and_authority_not_python_role_labels():
    tm = TrustedMachinery()
    machine = ProcessRuntime(tm)
    protocol = named(
        machine, "process-protocol",
        protocol_value(role="Reader", operations=(
            operation_value("read:Accept", terminal=True),
        )),
        "reader:protocol",
    )
    domain = tm.admit_authority_domain(
        description=RecordValue.from_mapping({"$kind": "ReaderDomain"}),
        establishes=(
            ProjectionGrant(
                key="reader",
                holder="worker",
                description=projection_value(key="reader", role="Reader", state="ready"),
            ),
            ProjectionGrant(
                key="foreign",
                holder="worker",
                description=projection_value(key="foreign", role="DifferentRole", state="ready"),
            ),
        ),
        request_id="reader:genesis",
    )
    process = named(machine, "process", RecordValue.from_mapping({
        "$kind": "ReaderProcess",
        "protocol": Name(protocol),
        "authority_domain": Name(domain["domain"]),
    }), "reader:process")
    valid = Socket(Name(domain["projections"]["reader"]))
    foreign = Socket(Name(domain["projections"]["foreign"]))
    wrong_operation = PraxisCore().realize(
        Perform(
            socket=Lit(valid),
            operation=Name("read:Unauthorized"),
            argument=Lit(None),
            result_as="answer",
            successor_as="next",
            then=Var("answer"),
        )
    )
    wrong_role = PraxisCore().realize(
        Perform(
            socket=Lit(foreign),
            operation=Name("read:Accept"),
            argument=Lit(None),
            result_as="answer",
            successor_as="next",
            then=Var("answer"),
        )
    )
    for i, suspended in enumerate((wrong_operation, wrong_role)):
        ckpt = machine.checkpoint(
            process=process, step=0, suspended=suspended,
            previous=None, parent_occurrence=None, extras={},
            request_id=f"reader:invalid:{i}",
        )
        with pytest.raises(ProcessRuntimeError):
            machine.load(ckpt)
    assert tm.projection(valid.name.value)["disposition"] == "live"
    assert tm.projection(foreign.name.value)["disposition"] == "live"


def test_one_host_interleaves_requester_and_responder_by_protocol_identity():
    tm = TrustedMachinery()
    machine = ProcessRuntime(tm, max_steps=16)
    protocol = RecursiveProtocol(
        name="generic-two-process-inquiry",
        initial=(
            ProjectionTemplate("A", "observing"),
            ProjectionTemplate("B", "observing"),
            ProjectionTemplate("Discloser", "ready"),
        ),
        reactions=(),
    )
    genesis = admit_genesis(
        tm, protocol,
        holders={"A": "O1", "B": "O2", "Discloser": "O2"},
        request_id="unified:genesis",
    )
    cut_a = tm.create_observed_cut(
        instance=genesis["domain"], observer="O1",
        protocol_cid=protocol.cid,
        projections=[genesis["projections"]["projection:A"]],
        request_id="unified:cut-a", elaborator="O1",
    )
    cut_b = tm.create_observed_cut(
        instance=genesis["domain"], observer="O2",
        protocol_cid=protocol.cid,
        projections=[genesis["projections"]["projection:B"]],
        request_id="unified:cut-b", elaborator="O2",
    )
    provider = named(
        machine, "provider",
        discovery_provider_value(
            label="O2", source_domain=genesis["domain"], observer="O2",
        ),
        "unified:provider",
    )

    requester_code = PraxisCore().realize(Lambda(
        ("request",),
        Perform(
            socket=Need(PROCESS_SOCKET_ROLE),
            operation=DISCOVER,
            argument=Lit(discover_request(provider, "Any related evidence?")),
            result_as="opened", successor_as="after_discover",
            then=Perform(
                socket=Var("after_discover"),
                operation=AWAIT_DISCOVERY,
                argument=Record.from_mapping({
                    "$kind": Lit("AwaitDiscoveryRequest"),
                    "inquiry": Get(Var("opened"), "inquiry"),
                }),
                result_as="answer", successor_as="after_answer",
                then=Record.from_mapping({
                    "$kind": Lit("ModelProposal"),
                    "context": Get(Var("answer"), "context"),
                    "claims": Lit(()),
                    "receipt": Var("answer"),
                }),
            ),
        ),
    ))
    assert isinstance(requester_code, Done)
    model = named(
        machine, "model",
        model_value("seeker", implementation=requester_code.value, process=True),
        "unified:model",
    )
    model_context = named(
        machine, "context",
        context_value(cuts=(cut_a["cut"],), models=(model,)),
        "unified:model-context",
    )
    request = model_input(
        context=Name(model_context),
        model=Name(model),
        cuts=(Name(cut_a["cut"]),),
        knowledge=(), facts=(), remaining_budget=1,
    )
    model_runner = ModelProcessRunner(tm, machine=machine)
    model_runner.authorize_discovery(model=model, provider=provider)
    model_started = model_runner.start(
        name=model, program=requester_code.value,
        request=request, request_id="unified:model-run",
    )

    source_code = PraxisCore().realize(Lambda(
        ("request",),
        Perform(
            socket=Need(OBSERVER_SOCKET_ROLE),
            operation=OBSERVER_REFUSE,
            argument=Lit(refuse_request("cannot disclose")),
            result_as="decision",
            successor_as="next",
            then=Var("decision"),
        ),
    ))
    assert isinstance(source_code, Done)
    source_context = named(
        machine, "context",
        context_value(cuts=(cut_b["cut"],)),
        "unified:source-context",
    )

    asked = machine.advance_registered(model_started.checkpoint)
    pending = machine.advance_registered(asked.checkpoint)
    assert pending.pending is not None
    assert tm.projection(
        tm.named_eidos_value(asked.checkpoint)["value"]
        .get("suspension").socket.name.value
    )["disposition"] == "live"

    observer_runner = ObserverProcessRunner(tm, identity="O2", machine=machine)
    source_started = observer_runner.start(
        inquiry=pending.pending,
        discloser_projection=genesis["projections"]["projection:Discloser"],
        context=source_context,
        program=source_code.value,
        request_id="unified:source-run",
    )

    model_protocol = tm.named_eidos_value(model_started.run)["value"].get("protocol")
    observer_protocol = tm.named_eidos_value(source_started.process)["value"].get("protocol")
    assert model_protocol != observer_protocol
    seeker_protocol = tm.named_eidos_value(model_protocol.value)["value"]
    assert any(
        op.get("name") == AWAIT_DISCOVERY and op.get("may_wait")
        for op in seeker_protocol.get("operations")
    )
    assert tm.named_eidos_value(model_protocol.value)["value"].get("projection_role") == "ModelProcess"
    assert tm.named_eidos_value(observer_protocol.value)["value"].get("projection_role") == "InquiryResponder"

    declined = machine.advance_registered(source_started.checkpoint)
    assert declined.outcome
    assert tm.authority_occurrence(declined.occurrence)["kind"] == "DiscoveryRefuse"
    answered = machine.advance_registered(asked.checkpoint)
    assert answered.outcome
    result = tm.named_eidos_value(answered.outcome)["value"].get("proposal")
    assert result.get("receipt").get("$kind") == "DiscoveryRefused"
    assert tm.projection(genesis["projections"]["projection:A"])["disposition"] == "live"
    assert tm.projection(genesis["projections"]["projection:B"])["disposition"] == "live"

    # Both participants can be replayed through the *same* host machine.
    assert machine.advance_registered(source_started.checkpoint) == declined
    assert machine.advance_registered(asked.checkpoint) == answered
