import pytest

from eidos.authority import ProjectionGrant
from eidos.genesis import admit_genesis
from eidos.semantic_values import projection_value
from eidos.occurrence import (
    ProjectionTemplate,
    ReactionRule,
    RecursiveProtocol,
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
    out = admit_genesis(
        tm,
        p,
        holders={"A": "alice"},
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
                holder="alice",
                description=projection_value(
                    key="next:A",
                    role="A",
                    state="a1",
                ),
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
                    holder="alice",
                    description=projection_value(
                        key="forbidden",
                        role="A",
                        state="a1",
                    ),
                ),
            ),
            fact={},
            request_id="mint-from-nothing",
        )


def test_generic_commit_cannot_atomically_cross_authority_instances():
    tm = TrustedMachinery()
    _, first = installed(tm, name="one", request_id="genesis-one")
    _, second = installed(tm, name="two", request_id="genesis-two")

    with pytest.raises(Conflict, match="one authority domain"):
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



def test_authority_domain_and_projection_tables_contain_only_authority_facts():
    tm = TrustedMachinery()
    p, out = installed(tm)

    domain_columns = [
        row["name"]
        for row in tm.db.execute("PRAGMA table_info(authority_domains)").fetchall()
    ]
    projection_columns = [
        row["name"]
        for row in tm.db.execute("PRAGMA table_info(projections)").fetchall()
    ]

    assert domain_columns == ["name"]
    assert projection_columns == [
        "name",
        "domain_name",
        "holder",
        "disposition",
    ]

    domain = tm.authority_domain(out["domain"])
    assert domain["description"].get("$kind") == "AuthorityDomain"
    assert domain["description"].get("protocol") == p.name
    assert domain["description"].get("protocol_cid") == p.cid


def test_projection_description_is_immutable_while_holder_authority_moves():
    tm = TrustedMachinery()
    _, out = installed(tm)
    projection = out["projections"]["projection:A"]

    before = tm.named_eidos_value(projection)
    semantic = before["value"]
    assert semantic.get("$kind") == "Projection"
    assert semantic.get("role") == "A"
    assert semantic.get("state") == "a0"
    assert tm.projection(projection)["holder"] == "alice"

    tm.transfer_projection(
        projection=projection,
        from_holder="alice",
        to_holder="specialist",
        request_id="delegate-A",
    )

    after = tm.named_eidos_value(projection)
    assert after["cid"] == before["cid"]
    assert after["value"] == semantic
    assert tm.projection(projection)["holder"] == "specialist"
    assert tm.projection(projection)["role"] == "A"
    assert tm.projection(projection)["protocol_state"] == "a0"


def test_successor_projection_semantics_are_values_not_machine_columns():
    tm = TrustedMachinery()
    _, out = installed(tm)
    old = out["projections"]["projection:A"]

    committed = tm.commit_projection_occurrence(
        kind="advance",
        consumes=(old,),
        establishes=(
            ProjectionGrant(
                key="next:A",
                holder="alice",
                description=projection_value(
                    key="next:A",
                    role="A",
                    state="a1",
                ),
            ),
        ),
        fact={},
        request_id="semantic-successor",
    )

    successor = committed["established"]["next:A"]
    row = tm.db.execute(
        "SELECT * FROM projections WHERE name=?",
        (successor,),
    ).fetchone()
    assert set(row.keys()) == {
        "name",
        "domain_name",
        "holder",
        "disposition",
    }
    assert tm.named_eidos_value(successor)["value"].get("state") == "a1"
    assert tm.projection(successor)["protocol_state"] == "a1"
