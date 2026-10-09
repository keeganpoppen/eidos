import pytest

from eidos.authority import ProjectionGrant
from eidos.occurrence import (
    ProjectionTemplate,
    ReactionRule,
    RecursiveProtocol,
    elaborate_genesis,
)
from eidos.trusted import Conflict, StaleProjection, TrustedMachinery


def protocol(name="authority-test"):
    return RecursiveProtocol(
        name=name,
        initial=(ProjectionTemplate("A", "a0"),),
        reactions=(
            ReactionRule(
                name="advance",
                requires=(ProjectionTemplate("A", "a0"),),
                successors=(ProjectionTemplate("A", "a1"),),
            ),
        ),
    )


def installed(tm, *, name="authority-test", request_id="genesis"):
    p = protocol(name)
    out = tm.install_occurrence_blueprint(
        blueprint=elaborate_genesis(p, holders={"A": "alice"}),
        request_id=request_id,
    )
    return p, out


def test_generic_commit_knows_only_linear_projection_transition():
    tm = TrustedMachinery()
    _, out = installed(tm)
    old = out["projections"]["projection:A"]

    committed = tm.commit_projection_occurrence(
        kind="test-step",
        consumes=(old,),
        establishes=(
            ProjectionGrant(
                key="next:A",
                role="A",
                state="a1",
                holder="alice",
            ),
        ),
        fact={"why": "opaque to Trusted Machinery"},
        request_id="generic-step",
    )

    new = committed["established"]["next:A"]
    assert tm.projection(old)["disposition"] == "spent"
    assert tm.projection(new)["disposition"] == "live"
    assert tm.projection(new)["protocol_state"] == "a1"

    record = tm.authority_occurrence(committed["occurrence"])
    assert record["kind"] == "test-step"
    assert record["inputs"] == [old]
    assert record["outputs"] == {"next:A": new}
    assert record["fact"] == {"why": "opaque to Trusted Machinery"}


def test_generic_commit_cannot_reuse_spent_capability():
    tm = TrustedMachinery()
    _, out = installed(tm)
    old = out["projections"]["projection:A"]

    tm.commit_projection_occurrence(
        kind="first",
        consumes=(old,),
        establishes=(),
        fact={},
        request_id="first",
    )

    with pytest.raises(StaleProjection):
        tm.commit_projection_occurrence(
            kind="second",
            consumes=(old,),
            establishes=(),
            fact={},
            request_id="second",
        )


def test_generic_commit_rejects_duplicate_input_and_empty_genesis_mint():
    tm = TrustedMachinery()
    _, out = installed(tm)
    old = out["projections"]["projection:A"]

    with pytest.raises(Conflict, match="twice"):
        tm.commit_projection_occurrence(
            kind="duplicate",
            consumes=(old, old),
            establishes=(),
            fact={},
            request_id="duplicate",
        )

    with pytest.raises(Exception, match="must consume"):
        tm.commit_projection_occurrence(
            kind="mint-from-nothing",
            consumes=(),
            establishes=(
                ProjectionGrant(
                    key="forbidden",
                    role="A",
                    state="a1",
                    holder="alice",
                ),
            ),
            fact={},
            request_id="mint-from-nothing",
        )


def test_generic_commit_cannot_atomically_cross_authority_instances():
    tm = TrustedMachinery()
    _, first = installed(tm, name="one", request_id="genesis-one")
    _, second = installed(tm, name="two", request_id="genesis-two")

    with pytest.raises(Conflict, match="one instance"):
        tm.commit_projection_occurrence(
            kind="cross-instance",
            consumes=(
                first["projections"]["projection:A"],
                second["projections"]["projection:A"],
            ),
            establishes=(),
            fact={},
            request_id="cross-instance",
        )
