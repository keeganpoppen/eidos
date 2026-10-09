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


def branching_protocol() -> RecursiveProtocol:
    return RecursiveProtocol(
        name="tableless-branching",
        initial=(
            ProjectionTemplate("A", "ready"),
            ProjectionTemplate("B", "ready"),
        ),
        reactions=(
            ReactionRule(
                name="yes",
                requires=(
                    ProjectionTemplate("A", "ready"),
                    ProjectionTemplate("B", "ready"),
                ),
                successors=(
                    ProjectionTemplate("A", "yes"),
                    ProjectionTemplate("B", "yes"),
                ),
            ),
            ReactionRule(
                name="no",
                requires=(
                    ProjectionTemplate("A", "ready"),
                    ProjectionTemplate("B", "ready"),
                ),
                successors=(
                    ProjectionTemplate("A", "no"),
                    ProjectionTemplate("B", "no"),
                ),
            ),
        ),
    )


def cut_value_view(tm: TrustedMachinery, cut: str) -> ObservedCut:
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
        ),
    )


def setup_branching():
    tm = TrustedMachinery()
    protocol = branching_protocol()
    installed = admit_genesis(
        tm,
        protocol,
        holders={"A": "alice", "B": "bob"},
        request_id="branching-genesis",
    )
    cut = tm.create_observed_cut(
        instance=installed["instance"],
        observer="observer",
        protocol_cid=protocol.cid,
        projections=[
            installed["projections"]["projection:A"],
            installed["projections"]["projection:B"],
        ],
        elaborator="elaborator",
        request_id="branching-cut",
    )
    blueprint = elaborate_cuts(
        protocol,
        cuts=(cut_value_view(tm, cut["cut"]),),
        elaborator="elaborator",
        actualizer="actualizer",
    )
    admitted = tm.admit_cut_elaboration(
        blueprint=blueprint,
        authorities={cut["cut"]: cut["elaborator_projection"]},
        request_id="branching-elaborate",
    )
    by_key = admitted["possibilities"]
    return tm, protocol, cut, admitted, by_key


def test_competing_possibility_is_precluded_by_generic_authority_occurrence():
    tm, _, _, admitted, by_key = setup_branching()

    yes = by_key[next(key for key in by_key if key.endswith("reaction:yes"))]
    no = by_key[next(key for key in by_key if key.endswith("reaction:no"))]

    assert tm.observed_possibility(yes)["state"] == "open"
    assert tm.observed_possibility(no)["state"] == "open"

    tm.actualize_observed(
        possibility=yes,
        actualizer="actualizer",
        authority=admitted["actualizers"][yes],
        observation={"choice": "yes"},
        request_id="actualize-yes",
    )

    assert tm.observed_possibility(yes)["state"] == "occurred"
    assert tm.observed_possibility(no)["state"] == "precluded"

    no_actualizer = admitted["actualizers"][no]
    rows = tm.db.execute(
        "SELECT ao.name,ao.kind,ao.fact_json "
        "FROM authority_occurrence_inputs aoi "
        "JOIN authority_occurrences ao ON ao.name=aoi.occurrence_name "
        "WHERE aoi.projection_name=?",
        (no_actualizer,),
    ).fetchall()
    assert len(rows) == 1
    assert rows[0]["kind"] == "Preclude"
    assert tm.projection(no_actualizer)["disposition"] == "spent"

    with pytest.raises(Conflict, match="Actualizer projection"):
        tm.actualize_observed(
            possibility=no,
            actualizer="actualizer",
            authority=no_actualizer,
            observation={"choice": "no"},
            request_id="actualize-precluded-no",
        )


def test_historical_cut_remains_semantically_elaborable_after_authority_moves():
    tm, protocol, cut, admitted, by_key = setup_branching()
    yes = by_key[next(key for key in by_key if key.endswith("reaction:yes"))]

    tm.actualize_observed(
        possibility=yes,
        actualizer="actualizer",
        authority=admitted["actualizers"][yes],
        observation={"choice": "yes"},
        request_id="actualize-for-stale-cut",
    )

    historical = tm.causal_cut(cut["cut"])
    assert historical["state"] == "historical"
    assert all(
        projection["disposition"] == "spent"
        for projection in historical["projections"]
    )

    # The old Cut is still a perfectly meaningful epistemic object. Pure
    # elaboration can ask what was possible from that old causal boundary.
    retrospective = elaborate_cuts(
        protocol,
        cuts=(cut_value_view(tm, cut["cut"]),),
        elaborator="retrospective-model",
        actualizer="counterfactual",
        knowledge=("later-model:deeper-context",),
    )
    assert {possibility.reaction for possibility in retrospective.possibilities} == {
        "yes",
        "no",
    }

    # But semantics do not resurrect authority. The Cut's original Elaborator
    # projection was already consumed by its historical elaboration.
    with pytest.raises(Conflict, match="Elaborator projection"):
        tm.admit_cut_elaboration(
            blueprint=retrospective,
            authorities={cut["cut"]: cut["elaborator_projection"]},
            request_id="cannot-readmit-stale-cut",
        )
