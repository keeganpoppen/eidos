from __future__ import annotations

"""Semantic possibility spaces for reaction/occurrence experiments.

This module deliberately lives above Trusted Machinery. It describes a protocol
frontier as current participant projections plus a finite set of possible next
Reactions. Elaborating a protocol produces an InstanceBlueprint that contains
all of those possibilities before any one of them becomes an occurrence.

Trusted Machinery need not understand why a possibility is semantically valid.
It only installs the blueprint and later atomically commits one predeclared
possibility against still-live input projections.
"""

from dataclasses import dataclass
from typing import Mapping

from .model import content_id


@dataclass(frozen=True)
class ProjectionTemplate:
    """One participant-relative projection at a protocol frontier."""

    role: str
    state: str


@dataclass(frozen=True)
class ReactionType:
    """One possible event latent at the current protocol frontier.

    consumes names the roles whose current projection capabilities jointly
    enable this event. successors names the exact successor projection states
    that become live if the event occurs. A missing successor for a consumed
    role means that participant's projection ends at this event.
    """

    name: str
    consumes: tuple[str, ...]
    successors: tuple[ProjectionTemplate, ...]


@dataclass(frozen=True)
class ProtocolSpace:
    """A deliberately tiny one-frontier protocol possibility space."""

    name: str
    initial: tuple[ProjectionTemplate, ...]
    reactions: tuple[ReactionType, ...]

    def __post_init__(self) -> None:
        roles = [projection.role for projection in self.initial]
        if len(set(roles)) != len(roles):
            raise ValueError("initial projection roles must be unique")
        known = set(roles)
        reaction_names: set[str] = set()
        for reaction in self.reactions:
            if reaction.name in reaction_names:
                raise ValueError(f"duplicate reaction type {reaction.name!r}")
            reaction_names.add(reaction.name)
            if not reaction.consumes:
                raise ValueError("reaction must consume at least one projection")
            if len(set(reaction.consumes)) != len(reaction.consumes):
                raise ValueError("reaction consumes the same role more than once")
            unknown = set(reaction.consumes) - known
            if unknown:
                raise ValueError(
                    f"reaction {reaction.name!r} consumes unknown roles {sorted(unknown)!r}"
                )
            successor_roles = [successor.role for successor in reaction.successors]
            if len(set(successor_roles)) != len(successor_roles):
                raise ValueError(
                    f"reaction {reaction.name!r} has duplicate successor roles"
                )


@dataclass(frozen=True)
class ProjectionSeed:
    """Concrete initial projection to be installed mechanically."""

    key: str
    role: str
    state: str
    holder: str


@dataclass(frozen=True)
class SuccessorSeed:
    """A latent successor projection, named only if its Reaction occurs."""

    key: str
    role: str
    state: str
    holder: str


@dataclass(frozen=True)
class PossibilitySeed:
    """One latent event derived before runtime occurrence."""

    key: str
    reaction: str
    consumes: tuple[str, ...]
    establishes: tuple[SuccessorSeed, ...]


@dataclass(frozen=True)
class InstanceBlueprint:
    """Exact genesis possibility structure handed down to Trusted Machinery."""

    protocol: str
    projections: tuple[ProjectionSeed, ...]
    possibilities: tuple[PossibilitySeed, ...]
    protocol_cid: str | None = None


