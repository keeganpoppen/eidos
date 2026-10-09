import pytest

from eidos.genesis import admit_genesis
from eidos.cuts import ObservedCut, elaborate_cuts
from eidos.occurrence import (
    FrontierProjection,
    ProjectionTemplate,
    ReactionRule,
    RecursiveProtocol,
)
from eidos.trusted import Conflict, TrustedMachinery


def observer_protocol() -> RecursiveProtocol:
    return RecursiveProtocol(
        name="observer-relative",
        initial=(
            ProjectionTemplate("A", "a0"),
            ProjectionTemplate("B", "b0"),
            ProjectionTemplate("C", "c0"),
            ProjectionTemplate("D", "d0"),
        ),
        reactions=(
            ReactionRule(
                name="left",
                requires=(
                    ProjectionTemplate("A", "a0"),
                    ProjectionTemplate("B", "b0"),
                ),
                successors=(
                    ProjectionTemplate("A", "a1"),
                    ProjectionTemplate("B", "b1"),
                ),
            ),
            ReactionRule(
                name="right",
                requires=(
                    ProjectionTemplate("C", "c0"),
                    ProjectionTemplate("D", "d0"),
                ),
                successors=(
                    ProjectionTemplate("C", "c1"),
                    ProjectionTemplate("D", "d1"),
                ),
            ),
            ReactionRule(
                name="join",
                requires=(
                    ProjectionTemplate("B", "b1"),
                    ProjectionTemplate("D", "d1"),
                ),
                successors=(
                    ProjectionTemplate("B", "b2"),
                    ProjectionTemplate("D", "d2"),
                ),
            ),
        ),
    )


def as_observed_cut(tm: TrustedMachinery, cut: str) -> ObservedCut:
    row = tm.causal_cut(cut)
    return ObservedCut(
        name=cut,
        observer=row["observer"],
        protocol_cid=row["protocol_cid"],
        parent_cut=row["parent_cut"],
        parent_occurrence=row["parent_occurrence"],
        projections=tuple(
            FrontierProjection(
                name=projection["name"],
                role=projection["role"],
                state=projection["protocol_state"],
                holder=projection["holder"],
            )
            for projection in row["projections"]
            if projection["disposition"] == "live"
        ),
    )


def setup_observer_cuts():
    tm = TrustedMachinery()
    protocol = observer_protocol()
    installed = admit_genesis(
        tm,
        protocol,
        holders={
            "A": "alice",
            "B": "bob",
            "C": "carol",
            "D": "dan",
        },
        request_id="observer-genesis",
    )

    left = tm.create_observed_cut(
        instance=installed["instance"],
        observer="O1",
        protocol_cid=protocol.cid,
        projections=[
            installed["projections"]["projection:A"],
            installed["projections"]["projection:B"],
        ],
        request_id="cut-o1",
        elaborator="elaborator:left",
    )
    right = tm.create_observed_cut(
        instance=installed["instance"],
        observer="O2",
        protocol_cid=protocol.cid,
        projections=[
            installed["projections"]["projection:C"],
            installed["projections"]["projection:D"],
        ],
        request_id="cut-o2",
        elaborator="elaborator:right",
    )
    return tm, protocol, installed, left, right


def admit_one(tm, protocol, cut_info, *, elaborator, actualizer, request_id):
    cut = as_observed_cut(tm, cut_info["cut"])
    blueprint = elaborate_cuts(
        protocol,
        cuts=(cut,),
        elaborator=elaborator,
        actualizer=actualizer,
    )
    admitted = tm.admit_cut_elaboration(
        blueprint=blueprint,
        authorities={cut.name: cut_info["authority"]},
        request_id=request_id,
    )
    return blueprint, admitted


