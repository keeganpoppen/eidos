import pytest

from eidos.core import (
    Done, Get, Lambda, Lit, Name, Need, Perform, PraxisCore, Record,
    RecordValue, Socket, Suspended, Var, content_id, from_data, to_data,
)
from eidos.epistemics import (
    attention_value, context_value, knowledge_value, model_value,
)
from eidos.authority import ProjectionGrant
from eidos.semantic_values import projection_value
from eidos.genesis import admit_genesis
from eidos.lenses import walk_named_values
from eidos.meta_protocol import (
    ACTUALIZE, ELABORATE, MetaProtocolDriver,
    actualize_operation, elaborate_operation,
)
from eidos.model_execution import (
    executor_value, model_claim, model_input, model_proposal,
)
from eidos.model_process import (
    CONSULT, INSPECT, PROCESS_SOCKET_ROLE, ModelProcessRunner,
    inspection_request, consultation_request,
)
from eidos.occurrence import (
    ProjectionTemplate, ReactionRule, RecursiveProtocol,
)
from eidos.trusted import TrustedMachinery
from eidos.model_execution import ModelExecutionError


def persist(tm, kind, value):
    name = tm.reserve_name(
        kind=kind, request_id=f"persist-model-process:{kind}:{len(tm.named_values())}"
    )
    tm.bind_eidos_value(
        name=name, value=value, request_id=f"persist-model-process:{name}"
    )
    return name


def process_program(cut_name, executor_name):
    """One ordinary Eidos Closure: Inspect -> Consult -> ModelProposal."""

    body = Perform(
        socket=Need(PROCESS_SOCKET_ROLE),
        operation=INSPECT,
        argument=Lit(inspection_request(Name(cut_name))),
        result_as="inspection",
        successor_as="after_inspect",
        then=Perform(
            socket=Var("after_inspect"),
            operation=CONSULT,
            argument=Lit(consultation_request(
                Name(executor_name), question="What does this observed pattern mean?"
            )),
            result_as="consulted",
            successor_as="after_consult",
            then=Record.from_mapping({
                "$kind": Lit("ModelProposal"),
                "context": Get(Var("request"), "context"),
                "claims": Get(Var("consulted"), "claims"),
                "receipt": Record.from_mapping({
                    "$kind": Lit("ProcessReceipt"),
                    "inspected": Get(Var("inspection"), "target"),
                    "consultation": Get(Var("consulted"), "receipt"),
                }),
            }),
        ),
    )
    built = PraxisCore().realize(Lambda(("request",), body))
    assert isinstance(built, Done)
    return built.value


def world():
    tm = TrustedMachinery()
    protocol = RecursiveProtocol(
        name="resumable-model-process",
        initial=(ProjectionTemplate("A", "watching"),
                 ProjectionTemplate("B", "watching")),
        reactions=(
            ReactionRule(
                "recognize",
                requires=(ProjectionTemplate("A", "watching"),
                          ProjectionTemplate("B", "watching")),
                successors=(ProjectionTemplate("A", "recognized"),
                            ProjectionTemplate("B", "recognized")),
                requires_facts=("sky:recognized",),
            ),
        ),
    )
    genesis = admit_genesis(
        tm, protocol,
        holders={"A": "alice", "B": "bob"},
        request_id="resumable-world-genesis",
    )
    cut = tm.create_observed_cut(
        instance=genesis["instance"], observer="O", protocol_cid=protocol.cid,
        projections=tuple(genesis["projections"].values()),
        elaborator="elaborator:sky", request_id="resumable-world-cut",
    )
    claim = persist(
        tm, "knowledge", knowledge_value("sky:pattern", grounds=(cut["cut"],))
    )
    attention = persist(tm, "attention", attention_value(inference_budget=1))
    executor = persist(
        tm, "executor",
        executor_value("virtual-subagent", label="astronomy specialist"),
    )
    program = process_program(cut["cut"], executor)
    model = persist(
        tm, "model",
        model_value(
            "resumable-astronomer",
            implementation=program,
            process=True,
            sources=(cut["cut"],),
        ),
    )
    context = persist(
        tm, "context",
        context_value(
            cuts=(cut["cut"],),
            knowledge=(claim,),
            models=(model,),
            attention=attention,
        ),
    )
    request = model_input(
        context=Name(context),
        model=Name(model),
        cuts=(Name(cut["cut"]),),
        facts=("sky:pattern",),
        knowledge=(Name(claim),),
        remaining_budget=1,
    )
    return tm, protocol, cut, {
        "program": program,
        "claim": claim,
        "executor": executor,
        "model": model,
        "context": context,
        "request": request,
        "genesis": genesis,
    }


