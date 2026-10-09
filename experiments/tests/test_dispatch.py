import json

import pytest

from eidos.core import (
    Bindings,
    Done,
    Get,
    Lambda,
    Let,
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
    from_data,
    to_data,
)
from eidos.dispatch import (
    DISPATCH_FIELD,
    INNER_FIELD,
    STATE_FIELD,
    PraxisDispatch,
    wrapper,
)


TURN = Name("operation:turn")
PING = Name("operation:ping")


def closure(praxis: PraxisCore, body):
    made = praxis.realize(Lambda(("self", "argument"), body))
    assert isinstance(made, Done)
    return made.value


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


def forwarding_wrapper(praxis, inner, *, prefix, suffix, state=0):
    method = praxis.realize(
        Let(
            "prefix",
            Lit(prefix),
            Let(
                "suffix",
                Lit(suffix),
                Lambda(
                    ("self", "argument"),
                    Perform(
                        socket=Get(Var("self"), INNER_FIELD),
                        operation=TURN,
                        argument=Prim(
                            "concat",
                            (Var("prefix"), Var("argument")),
                        ),
                        result_as="inner_reply",
                        successor_as="inner_next",
                        then=Record.from_mapping(
                            {
                                "value": Prim(
                                    "concat",
                                    (Var("suffix"), Var("inner_reply")),
                                ),
                                "successor": Record.from_mapping(
                                    {
                                        DISPATCH_FIELD: Get(
                                            Var("self"), DISPATCH_FIELD
                                        ),
                                        INNER_FIELD: Var("inner_next"),
                                        STATE_FIELD: Prim(
                                            "add",
                                            (
                                                Get(Var("self"), STATE_FIELD),
                                                Lit(1),
                                            ),
                                        ),
                                    }
                                ),
                            }
                        ),
                    ),
                ),
            ),
        )
    )
    assert isinstance(method, Done)
    return wrapper(inner=inner, methods={TURN: method.value}, state=state)


def test_structural_wrapper_answers_locally_as_ordinary_record_value():
    praxis = PraxisDispatch()
    base = Socket(Name("socket:unused"))
    method = closure(
        praxis,
        Record.from_mapping(
            {
                "value": Prim(
                    "concat",
                    (Lit("pong:"), Var("argument")),
                ),
                "successor": Var("self"),
            }
        ),
    )
    target = wrapper(inner=base, methods={PING: method})

    assert isinstance(target, RecordValue)

    result = praxis.realize(invoke(target, operation=PING))
    assert isinstance(result, Done)
    assert result.value.get("reply") == "pong:hello"
    assert result.value.get("next") == target


def test_structural_wrapper_forwards_and_rebuilds_successor_with_plain_records():
    praxis = PraxisDispatch()
    base0 = Socket(Name("socket:k0"))
    base1 = Socket(Name("socket:k1"))
    target0 = forwarding_wrapper(
        praxis, base0, prefix="request:", suffix="reply:"
    )

    suspended = praxis.realize(invoke(target0))
    assert isinstance(suspended, Suspended)
    assert suspended.socket == base0
    assert suspended.argument == "request:hello"

    resumed = praxis.resume(
        suspended,
        Reaction(
            name=Name("reaction:m0"),
            consumed=base0,
            successor=base1,
            value="world",
        ),
    )
    assert isinstance(resumed, Done)
    assert resumed.value.get("reply") == "reply:world"

    target1 = resumed.value.get("next")
    assert isinstance(target1, RecordValue)
    assert target1.get(INNER_FIELD) == base1
    assert target1.get(STATE_FIELD) == 1
    assert target1.get(DISPATCH_FIELD) == target0.get(DISPATCH_FIELD)


def test_nested_structural_wrappers_collapse_to_one_terminal_socket():
    praxis = PraxisDispatch()
    base0 = Socket(Name("socket:base0"))
    base1 = Socket(Name("socket:base1"))
    inner0 = forwarding_wrapper(
        praxis, base0, prefix="inner[", suffix="inner:"
    )
    outer0 = forwarding_wrapper(
        praxis, inner0, prefix="outer[", suffix="outer:"
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
    assert isinstance(outer1, RecordValue)
    assert outer1.get(STATE_FIELD) == 1
    inner1 = outer1.get(INNER_FIELD)
    assert isinstance(inner1, RecordValue)
    assert inner1.get(STATE_FIELD) == 1
    assert inner1.get(INNER_FIELD) == base1


def test_dispatch_method_remains_open_on_situated_role():
    praxis = PraxisDispatch()
    policy = Role("policy")
    method = closure(
        praxis,
        Record.from_mapping(
            {
                "value": Need(policy),
                "successor": Var("self"),
            }
        ),
    )
    target = wrapper(
        inner=Socket(Name("socket:unused")),
        methods={PING: method},
    )

    open_ = praxis.realize(invoke(target, operation=PING))
    assert isinstance(open_, Open)
    assert open_.role == policy

    resumed = praxis.supply(open_, "allowed")
    assert isinstance(resumed, Done)
    assert resumed.value.get("reply") == "allowed"
    assert resumed.value.get("next") == target


def test_structural_wrapper_and_captured_closures_round_trip_as_values():
    praxis = PraxisDispatch()
    value = forwarding_wrapper(
        praxis,
        forwarding_wrapper(
            praxis,
            Socket(Name("socket:base")),
            prefix="inner:",
            suffix="inner:",
        ),
        prefix="outer:",
        suffix="outer:",
    )

    encoded = to_data(value)
    assert from_data(json.loads(json.dumps(encoded))) == value


def test_unknown_structural_operation_is_not_implicitly_forwarded():
    praxis = PraxisDispatch()
    target = forwarding_wrapper(
        praxis,
        Socket(Name("socket:base")),
        prefix="",
        suffix="",
    )

    with pytest.raises(RealizationError, match="no method"):
        praxis.realize(
            invoke(target, operation=Name("operation:unknown"))
        )


def test_dispatch_entry_must_be_first_class_eidos_closure():
    target = RecordValue.from_mapping(
        {
            DISPATCH_FIELD: RecordValue.from_mapping(
                {PING.value: "not a closure"}
            ),
            INNER_FIELD: Socket(Name("socket:base")),
            STATE_FIELD: None,
        }
    )

    with pytest.raises(RealizationError, match="not an Eidos Closure"):
        PraxisDispatch().realize(invoke(target, operation=PING))
