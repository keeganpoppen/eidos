from __future__ import annotations

"""Eidos meta-protocol: Elaborate and Actualize as ordinary Socket operations.

The authority objects are ordinary projection Names represented at the Eidos
surface as Socket values.  Praxis therefore suspends on them exactly as it does
on any other relational continuation.

MetaProtocolDriver is an adapter between those Eidos suspensions and the current
Trusted Machinery experiment.  Its existence is intentionally provisional: the
next collapse is to replace its two branches with one generic authority-
occurrence commit operation.
"""

from typing import Any, Mapping

from .core import (
    Name,
    Perform,
    Reaction,
    RecordValue,
    Socket,
    Suspended,
    Term,
)
from .cuts import ObservedCut, elaborate_cuts
from .meta import ACTUALIZER_ROLE, ELABORATOR_ROLE
from .occurrence import FrontierProjection, RecursiveProtocol
from .trusted import Conflict, TrustedMachinery


ELABORATE = Name("meta:Elaborate")
ACTUALIZE = Name("meta:Actualize")


class MetaProtocolError(RuntimeError):
    pass


def elaborate_operation(
    authority: Term,
    *,
    protocol_cid: str,
    cuts: tuple[str, ...],
    authorities: Mapping[str, str],
    knowledge: tuple[str, ...] = (),
    actualizer: str,
    result_as: str,
    successor_as: str,
    then: Term,
) -> Perform:
    """Construct an ordinary Eidos perform against an Elaborator Socket."""

    return Perform(
        socket=authority,
        operation=ELABORATE,
        argument=_literal_request(
            {
                "protocol_cid": protocol_cid,
                "cuts": tuple(cuts),
                "authorities": tuple(sorted(authorities.items())),
                "knowledge": tuple(knowledge),
                "actualizer": actualizer,
            }
        ),
        result_as=result_as,
        successor_as=successor_as,
        then=then,
    )


def actualize_operation(
    authority: Term,
    *,
    possibility: str,
    observation: Any,
    result_as: str,
    successor_as: str,
    then: Term,
) -> Perform:
    """Construct an ordinary Eidos perform against an Actualizer Socket."""

    return Perform(
        socket=authority,
        operation=ACTUALIZE,
        argument=_literal_request(
            {
                "possibility": possibility,
                "observation": observation,
            }
        ),
        result_as=result_as,
        successor_as=successor_as,
        then=then,
    )


# Kept here to avoid making callers import Lit only to form meta operations.
def _literal_request(value: Any):
    from .core import Lit

    return Lit(value)