def responder(calls):
    def invoke(request):
        calls.append(request)
        assert request.get("$kind") == "ModelConsultation"
        assert request.get("question") == "What does this observed pattern mean?"
        return model_proposal(
            request.get("context"),
            (model_claim("sky:recognized", premises=("sky:pattern",),
                         witness="astronomy:subagent"),),
            receipt=RecordValue.from_mapping({
                "$kind": "ConsultReceipt",
                "question": request.get("question"),
            }),
        )
    return invoke


def snapshot_world(tm, refs):
    return {
        role: tm.projection(projection)["disposition"]
        for role, projection in refs["genesis"]["projections"].items()
    }


def reidentify_request(refs, model_name):
    original = refs["request"]
    return model_input(
        context=original.get("context"),
        model=Name(model_name),
        cuts=original.get("cuts"),
        facts=original.get("facts"),
        knowledge=original.get("knowledge"),
        remaining_budget=original.get("remaining_budget"),
    )


def test_model_process_checkpoints_inspects_consults_and_survives_restart():
    tm, _, cut, refs = world()
    calls = []
    before = snapshot_world(tm, refs)
    runner = ModelProcessRunner(
        tm, executors={refs["executor"]: responder(calls)}
    )
    runner.authorize_consultation(
        model=refs["model"], executor=refs["executor"]
    )
    started = runner.start(
        name=refs["model"],
        program=refs["program"],
        request=refs["request"],
        request_id="first-model-process",
    )
    assert started.checkpoint is not None
    checkpoint = tm.named_eidos_value(started.checkpoint)["value"]
    assert checkpoint.get("$kind") == "ModelCheckpoint"
    assert checkpoint.get("suspension").operation == INSPECT
    assert from_data(to_data(checkpoint.get("suspension"))) == checkpoint.get("suspension")
    assert tm.projection(
        checkpoint.get("suspension").socket.name.value
    )["disposition"] == "live"

    after_inspect = runner.advance(started.checkpoint)
    assert after_inspect.checkpoint
    first_event = tm.authority_occurrence(after_inspect.occurrence)
    assert first_event["kind"] == "ModelInteraction"
    assert first_event["fact"]["operation"] == INSPECT.value
    assert tm.named_eidos_value(after_inspect.occurrence)["value"].get("$kind") == "ModelInteraction"
    assert tm.projection(
        checkpoint.get("suspension").socket.name.value
    )["disposition"] == "spent"

    # A new runner, with no session cache, can recover the serialized
    # continuation and advance it through a different host realization.
    restarted = ModelProcessRunner(
        tm, executors={refs["executor"]: responder(calls)}
    )
    checkpoint_2 = tm.named_eidos_value(after_inspect.checkpoint)["value"]
    assert checkpoint_2.get("suspension").operation == CONSULT
    completed = restarted.advance(after_inspect.checkpoint)
    assert completed.outcome
    assert len(calls) == 1

    outcome = tm.named_eidos_value(completed.outcome)["value"]
    assert outcome.get("$kind") == "ModelProcessOutcome"
    assert len(outcome.get("events")) == 2
    assert len(outcome.get("checkpoints")) == 2
    proposal = outcome.get("proposal")
    assert proposal.get("$kind") == "ModelProposal"
    assert proposal.get("claims")[0].get("fact") == "sky:recognized"
    assert proposal.get("receipt").get("inspected") == Name(cut["cut"])

    # Retries reconstruct the same receipt/continuation without invoking the
    # delegated process again or double-spending an authority occurrence.
    assert restarted.advance(after_inspect.checkpoint) == completed
    assert runner.advance(started.checkpoint) == after_inspect
    assert len(calls) == 1
    assert snapshot_world(tm, refs) == before


