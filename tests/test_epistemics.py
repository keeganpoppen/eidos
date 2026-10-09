import pytest

from eidos.core import Done, Lit, Name, PraxisCore, RecordValue, Socket, Suspended, Var
from eidos.cuts import ObservedCut, elaborate_cuts
from eidos.epistemics import (
    ATTENTION_ROLE,
    KNOWLEDGE_ROLE,
    MODELS_ROLE,
    attention_value,
    context_value,
    implication_value,
    interpret_context,
    knowledge_value,
    model_value,
)
from eidos.genesis import admit_genesis
from eidos.lenses import walk_named_values
from eidos.meta_protocol import (
    ACTUALIZE,
    ELABORATE,
    MetaProtocolDriver,
    actualize_operation,
    elaborate_operation,
)
from eidos.occurrence import (
    FrontierProjection,
    ProjectionTemplate,
    ReactionRule,
    RecursiveProtocol,
)
from eidos.trusted import TrustedMachinery


def protocol():
    return RecursiveProtocol(
        name="sky-reading",
        initial=(
            ProjectionTemplate("A", "watching"),
            ProjectionTemplate("B", "watching"),
        ),
        reactions=(
            ReactionRule(
                name="simply-look",
                requires=(
                    ProjectionTemplate("A", "watching"),
                    ProjectionTemplate("B", "watching"),
                ),
                successors=(
                    ProjectionTemplate("A", "looked"),
                    ProjectionTemplate("B", "looked"),
                ),
            ),
            ReactionRule(
                name="recognize-pattern",
                requires=(
                    ProjectionTemplate("A", "watching"),
                    ProjectionTemplate("B", "watching"),
                ),
                successors=(
                    ProjectionTemplate("A", "recognized"),
                    ProjectionTemplate("B", "recognized"),
                ),
                requires_facts=("sky:recognized",),
            ),
        ),
    )


def persist(tm, kind, value):
    name = tm.reserve_name(kind=kind, request_id=f"reserve:{kind}:{len(tm.named_values())}")
    tm.bind_eidos_value(name=name, value=value, request_id=f"bind:{name}")
    return name


def cut_view(tm, cut):
    row = tm.causal_cut(cut)
    return ObservedCut(
        name=cut,
        observer=row["observer"],
        protocol_cid=row["protocol_cid"],
        parent_cut=row["parent_cut"],
        parent_occurrence=row["parent_occurrence"],
        projections=tuple(
            FrontierProjection(
                name=p["name"],
                role=p["role"],
                state=p["protocol_state"],
                holder=p["holder"],
            )
            for p in row["projections"]
        ),
    )


def world():
    tm = TrustedMachinery()
    p = protocol()
    genesis = admit_genesis(
        tm,
        p,
        holders={"A": "alice", "B": "bob"},
        request_id="sky-genesis",
    )
    cut = tm.create_observed_cut(
        instance=genesis["instance"],
        observer="O",
        protocol_cid=p.cid,
        projections=[
            genesis["projections"]["projection:A"],
            genesis["projections"]["projection:B"],
        ],
        elaborator="elaborator:sky",
        request_id="sky-cut",
    )
    cid = cut["cut"]

    observed = persist(
        tm,
        "knowledge",
        knowledge_value("sky:pattern", grounds=(Name(cid),)),
    )
    model = persist(
        tm,
        "model",
        model_value(
            "astronomy",
            rules=(
                implication_value(("sky:pattern",), "sky:triangulated"),
                implication_value(("sky:triangulated",), "sky:recognized"),
            ),
            sources=(cid,),
        ),
    )
    shallow_attention = persist(
        tm, "attention", attention_value(inference_budget=0)
    )
    intermediate_attention = persist(
        tm, "attention", attention_value(inference_budget=1)
    )
    deep_attention = persist(
        tm, "attention", attention_value(inference_budget=2)
    )

    shallow = persist(
        tm,
        "context",
        context_value(
            cuts=(cid,),
            knowledge=(observed,),
            attention=shallow_attention,
        ),
    )
    intermediate = persist(
        tm,
        "context",
        context_value(
            cuts=(cid,),
            models=(model,),
            attention=intermediate_attention,
            parent=shallow,
        ),
    )
    deep = persist(
        tm,
        "context",
        context_value(
            cuts=(cid,),
            attention=deep_attention,
            parent=intermediate,
        ),
    )

    return tm, p, cut, {
        "claim": observed,
        "model": model,
        "attention0": shallow_attention,
        "attention1": intermediate_attention,
        "attention2": deep_attention,
        "shallow": shallow,
        "intermediate": intermediate,
        "deep": deep,
    }