def test_disjoint_observer_cuts_actualize_without_global_generation_lock():
    tm, protocol, _, left, right = setup_observer_cuts()

    left_blueprint, left_admitted = admit_one(
        tm,
        protocol,
        left,
        elaborator="elaborator:left",
        actualizer="actualizer:local",
        request_id="admit-left",
    )
    right_blueprint, right_admitted = admit_one(
        tm,
        protocol,
        right,
        elaborator="elaborator:right",
        actualizer="actualizer:local",
        request_id="admit-right",
    )

    assert [p.reaction for p in left_blueprint.possibilities] == ["left"]
    assert [p.reaction for p in right_blueprint.possibilities] == ["right"]

    left_possibility = next(iter(left_admitted["possibilities"].values()))
    right_possibility = next(iter(right_admitted["possibilities"].values()))

    left_occurrence = tm.actualize_observed(
        possibility=left_possibility,
        actualizer="actualizer:local",
        authority=left_admitted["actualizers"][left_possibility],
        observation={"observer": "O1", "signal": "left"},
        request_id="actualize-left",
    )

    # O2's cut and possibility remain current. There is no global frontier
    # generation that was consumed by O1's independent occurrence.
    assert tm.causal_cut(right["cut"])["state"] == "elaborated"
    assert tm.observed_possibility(right_possibility)["state"] == "open"

    right_occurrence = tm.actualize_observed(
        possibility=right_possibility,
        actualizer="actualizer:local",
        authority=right_admitted["actualizers"][right_possibility],
        observation={"observer": "O2", "signal": "right"},
        request_id="actualize-right",
    )

    assert left_occurrence["occurrence"] != right_occurrence["occurrence"]
    assert tm.observed_possibility(left_possibility)["state"] == "occurred"
    assert tm.observed_possibility(right_possibility)["state"] == "occurred"


def test_joint_elaboration_discovers_reaction_in_union_of_observer_worlds():
    tm, protocol, _, left, right = setup_observer_cuts()

    _, left_admitted = admit_one(
        tm,
        protocol,
        left,
        elaborator="elaborator:left",
        actualizer="actualizer:local",
        request_id="join-admit-left",
    )
    _, right_admitted = admit_one(
        tm,
        protocol,
        right,
        elaborator="elaborator:right",
        actualizer="actualizer:local",
        request_id="join-admit-right",
    )

    left_possibility = next(iter(left_admitted["possibilities"].values()))
    right_possibility = next(iter(right_admitted["possibilities"].values()))

    left_occurrence = tm.actualize_observed(
        possibility=left_possibility,
        actualizer="actualizer:local",
        authority=left_admitted["actualizers"][left_possibility],
        observation={"observer": "O1"},
        request_id="join-left",
    )
    right_occurrence = tm.actualize_observed(
        possibility=right_possibility,
        actualizer="actualizer:local",
        authority=right_admitted["actualizers"][right_possibility],
        observation={"observer": "O2"},
        request_id="join-right",
    )

    left_cut = next(iter(left_occurrence["successor_cuts"].values()))
    right_cut = next(iter(right_occurrence["successor_cuts"].values()))

    # Neither observer can see the join alone.
    left_only = elaborate_cuts(
        protocol,
        cuts=(as_observed_cut(tm, left_cut),),
        elaborator="elaborator:left",
        actualizer="actualizer:joint",
    )
    right_only = elaborate_cuts(
        protocol,
        cuts=(as_observed_cut(tm, right_cut),),
        elaborator="elaborator:right",
        actualizer="actualizer:joint",
    )
    assert [p.reaction for p in left_only.possibilities] == []
    assert [p.reaction for p in right_only.possibilities] == []

    # The union of the two observer-relative cuts makes the relation addressable.
    joint = elaborate_cuts(
        protocol,
        cuts=(
            as_observed_cut(tm, left_cut),
            as_observed_cut(tm, right_cut),
        ),
        elaborator="elaborator:joint",
        actualizer="actualizer:joint",
    )
    assert joint.observers == ("O1", "O2")
    assert [p.reaction for p in joint.possibilities] == ["join"]

    left_elaborator = left_occurrence["elaborators"][left_cut]
    right_elaborator = right_occurrence["elaborators"][right_cut]
    tm.transfer_projection(
        projection=left_elaborator,
        from_holder="O1",
        to_holder="elaborator:joint",
        request_id="delegate-left-to-joint",
    )
    tm.transfer_projection(
        projection=right_elaborator,
        from_holder="O2",
        to_holder="elaborator:joint",
        request_id="delegate-right-to-joint",
    )

    admitted = tm.admit_cut_elaboration(
        blueprint=joint,
        authorities={
            left_cut: left_elaborator,
            right_cut: right_elaborator,
        },
        request_id="admit-joint",
    )
    join_possibility = next(iter(admitted["possibilities"].values()))

    joined = tm.actualize_observed(
        possibility=join_possibility,
        actualizer="actualizer:joint",
        authority=admitted["actualizers"][join_possibility],
        observation={"witness": "shared relation became discernible"},
        request_id="actualize-joint",
    )

    record = tm.observed_occurrence(joined["occurrence"])
    assert set(record["cuts"]) == {left_cut, right_cut}

    successor_left = joined["successor_cuts"][left_cut]
    successor_right = joined["successor_cuts"][right_cut]
    assert (
        tm.causal_cut(successor_left)["parent_occurrence"]
        == tm.causal_cut(successor_right)["parent_occurrence"]
        == joined["occurrence"]
    )

    # Each observer keeps a local cut, but both histories now name the same
    # occurrence as their immediate causal parent.
    left_states = {
        p["role"]: p["protocol_state"]
        for p in tm.causal_cut(successor_left)["projections"]
    }
    right_states = {
        p["role"]: p["protocol_state"]
        for p in tm.causal_cut(successor_right)["projections"]
    }
    assert left_states == {"A": "a1", "B": "b2"}
    assert right_states == {"C": "c1", "D": "d2"}


