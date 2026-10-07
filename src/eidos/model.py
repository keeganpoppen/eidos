from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from hashlib import sha256
import json
from typing import Any, Literal, Mapping

Direction = Literal["send", "recv"]
JSON = None | bool | int | float | str | list["JSON"] | dict[str, "JSON"]


def _jsonable(value: Any) -> JSON:
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if isinstance(value, Mapping):
        return {str(k): _jsonable(v) for k, v in sorted(value.items(), key=lambda kv: str(kv[0]))}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    raise TypeError(f"not canonical-json encodable: {type(value)!r}")


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(_jsonable(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def content_id(value: Any) -> str:
    return "sha256:" + sha256(canonical_bytes(value)).hexdigest()


@dataclass(frozen=True)
class Transition:
    direction: Direction
    label: str
    next_state: str


@dataclass(frozen=True)
class ProtocolSpec:
    """Deliberately weak v0 endpoint automata.

    roles maps role -> state -> one legal transition. Branching can be added later;
    keeping v0 tiny makes the Trusted Machinery invariants easier to inspect.
    """

    roles: dict[str, dict[str, Transition]]
    initial: dict[str, str]

    def transition(self, role: str, state: str) -> Transition:
        try:
            return self.roles[role][state]
        except KeyError as exc:
            raise ValueError(f"no transition for {role=} {state=}") from exc


@dataclass(frozen=True)
class OfferSpec:
    socket: str
    direction: Direction
    label: str
    payload: JSON = None
    continuation: JSON = None


@dataclass(frozen=True)
class Await:
    socket: str
    operation: str
    payload: JSON
    continuation: JSON


@dataclass(frozen=True)
class Done:
    value: JSON


@dataclass(frozen=True)
class Frame:
    """Immutable local causal cut.

    `bindings` are ordinary Eidos data. Rebinding means constructing another
    Frame; it is not a Trusted Machinery mutation primitive.

    `residuals` are durable descriptions of unfinished local computation.
    Historical Frames may retain Socket names without retaining live authority.
    """

    bindings: dict[str, JSON] = field(default_factory=dict)
    residuals: tuple[JSON, ...] = ()

    @property
    def cid(self) -> str:
        return content_id(self)
