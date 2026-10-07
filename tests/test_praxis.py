from eidos import Call, Get, Let, Lit, Perform, Praxis, Record, Var
from eidos.model import Await, Done


def test_pure_evaluation():
    p = Praxis()
    term = Let(
        "x",
        Lit("hel"),
        Call("concat", (Var("x"), Lit("lo"))),
    )
    assert p.eval(term) == Done("hello")


def test_perform_suspends_and_continuation_is_serializable():
    p = Praxis()
    term = Perform(
        socket=Lit("socket_1"),
        operation="ask",
        payload=Record({"q": Lit("meaning?")}),
        result_as="answer",
        then=Get(Var("answer"), "value"),
    )
    result = p.eval(term)
    assert isinstance(result, Await)
    assert result.socket == "socket_1"
    assert result.operation == "ask"
    assert result.payload == {"q": "meaning?"}
    assert p.resume(result, {"value": 42}) == Done(42)
