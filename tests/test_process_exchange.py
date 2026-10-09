import pytest

from eidos.core import (
    Done, Get, Lambda, Lit, Name, Need, Perform, PraxisCore, Record,
    RecordValue, Socket, Suspended, Var,
)
from eidos.cut_exchange import CutExchangeError, disclose_cut
from eidos.epistemics import (
    attention_value, context_value, interpret_context, knowledge_value,
    model_value,
)
from eidos.genesis import admit_genesis
from eidos.meta_protocol import MetaProtocolDriver, elaborate_operation
from eidos.model_execution import executor_value, model_claim, model_proposal
from eidos.model_process import (
    ACQUIRE, CONSULT, HANDOFF, INSPECT, PROCESS_SOCKET_ROLE,
    ModelExecutionError, ModelProcessRunner,
    acquisition_request, cut_provider_value, handoff_request,
    inspection_request, consultation_request,
)
from eidos.occurrence import ProjectionTemplate, ReactionRule, RecursiveProtocol
from eidos.trusted import TrustedMachinery


def persist(tm, kind, value):
    name = tm.reserve_name(
        kind=kind, request_id=f"exchange:{kind}:{len(tm.named_values())}"
    )
    tm.bind_eidos_value(
        name=name, value=value, request_id=f"exchange:bind:{name}"
    )
    return name


def process_program(left, right, provider, executor, *, handoff=None):
    final = Record.from_mapping({
        "$kind": Lit("ModelProposal"),
        "context": Get(Var("acquired"), "context"),
        "claims": Get(Var("consulted"), "claims"),
        "receipt": Record.from_mapping({
            "$kind": Lit("AcquisitionReceipt"),
            "disclosure": Get(Var("acquired"), "disclosure"),
            "observed": Get(Var("inspected_new"), "target"),
            "consultation": Get(Var("consulted"), "receipt"),
        }),
    })
    consultation = Perform(
        socket=Var("after_handoff" if handoff else "after_new_inspection"),
        operation=CONSULT,
        argument=Lit(consultation_request(
            Name(executor), question="Does the newly observed Cut add context?"
        )),
        result_as="consulted",
        successor_as="last_socket",
        then=final,
    )
    if handoff:
        continuation = Perform(
            socket=Var("after_new_inspection"),
            operation=HANDOFF,
            argument=Lit(handoff_request(handoff)),
            result_as="handoff_reply",
            successor_as="after_handoff",
            then=consultation,
        )
    else:
        continuation = consultation

    closure = PraxisCore().realize(Lambda(
        ("request",),
        Perform(
            socket=Need(PROCESS_SOCKET_ROLE),
            operation=INSPECT,
            argument=Lit(inspection_request(left)),
            result_as="first_inspection",
            successor_as="after_first",
            then=Perform(
                socket=Var("after_first"),
                operation=ACQUIRE,
                argument=Lit(acquisition_request(provider, right)),
                result_as="acquired",
                successor_as="after_acquire",
                then=Perform(
                    socket=Var("after_acquire"),
                    operation=INSPECT,
                    argument=Lit(inspection_request(right)),
                    result_as="inspected_new",
                    successor_as="after_new_inspection",
                    then=continuation,
                ),
            ),
        ),
    ))
    assert isinstance(closure, Done)
    return closure.value


