import json
import sys

import pytest

from eidos.core import (
    Closure,
    Done,
    Get,
    Lambda,
    LexicalEnv,
    Lit,
    Name,
    Need,
    PraxisCore,
    Record,
    RecordValue,
    Role,
    Socket,
    Suspended,
    Var,
)
from eidos.cuts import ObservedCut, elaborate_cuts
from eidos.epistemics import (
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
    ELABORATE,
    MetaProtocolDriver,
    elaborate_operation,
)
from eidos.model_execution import (
    MODEL_CONTEXT_ROLE,
    MODEL_ROLE,
    ModelExecutionError,
    SubprocessModelAdapter,
    executor_value,
    model_claim,
    model_proposal,
)
from eidos.occurrence import (
    FrontierProjection,
    ProjectionTemplate,
    ReactionRule,
    RecursiveProtocol,
)
from eidos.trusted import TrustedMachinery


def persist(tm, kind, value):
    name = tm.reserve_name(
        kind=kind, request_id=f"model-reserve:{kind}:{len(tm.named_values())}"
    )
    tm.bind_eidos_value(
        name=name, value=value, request_id=f"model-bind:{name}"
    )
    return name


def semantic_protocol():
    return RecursiveProtocol(
        name="executable-model-roles",
        initial=(
            ProjectionTemplate("A", "watching"),
            ProjectionTemplate("B", "watching"),
        ),
        reactions=(
            ReactionRule(
                "recognize",
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


def observed(tm, name):
    row = tm.causal_cut(name)
    return ObservedCut(
        name=name,
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


def closure_model(fact="sky:recognized", premises=("sky:pattern",)):
    """Ordinary serializable Eidos code, consuming context via situated Roles."""

    claim = model_claim(fact, premises=premises, witness="closure:rule")
    result = PraxisCore().realize(
        Lambda(
            ("request",),
            Record.from_mapping({
                "$kind": Lit("ModelProposal"),
                "context": Need(MODEL_CONTEXT_ROLE),
                "claims": Lit((claim,)),
                "receipt": Record.from_mapping({
                    "$kind": Lit("ClosureReceipt"),
                    "model": Need(MODEL_ROLE),
                    "context": Get(Var("request"), "context"),
                    "facts_seen": Get(Var("request"), "facts"),
                }),
            }),
        )
    )
    assert isinstance(result, Done)
    assert isinstance(result.value, Closure)
    return result.value


def world():
    tm = TrustedMachinery()
    p = semantic_protocol()
    genesis = admit_genesis(
        tm,
        p,
        holders={"A": "alice", "B": "bob"},
        request_id="model-genesis",
    )
    cut = tm.create_observed_cut(
        instance=genesis["instance"],
        observer="observer",
        protocol_cid=p.cid,
        projections=tuple(genesis["projections"].values()),
        elaborator="elaborator:model",
        request_id="model-cut",
    )
    claim = persist(
        tm, "knowledge",
        knowledge_value("sky:pattern", grounds=(cut["cut"],)),
    )
    attention = persist(
        tm, "attention", attention_value(inference_budget=1)
    )

    rule_model = persist(
        tm, "model",
        model_value(
            "rule",
            rules=(implication_value(("sky:pattern",), "sky:recognized"),),
            sources=(cut["cut"],),
        ),
    )
    eidos_model = persist(
        tm, "model",
        model_value(
            "eidos-closure",
            implementation=closure_model(),
            sources=(cut["cut"],),
        ),
    )
    executor = persist(
        tm, "executor",
        executor_value("local-process", label="sky-classifier"),
    )
    delegated_model = persist(
        tm, "model",
        model_value(
            "delegated",
            implementation=executor,
            sources=(cut["cut"],),
        ),
    )
    contexts = {
        mode: persist(
            tm, "context",
            context_value(
                cuts=(cut["cut"],),
                knowledge=(claim,),
                models=(model,),
                attention=attention,
            ),
        )
        for mode, model in (
            ("rules", rule_model),
            ("closure", eidos_model),
            ("delegated", delegated_model),
        )
    }
    return tm, p, cut, {
        "claim": claim,
        "attention": attention,
        "model:rules": rule_model,
        "model:closure": eidos_model,
        "model:delegated": delegated_model,
        "executor": executor,
        **contexts,
    }


def callback_proposal(seen):
    def adapter(request):
        seen.append(request)
        assert request.get("$kind") == "ModelInput"
        return model_proposal(
            request.get("context"),
            (model_claim(
                "sky:recognized",
                premises=("sky:pattern",),
                witness=RecordValue.from_mapping({
                    "$kind": "ExternalWitness",
                    "source": "specialist",
                }),
            ),),
            receipt=RecordValue.from_mapping({
                "$kind": "ExecutorReceipt",
                "facts_seen": request.get("facts"),
            }),
        )
    return adapter


def derive(tm, p, cut, context, adapters=None):
    return elaborate_cuts(
        p,
        cuts=(observed(tm, cut["cut"]),),
        elaborator="elaborator:model",
        actualizer="actualizer:model",
        context=context,
        resolve=lambda name: tm.named_eidos_value(name)["value"],
        adapters=adapters,
    )


def authority_snapshot(tm):
    return tuple(
        tuple(row)
        for row in tm.db.execute(
            "SELECT name,domain_name,holder,disposition FROM projections ORDER BY name"
        )
    )


def test_rule_closure_and_delegated_models_have_same_semantic_contract():
    tm, p, cut, refs = world()
    before = authority_snapshot(tm)
    calls = []
    adapters = {refs["executor"]: callback_proposal(calls)}

    realized = {
        mode: derive(tm, p, cut, refs[mode], adapters)
        for mode in ("rules", "closure", "delegated")
    }
    assert len(calls) == 1
    assert len({tuple(step.fact for step in v.inferences) for v in realized.values()}) == 1
    assert all(r.facts == ("sky:pattern", "sky:recognized") for r in realized.values())
    assert all(
        [possibility.reaction for possibility in r.possibilities] == ["recognize"]
        for r in realized.values()
    )
    assert {
        mode: result.inferences[0].engine
        for mode, result in realized.items()
    } == {
        "rules": "rules",
        "closure": "closure",
        "delegated": "delegated",
    }
    for result in realized.values():
        assert len(result.derivations) == 1
        assert result.derivations[0].get("$kind") == "ModelDerivation"
        assert result.inferences[0].derivation is not None
        assert result.inferences[0].premises == ("sky:pattern",)
    assert authority_snapshot(tm) == before


def test_delegated_model_is_explicitly_registered_and_derivation_is_addressable():
    tm, p, cut, refs = world()
    driver = MetaProtocolDriver(tm)
    driver.register(p)
    seen = []
    with pytest.raises(ModelExecutionError, match="explicitly registered"):
        derive(tm, p, cut, refs["delegated"])

    driver.register_executor(refs["executor"], callback_proposal(seen))
    praxis = PraxisCore()
    term = elaborate_operation(
        Lit(Socket(Name(cut["elaborator_projection"]))),
        protocol_cid=p.cid,
        cuts=(cut["cut"],),
        authorities={cut["cut"]: cut["elaborator_projection"]},
        context=refs["delegated"],
        actualizer="actualizer:model",
        result_as="result",
        successor_as="next",
        then=Var("result"),
    )
    suspended = praxis.realize(term)
    assert isinstance(suspended, Suspended)
    assert suspended.operation == ELABORATE

    reaction = driver.react(suspended, request_id="delegate-model-elaboration")
    assert len(seen) == 1
    done = praxis.resume(suspended, reaction)
    assert isinstance(done, Done)
    derivation_ref, = done.value.get("derivations")
    assert isinstance(derivation_ref, Name)

    elaboration = tm.named_eidos_value(reaction.name.value)["value"]
    assert derivation_ref in elaboration.get("derivations")
    derivation = tm.named_eidos_value(derivation_ref.value)["value"]
    assert derivation.get("$kind") == "ModelDerivation"
    assert derivation.get("engine") == "delegated"
    assert derivation.get("executor") == Name(refs["executor"])
    assert derivation.get("model") == Name(refs["model:delegated"])
    assert derivation.get("input").get("context") == Name(refs["delegated"])
    assert derivation.get("proposal").get("receipt").get("$kind") == "ExecutorReceipt"
    assert elaboration.get("inferences")[0].get("derivation") == tm.named_eidos_value(derivation_ref.value)["cid"]

    neighborhood = walk_named_values(
        (reaction.name.value,),
        resolve=lambda name: tm.named_eidos_value(name)["value"],
        depth=4,
    )
    nodes = neighborhood.by_name()
    assert derivation_ref.value in nodes
    assert refs["executor"] in nodes
    assert refs["delegated"] in nodes
    assert refs["claim"] in nodes

    # Only the delegated Elaborator projection has been consumed.
    assert tm.projection(cut["elaborator_projection"])["disposition"] == "spent"
    for p in tm.causal_cut(cut["cut"])["projections"]:
        assert p["disposition"] == "live"


def test_subprocess_transport_uses_same_model_proposal_value_protocol():
    tm, p, cut, refs = world()
    source = (
        "import json,sys;"
        "from eidos.core import from_data,to_data,RecordValue;"
        "from eidos.model_execution import model_claim,model_proposal;"
        "r=from_data(json.load(sys.stdin));"
        "o=model_proposal(r.get('context'),("
        "model_claim('sky:recognized',premises=('sky:pattern',),witness='subprocess'),),"
        "receipt=RecordValue.from_mapping({'$kind':'ProcessReceipt','ok':True}));"
        "json.dump(to_data(o),sys.stdout)"
    )
    adapter = SubprocessModelAdapter(
        argv=(sys.executable, "-c", source),
        timeout_seconds=5,
    )
    result = derive(tm, p, cut, refs["delegated"], {refs["executor"]: adapter})
    assert [p.reaction for p in result.possibilities] == ["recognize"]
    assert result.inferences[0].witness == "subprocess"
    assert result.derivations[0].get("proposal").get("receipt").get("$kind") == "ProcessReceipt"


def test_unsubstantiated_executor_claims_are_not_accepted_as_inferences():
    tm, p, cut, refs = world()
    before = authority_snapshot(tm)
    ungrounded = model_value(
        "unsubstantiated",
        implementation=closure_model(
            fact="sky:recognized",
            premises=("sky:invented-geometry",),
        ),
    )
    model = persist(tm, "model", ungrounded)
    context = persist(
        tm, "context",
        context_value(
            cuts=(cut["cut"],),
            knowledge=(refs["claim"],),
            models=(model,),
            attention=refs["attention"],
        ),
    )
    result = derive(tm, p, cut, context)
    assert result.inferences == ()
    assert result.facts == ("sky:pattern",)
    assert result.possibilities == ()
    assert len(result.derivations) == 1
    assert authority_snapshot(tm) == before


def test_closure_cannot_perform_from_a_pure_local_model():
    tm, p, cut, refs = world()
    unresolved = Closure(
        parameters=("request",),
        body=Need(Role("unsafe", "unbound")),
        lexical=LexicalEnv(),
    )
    model = persist(tm, "model", model_value("unbound", implementation=unresolved))
    context = persist(
        tm, "context",
        context_value(
            cuts=(cut["cut"],),
            knowledge=(refs["claim"],),
            models=(model,),
            attention=refs["attention"],
        ),
    )
    before = authority_snapshot(tm)
    with pytest.raises(ModelExecutionError, match="without unbound Roles or perform"):
        derive(tm, p, cut, context)
    assert authority_snapshot(tm) == before


def test_bad_delegated_proposal_is_rejected_before_any_authority_change():
    tm, p, cut, refs = world()
    before = authority_snapshot(tm)

    def forged_context(request):
        return model_proposal(
            Name("context:someone-else"),
            (model_claim("sky:recognized", premises=("sky:pattern",)),),
        )

    with pytest.raises(ModelExecutionError, match="wrong Context"):
        derive(tm, p, cut, refs["delegated"], {refs["executor"]: forged_context})
    assert authority_snapshot(tm) == before


def test_attention_does_not_call_unneeded_delegated_model():
    tm, p, cut, refs = world()
    calls = []
    context = persist(
        tm, "context",
        context_value(
            cuts=(cut["cut"],),
            knowledge=(refs["claim"],),
            models=(refs["model:rules"], refs["model:delegated"]),
            attention=refs["attention"],
        ),
    )
    result = derive(
        tm, p, cut, context,
        adapters={refs["executor"]: callback_proposal(calls)},
    )
    assert len(result.inferences) == 1
    assert result.inferences[0].engine == "rules"
    assert calls == []
    assert len(result.derivations) == 1
