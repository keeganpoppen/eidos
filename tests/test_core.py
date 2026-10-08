import json

import pytest

from eidos.core import (
    Bindings,
    Done,
    Lit,
    Name,
    Need,
    Open,
    Perform,
    PraxisCore,
    Prim,
    Reaction,
    RealizationError,
    Record,
    RecordValue,
    Role,
    Socket,
    Suspended,
    Var,
    With,
    content_id,
    from_data,
    to_data,
)


def test_role_is_local_parameter_while_name_is_stable_identity():
    executor = Role("executor")
    first = Socket(Name("socket:first"))
    second = Socket(Name("socket:second"))

    base = Bindings().bind(executor, first, name=Name("binding:executor"))
    changed = base.bind(executor, second)

    assert base.lookup(executor) == first
    assert changed.lookup(executor) == second
    assert first.name != second.name


def test_unbound_role_preserves_explicit_residual_then_specializes():
    praxis = PraxisCore()
    executor = Role("executor")
    term = Record.from_mapping(
        {
            "label": Lit("chosen"),
            "executor": Need(executor),
        }
    )

    open_ = praxis.realize(term)
    assert isinstance(open_, Open)
    assert open_.role == executor

    supplied = praxis.supply(open_, Socket(Name("socket:codex")))
    assert isinstance(supplied, Done)
    assert isinstance(supplied.value, RecordValue)
    assert supplied.value.get("label") == "chosen"
    assert supplied.value.get("executor") == Socket(Name("socket:codex"))


def test_perform_exposes_relational_frontier_and_successor_is_explicit():
    praxis = PraxisCore()
    executor = Role("executor")
    old_socket = Socket(Name("socket:k0"))
    next_socket = Socket(Name("socket:k1"))

    term = Perform(
        socket=Need(executor),
        operation=Name("operation:turn"),
        argument=Lit("hello"),
        result_as="reply",
        successor_as="next_executor",
        then=With(
            role=executor,
            value=Var("next_executor"),
            body=Record.from_mapping(
                {
                    "reply": Var("reply"),
                    "executor_inside": Need(executor),
                }
            ),
        ),
    )

    suspended = praxis.realize(term, bindings=Bindings().bind(executor, old_socket))
    assert isinstance(suspended, Suspended)
    assert suspended.socket == old_socket
    assert suspended.argument == "hello"

    # The residual is inert, ordinary serializable data.
    encoded = to_data(suspended)
    assert from_data(json.loads(json.dumps(encoded))) == suspended

    resumed = praxis.resume(
        suspended,
        Reaction(
            name=Name("reaction:m0"),
            consumed=old_socket,
            successor=next_socket,
            value="world",
        ),
    )
    assert isinstance(resumed, Done)
    assert resumed.value.get("reply") == "world"
    assert resumed.value.get("executor_inside") == next_socket

    # `With` was scoped: Praxis did not secretly rewrite ambient bindings.
    assert resumed.bindings.lookup(executor) == old_socket


def test_reaction_cannot_discharge_a_different_socket():
    praxis = PraxisCore()
    suspended = praxis.realize(
        Perform(
            socket=Lit(Socket(Name("socket:k0"))),
            operation=Name("operation:ask"),
            argument=Lit(1),
            result_as="answer",
            successor_as="next",
            then=Var("answer"),
        )
    )
    assert isinstance(suspended, Suspended)

    with pytest.raises(RealizationError):
        praxis.resume(
            suspended,
            Reaction(
                name=Name("reaction:wrong"),
                consumed=Socket(Name("socket:other")),
                successor=None,
                value=2,
            ),
        )


def test_old_residual_can_be_reinterpreted_with_mock_binding():
    praxis = PraxisCore()
    executor = Role("executor")
    real_socket = Socket(Name("socket:real"))
    mock_socket = Socket(Name("socket:mock"))

    program = Perform(
        socket=Need(executor),
        operation=Name("operation:turn"),
        argument=Prim("concat", (Lit("hel"), Lit("lo"))),
        result_as="reply",
        successor_as="next",
        then=Var("reply"),
    )

    live = praxis.realize(program, bindings=Bindings().bind(executor, real_socket))
    counterfactual = praxis.realize(
        program, bindings=Bindings().bind(executor, mock_socket)
    )

    assert isinstance(live, Suspended)
    assert isinstance(counterfactual, Suspended)
    assert live.socket == real_socket
    assert counterfactual.socket == mock_socket
    assert live.argument == counterfactual.argument == "hello"

    # The executable residue is shared; the situated binding environment differs.
    assert live.continuation.then == counterfactual.continuation.then
    assert live.continuation.lexical == counterfactual.continuation.lexical
    assert live.continuation.bindings.lookup(executor) == real_socket
    assert counterfactual.continuation.bindings.lookup(executor) == mock_socket
    assert content_id(live.continuation.then) == content_id(counterfactual.continuation.then)


def test_core_has_no_host_callable_escape_hatch():
    praxis = PraxisCore()
    assert praxis.realize(Prim("add", (Lit(20), Lit(22)))) == Done(42, Bindings())


def test_suspension_preserves_the_surrounding_control_stack():
    praxis = PraxisCore()
    socket = Socket(Name("socket:k0"))
    program = Prim(
        "add",
        (
            Lit(1),
            Perform(
                socket=Lit(socket),
                operation=Name("operation:number"),
                argument=Lit(None),
                result_as="number",
                successor_as="next",
                then=Var("number"),
            ),
        ),
    )

    suspended = praxis.realize(program)
    assert isinstance(suspended, Suspended)
    resumed = praxis.resume(
        suspended,
        Reaction(
            name=Name("reaction:number"),
            consumed=socket,
            successor=None,
            value=41,
        ),
    )
    assert resumed == Done(42, Bindings())