def world(*, handoff=None, protocol_mode="two-participant"):
    tm = TrustedMachinery()
    protocol = RecursiveProtocol(
        name=f"cut-sharing-{protocol_mode}",
        initial=(
            ProjectionTemplate("A", "watching"),
            ProjectionTemplate("B", "watching"),
            ProjectionTemplate("Discloser", "sharing"),
        ),
        reactions=(
            ReactionRule(
                "understand-A",
                requires=(ProjectionTemplate("A", "watching"),),
                successors=(ProjectionTemplate("A", "understood"),),
                requires_facts=("world:understood",),
            ),
        ),
    )
    genesis = admit_genesis(
        tm, protocol,
        holders={"A": "O1", "B": "O2", "Discloser": "O2"},
        request_id=f"sharing-genesis:{protocol_mode}",
    )
    left = tm.create_observed_cut(
        instance=genesis["instance"],
        observer="O1", protocol_cid=protocol.cid,
        projections=[genesis["projections"]["projection:A"]],
        elaborator="elaborator:left",
        request_id=f"sharing-left:{protocol_mode}",
    )
    right = tm.create_observed_cut(
        instance=genesis["instance"],
        observer="O2", protocol_cid=protocol.cid,
        projections=[genesis["projections"]["projection:B"]],
        elaborator="elaborator:right",
        request_id=f"sharing-right:{protocol_mode}",
    )
    claim = persist(
        tm, "knowledge",
        knowledge_value("signal:A", grounds=(left["cut"],)),
    )
    executor = persist(
        tm, "executor",
        executor_value("remote-specialist", label="compare observations"),
    )
    provider = persist(
        tm, "provider",
        cut_provider_value("O2's shared Cut service"),
    )
    program = process_program(
        left["cut"], right["cut"], provider, executor, handoff=handoff
    )
    model = persist(
        tm, "model",
        model_value("acquiring-observer", implementation=program, process=True),
    )
    attention = persist(
        tm, "attention", attention_value(inference_budget=1),
    )
    original_context = persist(
        tm, "context",
        context_value(
            cuts=(left["cut"],), knowledge=(claim,),
            models=(model,), attention=attention,
        ),
    )
    from eidos.model_execution import model_input

    input_ = model_input(
        context=Name(original_context),
        model=Name(model),
        cuts=(Name(left["cut"]),),
        facts=("signal:A",),
        knowledge=(Name(claim),),
        remaining_budget=1,
    )
    return tm, protocol, genesis, left, right, {
        "claim": claim,
        "provider": provider,
        "executor": executor,
        "model": model,
        "program": program,
        "context": original_context,
        "input": input_,
    }


def provider_adapter(tm, right, genesis, offers):
    current = {"capability": genesis["projections"]["projection:Discloser"]}

    def respond(request):
        assert request.get("$kind") == "CutAcquisitionRequest"
        assert request.get("cut") == Name(right["cut"])
        output = disclose_cut(
            tm,
            cut=right["cut"],
            discloser_projection=current["capability"],
            recipient_run=request.get("run").value,
            recipient_model=request.get("model").value,
            request_id=f"source-disclosure:{request.get('run').value}",
        )
        current["capability"] = output["successor_discloser"]
        offers.append(output)
        return output["disclosure"]
    return respond


def specialist_adapter(calls):
    def consult(request):
        calls.append(request)
        assert request.get("$kind") == "ModelConsultation"
        assert request.get("question") == "Does the newly observed Cut add context?"
        assert len(request.get("cuts")) == 2
        return model_proposal(
            request.get("context"),
            (
                model_claim(
                    "world:understood",
                    premises=("signal:A",),
                    witness=RecordValue.from_mapping({
                        "$kind": "SpecialistWitness",
                        "observed_cuts": request.get("cuts"),
                    }),
                ),
            ),
            receipt="remote-recognition",
        )
    return consult


def world_snapshot(tm, genesis):
    return {
        key: tm.projection(value)["disposition"]
        for key, value in genesis["projections"].items()
        if key in ("projection:A", "projection:B")
    }


