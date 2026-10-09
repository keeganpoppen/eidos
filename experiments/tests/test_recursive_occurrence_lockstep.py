import pytest

from eidos.occurrence import (
    FrontierProjection,
    ProjectionTemplate,
    ReactionRule,
    RecursiveProtocol,
    elaborate_frontier,
    elaborate_genesis,
)
from eidos.trusted import Conflict, TrustedMachinery


def recursive_protocol() -> RecursiveProtocol:
    return RecursiveProtocol(
        name="recursive-observation",
        initial=(
            ProjectionTemplate("A", "ready"),
            ProjectionTemplate("B", "ready"),
            ProjectionTemplate("O", "watching"),
        ),
        reactions=(
            ReactionRule(
                name="yes",
                requires=(
                    ProjectionTemplate("A", "ready"),
                    ProjectionTemplate("B", "ready"),
                    ProjectionTemplate("O", "watching"),
                ),
                successors=(
                    ProjectionTemplate("A", "after-yes"),
                    ProjectionTemplate("B", "after-yes"),
                    ProjectionTemplate("O", "recorded-yes"),
                ),
            ),
            ReactionRule(
                name="no",
                requires=(
                    ProjectionTemplate("A", "ready"),
                    ProjectionTemplate("B", "ready"),
                    ProjectionTemplate("O", "watching"),
                ),
                successors=(
                    ProjectionTemplate("A", "after-no"),
                    ProjectionTemplate("B", "after-no"),
                    ProjectionTemplate("O", "recorded-no"),
                ),
            ),
            ReactionRule(
                name="ack-yes",
                requires=(
                    ProjectionTemplate("A", "after-yes"),
                    ProjectionTemplate("B", "after-yes"),
                    ProjectionTemplate("O", "recorded-yes"),
                ),
                successors=(
                    ProjectionTemplate("A", "done"),
                    ProjectionTemplate("B", "done"),
                    ProjectionTemplate("O", "done"),
                ),
            ),
            ReactionRule(
                name="recover-no",
                requires=(
                    ProjectionTemplate("A", "after-no"),
                    ProjectionTemplate("B", "after-no"),
                    ProjectionTemplate("O", "recorded-no"),
                ),
                successors=(
                    ProjectionTemplate("A", "done"),
                    ProjectionTemplate("B", "done"),
                    ProjectionTemplate("O", "done"),
                ),
            ),
        ),
    )


def frontier_projections(tm: TrustedMachinery, frontier: str):
    return tuple(
        FrontierProjection(
            name=row["name"],
            role=row["role"],
            state=row["protocol_state"],
            holder=row["holder"],
        )
        for row in tm.frontier(frontier)["projections"]
    )


def test_occurrence_mints_open_frontier_then_semantic_dual_elaborates_it():
    protocol = recursive_protocol()
    tm = TrustedMachinery()

    genesis = elaborate_genesis(
        protocol,
        holders={"A": "alice", "B": "bob", "O": "observer"},
    )
    installed = tm.install_occurrence_blueprint(
        blueprint=genesis,
        request_id="recursive-genesis",
    )

    assert installed["protocol_cid"] == protocol.cid
    frontier0 = tm.frontier(installed["frontier"])
    assert frontier0["generation"] == 0
    assert frontier0["state"] == "elaborated"

    yes = installed["possibilities"]["reaction:yes"]
    first = tm.commit_occurrence(
        possibility=yes,
        observation={"signal": True},
        request_id="recursive-yes",
    )

    frontier1 = tm.frontier(first["frontier"])
    assert frontier1["generation"] == 1
    assert frontier1["state"] == "open"
    assert frontier1["parent_occurrence"] == first["occurrence"]

    proof1 = elaborate_frontier(
        protocol,
        frontier=first["frontier"],
        parent_occurrence=first["occurrence"],
        projections=frontier_projections(tm, first["frontier"]),
    )
    assert proof1.protocol_cid == protocol.cid
    assert [p.reaction for p in proof1.possibilities] == ["ack-yes"]

    admitted = tm.admit_frontier(
        blueprint=proof1,
        authority=first["elaboration_authority"],
        request_id="admit-generation-1",
    )
    assert admitted["proof"] == proof1.proof
    assert tm.frontier(first["frontier"])["state"] == "elaborated"
    assert tm.frontier(first["frontier"])["proof"] == proof1.proof

    ack = next(iter(admitted["possibilities"].values()))
    second = tm.commit_occurrence(
        possibility=ack,
        observation={"acknowledged": True},
        request_id="recursive-ack",
    )

    frontier2 = tm.frontier(second["frontier"])
    assert frontier2["generation"] == 2
    assert frontier2["state"] == "open"

    proof2 = elaborate_frontier(
        protocol,
        frontier=second["frontier"],
        parent_occurrence=second["occurrence"],
        projections=frontier_projections(tm, second["frontier"]),
    )
    assert proof2.possibilities == ()

    terminal = tm.admit_frontier(
        blueprint=proof2,
        authority=second["elaboration_authority"],
        request_id="admit-terminal",
    )
    assert terminal["possibilities"] == {}
    assert tm.frontier(second["frontier"])["state"] == "elaborated"