def test_process_model_integrates_with_real_elaborate_and_actualize():
    tm, protocol, cut, refs = world()
    calls = []
    driver = MetaProtocolDriver(tm)
    driver.register(protocol)
    driver.register_executor(refs["executor"], responder(calls))
    driver.authorize_model_consultation(
        model=refs["model"], executor=refs["executor"]
    )
    praxis = PraxisCore()

    elaborating = elaborate_operation(
        Lit(Socket(Name(cut["elaborator_projection"]))),
        protocol_cid=protocol.cid,
        cuts=(cut["cut"],),
        authorities={cut["cut"]: cut["elaborator_projection"]},
        context=refs["context"],
        actualizer="actualizer:sky",
        result_as="result",
        successor_as="next",
        then=Var("result"),
    )
    suspended = praxis.realize(elaborating)
    assert isinstance(suspended, Suspended)
    assert suspended.operation == ELABORATE
    reaction = driver.react(suspended, request_id="process-outer-elaborate")
    assert len(calls) == 1
    finished = praxis.resume(suspended, reaction)
    assert isinstance(finished, Done)

    elaboration = tm.named_eidos_value(reaction.name.value)["value"]
    derivation_name, = elaboration.get("derivations")
    derivation = tm.named_eidos_value(derivation_name.value)["value"]
    assert derivation.get("engine") == "process"
    process_outcome = derivation.get("process")
    assert isinstance(process_outcome, Name)
    outcome = tm.named_eidos_value(process_outcome.value)["value"]
    assert len(outcome.get("events")) == 2
    neighborhood = walk_named_values(
        (reaction.name.value,),
        resolve=lambda name: tm.named_eidos_value(name)["value"],
        depth=6,
    )
    assert process_outcome.value in neighborhood.by_name()
    assert outcome.get("run").value in neighborhood.by_name()

    recognized = next(iter(finished.value.get("possibilities").as_dict().values()))
    assert tm.observed_possibility(recognized.value)["state"] == "open"
    assert snapshot_world(tm, refs) == {
        "projection:A": "live", "projection:B": "live"
    }

    actualizer = finished.value.get("actualizers").get(recognized.value)
    actualizing = actualize_operation(
        Lit(actualizer),
        possibility=recognized.value,
        observation={"recognition": True},
        result_as="result",
        successor_as="next",
        then=Var("result"),
    )
    suspended_actualize = praxis.realize(actualizing)
    assert isinstance(suspended_actualize, Suspended)
    assert suspended_actualize.operation == ACTUALIZE
    actualized = driver.react(
        suspended_actualize, request_id="process-world-actualize"
    )
    assert isinstance(praxis.resume(suspended_actualize, actualized), Done)
    assert tm.observed_possibility(recognized.value)["state"] == "occurred"
    assert snapshot_world(tm, refs) == {
        "projection:A": "spent", "projection:B": "spent"
    }


def test_process_cannot_perform_on_a_world_socket():
    tm, _, _, refs = world()
    world_projection = refs["genesis"]["projections"]["projection:A"]
    malicious = PraxisCore().realize(
        Lambda(
            ("request",),
            Perform(
                socket=Lit(Socket(Name(world_projection))),
                operation=INSPECT,
                argument=Lit(inspection_request(Name(refs["context"]))),
                result_as="result",
                successor_as="next",
                then=Var("result"),
            ),
        )
    )
    assert isinstance(malicious, Done)
    rogue_model = persist(
        tm, "model",
        model_value("rogue-world-socket", implementation=malicious.value, process=True),
    )
    before = snapshot_world(tm, refs)
    runner = ModelProcessRunner(tm)
    with pytest.raises(ModelExecutionError, match="outside its own continuation"):
        runner.start(
            name=rogue_model, program=malicious.value,
            request=reidentify_request(refs, rogue_model),
        )
    assert snapshot_world(tm, refs) == before


