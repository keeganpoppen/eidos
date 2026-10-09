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
    Prim,
    Reaction,
    RealizationError,
    Record,
    RecordValue,
    Role,
    Socket,
    Suspended,
    Var,
)
from eidos.facets import (
    Clause,
    Facet,
    PraxisFacets,
    Rewrap,
    Step,
    from_data,
    to_data,
)


TURN = Name("operation:turn")
PING = Name("operation:ping")


def invoke(target, *, operation=TURN, argument="hello"):
    return Perform(
        socket=Lit(target),
        operation=operation,
        argument=Lit(argument),
        result_as="reply",
        successor_as="next",
        then=Record.from_mapping(
            {
                "reply": Var("reply"),
                "next": Var("next"),
            }
        ),
    )


def forwarding_facet(inner, *, prefix: str, suffix: str, state: int = 0) -> Facet:
    return Facet(
        inner=inner,
        state=state,
        clauses=(
            Clause(
                operation=TURN,
                body=Perform(
                    socket=Var("inner"),
                    operation=TURN,
                    argument=Prim(
                        "concat",
                        (Lit(prefix), Var("argument")),
                    ),
                    result_as="inner_reply",
                    successor_as="inner_successor",
                    then=Step(
                        value=Prim(
                            "concat",
                            (Lit(suffix), Var("inner_reply")),
                        ),
                        successor=Rewrap(
                            facet=Var("self"),
                            inner=Var("inner_successor"),
                            state=Prim(
                                "add",
                                (Var("state"), Lit(1)),
                            ),
                        ),
                    ),
                ),
            ),
        ),
    )


def test_facet_can_answer_locally_without_exposing_a_socket():
    inner = Socket(Name("socket:unused"))
    facet = Facet(
        inner=inner,
        clauses=(
            Clause(
                operation=PING,
                body=Step(
                    value=Prim(
                        "concat",
                        (Lit("pong:"), Var("argument")),
                    ),
                    successor=Var("self"),
                ),
            ),
        ),
    )

    result = PraxisFacets().realize(
        invoke(facet, operation=PING, argument="hello")
    )

    assert isinstance(result, Done)
    assert isinstance(result.value, RecordValue)
    assert result.value.get("reply") == "pong:hello"
    assert result.value.get("next") == facet


def test_facet_transforms_forwards_and_rewraps_successor_authority():
    praxis = PraxisFacets()
    inner0 = Socket(Name("socket:k0"))
    inner1 = Socket(Name("socket:k1"))
    facet0 = forwarding_facet(
        inner0,
        prefix="request:",
        suffix="reply:",
    )

    suspended = praxis.realize(invoke(facet0))
    assert isinstance(suspended, Suspended)
    assert suspended.socket == inner0
    assert suspended.argument == "request:hello"

    # The full local wrapper stack survives as ordinary serializable data.
    encoded = to_data(suspended)
    assert from_data(json.loads(json.dumps(encoded))) == suspended

    resumed = praxis.resume(
        suspended,
        Reaction(
            name=Name("reaction:m0"),
            consumed=inner0,
            successor=inner1,
            value="world",
        ),
    )

    assert isinstance(resumed, Done)
    assert resumed.value.get("reply") == "reply:world"
    successor = resumed.value.get("next")
    assert isinstance(successor, Facet)
    assert successor.inner == inner1
    assert successor.state == 1
    assert facet0.inner == inner0
    assert facet0.state == 0


def test_nested_facets_compose_into_one_terminal_socket_suspension():
    praxis = PraxisFacets()
    base0 = Socket(Name("socket:base0"))
    base1 = Socket(Name("socket:base1"))
    inner0 = forwarding_facet(
        base0,
        prefix="inner[",
        suffix="inner:",
    )
    outer0 = forwarding_facet(
        inner0,
        prefix="outer[",
        suffix="outer:",
    )

    suspended = praxis.realize(invoke(outer0))
    assert isinstance(suspended, Suspended)
    assert suspended.socket == base0
    assert suspended.argument == "inner[outer[hello"

    resumed = praxis.resume(
        suspended,
        Reaction(
            name=Name("reaction:nested"),
            consumed=base0,
            successor=base1,
            value="ok",
        ),
    )

    assert isinstance(resumed, Done)
    assert resumed.value.get("reply") == "outer:inner:ok"

    outer1 = resumed.value.get("next")
    assert isinstance(outer1, Facet)
    assert outer1.state == 1
    inner1 = outer1.inner
    assert isinstance(inner1, Facet)
    assert inner1.state == 1
    assert inner1.inner == base1


def test_facet_clause_may_remain_open_on_an_ambient_role():
    praxis = PraxisFacets()
    policy = Role("policy")
    facet = Facet(
        inner=Socket(Name("socket:unused")),
        clauses=(
            Clause(
                operation=PING,
                body=Step(
                    value=Need(policy),
                    successor=Var("self"),
                ),
            ),
        ),
    )

    open_ = praxis.realize(invoke(facet, operation=PING))
    assert isinstance(open_, Open)
    assert open_.role == policy

    resumed = praxis.supply(open_, "allowed")
    assert isinstance(resumed, Done)
    assert resumed.value.get("reply") == "allowed"
    assert resumed.value.get("next") == facet


def test_nested_facet_value_itself_round_trips_as_data():
    value = forwarding_facet(
        forwarding_facet(
            Socket(Name("socket:base")),
            prefix="inner:",
            suffix="inner:",
        ),
        prefix="outer:",
        suffix="outer:",
    )

    assert from_data(json.loads(json.dumps(to_data(value)))) == value


def test_unknown_operation_is_not_implicitly_forwarded():
    facet = forwarding_facet(
        Socket(Name("socket:base")),
        prefix="",
        suffix="",
    )

    with pytest.raises(RealizationError, match="no clause"):
        PraxisFacets().realize(
            invoke(facet, operation=Name("operation:unknown"))
        )


def test_clause_must_explicitly_return_result_and_successor():
    facet = Facet(
        inner=Socket(Name("socket:base")),
        clauses=(
            Clause(
                operation=PING,
                body=Lit("not a StepValue"),
            ),
        ),
    )

    with pytest.raises(RealizationError, match="StepValue"):
        PraxisFacets().realize(invoke(facet, operation=PING))