def test_cut_name_is_identity_not_elaboration_authority():
    tm, protocol, _, left, _ = setup_observer_cuts()
    cut = as_observed_cut(tm, left["cut"])
    blueprint = elaborate_cuts(
        protocol,
        cuts=(cut,),
        elaborator="elaborator:left",
        actualizer="actualizer:local",
    )

    with pytest.raises(Conflict, match="Elaborator projection"):
        tm.admit_cut_elaboration(
            blueprint=blueprint,
            authorities={cut.name: cut.name},
            request_id="cut-name-not-authority",
        )


def test_actualizer_is_a_role_selected_by_the_elaboration():
    tm, protocol, _, left, _ = setup_observer_cuts()
    tm.transfer_projection(
        projection=left["authority"],
        from_holder="elaborator:left",
        to_holder="elaborator:alice",
        request_id="delegate-elaborator-role",
    )
    _, admitted = admit_one(
        tm,
        protocol,
        left,
        elaborator="elaborator:alice",
        actualizer="actualizer:alpha",
        request_id="role-admission",
    )
    possibility = next(iter(admitted["possibilities"].values()))

    with pytest.raises(Conflict, match="Actualizer"):
        tm.actualize_observed(
            possibility=possibility,
            actualizer="actualizer:beta",
            authority=admitted["actualizers"][possibility],
            observation={},
            request_id="wrong-actualizer",
        )

    occurred = tm.actualize_observed(
        possibility=possibility,
        actualizer="actualizer:alpha",
        authority=admitted["actualizers"][possibility],
        observation={},
        request_id="right-actualizer",
    )
    assert occurred["actualizer"] == "actualizer:alpha"



def test_meta_roles_are_ordinary_live_projections():
    tm, protocol, _, left, _ = setup_observer_cuts()
    elaborator_projection = left["elaborator_projection"]
    row = tm.projection(elaborator_projection)
    assert row["role"] == "Elaborator"
    assert row["holder"] == "elaborator:left"
    assert row["disposition"] == "live"

    _, admitted = admit_one(
        tm,
        protocol,
        left,
        elaborator="elaborator:left",
        actualizer="actualizer:alpha",
        request_id="ordinary-meta-role-admission",
    )
    assert tm.projection(elaborator_projection)["disposition"] == "spent"

    possibility = next(iter(admitted["possibilities"].values()))
    actualizer_projection = admitted["actualizers"][possibility]
    actualizer_row = tm.projection(actualizer_projection)
    assert actualizer_row["role"] == "Actualizer"
    assert actualizer_row["holder"] == "actualizer:alpha"
    assert actualizer_row["disposition"] == "live"

    tm.actualize_observed(
        possibility=possibility,
        actualizer="actualizer:alpha",
        authority=actualizer_projection,
        observation={},
        request_id="ordinary-meta-role-actualize",
    )
    assert tm.projection(actualizer_projection)["disposition"] == "spent"


