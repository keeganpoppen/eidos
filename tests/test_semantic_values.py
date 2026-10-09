from eidos.core import Name, RecordValue
from eidos.cuts import ObservedCut, elaborate_cuts
from eidos.occurrence import (
    FrontierProjection,
    ProjectionTemplate,
    ReactionRule,
    RecursiveProtocol,
    elaborate_genesis,
)
from eidos.trusted import TrustedMachinery


def protocol() -> RecursiveProtocol:
    return RecursiveProtocol(
        name="semantic-values",
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


def observed_cut(tm: TrustedMachinery, cut: str) -> ObservedCut:
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


def test_semantic_objects_are_ordinary_named_eidos_values():
    tm = TrustedMachinery()
    p = protocol()
    installed = tm.install_occurrence_blueprint(
        blueprint=elaborate_genesis(
            p,
            holders={"A": "alice", "B": "bob"},
        ),
        request_id="semantic-genesis",
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
        request_id="semantic-cut",
    )

    cut_binding = tm.named_eidos_value(cut["cut"])
    cut_value = cut_binding["value"]
    assert isinstance(cut_value, RecordValue)
    assert cut_value.get("$kind") == "Cut"
    assert cut_value.get("name") == Name(cut["cut"])
    assert set(cut_value.get("projections")) == {
        Name(installed["projections"]["projection:A"]),
        Name(installed["projections"]["projection:B"]),
    }

    blueprint = elaborate_cuts(
        p,
        cuts=(observed_cut(tm, cut["cut"]),),
        elaborator="elaborator",
        actualizer="actualizer",
        knowledge=("observation:raw", "model:domain"),
    )
    admitted = tm.admit_cut_elaboration(
        blueprint=blueprint,
        authorities={cut["cut"]: cut["elaborator_projection"]},
        request_id="semantic-elaborate",
    )

    elaboration = tm.named_eidos_value(admitted["occurrence"])["value"]
    assert elaboration.get("$kind") == "Elaboration"
    assert elaboration.get("occurrence") == Name(admitted["occurrence"])
    assert elaboration.get("knowledge") == (
        "model:domain",
        "observation:raw",
    )

    possibility = next(iter(admitted["possibilities"].values()))
    possibility_value = tm.named_eidos_value(possibility)["value"]
    assert possibility_value.get("$kind") == "Possibility"
    assert possibility_value.get("name") == Name(possibility)
    assert possibility_value.get("reaction") == "advance"
    assert possibility_value.get("actualizer") == Name(
        admitted["actualizers"][possibility]
    )

    occurred = tm.actualize_observed(
        possibility=possibility,
        actualizer="actualizer",
        authority=admitted["actualizers"][possibility],
        observation={"seen": True},
        request_id="semantic-actualize",
    )

    occurrence = tm.named_eidos_value(occurred["occurrence"])["value"]
    assert occurrence.get("$kind") == "Occurrence"
    assert occurrence.get("occurrence") == Name(occurred["occurrence"])
    assert occurrence.get("possibility") == Name(possibility)
    assert occurrence.get("observation") == {"seen": True}

    successor_cut = next(iter(occurred["successor_cuts"].values()))
    successor = tm.named_eidos_value(successor_cut)["value"]
    assert successor.get("$kind") == "Cut"
    assert successor.get("parent_occurrence") == Name(occurred["occurrence"])
    assert successor.get("parent_cut") == Name(cut["cut"])


def test_named_value_binding_is_immutable_and_content_addressed():
    tm = TrustedMachinery()
    name = tm.reserve_name(kind="value", request_id="semantic-value-name")
    first = RecordValue.from_mapping({"$kind": "Example", "value": 1})

    bound = tm.bind_eidos_value(
        name=name,
        value=first,
        request_id="semantic-bind-first",
    )
    again = tm.named_eidos_value(name)

    assert again["cid"] == bound["cid"]
    assert again["value"] == first
    assert tm.eidos_value(bound["cid"]) == first



def test_specialized_semantic_columns_are_only_indexes():
    tm = TrustedMachinery()
    p = protocol()
    installed = tm.install_occurrence_blueprint(
        blueprint=elaborate_genesis(
            p,
            holders={"A": "alice", "B": "bob"},
        ),
        request_id="index-genesis",
    )
    cut = tm.create_observed_cut(
        instance=installed["instance"],
        observer="real-observer",
        protocol_cid=p.cid,
        projections=[
            installed["projections"]["projection:A"],
            installed["projections"]["projection:B"],
        ],
        elaborator="elaborator",
        request_id="index-cut",
    )

    # Corrupt fields that used to be semantic sources.
    tm.db.execute(
        "UPDATE causal_cuts SET observer=?,protocol_cid=? WHERE name=?",
        ("WRONG-OBSERVER", "WRONG-PROTOCOL", cut["cut"]),
    )
    interpreted_cut = tm.causal_cut(cut["cut"])
    assert interpreted_cut["observer"] == "real-observer"
    assert interpreted_cut["protocol_cid"] == p.cid

    blueprint = elaborate_cuts(
        p,
        cuts=(observed_cut(tm, cut["cut"]),),
        elaborator="elaborator",
        actualizer="actualizer",
    )
    admitted = tm.admit_cut_elaboration(
        blueprint=blueprint,
        authorities={cut["cut"]: cut["elaborator_projection"]},
        request_id="index-elaborate",
    )
    possibility = next(iter(admitted["possibilities"].values()))

    tm.db.execute(
        "UPDATE observed_possibilities "
        "SET reaction=?,proof=?,elaborator=?,actualizer=? WHERE name=?",
        ("WRONG-REACTION", "WRONG-PROOF", "WRONG-E", "WRONG-A", possibility),
    )
    interpreted_possibility = tm.observed_possibility(possibility)
    assert interpreted_possibility["reaction"] == "advance"
    assert interpreted_possibility["proof"] == blueprint.proof
    assert interpreted_possibility["elaborator"] == "elaborator"
    assert interpreted_possibility["actualizer"] == "actualizer"

    occurred = tm.actualize_observed(
        possibility=possibility,
        actualizer="actualizer",
        authority=admitted["actualizers"][possibility],
        observation={"truth": "semantic-value"},
        request_id="index-actualize",
    )

    tm.db.execute(
        "UPDATE observed_occurrences "
        "SET actualizer=?,observation_json=? WHERE name=?",
        ("WRONG-ACTUALIZER", '{"truth":"index"}', occurred["occurrence"]),
    )
    interpreted_occurrence = tm.observed_occurrence(occurred["occurrence"])
    assert interpreted_occurrence["actualizer"] == "actualizer"
    assert interpreted_occurrence["observation"] == {
        "truth": "semantic-value"
    }
