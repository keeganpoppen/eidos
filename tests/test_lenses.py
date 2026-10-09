from eidos.genesis import admit_genesis
from eidos.core import Name
from eidos.cuts import ObservedCut, elaborate_cuts
from eidos.lenses import build_semantic_index, walk_named_values
from eidos.occurrence import (
    FrontierProjection,
    ProjectionTemplate,
    ReactionRule,
    RecursiveProtocol,
)
from eidos.trusted import TrustedMachinery


def protocol() -> RecursiveProtocol:
    return RecursiveProtocol(
        name="lens-depth",
        initial=(
            ProjectionTemplate("A", "a0"),
            ProjectionTemplate("B", "b0"),
        ),
        reactions=(
            ReactionRule(
                name="advance",
                requires=(
                    ProjectionTemplate("A", "a0"),
                    ProjectionTemplate("B", "b0"),
                ),
                successors=(
                    ProjectionTemplate("A", "a1"),
                    ProjectionTemplate("B", "b1"),
                ),
            ),
        ),
    )


def cut_from_name(tm: TrustedMachinery, name: str) -> ObservedCut:
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


def build_history():
    tm = TrustedMachinery()
    p = protocol()
    installed = admit_genesis(
        tm,
        p,
        holders={"A": "alice", "B": "bob"},
        request_id="lens-genesis",
    )
    cut = tm.create_observed_cut(
        instance=installed["instance"],
        observer="observer",
        protocol_cid=p.cid,
        projections=[
            installed["projections"]["projection:A"],
            installed["projections"]["projection:B"],
        ],
        elaborator="elaborator",
        request_id="lens-cut",
    )
    blueprint = elaborate_cuts(
        p,
        cuts=(cut_from_name(tm, cut["cut"]),),
        elaborator="elaborator",
        actualizer="actualizer",
        knowledge=("observation:raw", "model:domain"),
    )
    admitted = tm.admit_cut_elaboration(
        blueprint=blueprint,
        authorities={cut["cut"]: cut["elaborator_projection"]},
        request_id="lens-elaborate",
    )
    possibility = next(iter(admitted["possibilities"].values()))
    occurred = tm.actualize_observed(
        possibility=possibility,
        actualizer="actualizer",
        authority=admitted["actualizers"][possibility],
        observation={"seen": True},
        request_id="lens-actualize",
    )
    return tm, cut["cut"], admitted["occurrence"], possibility, occurred["occurrence"]


def resolve(tm: TrustedMachinery):
    return lambda name: tm.named_eidos_value(name)["value"]


def test_semantic_neighborhood_expands_progressively_by_depth():
    tm, cut, elaboration, possibility, occurrence = build_history()

    shallow = walk_named_values(
        (Name(occurrence),),
        resolve=resolve(tm),
        depth=0,
    )
    assert set(shallow.by_name()) == {occurrence}

    one_hop = walk_named_values(
        (occurrence,),
        resolve=resolve(tm),
        depth=1,
    )
    one = one_hop.by_name()
    assert occurrence in one
    assert possibility in one
    assert cut in one
    assert elaboration not in one

    two_hops = walk_named_values(
        (occurrence,),
        resolve=resolve(tm),
        depth=2,
    )
    two = two_hops.by_name()
    assert elaboration in two
    assert two[occurrence].depth == 0
    assert two[possibility].depth == 1
    assert two[elaboration].depth == 2


def test_capability_names_resolve_to_descriptions_without_granting_authority():
    tm, _, _, _, occurrence = build_history()

    neighborhood = walk_named_values(
        (occurrence,),
        resolve=resolve(tm),
        depth=3,
    )
    nodes = neighborhood.by_name()

    occurrence_node = nodes[occurrence]
    referenced = {
        name.value
        for name in occurrence_node.references
        if name.value.startswith("projection_")
    }
    assert referenced

    described = referenced & set(nodes)
    assert described
    for projection in described:
        node = nodes[projection]
        assert node.value.get("$kind") == "Projection"

    # Semantic inspection does not change or manufacture authority.
    before = {
        projection: tm.projection(projection)["disposition"]
        for projection in referenced
    }
    walk_named_values(
        tuple(referenced),
        resolve=resolve(tm),
        depth=1,
    )
    after = {
        projection: tm.projection(projection)["disposition"]
        for projection in referenced
    }
    assert after == before




def test_semantic_indexes_are_disposable_and_rebuildable():
    tm, cut, elaboration, possibility, occurrence = build_history()

    before_values = dict(tm.named_values())
    before_authority = {
        name: tm.projection(name)["disposition"]
        for name in before_values
        if name.startswith("projection_")
    }

    first = build_semantic_index(tm.named_values())
    rebuilt = build_semantic_index(tuple(reversed(tm.named_values())))

    assert first == rebuilt
    assert Name(cut) in first.names_of_kind("Cut")
    assert Name(possibility) in first.names_of_kind("Possibility")
    assert Name(elaboration) in first.names_of_kind("Elaboration")
    assert Name(occurrence) in first.names_of_kind("Occurrence")
    assert Name(occurrence) in first.referrers_of(possibility)

    # Rebuilding the index has no semantic or authority side effects.
    assert dict(tm.named_values()) == before_values
    after_authority = {
        name: tm.projection(name)["disposition"]
        for name in before_values
        if name.startswith("projection_")
    }
    assert after_authority == before_authority
