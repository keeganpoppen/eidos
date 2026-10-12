import pytest

from eidos.core import (
    Done, Get, If, Lambda, Lit, Name, Need, Perform, PraxisCore, Prim,
    Record, RecordValue, Socket, Suspended, Var, from_data, to_data,
)
from eidos.discovery import (
    discovery_provider_value, discover_request, poll_inquiry,
)
from eidos.epistemics import (
    attention_value, context_value, knowledge_value, model_value,
)
from eidos.genesis import admit_genesis
from eidos.lenses import walk_named_values
from eidos.model_execution import (
    ModelExecutionError, consultation_request, executor_value, model_input,
)
from eidos.model_process import (
    AWAIT_DISCOVERY, DISCOVER, INSPECT, PROCESS_SOCKET_ROLE, ModelProcessRunner,
    inspection_request,
)
from eidos.observer_process import (
    OBSERVER_CONSULT, OBSERVER_CONTEXT_ROLE, OBSERVER_DEFER, OBSERVER_INSPECT,
    OBSERVER_OFFER, OBSERVER_REFUSE, OBSERVER_SOCKET_ROLE,
    ObserverProcessRunner, defer_request, observer_advice, offer_request,
    refuse_request,
)
from eidos.occurrence import ProjectionTemplate, RecursiveProtocol
from eidos.trusted import TrustedMachinery


def store(tm, kind, value):
    name = tm.reserve_name(
        kind=kind, request_id=f"observer-test-name:{len(tm.named_values())}:{kind}"
    )
    tm.bind_eidos_value(
        name=name, value=value, request_id=f"observer-test-bind:{name}"
    )
    return name


def requester_program(provider, *, refusal=False):
    after_decision = (
        Record.from_mapping({
            "$kind": Lit("ModelProposal"),
            "context": Get(Var("decision"), "context"),
            "claims": Lit(()),
            "receipt": Var("decision"),
        })
        if refusal else
        Perform(
            socket=Var("after_wait"),
            operation=INSPECT,
            argument=Record.from_mapping({
                "$kind": Lit("InspectRequest"),
                "target": Get(Var("decision"), "cut"),
            }),
            result_as="inspected",
            successor_as="after_inspect",
            then=Record.from_mapping({
                "$kind": Lit("ModelProposal"),
                "context": Get(Var("decision"), "context"),
                "claims": Lit(()),
                "receipt": Record.from_mapping({
                    "$kind": Lit("RequestReceipt"),
                    "cut": Get(Var("inspected"), "target"),
                    "source": Get(Var("decision"), "disclosure"),
                }),
            }),
        )
    )
    result = PraxisCore().realize(Lambda(("request",), Perform(
        socket=Need(PROCESS_SOCKET_ROLE),
        operation=DISCOVER,
        argument=Lit(discover_request(
            provider, "Does anyone else see a matching signal?"
        )),
        result_as="opened",
        successor_as="next",
        then=Perform(
            socket=Var("next"),
            operation=AWAIT_DISCOVERY,
            argument=Record.from_mapping({
                "$kind": Lit("AwaitDiscoveryRequest"),
                "inquiry": Get(Var("opened"), "inquiry"),
            }),
            result_as="decision",
            successor_as="after_wait",
            then=after_decision,
        ),
    )))
    assert isinstance(result, Done)
    return result.value


def observer_program(cut, executor):
    """Source Eidos code: Inspect -> Defer -> Consult -> If(Offer, Refuse)."""

    complete = Record.from_mapping({
        "$kind": Lit("ObserverCompleted"),
        "decision": Var("decision"),
        "inspected": Get(Var("inspected"), "target"),
        "advice": Var("advice"),
    })
    code = Lambda(
        ("request",),
        Perform(
            socket=Need(OBSERVER_SOCKET_ROLE),
            operation=OBSERVER_INSPECT,
            argument=Lit(inspection_request(cut)),
            result_as="inspected",
            successor_as="after_inspect",
            then=Perform(
                socket=Var("after_inspect"),
                operation=OBSERVER_DEFER,
                argument=Lit(defer_request("checking what these observations mean")),
                result_as="deferred",
                successor_as="after_defer",
                then=Perform(
                    socket=Var("after_defer"),
                    operation=OBSERVER_CONSULT,
                    argument=Lit(consultation_request(
                        executor, question="May I disclose this observed Cut?"
                    )),
                    result_as="advice",
                    successor_as="after_consult",
                    then=If(
                        Prim("eq", (
                            Get(Var("advice"), "recommendation"),
                            Lit("offer"),
                        )),
                        Perform(
                            socket=Var("after_consult"),
                            operation=OBSERVER_OFFER,
                            argument=Lit(offer_request(cut)),
                            result_as="decision",
                            successor_as="final_socket",
                            then=complete,
                        ),
                        Perform(
                            socket=Var("after_consult"),
                            operation=OBSERVER_REFUSE,
                            argument=Lit(refuse_request("specialist advised against it")),
                            result_as="decision",
                            successor_as="final_socket",
                            then=complete,
                        ),
                    ),
                ),
            ),
        ),
    )
    evaluated = PraxisCore().realize(code)
    assert isinstance(evaluated, Done)
    return evaluated.value


