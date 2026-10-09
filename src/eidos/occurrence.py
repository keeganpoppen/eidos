from __future__ import annotations

"""Observer-relative protocol elaboration primitives.

This module contains semantic descriptions only. It does not install protocol
state into Trusted Machinery. Authority genesis is planned here, then admitted
explicitly through the generic authority-domain substrate.
"""

from dataclasses import dataclass
from typing import Mapping

from .authority import ProjectionGrant
from .model import content_id
from .semantic_values import authority_domain_value, projection_value


@dataclass(frozen=True)
class ProjectionTemplate:
    """One role-relative projected protocol state."""

    role: str
    state: str


@dataclass(frozen=True)
class SuccessorSeed:
    """One possible successor projection description plus intended holder."""

    key: str
    role: str
    state: str
    holder: str


@dataclass(frozen=True)
class ReactionRule:
    """One semantic event shape enabled by matching projected states."""

    name: str
    requires: tuple[ProjectionTemplate, ...]
    successors: tuple[ProjectionTemplate, ...]
    requires_facts: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        required_roles = [projection.role for projection in self.requires]
        if not required_roles:
            raise ValueError("reaction rule requires at least one projection")
        if len(set(required_roles)) != len(required_roles):
            raise ValueError("reaction rule requires a role more than once")

        if any(not fact for fact in self.requires_facts):
            raise ValueError("knowledge preconditions must be nonempty facts")
        if len(set(self.requires_facts)) != len(self.requires_facts):
            raise ValueError("duplicate knowledge precondition")

        successor_roles = [projection.role for projection in self.successors]
        if len(set(successor_roles)) != len(successor_roles):
            raise ValueError("reaction rule has duplicate successor roles")

        unknown = set(successor_roles) - set(required_roles)
        if unknown:
            raise ValueError(
                "this experiment may only establish successors for consumed "
                f"roles; unknown={sorted(unknown)!r}"
            )


@dataclass(frozen=True)
class RecursiveProtocol:
    """An immutable semantic description of possible recursive evolution."""

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
    """Concrete projection visible at an observer-relative causal cut.

    The historical name is retained for now; semantically this is not a global
    frontier object.
    """

    name: str
    role: str
    state: str
    holder: str


@dataclass(frozen=True)
class FrontierPossibilitySeed:
    """A semantically derived possible Reaction over concrete projections."""

    key: str
    reaction: str
    consumes: tuple[str, ...]
    establishes: tuple[SuccessorSeed, ...]


@dataclass(frozen=True)
class GenesisPlan:
    """Semantic input to the explicitly separate admitted genesis act."""

    description: object
    establishes: tuple[ProjectionGrant, ...]
    protocol_cid: str


def plan_genesis(
    protocol: RecursiveProtocol,
    *,
    holders: Mapping[str, str],
) -> GenesisPlan:
    """Describe authority-domain genesis without minting authority itself."""

    initial_by_role = {projection.role: projection for projection in protocol.initial}
    if set(holders) != set(initial_by_role):
        missing = sorted(set(initial_by_role) - set(holders))
        extra = sorted(set(holders) - set(initial_by_role))
        raise ValueError(
            "holders must name every initial role exactly once; "
            f"missing={missing!r} extra={extra!r}"
        )

    return GenesisPlan(
        description=authority_domain_value(
            protocol=protocol.name,
            protocol_cid=protocol.cid,
        ),
        establishes=tuple(
            ProjectionGrant(
                key=f"projection:{projection.role}",
                holder=holders[projection.role],
                description=projection_value(
                    key=f"projection:{projection.role}",
                    role=projection.role,
                    state=projection.state,
                ),
            )
            for projection in protocol.initial
        ),
        protocol_cid=protocol.cid,
    )