def derive(tm, p, cut, context):
    return elaborate_cuts(
        p,
        cuts=(cut_view(tm, cut["cut"]),),
        elaborator="elaborator:sky",
        actualizer="actualizer:sky",
        context=context,
        resolve=lambda name: tm.named_eidos_value(name)["value"],
    )


def test_epistemic_contexts_progressively_change_possibilities_without_authority():
    tm, p, cut, refs = world()
    before = tm.db.execute(
        "SELECT name,domain_name,holder,disposition FROM projections ORDER BY name"
    ).fetchall()
    before_rows = [tuple(row) for row in before]

    shallow = derive(tm, p, cut, refs["shallow"])
    intermediate = derive(tm, p, cut, refs["intermediate"])
    deep = derive(tm, p, cut, refs["deep"])

    assert [r.reaction for r in shallow.possibilities] == ["simply-look"]
    assert [r.reaction for r in intermediate.possibilities] == ["simply-look"]
    assert {r.reaction for r in deep.possibilities} == {
        "simply-look", "recognize-pattern"
    }

    assert shallow.facts == ("sky:pattern",)
    assert intermediate.facts == ("sky:pattern", "sky:triangulated")
    assert deep.facts == (
        "sky:pattern", "sky:recognized", "sky:triangulated"
    )
    assert [step.fact for step in deep.inferences] == [
        "sky:triangulated", "sky:recognized"
    ]
    assert all(step.model == refs["model"] for step in deep.inferences)
    assert deep.inferences[1].premises == ("sky:triangulated",)
    assert len({shallow.proof, intermediate.proof, deep.proof}) == 3

    after = tm.db.execute(
        "SELECT name,domain_name,holder,disposition FROM projections ORDER BY name"
    ).fetchall()
    assert [tuple(row) for row in after] == before_rows


def test_context_ancestry_and_role_bindings_are_ordinary_serializable_values():
    tm, _, cut, refs = world()
    result = interpret_context(
        refs["deep"],
        resolve=lambda name: tm.named_eidos_value(name)["value"],
        cuts=(cut["cut"],),
    )
    assert result.ancestry == (
        refs["shallow"], refs["intermediate"], refs["deep"]
    )
    assert result.knowledge == (refs["claim"],)
    assert result.models == (refs["model"],)
    assert result.attention == refs["attention2"]

    base = tm.named_eidos_value(refs["shallow"])["value"]
    bindings = base.get("bindings")
    assert tuple(ref.value for ref in bindings.lookup(KNOWLEDGE_ROLE)) == (
        refs["claim"],
    )
    assert bindings.lookup(MODELS_ROLE) == ()
    assert bindings.lookup(ATTENTION_ROLE) == Name(refs["attention0"])

    child = tm.named_eidos_value(refs["deep"])["value"]
    assert child.get("parent") == Name(refs["intermediate"])
    assert tm.named_eidos_value(refs["shallow"])["value"] == base