def world(*, refusal=False):
    tm = TrustedMachinery()
    protocol = RecursiveProtocol(
        name="two-self-realizing-observers",
        initial=(
            ProjectionTemplate("A", "watching"),
            ProjectionTemplate("B", "watching"),
            ProjectionTemplate("Discloser", "available"),
        ),
        reactions=(),
    )
    admitted = admit_genesis(
        tm, protocol,
        holders={"A": "O1", "B": "O2", "Discloser": "O2"},
        request_id="observer-world-genesis",
    )
    left = tm.create_observed_cut(
        instance=admitted["domain"], observer="O1",
        protocol_cid=protocol.cid,
        projections=[admitted["projections"]["projection:A"]],
        elaborator="observer:left",
        request_id="observer-left",
    )
    right = tm.create_observed_cut(
        instance=admitted["domain"], observer="O2",
        protocol_cid=protocol.cid,
        projections=[admitted["projections"]["projection:B"]],
        elaborator="observer:right",
        request_id="observer-right",
    )
    provider = store(
        tm, "provider",
        discovery_provider_value(
            label="O2",
            source_domain=admitted["domain"],
            observer="O2",
        ),
    )
    model_closure = requester_program(provider, refusal=refusal)
    model = store(tm, "model", model_value(
        "questioning-model", implementation=model_closure, process=True
    ))
    claim = store(tm, "knowledge", knowledge_value(
        "signal:A", grounds=(left["cut"],)
    ))
    attention = store(tm, "attention", attention_value(inference_budget=1))
    requester_context = store(tm, "context", context_value(
        cuts=(left["cut"],), knowledge=(claim,),
        models=(model,), attention=attention,
    ))
    request = model_input(
        context=Name(requester_context),
        model=Name(model),
        cuts=(Name(left["cut"]),),
        knowledge=(Name(claim),),
        facts=("signal:A",),
        remaining_budget=1,
    )
    observer_claim = store(
        tm, "knowledge",
        knowledge_value("signal:B", grounds=(right["cut"],))
    )
    observer_context = store(tm, "context", context_value(
        cuts=(right["cut"],), knowledge=(observer_claim,), attention=attention,
    ))
    executor = store(
        tm, "executor",
        executor_value("specialist", label="source-side disclosure specialist"),
    )
    return tm, admitted, left, right, {
        "provider": provider,
        "model": model,
        "model_closure": model_closure,
        "request": request,
        "observer_context": observer_context,
        "executor": executor,
        "requester_context": requester_context,
    }


def issue_question(tm, refs):
    runner = ModelProcessRunner(tm)
    runner.authorize_discovery(model=refs["model"], provider=refs["provider"])
    start = runner.start(
        name=refs["model"], program=refs["model_closure"],
        request=refs["request"], request_id="requester-start",
    )
    asked = runner.advance(start.checkpoint)
    pending = runner.advance(asked.checkpoint)
    assert pending.pending
    return runner, asked, pending


def advice_executor(refs, decision, calls):
    def invoke(request):
        calls.append(request)
        assert request.get("$kind") == "ObserverConsultation"
        assert request.get("question") == "May I disclose this observed Cut?"
        return observer_advice(
            request.get("context"),
            recommendation=decision,
            receipt=RecordValue.from_mapping({
                "$kind": "AdviceReceipt",
                "reason": "source observer considered the evidence",
            }),
        )
    return invoke


def world_state(tm, admitted):
    return {
        key: tm.projection(name)["disposition"]
        for key, name in admitted["projections"].items()
        if key in ("projection:A", "projection:B")
    }