def test_inspection_cannot_escape_its_scoped_context():
    tm, _, _, refs = world()
    outsider = persist(tm, "other", RecordValue.from_mapping({
        "$kind": "PrivateData", "value": "not in this context"
    }))
    unsafe = PraxisCore().realize(
        Lambda(("request",), Perform(
            socket=Need(PROCESS_SOCKET_ROLE),
            operation=INSPECT,
            argument=Lit(inspection_request(Name(outsider))),
            result_as="result",
            successor_as="next",
            then=Record.from_mapping({
                "$kind": Lit("ModelProposal"),
                "context": Get(Var("request"), "context"),
                "claims": Lit(()),
                "receipt": Var("result"),
            }),
        ))
    )
    assert isinstance(unsafe, Done)
    unsafe_model = persist(
        tm, "model",
        model_value("out-of-scope-inspector", implementation=unsafe.value, process=True),
    )
    runner = ModelProcessRunner(tm)
    progress = runner.start(
        name=unsafe_model, program=unsafe.value,
        request=reidentify_request(refs, unsafe_model),
    )
    with pytest.raises(ModelExecutionError, match="outside scoped Context"):
        runner.advance(progress.checkpoint)
    assert snapshot_world(tm, refs) == {
        "projection:A": "live", "projection:B": "live"
    }



def test_registered_executor_name_alone_does_not_authorize_consultation():
    tm, _, _, refs = world()
    calls = []
    runner = ModelProcessRunner(
        tm, executors={refs["executor"]: responder(calls)}
    )
    started = runner.start(
        name=refs["model"], program=refs["program"],
        request=refs["request"], request_id="model-without-consultation-grant",
    )
    first = runner.advance(started.checkpoint)
    with pytest.raises(
        ModelExecutionError, match="explicitly delegated executor authority"
    ):
        runner.advance(first.checkpoint)
    assert calls == []
    assert tm.projection(
        tm.named_eidos_value(first.checkpoint)["value"]
        .get("suspension").socket.name.value
    )["disposition"] == "live"
    assert snapshot_world(tm, refs) == {
        "projection:A": "live", "projection:B": "live"
    }



def test_prepared_consultation_survives_commit_before_continuation_resume():
    """Inject a crash precisely after TM committed but before Praxis resumed."""

    tm, _, _, refs = world()
    calls = []
    runner = ModelProcessRunner(
        tm, executors={refs["executor"]: responder(calls)}
    )
    runner.authorize_consultation(
        model=refs["model"], executor=refs["executor"]
    )
    initial = runner.start(
        name=refs["model"], program=refs["program"],
        request=refs["request"], request_id="injected-crash-process",
    )
    first = runner.advance(initial.checkpoint)
    checkpoint = first.checkpoint
    state = tm.named_eidos_value(checkpoint)["value"]
    suspension = state.get("suspension")
    run = state.get("run").value
    step = state.get("step")
    descriptor = tm.named_eidos_value(run)["value"]

    # The host has already consulted its specialist and durably recorded
    # exactly what the specialist said, before the authority transaction.
    prepared_name, prepared = runner._prepare(
        run=run, checkpoint=checkpoint,
        context=state.get("context"),
        suspended=suspension, descriptor=descriptor,
    )
    assert len(calls) == 1

    response = prepared.get("response")
    grant_key = f"step:{step + 1}"
    receipt = tm.commit_projection_occurrence(
        kind="ModelInteraction",
        consumes=(suspension.socket.name.value,),
        establishes=(
            ProjectionGrant(
                key=grant_key,
                holder=refs["model"],
                description=projection_value(
                    key=f"model-process:{grant_key}",
                    role="ModelProcess",
                    state=grant_key,
                ),
            ),
        ),
        fact={
            "run": run,
            "checkpoint": checkpoint,
            "prepared": prepared_name,
            "operation": suspension.operation.value,
            "request": to_data(suspension.argument),
            "response_cid": content_id(response),
            "context": state.get("context").value,
            "next_context": state.get("context").value,
            "causal_source": None,
            "next_holder": refs["model"],
        },
        request_id=f"{run}:{checkpoint}:interact",
    )

    assert tm.projection(suspension.socket.name.value)["disposition"] == "spent"

    # Nothing has resumed locally. The next runner reconstructs the same
    # Reaction from the idempotent generic TM receipt and the prepared answer.
    restarted = ModelProcessRunner(tm)
    outcome = restarted.advance(checkpoint)
    assert outcome.outcome
    assert len(calls) == 1
    assert receipt["occurrence"] in {
        reference.value
        for reference in tm.named_eidos_value(outcome.outcome)["value"].get("events")
    }

    repeated = restarted.advance(checkpoint)
    assert repeated == outcome
    assert len(calls) == 1