def test_acquire_second_cut_then_handoff_single_continuation_to_another_runner():
    tm, _, genesis, left, right, refs = world(handoff="worker:remote")
    calls, offers = [], []
    provider = provider_adapter(tm, right, genesis, offers)
    specialist = specialist_adapter(calls)
    first_runner = ModelProcessRunner(
        tm,
        providers={refs["provider"]: provider},
        executors={refs["executor"]: specialist},
    )
    first_runner.authorize_cut_acquisition(
        model=refs["model"], provider=refs["provider"]
    )
    first_runner.authorize_consultation(
        model=refs["model"], executor=refs["executor"]
    )
    first_runner.authorize_handoff(
        model=refs["model"], target="worker:remote"
    )

    start = first_runner.start(
        name=refs["model"], program=refs["program"],
        request=refs["input"], request_id="exchange-process",
    )
    assert tm.named_eidos_value(start.checkpoint)["value"].get("suspension").operation == INSPECT
    after_first = first_runner.advance(start.checkpoint)
    assert tm.named_eidos_value(after_first.checkpoint)["value"].get("suspension").operation == ACQUIRE

    after_acquisition = first_runner.advance(after_first.checkpoint)
    assert len(offers) == 1
    assert len(calls) == 0

    disclosure = offers[0]["disclosure"]
    source = tm.authority_occurrence(disclosure)
    receiving = tm.authority_occurrence(after_acquisition.occurrence)
    assert source["kind"] == "DiscloseCut"
    assert receiving["kind"] == "ModelInteraction"
    assert source["domain_name"] == genesis["domain"]
    assert receiving["domain_name"] == start.run
    assert source["domain_name"] != receiving["domain_name"]
    assert receiving["fact"]["causal_source"] == disclosure

    acquired_checkpoint = tm.named_eidos_value(after_acquisition.checkpoint)["value"]
    expanded_context = acquired_checkpoint.get("context")
    assert isinstance(expanded_context, Name)
    assert expanded_context != Name(refs["context"])
    expanded = tm.named_eidos_value(expanded_context.value)["value"]
    assert set(expanded.get("cuts")) == {Name(left["cut"]), Name(right["cut"])}
    assert expanded.get("parent") == Name(refs["context"])
    assert expanded.get("acquisition") == Name(disclosure)
    assert tm.named_eidos_value(refs["context"])["value"].get("cuts") == (
        Name(left["cut"]),
    )
    interpreted = interpret_context(
        expanded_context,
        resolve=lambda name: tm.named_eidos_value(name)["value"],
        cuts=(left["cut"], right["cut"]),
        inference_limit=0,
    )
    assert interpreted.knowledge == (refs["claim"],)
    assert world_snapshot(tm, genesis) == {
        "projection:A": "live", "projection:B": "live"
    }

    # The newly disclosed Cut is now within scope for Inspect.
    after_new_inspection = first_runner.advance(after_acquisition.checkpoint)
    assert tm.named_eidos_value(
        after_new_inspection.checkpoint
    )["value"].get("suspension").operation == HANDOFF

    transferred = first_runner.advance(after_new_inspection.checkpoint)
    assert transferred.handoff_to == "worker:remote"
    active = tm.named_eidos_value(transferred.checkpoint)["value"].get("suspension")
    assert active.operation == CONSULT
    assert tm.projection(active.socket.name.value)["holder"] == "worker:remote"

    with pytest.raises(ModelExecutionError, match="another holder"):
        first_runner.advance(transferred.checkpoint)

    second_runner = ModelProcessRunner(
        tm, executors={refs["executor"]: specialist},
        identity="worker:remote",
    )
    completed = second_runner.advance(transferred.checkpoint)
    assert completed.outcome
    assert len(calls) == 1

    outcome = tm.named_eidos_value(completed.outcome)["value"]
    assert len(outcome.get("events")) == 5
    assert outcome.get("context") == expanded_context
    proposal = outcome.get("proposal")
    assert proposal.get("context") == expanded_context
    receipt = proposal.get("receipt")
    assert receipt.get("observed") == Name(right["cut"])
    assert receipt.get("disclosure") == Name(disclosure)
    assert world_snapshot(tm, genesis) == {
        "projection:A": "live", "projection:B": "live"
    }

    # A retry recovers without rerunning either remote service.
    assert second_runner.advance(transferred.checkpoint) == completed
    assert first_runner.advance(after_first.checkpoint) == after_acquisition
    assert len(calls) == 1
    assert len(offers) == 1