def test_meta_protocol_uses_context_and_persists_addressable_inferences():
    tm, p, cut, refs = world()
    driver = MetaProtocolDriver(tm)
    driver.register(p)
    praxis = PraxisCore()

    term = elaborate_operation(
        Lit(Socket(Name(cut["elaborator_projection"]))),
        protocol_cid=p.cid,
        cuts=(cut["cut"],),
        authorities={cut["cut"]: cut["elaborator_projection"]},
        context=Name(refs["deep"]),
        actualizer="actualizer:sky",
        result_as="result",
        successor_as="next",
        then=Var("result"),
    )
    suspended = praxis.realize(term)
    assert isinstance(suspended, Suspended)
    assert suspended.operation == ELABORATE

    reaction = driver.react(suspended, request_id="perform-sky-elaborate")
    resumed = praxis.resume(suspended, reaction)
    assert isinstance(resumed, Done)
    result = resumed.value
    assert isinstance(result, RecordValue)
    assert result.get("context") == Name(refs["deep"])
    assert "sky:recognized" in result.get("facts")

    elaboration = tm.named_eidos_value(reaction.name.value)["value"]
    assert elaboration.get("$kind") == "Elaboration"
    assert elaboration.get("context") == Name(refs["deep"])
    evidence = elaboration.get("inferences")
    assert len(evidence) == 2
    assert evidence[1].get("model") == Name(refs["model"])
    assert evidence[1].get("premises") == ("sky:triangulated",)

    neighborhood = walk_named_values(
        (reaction.name.value,),
        resolve=lambda name: tm.named_eidos_value(name)["value"],
        depth=5,
    )
    assert refs["deep"] in neighborhood.by_name()
    assert refs["model"] in neighborhood.by_name()
    assert refs["claim"] in neighborhood.by_name()
    assert refs["attention2"] in neighborhood.by_name()

    possibilities = result.get("possibilities").as_dict()
    recognized = next(
        name.value
        for key, name in possibilities.items()
        if key.endswith("reaction:recognize-pattern")
    )
    actualizer = result.get("actualizers").get(recognized)
    assert isinstance(actualizer, Socket)

    actualize = actualize_operation(
        Lit(actualizer),
        possibility=recognized,
        observation={"choice": "recognize-pattern"},
        result_as="result",
        successor_as="next",
        then=Var("result"),
    )
    suspended_actualize = praxis.realize(actualize)
    assert isinstance(suspended_actualize, Suspended)
    assert suspended_actualize.operation == ACTUALIZE
    committed_reaction = driver.react(
        suspended_actualize, request_id="actualize-recognized-sky"
    )
    assert committed_reaction.consumed_sockets
    finished = praxis.resume(suspended_actualize, committed_reaction)
    assert isinstance(finished, Done)
    assert tm.observed_possibility(recognized)["state"] == "occurred"

    # The contexts/models/knowledge never became consumable projection authority.
    assert tm.projection(cut["elaborator_projection"])["disposition"] == "spent"
    assert tm.named_eidos_value(refs["model"])["value"].get("$kind") == "Model"


def test_context_cannot_claim_another_cut_without_being_rebound():
    tm, p, cut, refs = world()
    unrelated = tm.create_observed_cut(
        instance=tm.causal_cut(cut["cut"])["instance_name"],
        observer="O2",
        protocol_cid=p.cid,
        projections=[],
        elaborator="other-elaborator",
        request_id="unrelated-cut",
    )
    with pytest.raises(ValueError, match="context causal cuts"):
        interpret_context(
            refs["deep"],
            resolve=lambda name: tm.named_eidos_value(name)["value"],
            cuts=(unrelated["cut"],),
        )


def test_model_facts_do_not_create_missing_world_projections():
    tm, p, cut, refs = world()
    # This model supplies an epistemic condition, not an authority capability.
    phantom = RecursiveProtocol(
        name="phantom-capabilities",
        initial=p.initial,
        reactions=(
            ReactionRule(
                name="requires-C",
                requires=(
                    ProjectionTemplate("A", "watching"),
                    ProjectionTemplate("C", "watching"),
                ),
                successors=(ProjectionTemplate("A", "a1"),),
                requires_facts=("sky:recognized",),
            ),
        ),
    )
    # Elaborate against the actual cut and a matching protocol commitment.
    # Keep the same protocol identity here by testing the local rule predicate.
    from eidos.cuts import _enabled

    by_role = {
        projection.role: projection
        for projection in cut_view(tm, cut["cut"]).projections
    }
    knowledge = interpret_context(
        refs["deep"],
        resolve=lambda name: tm.named_eidos_value(name)["value"],
        cuts=(cut["cut"],),
    )
    assert not _enabled(
        phantom.reactions[0],
        by_role,
        facts=knowledge.facts,
    )