def test_joint_elaboration_uses_resumable_process_to_inspect_both_cuts():
    """Two observers delegate; one Model inspects both cuts and consults a specialist."""

    tm = TrustedMachinery()
    joint_protocol = RecursiveProtocol(
        name="resumable-joint-recognition",
        initial=(
            ProjectionTemplate("A", "watching"),
            ProjectionTemplate("B", "watching"),
        ),
        reactions=(
            ReactionRule(
                "joint-recognition",
                requires=(
                    ProjectionTemplate("A", "watching"),
                    ProjectionTemplate("B", "watching"),
                ),
                successors=(
                    ProjectionTemplate("A", "recognized"),
                    ProjectionTemplate("B", "recognized"),
                ),
                requires_facts=("joint:recognized",),
            ),
        ),
    )
    genesis = admit_genesis(
        tm, joint_protocol,
        holders={"A": "alice", "B": "bob"},
        request_id="model-process-joint-genesis",
    )
    left = tm.create_observed_cut(
        instance=genesis["instance"],
        observer="O1",
        protocol_cid=joint_protocol.cid,
        projections=[genesis["projections"]["projection:A"]],
        elaborator="elaborator:left",
        request_id="model-process-joint-cut-left",
    )
    right = tm.create_observed_cut(
        instance=genesis["instance"],
        observer="O2",
        protocol_cid=joint_protocol.cid,
        projections=[genesis["projections"]["projection:B"]],
        elaborator="elaborator:right",
        request_id="model-process-joint-cut-right",
    )
    claim_a = persist(
        tm, "knowledge",
        knowledge_value("signal:A", grounds=(left["cut"],)),
    )
    claim_b = persist(
        tm, "knowledge",
        knowledge_value("signal:B", grounds=(right["cut"],)),
    )
    executor = persist(
        tm, "executor",
        executor_value("remote-subagent", label="joint-pattern specialist"),
    )

    closure = PraxisCore().realize(Lambda(
        ("request",),
        Perform(
            socket=Need(PROCESS_SOCKET_ROLE),
            operation=INSPECT,
            argument=Lit(inspection_request(left["cut"])),
            result_as="observed_left",
            successor_as="k1",
            then=Perform(
                socket=Var("k1"),
                operation=INSPECT,
                argument=Lit(inspection_request(right["cut"])),
                result_as="observed_right",
                successor_as="k2",
                then=Perform(
                    socket=Var("k2"),
                    operation=CONSULT,
                    argument=Lit(consultation_request(
                        executor, question="Do the two independently seen signals match?"
                    )),
                    result_as="consulted",
                    successor_as="k3",
                    then=Record.from_mapping({
                        "$kind": Lit("ModelProposal"),
                        "context": Get(Var("request"), "context"),
                        "claims": Get(Var("consulted"), "claims"),
                        "receipt": Record.from_mapping({
                            "$kind": Lit("JointModelReceipt"),
                            "left": Get(Var("observed_left"), "target"),
                            "right": Get(Var("observed_right"), "target"),
                            "consulted": Get(Var("consulted"), "receipt"),
                        }),
                    }),
                ),
            ),
        ),
    ))
    assert isinstance(closure, Done)
    model = persist(
        tm, "model",
        model_value("joint-resumable-specialist", implementation=closure.value, process=True),
    )
    attention = persist(
        tm, "attention", attention_value(inference_budget=1),
    )
    context = persist(
        tm, "context",
        context_value(
            cuts=(left["cut"], right["cut"]),
            knowledge=(claim_a, claim_b),
            models=(model,),
            attention=attention,
        ),
    )
    for cut, holder in ((left, "elaborator:left"), (right, "elaborator:right")):
        tm.transfer_projection(
            projection=cut["elaborator_projection"],
            from_holder=holder,
            to_holder="elaborator:joint",
            request_id=f"delegate:{cut['cut']}",
        )

    consultations = []
    def specialist(request):
        consultations.append(request)
        assert set(request.get("facts")) == {"signal:A", "signal:B"}
        return model_proposal(
            request.get("context"),
            (model_claim(
                "joint:recognized",
                premises=("signal:A", "signal:B"),
                witness="remote-specialist",
            ),),
            receipt="two-cuts-correspond",
        )

    driver = MetaProtocolDriver(tm)
    driver.register(joint_protocol)
    driver.register_executor(executor, specialist)
    driver.authorize_model_consultation(model=model, executor=executor)

    praxis = PraxisCore()
    term = elaborate_operation(
        Lit(Socket(Name(left["elaborator_projection"]))),
        protocol_cid=joint_protocol.cid,
        cuts=(left["cut"], right["cut"]),
        authorities={
            left["cut"]: left["elaborator_projection"],
            right["cut"]: right["elaborator_projection"],
        },
        context=context,
        actualizer="actualizer:joint",
        result_as="result",
        successor_as="next",
        then=Var("result"),
    )
    suspended = praxis.realize(term)
    assert isinstance(suspended, Suspended)
    reaction = driver.react(suspended, request_id="joint-process-elaborate")
    assert len(consultations) == 1
    assert {item.name.value for item in reaction.consumed_sockets} == {
        left["elaborator_projection"], right["elaborator_projection"],
    }
    done = praxis.resume(suspended, reaction)
    assert isinstance(done, Done)
    possible = done.value.get("possibilities").as_dict()
    assert len(possible) == 1
    assert next(iter(possible)).endswith("joint-recognition")

    elaboration = tm.named_eidos_value(reaction.name.value)["value"]
    derivation_name, = elaboration.get("derivations")
    derivation = tm.named_eidos_value(derivation_name.value)["value"]
    outcome = tm.named_eidos_value(derivation.get("process").value)["value"]
    assert len(outcome.get("events")) == 3
    receipt = outcome.get("proposal").get("receipt")
    assert receipt.get("left") == Name(left["cut"])
    assert receipt.get("right") == Name(right["cut"])
    assert tm.projection(genesis["projections"]["projection:A"])["disposition"] == "live"
    assert tm.projection(genesis["projections"]["projection:B"])["disposition"] == "live"



def test_model_process_rejects_spoofed_program_or_input_identity():
    tm, _, _, refs = world()
    runner = ModelProcessRunner(tm)

    fake = PraxisCore().realize(Lambda(("request",), Lit("not a ModelProposal")))
    assert isinstance(fake, Done)
    with pytest.raises(ModelExecutionError, match="immutable named Model"):
        runner.start(
            name=refs["model"], program=fake.value,
            request=refs["request"],
        )

    other_model = persist(
        tm, "model", model_value(
            "other-identical-program", implementation=refs["program"], process=True
        ),
    )
    with pytest.raises(ModelExecutionError, match="ModelInput must name"):
        runner.start(
            name=other_model, program=refs["program"],
            request=refs["request"],
        )
