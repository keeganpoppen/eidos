"""Local process recovery, not native-stack recovery or plural product admission."""

import pytest

from eidos.core import Done, Get, Lambda, Lit, Name, Need, Perform, PraxisCore, Record, Var
from eidos.discovery import (
    DiscoveryError, accept_inquiry, decide_inquiry, discover_request,
    discovery_inbox, discovery_provider_value, poll_inquiry,
)
from eidos.epistemics import context_value, model_value
from eidos.genesis import admit_genesis
from eidos.model_execution import model_input
from eidos.model_process import AWAIT_DISCOVERY, DISCOVER, PROCESS_SOCKET_ROLE, ModelProcessRunner
from eidos.occurrence import ProjectionTemplate, RecursiveProtocol
from eidos.process_runtime import ProcessRuntime
from eidos.trusted import TrustedMachinery


def _program(provider):
    # One fixed program: Discover A, Discover B, Await A, Await B. B's source
    # can answer first, although recipient incorporation follows program order.
    body = Record.from_mapping({
        "$kind": Lit("ModelProposal"),
        "context": Get(Var("answerB"), "context"),
        "claims": Lit(()),
        "refusalA": Var("answerA"),
        "offerB": Var("answerB"),
    })
    for letter, socket in (("B", "afterA"), ("A", "afterOpenB")):
        body = Perform(
            socket=Var(socket), operation=AWAIT_DISCOVERY,
            argument=Record.from_mapping({
                "$kind": Lit("AwaitDiscoveryRequest"),
                "inquiry": Get(Var("opened" + letter), "inquiry"),
            }),
            result_as="answer" + letter, successor_as="after" + letter,
            then=body,
        )
    for letter, socket in (("B", Var("afterOpenA")), ("A", Need(PROCESS_SOCKET_ROLE))):
        body = Perform(
            socket=socket, operation=DISCOVER,
            argument=Lit(discover_request(provider, "Independent question " + letter)),
            result_as="opened" + letter, successor_as="afterOpen" + letter,
            then=body,
        )
    realized = PraxisCore().realize(Lambda(("request",), body))
    assert isinstance(realized, Done)
    return realized.value


def _occurrences(trusted):
    return trusted.db.execute("SELECT COUNT(*) FROM authority_occurrences").fetchone()[0]


