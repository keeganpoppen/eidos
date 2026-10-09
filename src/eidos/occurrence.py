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
    """Exact possibility structure handed down to Trusted Machinery."""

    protocol: str
    projections: tuple[ProjectionSeed, ...]
    possibilities: tuple[PossibilitySeed, ...]


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
    )