def test_observer_is_resumable_and_can_defer_consult_then_offer():
    tm, admitted, left, right, refs = world()
    requester, asked, pending = issue_question(tm, refs)
    inquiry = pending.pending
    calls = []
    specialist = advice_executor(refs, "offer", calls)
    responder = ObserverProcessRunner(
        tm, executors={refs["executor"]: specialist}, identity="O2",
    )
    observer_program_ = observer_program(right["cut"], refs["executor"])
    started = responder.start(
        inquiry=inquiry,
        discloser_projection=admitted["projections"]["projection:Discloser"],
        context=refs["observer_context"],
        program=observer_program_,
        allowed_executors=(refs["executor"],),
        request_id="observer-responds",
    )
    first = tm.named_eidos_value(started.checkpoint)["value"]
    assert first.get("suspension").operation == OBSERVER_INSPECT
    assert from_data(to_data(first.get("suspension"))) == first.get("suspension")
    assert requester.advance(asked.checkpoint).pending == inquiry

    inspected = responder.advance(started.checkpoint)
    assert tm.authority_occurrence(inspected.occurrence)["kind"] == "ObserverInspect"
    assert tm.named_eidos_value(inspected.checkpoint)["value"].get("suspension").operation == OBSERVER_DEFER
    assert poll_inquiry(tm, inquiry)["status"] == "pending"

    deferred = responder.advance(inspected.checkpoint)
    assert tm.authority_occurrence(deferred.occurrence)["kind"] == "DiscoveryDefer"
    assert poll_inquiry(tm, inquiry)["status"] == "deferred"
    assert requester.advance(asked.checkpoint).pending == inquiry

    # Restart the source interpreter from its checkpoint; no hidden call stack.
    resumed = ObserverProcessRunner(
        tm, executors={refs["executor"]: specialist}, identity="O2"
    )
    consulted = resumed.advance(deferred.checkpoint)
    assert tm.authority_occurrence(consulted.occurrence)["kind"] == "ObserverConsult"
    assert len(calls) == 1
    assert tm.named_eidos_value(consulted.checkpoint)["value"].get("suspension").operation == OBSERVER_OFFER

    finished = ObserverProcessRunner(tm, identity="O2").advance(consulted.checkpoint)
    assert finished.outcome
    assert tm.authority_occurrence(finished.occurrence)["kind"] == "DiscoveryOffer"
    assert poll_inquiry(tm, inquiry) == {
        "status": "offer",
        "decision": finished.occurrence,
        "cut": right["cut"],
    }
    outcome = tm.named_eidos_value(finished.outcome)["value"]
    assert outcome.get("$kind") == "ObserverOutcome"
    assert len(outcome.get("checkpoints")) == 4
    assert tuple(
        tm.authority_occurrence(ref.value)["kind"]
        for ref in outcome.get("occurrences")
    ) == ("ObserverInspect", "DiscoveryDefer", "ObserverConsult", "DiscoveryOffer")
    assert outcome.get("result").get("inspected") == Name(right["cut"])
    assert responder.advance(started.checkpoint) == inspected
    assert resumed.advance(deferred.checkpoint) == consulted
    assert ObserverProcessRunner(tm).advance(consulted.checkpoint) == finished
    assert len(calls) == 1

    # The requester now incorporates the source response in its own domain.
    acquired = ModelProcessRunner(tm).advance(asked.checkpoint)
    context = tm.named_eidos_value(acquired.checkpoint)["value"].get("context")
    assert set(tm.named_eidos_value(context.value)["value"].get("cuts")) == {
        Name(left["cut"]), Name(right["cut"])
    }
    request_finished = ModelProcessRunner(tm).advance(acquired.checkpoint)
    assert request_finished.outcome
    assert world_state(tm, admitted) == {
        "projection:A": "live", "projection:B": "live"
    }
    neighborhood = walk_named_values(
        (finished.outcome,),
        resolve=lambda name: tm.named_eidos_value(name)["value"],
        depth=5,
    )
    assert started.process in neighborhood.by_name()