def elaborate(
    protocol: ProtocolSpace,
    *,
    holders: Mapping[str, str],
) -> InstanceBlueprint:
    """Project one protocol frontier into capabilities and latent Reactions.

    This is semantic work. The returned blueprint contains the exact input
    projections and successor templates for every possible event. Trusted
    Machinery later commits one of these possibilities mechanically; it does not
    recompute protocol semantics at occurrence time.
    """

    initial_by_role = {projection.role: projection for projection in protocol.initial}
    if set(holders) != set(initial_by_role):
        missing = sorted(set(initial_by_role) - set(holders))
        extra = sorted(set(holders) - set(initial_by_role))
        raise ValueError(
            f"holders must name every initial role exactly once; "
            f"missing={missing!r} extra={extra!r}"
        )

    projections = tuple(
        ProjectionSeed(
            key=f"projection:{projection.role}",
            role=projection.role,
            state=projection.state,
            holder=holders[projection.role],
        )
        for projection in protocol.initial
    )

    possibilities: list[PossibilitySeed] = []
    for reaction in protocol.reactions:
        consumes = tuple(f"projection:{role}" for role in reaction.consumes)
        successors: list[SuccessorSeed] = []
        for successor in reaction.successors:
            if successor.role not in holders:
                raise ValueError(
                    f"successor role {successor.role!r} has no holder lineage"
                )
            successors.append(
                SuccessorSeed(
                    key=f"{reaction.name}:successor:{successor.role}",
                    role=successor.role,
                    state=successor.state,
                    holder=holders[successor.role],
                )
            )
        possibilities.append(
            PossibilitySeed(
                key=f"reaction:{reaction.name}",
                reaction=reaction.name,
                consumes=consumes,
                establishes=tuple(successors),
            )
        )

    return InstanceBlueprint(
        protocol=protocol.name,
        projections=projections,
        possibilities=tuple(possibilities),
        protocol_cid=content_id(protocol),
    )



# ---------------------------------------------------------------------------
# Recursive protocol elaboration


@dataclass(frozen=True)
class ReactionRule:
    """A protocol event enabled by a particular projected frontier.

    requires states what participant-relative projection states must coexist for
    this event to be semantically possible. successors is the projected frontier
    for the roles consumed by the event after it occurs.
    """

    name: str
    requires: tuple[ProjectionTemplate, ...]
    successors: tuple[ProjectionTemplate, ...]

    def __post_init__(self) -> None:
        required_roles = [projection.role for projection in self.requires]
        if not required_roles:
            raise ValueError("reaction rule requires at least one projection")
        if len(set(required_roles)) != len(required_roles):
            raise ValueError("reaction rule requires a role more than once")
        successor_roles = [projection.role for projection in self.successors]
        if len(set(successor_roles)) != len(successor_roles):
            raise ValueError("reaction rule has duplicate successor roles")
        unknown = set(successor_roles) - set(required_roles)
        if unknown:
            raise ValueError(
                "this recursive experiment may only establish successors for "
                f"consumed roles; unknown={sorted(unknown)!r}"
            )


@dataclass(frozen=True)
class RecursiveProtocol:
    """An enduring protocol description whose rules can elaborate every frontier."""

    name: str
    initial: tuple[ProjectionTemplate, ...]
    reactions: tuple[ReactionRule, ...]

    def __post_init__(self) -> None:
        roles = [projection.role for projection in self.initial]
        if len(set(roles)) != len(roles):
            raise ValueError("initial projection roles must be unique")
        names = [reaction.name for reaction in self.reactions]
        if len(set(names)) != len(names):
            raise ValueError("reaction rule names must be unique")

    @property
    def cid(self) -> str:
        return content_id(self)


@dataclass(frozen=True)
class FrontierProjection:
    """A concrete current live projection exposed by Trusted Machinery."""

    name: str
    role: str
    state: str
    holder: str


@dataclass(frozen=True)
class FrontierPossibilitySeed:
    """One recursively elaborated possibility over concrete live projections."""

    key: str
    reaction: str
    consumes: tuple[str, ...]
    establishes: tuple[SuccessorSeed, ...]


@dataclass(frozen=True)
class FrontierBlueprint:
    """A proof-shaped description of the next possibility space.

    The blueprint is anchored to one linear frontier capability and one protocol
    commitment. It names the exact live projections from which it was derived.
    Trusted Machinery can therefore check provenance/mechanical freshness while
    remaining ignorant of the rich protocol rules that produced the blueprint.
    """

    protocol: str
    protocol_cid: str
    frontier: str
    parent_occurrence: str
    projections: tuple[FrontierProjection, ...]
    possibilities: tuple[FrontierPossibilitySeed, ...]

    @property
    def proof(self) -> str:
        return content_id(self)