def test_wrong_protocol_commitment_cannot_elaborate_frontier():
    protocol = recursive_protocol()
    tm = TrustedMachinery()
    installed = tm.install_occurrence_blueprint(
        blueprint=elaborate_genesis(
            protocol,
            holders={"A": "alice", "B": "bob", "O": "observer"},
        ),
        request_id="wrong-protocol-genesis",
    )
    first = tm.commit_occurrence(
        possibility=installed["possibilities"]["reaction:yes"],
        observation={"signal": True},
        request_id="wrong-protocol-first",
    )

    proof = elaborate_frontier(
        protocol,
        frontier=first["frontier"],
        parent_occurrence=first["occurrence"],
        projections=frontier_projections(tm, first["frontier"]),
    )
    wrong = type(proof)(
        protocol=proof.protocol,
        protocol_cid="sha256:not-the-protocol",
        frontier=proof.frontier,
        parent_occurrence=proof.parent_occurrence,
        projections=proof.projections,
        possibilities=proof.possibilities,
    )

    with pytest.raises(Conflict, match="protocol commitment"):
        tm.admit_frontier(
            blueprint=wrong,
            authority=first["elaboration_authority"],
            request_id="wrong-protocol-admission",
        )


def test_frontier_capability_is_linear_across_occurrences():
    protocol = recursive_protocol()
    tm = TrustedMachinery()
    installed = tm.install_occurrence_blueprint(
        blueprint=elaborate_genesis(
            protocol,
            holders={"A": "alice", "B": "bob", "O": "observer"},
        ),
        request_id="linear-frontier-genesis",
    )

    yes = installed["possibilities"]["reaction:yes"]
    no = installed["possibilities"]["reaction:no"]
    tm.commit_occurrence(
        possibility=yes,
        observation={"signal": True},
        request_id="linear-frontier-yes",
    )

    assert tm.frontier(installed["frontier"])["state"] == "spent"
    with pytest.raises(Conflict):
        tm.commit_occurrence(
            possibility=no,
            observation={"signal": False},
            request_id="linear-frontier-no",
        )


def test_frontier_proof_must_name_exact_authoritative_projection_set():
    protocol = recursive_protocol()
    tm = TrustedMachinery()
    installed = tm.install_occurrence_blueprint(
        blueprint=elaborate_genesis(
            protocol,
            holders={"A": "alice", "B": "bob", "O": "observer"},
        ),
        request_id="exact-frontier-genesis",
    )
    first = tm.commit_occurrence(
        possibility=installed["possibilities"]["reaction:yes"],
        observation={"signal": True},
        request_id="exact-frontier-yes",
    )

    projections = frontier_projections(tm, first["frontier"])
    proof = elaborate_frontier(
        protocol,
        frontier=first["frontier"],
        parent_occurrence=first["occurrence"],
        projections=projections,
    )
    truncated = type(proof)(
        protocol=proof.protocol,
        protocol_cid=proof.protocol_cid,
        frontier=proof.frontier,
        parent_occurrence=proof.parent_occurrence,
        projections=proof.projections[:-1],
        possibilities=proof.possibilities,
    )

    with pytest.raises(Conflict, match="authoritative live frontier"):
        tm.admit_frontier(
            blueprint=truncated,
            authority=first["elaboration_authority"],
            request_id="truncated-frontier",
        )



def test_frontier_name_does_not_authorize_elaboration():
    protocol = recursive_protocol()
    tm = TrustedMachinery()
    installed = tm.install_occurrence_blueprint(
        blueprint=elaborate_genesis(
            protocol,
            holders={"A": "alice", "B": "bob", "O": "observer"},
        ),
        request_id="name-is-not-authority-genesis",
    )
    first = tm.commit_occurrence(
        possibility=installed["possibilities"]["reaction:yes"],
        observation={"signal": True},
        request_id="name-is-not-authority-first",
    )
    proof = elaborate_frontier(
        protocol,
        frontier=first["frontier"],
        parent_occurrence=first["occurrence"],
        projections=frontier_projections(tm, first["frontier"]),
    )

    with pytest.raises(Conflict, match="elaboration authority"):
        tm.admit_frontier(
            blueprint=proof,
            authority=first["frontier"],
            request_id="frontier-name-is-not-token",
        )

    admitted = tm.admit_frontier(
        blueprint=proof,
        authority=first["elaboration_authority"],
        request_id="real-elaboration-token",
    )
    assert admitted["proof"] == proof.proof

    with pytest.raises(Conflict, match="elaboration authority"):
        tm.admit_frontier(
            blueprint=proof,
            authority=first["elaboration_authority"],
            request_id="reuse-elaboration-token",
        )
