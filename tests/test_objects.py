import json

from eidos.core import (
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
    Record,
    RecordValue,
    Role,
    Socket,
    Suspended,
    Var,
    from_data,
    to_data,
)
from eidos.objects import (
    INNER_FIELD,
    METHODS_FIELD,
    SOCKET_FIELD,
    STATE_FIELD,
    invoke,
    object_value,
)


TURN = Name("operation:turn")
PING = Name("operation:ping")


def closure(praxis: PraxisCore, body):
    made = praxis.realize(Lambda(("self", "argument"), body))
    assert isinstance(made, Done)
    return made.value


def call(target, *, operation=TURN, argument="hello"):
    return invoke(
        Lit(target),
        operation,
        Lit(argument),
        result_as="reply",
        successor_as="next",
        then=Record.from_mapping(
            {
                "reply": Var("reply"),
                "next": Var("next"),
            }
        ),
    )


def terminal_endpoint(praxis: PraxisCore, socket: Socket):
    method = closure(
        praxis,
        Perform(
            socket=Get(Var("self"), SOCKET_FIELD),
            operation=TURN,
            argument=Var("argument"),
            result_as="remote_reply",
            successor_as="remote_next",
            then=Record.from_mapping(
                {
                    "value": Var("remote_reply"),
                    "successor": Record.from_mapping(
                        {
                            METHODS_FIELD: Get(
                                Var("self"), METHODS_FIELD
                            ),
                            SOCKET_FIELD: Var("remote_next"),
                        }
                    ),
                }
            ),
        ),
    )
    return object_value(
        methods={TURN: method},
        fields={SOCKET_FIELD: socket},
    )


def forwarding_wrapper(
    praxis: PraxisCore,
    inner,
    *,
    prefix: str,
    suffix: str,
    state: int = 0,
):
    made = praxis.realize(
        Let(
            "prefix",
            Lit(prefix),
            Let(
                "suffix",
                Lit(suffix),
                Lambda(
                    ("self", "argument"),
                    invoke(
                        Get(Var("self"), INNER_FIELD),
                        TURN,
                        Prim(
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
                                        METHODS_FIELD: Get(
                                            Var("self"), METHODS_FIELD
                                        ),
                                        INNER_FIELD: Var("inner_next"),
                                        STATE_FIELD: Prim(
                                            "add",
                                            (
                                                Get(
                                                    Var("self"), STATE_FIELD
                                                ),
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
    assert isinstance(made, Done)
    return object_value(
        methods={TURN: made.value},
        fields={
            INNER_FIELD: inner,
            STATE_FIELD: state,
        },
    )


def test_terminal_object_is_plain_value_until_its_method_hits_core_perform():
    praxis = PraxisCore()
    socket0 = Socket(Name("socket:k0"))
    endpoint = terminal_endpoint(praxis, socket0)

    result = praxis.realize(call(endpoint))
    assert isinstance(result, Suspended)
    assert result.socket == socket0
    assert result.argument == "hello"


def test_local_object_method_answers_without_any_relational_suspension():
    praxis = PraxisCore()
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
    target = object_value(methods={PING: method})

    result = praxis.realize(call(target, operation=PING))
    assert isinstance(result, Done)
    assert result.value.get("reply") == "pong:hello"
    assert result.value.get("next") == target


def test_nested_wrappers_are_ordinary_values_and_core_sees_only_terminal_socket():
    praxis = PraxisCore()
    socket0 = Socket(Name("socket:k0"))
    socket1 = Socket(Name("socket:k1"))

    terminal0 = terminal_endpoint(praxis, socket0)
    inner0 = forwarding_wrapper(
        praxis, terminal0, prefix="inner[", suffix="inner:"
    )
    outer0 = forwarding_wrapper(
        praxis, inner0, prefix="outer[", suffix="outer:"
    )

    suspended = praxis.realize(call(outer0))
    assert isinstance(suspended, Suspended)
    assert suspended.socket == socket0
    assert suspended.argument == "inner[outer[hello"

    resumed = praxis.resume(
        suspended,
        Reaction(
            name=Name("reaction:m0"),
            consumed=socket0,
            successor=socket1,
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

    terminal1 = inner1.get(INNER_FIELD)
    assert isinstance(terminal1, RecordValue)
    assert terminal1.get(SOCKET_FIELD) == socket1


def test_object_methods_remain_open_on_current_role_bindings():
    praxis = PraxisCore()
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
    target = object_value(methods={PING: method})

    open_ = praxis.realize(call(target, operation=PING))
    assert isinstance(open_, Open)
    assert open_.role == policy

    resumed = praxis.supply(open_, "allowed")
    assert isinstance(resumed, Done)
    assert resumed.value.get("reply") == "allowed"


def test_object_stack_is_just_serializable_core_values():
    praxis = PraxisCore()
    value = forwarding_wrapper(
        praxis,
        terminal_endpoint(
            praxis,
            Socket(Name("socket:base")),
        ),
        prefix="wrap:",
        suffix="wrap:",
    )

    encoded = to_data(value)
    assert from_data(json.loads(json.dumps(encoded))) == value