def test_two_pending_inquiries_keep_ordered_receipts_across_executor_restart(tmp_path):
    path = tmp_path / "multiple-discovery.sqlite"
    trusted = TrustedMachinery(path)
    try:
        machine = ProcessRuntime(trusted)
        protocol = RecursiveProtocol(
            name="multiple-discovery-synthetic",
            initial=(ProjectionTemplate("A", "observed"), ProjectionTemplate("B", "observed"),
                     ProjectionTemplate("Discloser", "available")),
            reactions=(),
        )
        genesis = admit_genesis(
            trusted, protocol, holders={"A": "requester", "B": "source", "Discloser": "source"},
            request_id="multiple:genesis",
        )
        cuts = {}
        for letter, observer in (("A", "requester"), ("B", "source")):
            cuts[letter] = trusted.create_observed_cut(
                instance=genesis["domain"], observer=observer, protocol_cid=protocol.cid,
                projections=[genesis["projections"]["projection:" + letter]],
                request_id="multiple:cut:" + letter,
            )["cut"]
        provider = machine.persist(
            kind="discovery-provider", request_id="multiple:provider",
            value=discovery_provider_value(
                label="Synthetic source", source_domain=genesis["domain"], observer="source",
            ),
        )
        program = _program(provider)
        model = machine.persist(
            kind="model", request_id="multiple:model",
            value=model_value("Two independent questions", implementation=program, process=True),
        )
        context = machine.persist(
            kind="context", request_id="multiple:context",
            value=context_value(cuts=(cuts["A"],), models=(model,)),
        )
        runner = ModelProcessRunner(trusted, machine=machine)
        runner.authorize_discovery(model=model, provider=provider)
        started = runner.start(
            name=model, program=program, request_id="multiple:process",
            request=model_input(context=Name(context), model=Name(model), cuts=(Name(cuts["A"]),),
                                facts=(), knowledge=(), remaining_budget=0),
        )
        opened_a = runner.advance(started.checkpoint)
        opened_b = runner.advance(opened_a.checkpoint)
        inbox = discovery_inbox(trusted, provider=provider)
        assert len(inbox) == 2
        inquiries = {}
        for entry in inbox:
            name = entry.get("inquiry").value
            value = trusted.named_eidos_value(name)["value"]
            assert value.get("run") == Name(started.run)
            inquiries[value.get("question")] = name
        a, b = (inquiries["Independent question " + letter] for letter in "AB")
        assert a != b
        checkpoint = trusted.named_eidos_value(opened_b.checkpoint)["value"]
        waiting_socket = checkpoint.get("suspension").socket.name.value
        pending = runner.advance(opened_b.checkpoint)
        assert pending.pending == a and pending.run == started.run

        # Naming an inquiry/provider does not admit a source response.
        before = _occurrences(trusted)
        with pytest.raises(DiscoveryError, match="first accept"):
            decide_inquiry(trusted, inquiry=b, responder_projection=provider,
                           decision="refuse", request_id="multiple:unadmitted")
        assert _occurrences(trusted) == before
        accepted_a = accept_inquiry(
            trusted, inquiry=a, discloser_projection=genesis["projections"]["projection:Discloser"],
            request_id="multiple:accept:A",
        )
        accepted_b = accept_inquiry(
            trusted, inquiry=b, discloser_projection=accepted_a["next_discloser"],
            request_id="multiple:accept:B",
        )
        before = _occurrences(trusted)
        with pytest.raises(DiscoveryError, match="different inquiry"):
            decide_inquiry(trusted, inquiry=b, responder_projection=accepted_a["responder"],
                           decision="refuse", request_id="multiple:wrong-responder")
        assert _occurrences(trusted) == before
        offer_b = decide_inquiry(
            trusted, inquiry=b, responder_projection=accepted_b["responder"],
            decision="offer", cut=cuts["B"], request_id="multiple:offer:B",
        )
        assert poll_inquiry(trusted, a)["status"] == "pending"
        assert poll_inquiry(trusted, b)["decision"] == offer_b["occurrence"]
        before = _occurrences(trusted)
        assert runner.advance(opened_b.checkpoint) == pending
        assert _occurrences(trusted) == before
        assert trusted.projection(waiting_socket)["disposition"] == "live"
        assert checkpoint.get("context") == Name(context)
    finally:
        trusted.close()

    # Reconstruct the executor from durable authority/checkpoint state. No
    # provider re-admission, captured Python continuation or native relaunch.
    trusted = TrustedMachinery(path)
    try:
        restarted = ModelProcessRunner(trusted)
        assert restarted.advance(opened_b.checkpoint) == pending
        assert poll_inquiry(trusted, b) == {
            "status": "offer", "decision": offer_b["occurrence"], "cut": cuts["B"],
        }
        refusal_a = decide_inquiry(
            trusted, inquiry=a, responder_projection=accepted_a["responder"],
            decision="refuse", request_id="multiple:refuse:A",
        )
        assert refusal_a["cut"] is None
        incorporated_a = restarted.advance(opened_b.checkpoint)
        assert incorporated_a.run == started.run and incorporated_a.outcome is None
        after_a = trusted.named_eidos_value(incorporated_a.checkpoint)["value"]
        assert after_a.get("context") == Name(context)
        assert after_a.get("suspension").argument.get("inquiry") == Name(b)
        assert trusted.projection(waiting_socket)["disposition"] == "spent"
        finished = restarted.advance(incorporated_a.checkpoint)
        assert finished.run == started.run and finished.outcome is not None
        outcome = trusted.named_eidos_value(finished.outcome)["value"]
        proposal = outcome.get("proposal")
        assert proposal.get("claims") == ()
        assert proposal.get("refusalA").get("inquiry") == Name(a)
        assert proposal.get("refusalA").get("decision") == Name(refusal_a["occurrence"])
        assert proposal.get("refusalA").get("$kind") == "DiscoveryRefused"
        assert proposal.get("offerB").get("inquiry") == Name(b)
        assert proposal.get("offerB").get("disclosure") == Name(offer_b["occurrence"])
        assert proposal.get("offerB").get("cut") == Name(cuts["B"])
        expanded = trusted.named_eidos_value(outcome.get("context").value)["value"]
        # Context cuts are canonically sorted; incorporation order belongs to
        # the occurrence lineage below, not this set-like collection.
        assert len(expanded.get("cuts")) == 2
        assert set(expanded.get("cuts")) == {Name(cuts["A"]), Name(cuts["B"])}
        assert expanded.get("parent") == Name(context)
        events = [trusted.named_eidos_value(ref.value)["value"] for ref in outcome.get("events")]
        assert [event.get("operation") for event in events] == [DISCOVER, DISCOVER, AWAIT_DISCOVERY, AWAIT_DISCOVERY]
        assert [event.get("response").get("inquiry") for event in events] == [Name(a), Name(b), Name(a), Name(b)]
        for event, decision in zip(outcome.get("events")[-2:], (refusal_a, offer_b)):
            assert trusted.authority_occurrence(event.value)["fact"]["causal_source"] == decision["occurrence"]

        # Historical checkpoints/decisions reproduce receipts, not new grants.
        before = _occurrences(trusted)
        assert restarted.advance(started.checkpoint) == opened_a
        assert restarted.advance(opened_a.checkpoint) == opened_b
        assert restarted.advance(opened_b.checkpoint) == incorporated_a
        assert restarted.advance(incorporated_a.checkpoint) == finished
        assert decide_inquiry(
            trusted, inquiry=b, responder_projection=accepted_b["responder"],
            decision="offer", cut=cuts["B"], request_id="multiple:offer:B",
        ) == offer_b
        with pytest.raises(DiscoveryError, match="terminal response"):
            decide_inquiry(trusted, inquiry=b, responder_projection=accepted_b["responder"],
                           decision="refuse", request_id="multiple:rewrite:B")
        assert _occurrences(trusted) == before
        assert trusted.projection(accepted_a["responder"])["disposition"] == "spent"
        assert trusted.projection(accepted_b["responder"])["disposition"] == "spent"
    finally:
        trusted.close()