def test_specialist_can_cause_observer_to_refuse_without_disclosing_cut():
    tm, admitted, left, right, refs = world(refusal=True)
    requester, asked, pending = issue_question(tm, refs)
    calls = []
    observer = ObserverProcessRunner(
        tm, executors={refs["executor"]: advice_executor(refs, "refuse", calls)},
        identity="O2",
    )
    started = observer.start(
        inquiry=pending.pending,
        discloser_projection=admitted["projections"]["projection:Discloser"],
        context=refs["observer_context"],
        program=observer_program(right["cut"], refs["executor"]),
        allowed_executors=(refs["executor"],),
        request_id="observer-refusal",
    )
    first = observer.advance(started.checkpoint)
    deferred = observer.advance(first.checkpoint)
    consulted = observer.advance(deferred.checkpoint)
    assert tm.named_eidos_value(consulted.checkpoint)["value"].get("suspension").operation == OBSERVER_REFUSE

    finished = ObserverProcessRunner(tm, identity="O2").advance(consulted.checkpoint)
    assert tm.authority_occurrence(finished.occurrence)["kind"] == "DiscoveryRefuse"
    assert poll_inquiry(tm, pending.pending)["status"] == "refuse"

    requester_finished = ModelProcessRunner(tm).advance(asked.checkpoint)
    assert requester_finished.outcome
    proposal = tm.named_eidos_value(requester_finished.outcome)["value"].get("proposal")
    assert proposal.get("context") == Name(refs["requester_context"])
    assert proposal.get("receipt").get("$kind") == "DiscoveryRefused"
    assert world_state(tm, admitted) == {
        "projection:A": "live", "projection:B": "live"
    }


def test_observer_knowledge_of_another_cut_does_not_grant_inspection():
    tm, admitted, left, right, refs = world()
    requester, asked, pending = issue_question(tm, refs)
    unsafe = PraxisCore().realize(Lambda(("request",), Perform(
        socket=Need(OBSERVER_SOCKET_ROLE),
        operation=OBSERVER_INSPECT,
        argument=Lit(inspection_request(left["cut"])),
        result_as="inspection",
        successor_as="next",
        then=Record.from_mapping({
            "$kind": Lit("ObserverCompleted"),
            "inspection": Var("inspection"),
        }),
    )))
    assert isinstance(unsafe, Done)
    observer = ObserverProcessRunner(tm, identity="O2")
    started = observer.start(
        inquiry=pending.pending,
        discloser_projection=admitted["projections"]["projection:Discloser"],
        context=refs["observer_context"],
        program=unsafe.value,
        request_id="observer-out-of-scope",
    )
    with pytest.raises(ModelExecutionError, match="outside scoped Context"):
        observer.advance(started.checkpoint)
    assert tm.projection(
        tm.named_eidos_value(started.checkpoint)["value"].get("suspension").socket.name.value
    )["disposition"] == "live"


def test_executor_name_does_not_grant_observer_consultation():
    tm, admitted, left, right, refs = world()
    requester, asked, pending = issue_question(tm, refs)
    calls = []
    observer = ObserverProcessRunner(
        tm, executors={refs["executor"]: advice_executor(refs, "offer", calls)},
        identity="O2",
    )
    started = observer.start(
        inquiry=pending.pending,
        discloser_projection=admitted["projections"]["projection:Discloser"],
        context=refs["observer_context"],
        program=observer_program(right["cut"], refs["executor"]),
        # Deliberately don't admit the named executor to this process.
        request_id="observer-no-consultation-admission",
    )
    inspected = observer.advance(started.checkpoint)
    deferred = observer.advance(inspected.checkpoint)
    with pytest.raises(ModelExecutionError, match="explicitly admitted executor"):
        observer.advance(deferred.checkpoint)
    assert calls == []
    assert poll_inquiry(tm, pending.pending)["status"] == "deferred"


def test_observer_program_cannot_spend_foreign_participant_socket():
    tm, admitted, left, right, refs = world()
    requester, asked, pending = issue_question(tm, refs)
    rogue = PraxisCore().realize(Lambda(("request",), Perform(
        socket=Lit(Socket(Name(admitted["projections"]["projection:B"]))),
        operation=OBSERVER_REFUSE,
        argument=Lit(refuse_request("wrong authority")),
        result_as="decision",
        successor_as="next",
        then=Var("decision"),
    )))
    assert isinstance(rogue, Done)
    observer = ObserverProcessRunner(tm, identity="O2")
    with pytest.raises(ModelExecutionError, match="foreign Socket"):
        observer.start(
            inquiry=pending.pending,
            discloser_projection=admitted["projections"]["projection:Discloser"],
            context=refs["observer_context"],
            program=rogue.value,
            request_id="rogue-socket-program",
        )
    assert tm.projection(admitted["projections"]["projection:B"])["disposition"] == "live"