def test_epistemic_context_changes_elaboration_proof_not_world_authority():
    tm, protocol, _, left, _ = setup_observer_cuts()
    cut = as_observed_cut(tm, left["cut"])

    shallow = elaborate_cuts(
        protocol,
        cuts=(cut,),
        elaborator="elaborator:left",
        actualizer="actualizer:local",
        knowledge=("night-sky:raw-observation",),
    )
    deep = elaborate_cuts(
        protocol,
        cuts=(cut,),
        elaborator="elaborator:left",
        actualizer="actualizer:local",
        knowledge=(
            "night-sky:raw-observation",
            "astronomy:model",
            "catalog:stellar-objects",
        ),
    )

    assert shallow.projections == deep.projections
    assert shallow.possibilities == deep.possibilities
    assert shallow.proof != deep.proof
    assert shallow.knowledge != deep.knowledge



def test_delegating_elaborator_changes_interpreter_not_observed_world():
    tm, protocol, _, left, _ = setup_observer_cuts()
    cut_before = tm.causal_cut(left["cut"])
    world_projection_names = {
        projection["name"] for projection in cut_before["projections"]
    }

    delegated = tm.transfer_projection(
        projection=left["elaborator_projection"],
        from_holder="elaborator:left",
        to_holder="elaborator:deep",
        request_id="delegate-to-deeper-model",
    )
    assert delegated["role"] == "Elaborator"

    cut_after = tm.causal_cut(left["cut"])
    assert {
        projection["name"] for projection in cut_after["projections"]
    } == world_projection_names

    blueprint = elaborate_cuts(
        protocol,
        cuts=(as_observed_cut(tm, left["cut"]),),
        elaborator="elaborator:deep",
        actualizer="actualizer:local",
        knowledge=(
            "observation:raw",
            "model:domain-theory",
            "model:historical-context",
        ),
    )
    admitted = tm.admit_cut_elaboration(
        blueprint=blueprint,
        authorities={left["cut"]: left["elaborator_projection"]},
        request_id="deep-elaboration",
    )
    assert admitted["possibilities"]


def test_actualizer_authority_is_not_just_the_actualizer_name():
    tm, protocol, _, left, _ = setup_observer_cuts()
    _, admitted = admit_one(
        tm,
        protocol,
        left,
        elaborator="elaborator:left",
        actualizer="actualizer:alpha",
        request_id="actualizer-authority-admission",
    )
    possibility = next(iter(admitted["possibilities"].values()))

    with pytest.raises(Conflict, match="Actualizer projection"):
        tm.actualize_observed(
            possibility=possibility,
            actualizer="actualizer:alpha",
            authority=left["cut"],
            observation={},
            request_id="actualizer-name-is-not-capability",
        )


def test_actualization_mints_next_elaborator_as_ordinary_projection():
    tm, protocol, _, left, _ = setup_observer_cuts()
    _, admitted = admit_one(
        tm,
        protocol,
        left,
        elaborator="elaborator:left",
        actualizer="actualizer:alpha",
        request_id="next-elaborator-admission",
    )
    possibility = next(iter(admitted["possibilities"].values()))
    occurred = tm.actualize_observed(
        possibility=possibility,
        actualizer="actualizer:alpha",
        authority=admitted["actualizers"][possibility],
        observation={},
        request_id="next-elaborator-occurrence",
    )

    successor_cut = next(iter(occurred["successor_cuts"].values()))
    elaborator_projection = occurred["elaborators"][successor_cut]
    row = tm.projection(elaborator_projection)
    assert row["role"] == "Elaborator"
    assert row["holder"] == "O1"
    assert row["disposition"] == "live"