def test_registered_provider_name_does_not_grant_acquisition_authority():
    tm, _, genesis, _, right, refs = world()
    offers = []
    runner = ModelProcessRunner(
        tm, providers={refs["provider"]: provider_adapter(tm, right, genesis, offers)}
    )
    initial = runner.start(
        name=refs["model"], program=refs["program"],
        request=refs["input"], request_id="unadmitted-acquisition",
    )
    next_ = runner.advance(initial.checkpoint)
    with pytest.raises(ModelExecutionError, match="explicitly delegated CutProvider"):
        runner.advance(next_.checkpoint)
    assert offers == []
    assert tm.projection(genesis["projections"]["projection:Discloser"])["disposition"] == "live"
    assert world_snapshot(tm, genesis) == {
        "projection:A": "live", "projection:B": "live"
    }


def test_acquire_rejects_disclosure_without_source_domain_occurrence():
    tm, _, genesis, _, right, refs = world()
    forged = persist(
        tm, "disclosure",
        RecordValue.from_mapping({
            "$kind": "CutDisclosure",
            "cut": Name(right["cut"]),
        }),
    )

    def bad_provider(_request):
        return forged

    runner = ModelProcessRunner(
        tm, providers={refs["provider"]: bad_provider}
    )
    runner.authorize_cut_acquisition(
        model=refs["model"], provider=refs["provider"]
    )
    initial = runner.start(
        name=refs["model"], program=refs["program"],
        request=refs["input"], request_id="false-source"
    )
    next_ = runner.advance(initial.checkpoint)
    with pytest.raises(KeyError):
        runner.advance(next_.checkpoint)
    assert world_snapshot(tm, genesis) == {
        "projection:A": "live", "projection:B": "live"
    }


def test_acquisition_extends_epistemic_context_but_not_outer_elaboration_authority():
    tm, protocol, genesis, left, right, refs = world(
        protocol_mode="outer-elaboration"
    )
    calls, offers = [], []
    driver = MetaProtocolDriver(tm)
    driver.register(protocol)
    driver.register_executor(refs["executor"], specialist_adapter(calls))
    driver.register_cut_provider(
        refs["provider"], provider_adapter(tm, right, genesis, offers)
    )
    driver.authorize_model_acquisition(
        model=refs["model"], provider=refs["provider"]
    )
    driver.authorize_model_consultation(
        model=refs["model"], executor=refs["executor"]
    )
    praxis = PraxisCore()
    term = elaborate_operation(
        Lit(Socket(Name(left["elaborator_projection"]))),
        protocol_cid=protocol.cid,
        cuts=(left["cut"],),
        authorities={left["cut"]: left["elaborator_projection"]},
        context=refs["context"],
        actualizer="actualizer:outer",
        result_as="result",
        successor_as="next",
        then=Var("result"),
    )
    suspended = praxis.realize(term)
    assert isinstance(suspended, Suspended)
    reaction = driver.react(suspended, request_id="outer-epistemic-acquisition")
    resumed = praxis.resume(suspended, reaction)
    assert isinstance(resumed, Done)
    assert len(offers) == 1
    assert len(calls) == 1
    possible = resumed.value.get("possibilities").as_dict()
    assert len(possible) == 1
    candidate = next(iter(possible.values())).value

    elaboration = tm.named_eidos_value(reaction.name.value)["value"]
    derivation_name, = elaboration.get("derivations")
    derivation = tm.named_eidos_value(derivation_name.value)["value"]
    outcome = tm.named_eidos_value(derivation.get("process").value)["value"]
    extended_context = outcome.get("context")
    assert extended_context != Name(refs["context"])
    assert Name(right["cut"]) in tm.named_eidos_value(extended_context.value)["value"].get("cuts")
    # The Reaction can consume only A, which the original outer Cut supplied.
    possibility = tm.observed_possibility(candidate)
    assert possibility["inputs"] == [genesis["projections"]["projection:A"]]
    assert tm.projection(genesis["projections"]["projection:B"])["disposition"] == "live"