def test_joint_specialist_elaboration_uses_two_grounded_cuts_without_new_authority():
    joint_protocol = RecursiveProtocol(
        name="joint-epistemic-recognition",
        initial=(
            ProjectionTemplate("A", "observing"),
            ProjectionTemplate("B", "observing"),
        ),
        reactions=(
            ReactionRule(
                name="recognize-together",
                requires=(
                    ProjectionTemplate("A", "observing"),
                    ProjectionTemplate("B", "observing"),
                ),
                successors=(
                    ProjectionTemplate("A", "recognized"),
                    ProjectionTemplate("B", "recognized"),
                ),
                requires_facts=("joint:recognized",),
            ),
        ),
    )
    tm = TrustedMachinery()
    genesis = admit_genesis(
        tm,
        joint_protocol,
        holders={"A": "alice", "B": "bob"},
        request_id="joint-knowledge-genesis",
    )
    left = tm.create_observed_cut(
        instance=genesis["instance"],
        observer="O1",
        protocol_cid=joint_protocol.cid,
        projections=[genesis["projections"]["projection:A"]],
        elaborator="elaborator:left",
        request_id="joint-knowledge-left",
    )
    right = tm.create_observed_cut(
        instance=genesis["instance"],
        observer="O2",
        protocol_cid=joint_protocol.cid,
        projections=[genesis["projections"]["projection:B"]],
        elaborator="elaborator:right",
        request_id="joint-knowledge-right",
    )

    claim_a = persist(
        tm, "knowledge", knowledge_value("signal:A", grounds=(left["cut"],))
    )
    claim_b = persist(
        tm, "knowledge", knowledge_value("signal:B", grounds=(right["cut"],))
    )
    model = persist(
        tm,
        "model",
        model_value(
            "cross-cut-correspondence",
            rules=(
                implication_value(
                    ("signal:A", "signal:B"), "joint:recognized"
                ),
            ),
            sources=(claim_a, claim_b),
        ),
    )
    attention = persist(
        tm, "attention", attention_value(inference_budget=1)
    )
    context = persist(
        tm,
        "context",
        context_value(
            cuts=(left["cut"], right["cut"]),
            knowledge=(claim_a, claim_b),
            models=(model,),
            attention=attention,
        ),
    )

    assert elaborate_cuts(
        joint_protocol,
        cuts=(cut_view(tm, left["cut"]),),
        elaborator="elaborator:left",
        actualizer="actualizer:joint",
    ).possibilities == ()
    assert elaborate_cuts(
        joint_protocol,
        cuts=(cut_view(tm, right["cut"]),),
        elaborator="elaborator:right",
        actualizer="actualizer:joint",
    ).possibilities == ()

    before_context_cid = tm.named_eidos_value(context)["cid"]
    tm.transfer_projection(
        projection=left["elaborator_projection"],
        from_holder="elaborator:left",
        to_holder="elaborator:specialist",
        request_id="joint-specialist-left",
    )
    tm.transfer_projection(
        projection=right["elaborator_projection"],
        from_holder="elaborator:right",
        to_holder="elaborator:specialist",
        request_id="joint-specialist-right",
    )
    assert tm.named_eidos_value(context)["cid"] == before_context_cid

    driver = MetaProtocolDriver(tm)
    driver.register(joint_protocol)
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
    reaction = driver.react(suspended, request_id="joint-specialist-elaborate")
    assert {socket.name.value for socket in reaction.consumed_sockets} == {
        left["elaborator_projection"], right["elaborator_projection"]
    }

    result = praxis.resume(suspended, reaction)
    assert isinstance(result, Done)
    possibilities = result.value.get("possibilities").as_dict()
    assert len(possibilities) == 1
    assert next(iter(possibilities)).endswith("reaction:recognize-together")

    elaboration = tm.named_eidos_value(reaction.name.value)["value"]
    assert elaboration.get("context") == Name(context)
    assert elaboration.get("inferences")[0].get("premises") == (
        "signal:A", "signal:B"
    )
    assert {ref.value for ref in elaboration.get("cuts")} == {
        left["cut"], right["cut"]
    }


def test_later_understanding_of_a_spent_cut_does_not_restore_authority():
    tm, p, cut, refs = world()
    original = derive(tm, p, cut, refs["shallow"])
    admitted = tm.admit_cut_elaboration(
        blueprint=original,
        authorities={cut["cut"]: cut["elaborator_projection"]},
        request_id="original-shallow-world",
    )
    look = next(iter(admitted["possibilities"].values()))
    tm.actualize_observed(
        possibility=look,
        actualizer="actualizer:sky",
        authority=admitted["actualizers"][look],
        observation={"did": "look"},
        request_id="actualize-shallow-world",
    )

    retrospective = derive(tm, p, cut, refs["deep"])
    assert {possibility.reaction for possibility in retrospective.possibilities} == {
        "simply-look", "recognize-pattern"
    }
    assert tm.causal_cut(cut["cut"])["state"] == "historical"

    from eidos.trusted import Conflict

    with pytest.raises(Conflict, match="Elaborator projection"):
        tm.admit_cut_elaboration(
            blueprint=retrospective,
            authorities={cut["cut"]: cut["elaborator_projection"]},
            request_id="retrospective-cannot-admit",
        )