def elaborate_genesis(
    protocol: RecursiveProtocol,
    *,
    holders: Mapping[str, str],
) -> InstanceBlueprint:
    """Elaborate generation zero of a recursive protocol."""

    initial_by_role = {projection.role: projection for projection in protocol.initial}
    if set(holders) != set(initial_by_role):
        missing = sorted(set(initial_by_role) - set(holders))
        extra = sorted(set(holders) - set(initial_by_role))
        raise ValueError(
            f"holders must name every initial role exactly once; "
            f"missing={missing!r} extra={extra!r}"
        )

    projections = tuple(
        ProjectionSeed(
            key=f"projection:{projection.role}",
            role=projection.role,
            state=projection.state,
            holder=holders[projection.role],
        )
        for projection in protocol.initial
    )
    by_role = {projection.role: projection for projection in projections}

    possibilities: list[PossibilitySeed] = []
    for rule in _enabled_rules(
        protocol,
        {
            role: (projection.state, projection.key, projection.holder)
            for role, projection in by_role.items()
        },
    ):
        possibilities.append(
            PossibilitySeed(
                key=f"reaction:{rule.name}",
                reaction=rule.name,
                consumes=tuple(
                    by_role[required.role].key for required in rule.requires
                ),
                establishes=tuple(
                    SuccessorSeed(
                        key=f"{rule.name}:successor:{successor.role}",
                        role=successor.role,
                        state=successor.state,
                        holder=holders[successor.role],
                    )
                    for successor in rule.successors
                ),
            )
        )

    return InstanceBlueprint(
        protocol=protocol.name,
        protocol_cid=protocol.cid,
        projections=projections,
        possibilities=tuple(possibilities),
    )


def elaborate_frontier(
    protocol: RecursiveProtocol,
    *,
    frontier: str,
    parent_occurrence: str,
    projections: tuple[FrontierProjection, ...],
) -> FrontierBlueprint:
    """Derive the next possibilities from one authoritative live frontier."""

    if not projections:
        raise ValueError("cannot elaborate an empty frontier")
    by_role: dict[str, FrontierProjection] = {}
    for projection in projections:
        if projection.role in by_role:
            raise ValueError(
                f"frontier contains more than one live projection for role "
                f"{projection.role!r}"
            )
        by_role[projection.role] = projection

    enabled = _enabled_rules(
        protocol,
        {
            role: (projection.state, projection.name, projection.holder)
            for role, projection in by_role.items()
        },
    )

    possibilities: list[FrontierPossibilitySeed] = []
    for rule in enabled:
        successors = tuple(
            SuccessorSeed(
                key=f"{parent_occurrence}:{rule.name}:successor:{successor.role}",
                role=successor.role,
                state=successor.state,
                holder=by_role[successor.role].holder,
            )
            for successor in rule.successors
        )
        possibilities.append(
            FrontierPossibilitySeed(
                key=f"{parent_occurrence}:reaction:{rule.name}",
                reaction=rule.name,
                consumes=tuple(
                    by_role[required.role].name for required in rule.requires
                ),
                establishes=successors,
            )
        )

    return FrontierBlueprint(
        protocol=protocol.name,
        protocol_cid=protocol.cid,
        frontier=frontier,
        parent_occurrence=parent_occurrence,
        projections=tuple(sorted(projections, key=lambda projection: projection.role)),
        possibilities=tuple(possibilities),
    )


def _enabled_rules(
    protocol: RecursiveProtocol,
    frontier: Mapping[str, tuple[str, str, str]],
) -> tuple[ReactionRule, ...]:
    enabled: list[ReactionRule] = []
    for rule in protocol.reactions:
        for required in rule.requires:
            current = frontier.get(required.role)
            if current is None or current[0] != required.state:
                break
        else:
            enabled.append(rule)
    return tuple(enabled)
