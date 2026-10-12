import pytest

from eidos.core import (
    Done, Get, Lambda, Lit, Name, Need, Perform, PraxisCore,
    Record, RecordValue, Suspended, Var,
)
from eidos.discovery import (
    DiscoveryError, accept_inquiry, await_discovery, decide_inquiry,
    discover_request, discovery_provider_value, discovery_inbox, poll_inquiry,
)
from eidos.epistemics import (
    attention_value, context_value, knowledge_value, model_value,
    interpret_context,
)
from eidos.genesis import admit_genesis
from eidos.lenses import referenced_names
from eidos.model_execution import ModelExecutionError, model_input
from eidos.model_process import (
    AWAIT_DISCOVERY, DISCOVER, INSPECT, PROCESS_SOCKET_ROLE,
    ModelProcessRunner,
)
from eidos.occurrence import ProjectionTemplate, RecursiveProtocol
from eidos.trusted import StaleProjection, TrustedMachinery


def persist(tm, kind, value):
    name = tm.reserve_name(
        kind=kind, request_id=f"discovery-reserve:{kind}:{len(tm.named_values())}"
    )
    tm.bind_eidos_value(
        name=name, value=value, request_id=f"discovery-bind:{name}"
    )
    return name


def program(provider, *, refusal=False):
    after_wait = (
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
            result_as="observed",
            successor_as="after_inspect",
            then=Record.from_mapping({
                "$kind": Lit("ModelProposal"),
                "context": Get(Var("decision"), "context"),
                "claims": Lit(()),
                "receipt": Record.from_mapping({
                    "$kind": Lit("DiscoveryReceipt"),
                    "inquiry": Get(Var("opened"), "inquiry"),
                    "disclosure": Get(Var("decision"), "disclosure"),
                    "cut": Get(Var("observed"), "target"),
                }),
            }),
        )
    )
    closure = PraxisCore().realize(
        Lambda(
            ("request",),
            Perform(
                socket=Need(PROCESS_SOCKET_ROLE),
                operation=DISCOVER,
                argument=Lit(discover_request(
                    provider, "What else might illuminate this observation?"
                )),
                result_as="opened",
                successor_as="after_open",
                then=Perform(
                    socket=Var("after_open"),
                    operation=AWAIT_DISCOVERY,
                    argument=Record.from_mapping({
                        "$kind": Lit("AwaitDiscoveryRequest"),
                        "inquiry": Get(Var("opened"), "inquiry"),
                    }),
                    result_as="decision",
                    successor_as="after_wait",
                    then=after_wait,
                ),
            ),
        )
    )
    assert isinstance(closure, Done)
    return closure.value


def world(*, refusal=False):
    tm = TrustedMachinery()
    protocol = RecursiveProtocol(
        name="open-discovery",
        initial=(
            ProjectionTemplate("A", "watching"),
            ProjectionTemplate("B", "watching"),
            ProjectionTemplate("Discloser", "available"),
        ),
        reactions=(),
    )
    genesis = admit_genesis(
        tm, protocol,
        holders={"A": "O1", "B": "O2", "Discloser": "O2"},
        request_id="discovery-world-genesis",
    )
    left = tm.create_observed_cut(
        instance=genesis["domain"],
        observer="O1",
        protocol_cid=protocol.cid,
        projections=[genesis["projections"]["projection:A"]],
        elaborator="elaborator:left",
        request_id="discovery-left-cut",
    )
    right = tm.create_observed_cut(
        instance=genesis["domain"],
        observer="O2",
        protocol_cid=protocol.cid,
        projections=[genesis["projections"]["projection:B"]],
        elaborator="elaborator:right",
        request_id="discovery-right-cut",
    )
    provider = persist(
        tm, "discovery-provider",
        discovery_provider_value(
            label="O2 evidence exchange",
            source_domain=genesis["domain"],
            observer="O2",
        ),
    )
    closure = program(provider, refusal=refusal)
    model = persist(
        tm, "model",
        model_value(
            "discovery seeker",
            implementation=closure,
            process=True,
        ),
    )
    claim = persist(
        tm, "knowledge",
        knowledge_value("signal:A", grounds=(left["cut"],)),
    )
    attention = persist(
        tm, "attention", attention_value(inference_budget=1),
    )
    context = persist(
        tm, "context",
        context_value(
            cuts=(left["cut"],),
            knowledge=(claim,),
            models=(model,),
            attention=attention,
        ),
    )
    request = model_input(
        context=Name(context),
        model=Name(model),
        cuts=(Name(left["cut"]),),
        facts=("signal:A",),
        knowledge=(Name(claim),),
        remaining_budget=1,
    )
    return tm, left, right, genesis, {
        "provider": provider,
        "model": model,
        "closure": closure,
        "context": context,
        "input": request,
    }


