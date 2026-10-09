from pathlib import Path

import pytest

from eidos.experiments.lockstep_occurrence import (
    ProjectionTemplate,
    ProtocolSpace,
    ReactionType,
    elaborate,
)
from eidos.trusted import Conflict, TrustedMachinery


def observed_choice_protocol() -> ProtocolSpace:
    return ProtocolSpace(
        name="observed-choice",
        initial=(
            ProjectionTemplate("A", "ready"),
            ProjectionTemplate("B", "ready"),
            ProjectionTemplate("O", "watching"),
        ),
        reactions=(
            ReactionType(
                name="yes",
                consumes=("A", "B", "O"),
                successors=(
                    ProjectionTemplate("A", "after-yes"),
                    ProjectionTemplate("B", "after-yes"),
                    ProjectionTemplate("O", "recorded-yes"),
                ),
            ),
            ReactionType(
                name="no",
                consumes=("A", "B", "O"),
                successors=(
                    ProjectionTemplate("A", "after-no"),
                    ProjectionTemplate("B", "after-no"),
                    ProjectionTemplate("O", "recorded-no"),
                ),
            ),
        ),
    )


def install_choice(tm: TrustedMachinery):
    blueprint = elaborate(
        observed_choice_protocol(),
        holders={"A": "alice", "B": "bob", "O": "observer"},
    )
    installed = tm.install_occurrence_blueprint(
        blueprint=blueprint,
        request_id="install-choice",
    )
    return blueprint, installed


def test_protocol_elaboration_contains_latent_branches_before_occurrence():
    blueprint = elaborate(
        observed_choice_protocol(),
        holders={"A": "alice", "B": "bob", "O": "observer"},
    )

    assert {projection.key for projection in blueprint.projections} == {
        "projection:A",
        "projection:B",
        "projection:O",
    }

    yes, no = blueprint.possibilities
    assert yes.reaction == "yes"
    assert no.reaction == "no"
    assert yes.consumes == no.consumes == (
        "projection:A",
        "projection:B",
        "projection:O",
    )
    assert [successor.state for successor in yes.establishes] == [
        "after-yes",
        "after-yes",
        "recorded-yes",
    ]
    assert [successor.state for successor in no.establishes] == [
        "after-no",
        "after-no",
        "recorded-no",
    ]


def test_observation_selects_one_latent_reaction_and_commit_is_mechanical():
    tm = TrustedMachinery()
    _, installed = install_choice(tm)

    yes = installed["possibilities"]["reaction:yes"]
    no = installed["possibilities"]["reaction:no"]

    assert tm.reaction_possibility(yes)["state"] == "open"
    assert tm.reaction_possibility(no)["state"] == "open"

    occurred = tm.commit_occurrence(
        possibility=yes,
        observation={
            "observer": "observer",
            "condition": "signal-present",
            "value": True,
        },
        request_id="observe-yes",
    )

    assert occurred["reaction"] == "yes"
    assert tm.reaction_possibility(yes)["state"] == "occurred"
    assert tm.reaction_possibility(no)["state"] == "precluded"

    for projection in installed["projections"].values():
        assert tm.projection(projection)["disposition"] == "spent"

    successors = occurred["successors"]
    assert set(successors) == {
        "yes:successor:A",
        "yes:successor:B",
        "yes:successor:O",
    }
    assert tm.projection(successors["yes:successor:A"])["protocol_state"] == "after-yes"
    assert tm.projection(successors["yes:successor:B"])["protocol_state"] == "after-yes"
    assert tm.projection(successors["yes:successor:O"])["protocol_state"] == "recorded-yes"
    assert all(
        tm.projection(projection)["disposition"] == "live"
        for projection in successors.values()
    )

    record = tm.occurrence_record(occurred["occurrence"])
    assert record["observation"]["condition"] == "signal-present"
    assert set(record["inputs"]) == set(installed["projections"].values())
    assert record["outputs"] == list(successors.values())


def test_competing_branch_cannot_occur_after_shared_frontier_was_consumed():
    tm = TrustedMachinery()
    _, installed = install_choice(tm)

    yes = installed["possibilities"]["reaction:yes"]
    no = installed["possibilities"]["reaction:no"]

    tm.commit_occurrence(
        possibility=yes,
        observation={"value": True},
        request_id="yes",
    )

    with pytest.raises(Conflict, match="precluded"):
        tm.commit_occurrence(
            possibility=no,
            observation={"value": False},
            request_id="no-too-late",
        )


def test_occurrence_commit_is_idempotent_but_request_id_cannot_change_observation():
    tm = TrustedMachinery()
    _, installed = install_choice(tm)
    yes = installed["possibilities"]["reaction:yes"]

    first = tm.commit_occurrence(
        possibility=yes,
        observation={"value": True},
        request_id="same-occurrence",
    )
    second = tm.commit_occurrence(
        possibility=yes,
        observation={"value": True},
        request_id="same-occurrence",
    )
    assert second == first

    with pytest.raises(Conflict):
        tm.commit_occurrence(
            possibility=yes,
            observation={"value": "different"},
            request_id="same-occurrence",
        )


def test_occurrence_survives_restart_before_any_participant_incorporates_it(
    tmp_path: Path,
):
    db = tmp_path / "tm.db"
    tm = TrustedMachinery(db)
    _, installed = install_choice(tm)
    yes = installed["possibilities"]["reaction:yes"]

    occurred = tm.commit_occurrence(
        possibility=yes,
        observation={
            "observer": "observer",
            "condition": "signal-present",
        },
        request_id="commit-before-crash",
    )
    old_projections = dict(installed["projections"])
    tm.close()

    tm = TrustedMachinery(db)
    record = tm.occurrence_record(occurred["occurrence"])
    assert record["possibility_name"] == yes
    assert record["observation"]["observer"] == "observer"

    for projection in old_projections.values():
        assert tm.projection(projection)["disposition"] == "spent"

    for projection in occurred["successors"].values():
        assert tm.projection(projection)["disposition"] == "live"


def test_trusted_commit_cannot_be_asked_to_mint_arbitrary_successors():
    tm = TrustedMachinery()
    blueprint, installed = install_choice(tm)
    yes = installed["possibilities"]["reaction:yes"]

    planned = {
        output["output_key"]: output["protocol_state"]
        for output in tm.reaction_possibility(yes)["outputs"]
    }
    assert planned == {
        "yes:successor:A": "after-yes",
        "yes:successor:B": "after-yes",
        "yes:successor:O": "recorded-yes",
    }

    occurred = tm.commit_occurrence(
        possibility=yes,
        observation={"anything": "TM does not interpret this"},
        request_id="mechanical-commit",
    )

    realized = {
        key: tm.projection(projection)["protocol_state"]
        for key, projection in occurred["successors"].items()
    }
    assert realized == planned

    # The commit API receives no successor specification. The only successor
    # authority it can establish is the latent output already installed by the
    # semantic elaborator.
    assert len(blueprint.possibilities[0].establishes) == len(realized)