class MetaProtocolDriver:
    """Realize terminal meta-protocol Sockets against Trusted Machinery.

    The driver does not choose the semantic world model. RecursiveProtocol
    values are explicitly registered by content identity; Elaborator placement
    may be local, a subagent, a remote process, or any other realization that
    eventually presents the same projection capability and proof.
    """

    def __init__(
        self,
        trusted: TrustedMachinery,
        protocols: Mapping[str, RecursiveProtocol] | None = None,
    ) -> None:
        self.trusted = trusted
        self.protocols: dict[str, RecursiveProtocol] = dict(protocols or {})

    def register(self, protocol: RecursiveProtocol) -> None:
        self.protocols[protocol.cid] = protocol

    def react(self, suspended: Suspended, *, request_id: str) -> Reaction:
        """Turn one meta-protocol suspension into its authoritative Reaction."""

        projection_name = suspended.socket.name.value
        projection = self.trusted.projection(projection_name)
        if projection["disposition"] != "live":
            raise Conflict(f"projection {projection_name!r} is not live")

        if suspended.operation == ELABORATE:
            return self._elaborate(
                suspended,
                projection_name=projection_name,
                projection=projection,
                request_id=request_id,
            )
        if suspended.operation == ACTUALIZE:
            return self._actualize(
                suspended,
                projection_name=projection_name,
                projection=projection,
                request_id=request_id,
            )
        raise MetaProtocolError(
            f"unknown meta-protocol operation {suspended.operation.value!r}"
        )

    def _elaborate(
        self,
        suspended: Suspended,
        *,
        projection_name: str,
        projection: Mapping[str, Any],
        request_id: str,
    ) -> Reaction:
        if projection["role"] != ELABORATOR_ROLE:
            raise Conflict("Elaborate requires an Elaborator projection")

        request = _request_dict(suspended.argument)
        protocol_cid = _string(request, "protocol_cid")
        try:
            protocol = self.protocols[protocol_cid]
        except KeyError as exc:
            raise MetaProtocolError(
                f"protocol {protocol_cid!r} is not registered with this Elaborator"
            ) from exc

        cuts = tuple(str(cut) for cut in request.get("cuts", ()))
        if not cuts:
            raise MetaProtocolError("Elaborate requires at least one causal cut")

        authority_pairs = request.get("authorities", ())
        authorities = {
            str(cut): str(authority)
            for cut, authority in authority_pairs
        }
        if projection_name not in authorities.values():
            raise Conflict(
                "the performed Elaborator Socket must participate in the elaboration"
            )

        observed = tuple(self._cut(cut) for cut in cuts)
        blueprint = elaborate_cuts(
            protocol,
            cuts=observed,
            elaborator=str(projection["holder"]),
            actualizer=_string(request, "actualizer"),
            knowledge=tuple(str(item) for item in request.get("knowledge", ())),
        )
        admitted = self.trusted.admit_cut_elaboration(
            blueprint=blueprint,
            authorities=authorities,
            request_id=request_id,
        )

        consumed = tuple(
            Socket(Name(authority))
            for _, authority in sorted(authorities.items())
        )
        value = _eidos_value(
            {
                "occurrence": Name(admitted["occurrence"]),
                "proof": admitted["proof"],
                "possibilities": {
                    key: Name(name)
                    for key, name in admitted["possibilities"].items()
                },
                "actualizers": {
                    possibility: Socket(Name(authority))
                    for possibility, authority in admitted["actualizers"].items()
                },
            }
        )
        return Reaction(
            name=Name(admitted["occurrence"]),
            consumed=consumed,
            successor=None,
            value=value,
        )

    def _actualize(
        self,
        suspended: Suspended,
        *,
        projection_name: str,
        projection: Mapping[str, Any],
        request_id: str,
    ) -> Reaction:
        if projection["role"] != ACTUALIZER_ROLE:
            raise Conflict("Actualize requires an Actualizer projection")

        request = _request_dict(suspended.argument)
        possibility = _string(request, "possibility")
        out = self.trusted.actualize_observed(
            possibility=possibility,
            actualizer=str(projection["holder"]),
            authority=projection_name,
            observation=request.get("observation"),
            request_id=request_id,
        )

        consumed = (
            Socket(Name(projection_name)),
            *tuple(Socket(Name(name)) for name in out["consumed"]),
        )
        value = _eidos_value(
            {
                "occurrence": Name(out["occurrence"]),
                "reaction": out["reaction"],
                "successors": {
                    key: Socket(Name(name))
                    for key, name in out["successors"].items()
                },
                "successor_cuts": {
                    old: Name(new)
                    for old, new in out["successor_cuts"].items()
                },
                "elaborators": {
                    cut: Socket(Name(authority))
                    for cut, authority in out["elaborators"].items()
                },
            }
        )
        return Reaction(
            name=Name(out["occurrence"]),
            consumed=consumed,
            successor=None,
            value=value,
        )

    def _cut(self, cut: str) -> ObservedCut:
        """Interpret a cut from its ordinary named Eidos Value.

        Trusted Machinery is consulted only for projection realization details
        such as role/state/holder. Spent projections remain part of the Cut's
        historical semantics; liveness matters later when an occurrence tries
        to consume authority.
        """

        bound = self.trusted.named_eidos_value(cut)
        value = bound["value"]
        if not isinstance(value, RecordValue) or value.get("$kind") != "Cut":
            raise MetaProtocolError(f"Name {cut!r} does not denote a Cut Value")

        projections: list[FrontierProjection] = []
        for projection_name in value.get("projections"):
            if not isinstance(projection_name, Name):
                raise MetaProtocolError("Cut projection references must be Names")
            row = self.trusted.projection(projection_name.value)
            projections.append(
                FrontierProjection(
                    name=projection_name.value,
                    role=str(row["role"]),
                    state=str(row["protocol_state"]),
                    holder=str(row["holder"]),
                )
            )

        parent_cut = value.get("parent_cut")
        parent_occurrence = value.get("parent_occurrence")
        return ObservedCut(
            name=cut,
            observer=str(value.get("observer")),
            protocol_cid=str(value.get("protocol")),
            parent_cut=(
                None
                if parent_cut is None
                else parent_cut.value
            ),
            parent_occurrence=(
                None
                if parent_occurrence is None
                else parent_occurrence.value
            ),
            projections=tuple(projections),
        )


def _request_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, RecordValue):
        return value.as_dict()
    raise MetaProtocolError("meta-protocol request must be a record/map value")


def _string(value: Mapping[str, Any], field: str) -> str:
    try:
        item = value[field]
    except KeyError as exc:
        raise MetaProtocolError(f"meta-protocol request lacks {field!r}") from exc
    if isinstance(item, Name):
        return item.value
    return str(item)


def _eidos_value(value: Any) -> Any:
    if isinstance(value, dict):
        return RecordValue.from_mapping(
            {str(key): _eidos_value(item) for key, item in value.items()}
        )
    if isinstance(value, list):
        return tuple(_eidos_value(item) for item in value)
    if isinstance(value, tuple):
        return tuple(_eidos_value(item) for item in value)
    return value