def issue(tm, refs, *, admit=True):
    runner = ModelProcessRunner(tm)
    if admit:
        runner.authorize_discovery(
            model=refs["model"], provider=refs["provider"],
        )
    start = runner.start(
        name=refs["model"],
        program=refs["closure"],
        request=refs["input"],
        request_id="discovery-seeking-process",
    )
    first = tm.named_eidos_value(start.checkpoint)["value"]
    assert first.get("suspension").operation == DISCOVER
    requested = runner.advance(start.checkpoint)
    checkpoint = tm.named_eidos_value(requested.checkpoint)["value"]
    assert checkpoint.get("suspension").operation == AWAIT_DISCOVERY
    awaiting = runner.advance(requested.checkpoint)
    assert awaiting.pending is not None
    assert awaiting.checkpoint == requested.checkpoint
    return runner, start, requested, awaiting


def test_question_is_causal_and_stays_pending_across_observer_deferrals():
    tm, left, right, genesis, refs = world()
    assert right["cut"] not in {
        ref.value for ref in referenced_names(refs["closure"])
    }

    runner, started, requested, awaiting = issue(tm, refs)
    inquiry = awaiting.pending
    named = tm.named_eidos_value(inquiry)["value"]
    assert named.get("$kind") == "DiscoveryInquiry"
    assert named.get("question") == "What else might illuminate this observation?"
    assert named.get("provider") == Name(refs["provider"])
    assert poll_inquiry(tm, inquiry)["status"] == "pending"
    inbox = discovery_inbox(tm, provider=refs["provider"])
    assert len(inbox) == 1
    assert inbox[0].get("inquiry") == Name(inquiry)
    assert inbox[0].get("status") == "pending"
    pending = tm.named_eidos_value(requested.checkpoint)["value"]
    waiting_socket = pending.get("suspension").socket.name.value
    assert tm.projection(waiting_socket)["disposition"] == "live"
    assert runner.advance(requested.checkpoint) == awaiting

    accepted = accept_inquiry(
        tm, inquiry=inquiry,
        discloser_projection=genesis["projections"]["projection:Discloser"],
        request_id="discovery-accept",
    )
    assert tm.authority_occurrence(accepted["acceptance"])["kind"] == "DiscoveryAccept"
    assert accept_inquiry(
        tm, inquiry=inquiry,
        discloser_projection=genesis["projections"]["projection:Discloser"],
        request_id="discovery-accept",
    ) == accepted
    deferred = decide_inquiry(
        tm, inquiry=inquiry,
        responder_projection=accepted["responder"],
        decision="defer",
        request_id="discovery-defer",
    )
    assert deferred["responder"] is not None
    assert tm.authority_occurrence(deferred["occurrence"])["kind"] == "DiscoveryDefer"
    assert poll_inquiry(tm, inquiry)["status"] == "deferred"
    assert discovery_inbox(tm, provider=refs["provider"])[0].get("status") == "deferred"
    assert runner.advance(requested.checkpoint).pending == inquiry
    assert tm.projection(waiting_socket)["disposition"] == "live"

    offered = decide_inquiry(
        tm, inquiry=inquiry,
        responder_projection=deferred["responder"],
        decision="offer",
        cut=right["cut"],
        request_id="discovery-offer",
    )
    assert poll_inquiry(tm, inquiry) == {
        "status": "offer",
        "decision": offered["occurrence"],
        "cut": right["cut"],
    }
    assert discovery_inbox(tm, provider=refs["provider"]) == ()
    assert decide_inquiry(
        tm, inquiry=inquiry,
        responder_projection=deferred["responder"],
        decision="offer", cut=right["cut"],
        request_id="discovery-offer",
    ) == offered
    resumed = ModelProcessRunner(tm).advance(requested.checkpoint)
    assert resumed.checkpoint is not None
    assert resumed.pending is None
    assert tm.projection(waiting_socket)["disposition"] == "spent"

    expanded = tm.named_eidos_value(resumed.checkpoint)["value"].get("context")
    value = tm.named_eidos_value(expanded.value)["value"]
    assert set(value.get("cuts")) == {Name(left["cut"]), Name(right["cut"])}
    assert value.get("parent") == Name(refs["context"])
    assert value.get("acquisition") == Name(offered["occurrence"])
    interpreted = interpret_context(
        expanded,
        resolve=lambda name: tm.named_eidos_value(name)["value"],
        cuts=(left["cut"], right["cut"]),
        inference_limit=0,
    )
    assert interpreted.knowledge != ()

    completed = ModelProcessRunner(tm).advance(resumed.checkpoint)
    assert completed.outcome
    proposal = tm.named_eidos_value(completed.outcome)["value"].get("proposal")
    assert proposal.get("context") == expanded
    assert proposal.get("receipt").get("cut") == Name(right["cut"])
    assert proposal.get("receipt").get("disclosure") == Name(offered["occurrence"])
    assert ModelProcessRunner(tm).advance(requested.checkpoint) == resumed
    assert all(
        tm.projection(genesis["projections"][f"projection:{role}"])["disposition"] == "live"
        for role in ("A", "B")
    )


