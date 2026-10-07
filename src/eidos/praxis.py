from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping

from .model import Await, Done, JSON, _jsonable


class Term:
    pass


@dataclass(frozen=True)
class Lit(Term):
    value: JSON


@dataclass(frozen=True)
class Var(Term):
    name: str


@dataclass(frozen=True)
class Let(Term):
    name: str
    value: Term
    body: Term


@dataclass(frozen=True)
class Record(Term):
    fields: dict[str, Term]


@dataclass(frozen=True)
class Get(Term):
    record: Term
    field: str


@dataclass(frozen=True)
class Call(Term):
    fn: str
    args: tuple[Term, ...]


@dataclass(frozen=True)
class Perform(Term):
    socket: Term
    operation: str
    payload: Term
    result_as: str
    then: Term


def term_to_data(term: Term) -> JSON:
    match term:
        case Lit(value):
            return {"lit": value}
        case Var(name):
            return {"var": name}
        case Let(name, value, body):
            return {"let": name, "value": term_to_data(value), "body": term_to_data(body)}
        case Record(fields):
            return {"record": {k: term_to_data(v) for k, v in fields.items()}}
        case Get(record, field):
            return {"get": term_to_data(record), "field": field}
        case Call(fn, args):
            return {"call": fn, "args": [term_to_data(a) for a in args]}
        case Perform(socket, operation, payload, result_as, then):
            return {
                "perform": operation,
                "socket": term_to_data(socket),
                "payload": term_to_data(payload),
                "result_as": result_as,
                "then": term_to_data(then),
            }
        case _:
            raise TypeError(term)


def term_from_data(data: Mapping[str, Any]) -> Term:
    if "lit" in data:
        return Lit(data["lit"])
    if "var" in data:
        return Var(data["var"])
    if "let" in data:
        return Let(data["let"], term_from_data(data["value"]), term_from_data(data["body"]))
    if "record" in data:
        return Record({k: term_from_data(v) for k, v in data["record"].items()})
    if "get" in data:
        return Get(term_from_data(data["get"]), data["field"])
    if "call" in data:
        return Call(data["call"], tuple(term_from_data(a) for a in data["args"]))
    if "perform" in data:
        return Perform(
            term_from_data(data["socket"]),
            data["perform"],
            term_from_data(data["payload"]),
            data["result_as"],
            term_from_data(data["then"]),
        )
    raise ValueError(f"unknown term: {data!r}")


class Praxis:
    """Tiny local evaluator.

    It evaluates purely until `perform` reaches a socket. At that point the
    remainder is returned as an explicit serializable continuation instead of
    being executed. Trusted Machinery, not Praxis, decides whether the socket
    authority is live and whether any external transition may commit.
    """

    def __init__(self) -> None:
        self._fns: dict[str, Callable[..., JSON]] = {
            "eq": lambda a, b: a == b,
            "concat": lambda a, b: str(a) + str(b),
        }

    def register(self, name: str, fn: Callable[..., JSON]) -> None:
        self._fns[name] = fn

    def eval(self, term: Term, env: Mapping[str, JSON] | None = None) -> Done | Await:
        return self._eval(term, dict(env or {}))

    def resume(self, await_: Await, result: JSON) -> Done | Await:
        k = await_.continuation
        assert isinstance(k, dict)
        env = dict(k["env"])
        env[k["result_as"]] = result
        return self._eval(term_from_data(k["then"]), env)

    def _pure(self, term: Term, env: dict[str, JSON]) -> JSON:
        result = self._eval(term, env)
        if isinstance(result, Await):
            raise ValueError("effectful term used where a pure value is required")
        return result.value

    def _eval(self, term: Term, env: dict[str, JSON]) -> Done | Await:
        match term:
            case Lit(value):
                return Done(value)
            case Var(name):
                return Done(env[name])
            case Let(name, value_term, body):
                value = self._pure(value_term, env)
                return self._eval(body, {**env, name: value})
            case Record(fields):
                return Done({k: self._pure(v, env) for k, v in fields.items()})
            case Get(record_term, field):
                record = self._pure(record_term, env)
                assert isinstance(record, dict)
                return Done(record[field])
            case Call(fn, args):
                values = [self._pure(a, env) for a in args]
                return Done(_jsonable(self._fns[fn](*values)))
            case Perform(socket_term, operation, payload_term, result_as, then):
                socket = self._pure(socket_term, env)
                payload = self._pure(payload_term, env)
                if not isinstance(socket, str):
                    raise TypeError("v0 sockets are referred to by Name strings")
                return Await(
                    socket=socket,
                    operation=operation,
                    payload=payload,
                    continuation={
                        "env": _jsonable(env),
                        "result_as": result_as,
                        "then": term_to_data(then),
                    },
                )
            case _:
                raise TypeError(term)
