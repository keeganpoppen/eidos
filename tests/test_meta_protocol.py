from eidos.core import (
    Done,
    Lit,
    Name,
    PraxisCore,
    RecordValue,
    Socket,
    Suspended,
    Var,
)
from eidos.meta_protocol import (
    ACTUALIZE,
    ELABORATE,
    MetaProtocolDriver,
    actualize_operation,
    elaborate_operation,
)
from eidos.occurrence import (
    ProjectionTemplate,
    ReactionRule,
    RecursiveProtocol,
    elaborate_genesis,
)
from eidos.trusted import TrustedMachinery


def protocol() -> RecursiveProtocol:
    return RecursiveProtocol(
        name="meta-protocol-test",
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


def setup():
    tm = TrustedMachinery()
    p = protocol()
    installed = tm.install_occurrence_blueprint(
        blueprint=elaborate_genesis(
            p,
            holders={
                "A": "alice",
                "B": "bob",
                "C": "carol",
                "D": "dan",
            },
        ),
        request_id="meta-genesis",
    )
    left = tm.create_observed_cut(
        instance=installed["instance"],
        observer="O1",
        protocol_cid=p.cid,
        projections=[
            installed["projections"]["projection:A"],
            installed["projections"]["projection:B"],
        ],
        request_id="meta-cut-left",
        elaborator="elaborator:left",
    )
    right = tm.create_observed_cut(
        instance=installed["instance"],
        observer="O2",
        protocol_cid=p.cid,
        projections=[
            installed["projections"]["projection:C"],
            installed["projections"]["projection:D"],
        ],
        request_id="meta-cut-right",
        elaborator="elaborator:right",
    )
    driver = MetaProtocolDriver(tm)
    driver.register(p)
    return tm, p, left, right, driver


def perform_elaboration(
    praxis,
    driver,
    *,
    target,
    protocol_cid,
    cuts,
    authorities,
    actualizer,
    knowledge=(),
    request_id,
):
    term = elaborate_operation(
        Lit(Socket(Name(target))),
        protocol_cid=protocol_cid,
        cuts=cuts,
        authorities=authorities,
        knowledge=knowledge,
        actualizer=actualizer,
        result_as="meta_result",
        successor_as="meta_next",
        then=Var("meta_result"),
    )
    suspended = praxis.realize(term)
    assert isinstance(suspended, Suspended)
    assert suspended.operation == ELABORATE
    reaction = driver.react(suspended, request_id=request_id)
    resumed = praxis.resume(suspended, reaction)
    assert isinstance(resumed, Done)
    assert isinstance(resumed.value, RecordValue)
    return suspended, reaction, resumed.value


def perform_actualization(
    praxis,
    driver,
    *,
    target,
    possibility,
    observation,
    request_id,
):
    term = actualize_operation(
        Lit(target),
        possibility=possibility,
        observation=observation,
        result_as="meta_result",
        successor_as="meta_next",
        then=Var("meta_result"),
    )
    suspended = praxis.realize(term)
    assert isinstance(suspended, Suspended)
    assert suspended.operation == ACTUALIZE
    reaction = driver.react(suspended, request_id=request_id)
    resumed = praxis.resume(suspended, reaction)
    assert isinstance(resumed, Done)
    assert isinstance(resumed.value, RecordValue)
    return suspended, reaction, resumed.value


def only_entry(record: RecordValue):
    mapping = record.as_dict()
    assert len(mapping) == 1
    return next(iter(mapping.items()))


def test_elaborate_and_actualize_are_ordinary_eidos_socket_operations():
    tm, p, left, _, driver = setup()
    praxis = PraxisCore()

    _, elaboration_reaction, elaborated = perform_elaboration(
        praxis,
        driver,
        target=left["elaborator_projection"],
        protocol_cid=p.cid,
        cuts=(left["cut"],),
        authorities={left["cut"]: left["elaborator_projection"]},
        actualizer="actualizer:left",
        knowledge=("observation:raw", "model:domain"),
        request_id="eidos-elaborate-left",
    )

    assert elaboration_reaction.consumed_sockets == (
        Socket(Name(left["elaborator_projection"])),
    )
    possibility_key, possibility = only_entry(elaborated.get("possibilities"))
    assert isinstance(possibility, Name)
    actualizer = elaborated.get("actualizers").get(possibility.value)
    assert isinstance(actualizer, Socket)

    _, actualization_reaction, actualized = perform_actualization(
        praxis,
        driver,
        target=actualizer,
        possibility=possibility.value,
        observation={"observer": "O1", "choice": possibility_key},
        request_id="eidos-actualize-left",
    )

    consumed = set(actualization_reaction.consumed_sockets)
    assert actualizer in consumed
    assert len(consumed) == 3  # Actualizer + A + B.

    occurrence = actualized.get("occurrence")
    assert isinstance(occurrence, Name)
    successor_cuts = actualized.get("successor_cuts")
    _, successor_cut = only_entry(successor_cuts)
    assert isinstance(successor_cut, Name)

    elaborators = actualized.get("elaborators")
    next_elaborator = elaborators.get(successor_cut.value)
    assert isinstance(next_elaborator, Socket)
    meta_row = tm.projection(next_elaborator.name.value)
    assert meta_row["role"] == "Elaborator"
    assert meta_row["disposition"] == "live"


def test_joint_elaborate_is_a_multi_socket_meta_reaction():
    tm, p, left, right, driver = setup()
    praxis = PraxisCore()

    _, _, left_elab = perform_elaboration(
        praxis,
        driver,
        target=left["elaborator_projection"],
        protocol_cid=p.cid,
        cuts=(left["cut"],),
        authorities={left["cut"]: left["elaborator_projection"]},
        actualizer="actualizer:local",
        request_id="joint-eidos-elab-left",
    )
    _, left_possibility = only_entry(left_elab.get("possibilities"))
    left_actualizer = left_elab.get("actualizers").get(left_possibility.value)
    _, _, left_out = perform_actualization(
        praxis,
        driver,
        target=left_actualizer,
        possibility=left_possibility.value,
        observation={"observer": "O1"},
        request_id="joint-eidos-actualize-left",
    )

    _, _, right_elab = perform_elaboration(
        praxis,
        driver,
        target=right["elaborator_projection"],
        protocol_cid=p.cid,
        cuts=(right["cut"],),
        authorities={right["cut"]: right["elaborator_projection"]},
        actualizer="actualizer:local",
        request_id="joint-eidos-elab-right",
    )
    _, right_possibility = only_entry(right_elab.get("possibilities"))
    right_actualizer = right_elab.get("actualizers").get(right_possibility.value)
    _, _, right_out = perform_actualization(
        praxis,
        driver,
        target=right_actualizer,
        possibility=right_possibility.value,
        observation={"observer": "O2"},
        request_id="joint-eidos-actualize-right",
    )

    _, left_cut = only_entry(left_out.get("successor_cuts"))
    _, right_cut = only_entry(right_out.get("successor_cuts"))
    left_elaborator = left_out.get("elaborators").get(left_cut.value)
    right_elaborator = right_out.get("elaborators").get(right_cut.value)

    tm.transfer_projection(
        projection=left_elaborator.name.value,
        from_holder="O1",
        to_holder="elaborator:joint",
        request_id="meta-delegate-left",
    )
    tm.transfer_projection(
        projection=right_elaborator.name.value,
        from_holder="O2",
        to_holder="elaborator:joint",
        request_id="meta-delegate-right",
    )

    suspended, reaction, joined = perform_elaboration(
        praxis,
        driver,
        target=left_elaborator.name.value,
        protocol_cid=p.cid,
        cuts=(left_cut.value, right_cut.value),
        authorities={
            left_cut.value: left_elaborator.name.value,
            right_cut.value: right_elaborator.name.value,
        },
        actualizer="actualizer:joint",
        knowledge=("model:left-context", "model:right-context"),
        request_id="eidos-joint-elaborate",
    )

    assert suspended.socket == left_elaborator
    assert set(reaction.consumed_sockets) == {
        left_elaborator,
        right_elaborator,
    }
    _, possibility = only_entry(joined.get("possibilities"))
    assert isinstance(possibility, Name)
    row = tm.observed_possibility(possibility.value)
    assert row["reaction"] == "join"