def test_observer_can_refuse_and_requester_resumes_without_new_cut():
    tm, left, right, genesis, refs = world(refusal=True)
    runner, started, requested, awaiting = issue(tm, refs)
    accepted = accept_inquiry(
        tm, inquiry=awaiting.pending,
        discloser_projection=genesis["projections"]["projection:Discloser"],
        request_id="discovery-accept-refusal",
    )
    refused = decide_inquiry(
        tm, inquiry=awaiting.pending,
        responder_projection=accepted["responder"],
        decision="refuse",
        request_id="discovery-refuse",
    )
    assert poll_inquiry(tm, awaiting.pending)["status"] == "refuse"
    assert discovery_inbox(tm, provider=refs["provider"]) == ()
    completed = ModelProcessRunner(tm).advance(requested.checkpoint)
    assert completed.outcome
    outcome = tm.named_eidos_value(completed.outcome)["value"]
    proposal = outcome.get("proposal")
    assert proposal.get("context") == Name(refs["context"])
    receipt = proposal.get("receipt")
    assert tm.authority_occurrence(outcome.get("events")[-1].value)["fact"]["causal_source"] == refused["occurrence"]
    assert receipt.get("$kind") == "DiscoveryRefused"
    assert receipt.get("decision") == Name(refused["occurrence"])
    assert len(outcome.get("events")) == 2
    with pytest.raises(DiscoveryError, match="terminal"):
        decide_inquiry(
            tm, inquiry=awaiting.pending,
            responder_projection=accepted["responder"],
            decision="offer", cut=right["cut"],
            request_id="invalid-after-refusal",
        )


def test_inquiry_name_and_registered_provider_do_not_grant_reply_authority():
    tm, left, right, genesis, refs = world()
    runner, start, requested, awaiting = issue(tm, refs)
    inquiry = awaiting.pending

    with pytest.raises(DiscoveryError, match="accept"):
        decide_inquiry(
            tm, inquiry=inquiry,
            responder_projection=genesis["projections"]["projection:Discloser"],
            decision="offer", cut=right["cut"],
            request_id="no-acceptance",
        )
    with pytest.raises(DiscoveryError, match="authority"):
        accept_inquiry(
            tm, inquiry=inquiry,
            discloser_projection=genesis["projections"]["projection:A"],
            request_id="wrong-observer-discloser",
        )
    correct = accept_inquiry(
        tm, inquiry=inquiry,
        discloser_projection=genesis["projections"]["projection:Discloser"],
        request_id="correct-observer-acceptance",
    )
    with pytest.raises(DiscoveryError, match="observer domain"):
        decide_inquiry(
            tm, inquiry=inquiry,
            responder_projection=correct["responder"],
            decision="offer", cut=left["cut"],
            request_id="offer-foreign-cut",
        )
    assert tm.projection(correct["responder"])["disposition"] == "live"


def test_unadmitted_discovery_provider_cannot_issue_an_open_inquiry():
    tm, _, _, genesis, refs = world()
    runner = ModelProcessRunner(tm)
    started = runner.start(
        name=refs["model"], program=refs["closure"],
        request=refs["input"], request_id="unadmitted-discovery",
    )
    with pytest.raises(ModelExecutionError, match="explicitly admitted DiscoveryProvider"):
        runner.advance(started.checkpoint)
    assert tm.projection(genesis["projections"]["projection:Discloser"])["disposition"] == "live"



def test_forged_acceptance_value_cannot_create_responder_authority():
    tm, left, right, genesis, refs = world()
    runner, started, requested, awaiting = issue(tm, refs)
    inquiry = awaiting.pending
    forged = persist(
        tm,
        "forged-discovery-acceptance",
        RecordValue.from_mapping({
            "$kind": "DiscoveryAcceptance",
            "inquiry": Name(inquiry),
            "provider": Name(refs["provider"]),
            "responder": Name(genesis["projections"]["projection:B"]),
            "next_discloser": Name(genesis["projections"]["projection:Discloser"]),
        }),
    )

    with pytest.raises(DiscoveryError, match="authoritative occurrence"):
        accept_inquiry(
            tm, inquiry=inquiry,
            discloser_projection=genesis["projections"]["projection:Discloser"],
            request_id="accept-with-forged-sibling",
        )
    assert tm.projection(genesis["projections"]["projection:Discloser"])["disposition"] == "live"


def test_inquiry_acceptance_requires_requester_to_commit_its_question():
    tm, left, right, genesis, refs = world()
    runner = ModelProcessRunner(tm)
    runner.authorize_discovery(model=refs["model"], provider=refs["provider"])
    started = runner.start(
        name=refs["model"], program=refs["closure"],
        request=refs["input"], request_id="discover-not-yet-committed",
    )
    from eidos.discovery import open_inquiry

    inquiry = open_inquiry(
        tm,
        run=started.run,
        model=refs["model"],
        context=refs["context"],
        checkpoint=started.checkpoint,
        provider=refs["provider"],
        question="What else might illuminate this observation?",
        request_id="premature-inquiry",
    )
    with pytest.raises(DiscoveryError, match="not been committed"):
        accept_inquiry(
            tm, inquiry=inquiry,
            discloser_projection=genesis["projections"]["projection:Discloser"],
            request_id="premature-acceptance",
        )
