from __future__ import annotations

"""Observer-relative causal cuts over the occurrence calculus.

A Cut is not a global world frontier. It is one observer's addressable causal
boundary: the concrete live projections that observer can presently relate to a
protocol history.

Elaborator and Actualizer are roles. A cut elaboration names who is filling the
Elaborator role for that derivation and which Actualizer role is expected to
commit any occurrence selected from it. Nothing in this module assumes either
role is a singleton process.
"""

from dataclasses import dataclass
from typing import Iterable

from .model import content_id
from .occurrence import (
    FrontierPossibilitySeed,
    FrontierProjection,
    ReactionRule,
    RecursiveProtocol,
    SuccessorSeed,
)


@dataclass(frozen=True)
class ObservedCut:
    """One observer-relative causal boundary."""

    name: str
    observer: str
    protocol_cid: str
    projections: tuple[FrontierProjection, ...]
    parent_cut: str | None = None
    parent_occurrence: str | None = None


@dataclass(frozen=True)
class CutElaboration:
    """Possibilities derived from one or more observer-relative cuts."""

    protocol: str
    protocol_cid: str
    cuts: tuple[str, ...]
    observers: tuple[str, ...]
    elaborator: str
    actualizer: str
    projections: tuple[FrontierProjection, ...]
    possibilities: tuple[FrontierPossibilitySeed, ...]

    @property
    def proof(self) -> str:
        return content_id(self)


def elaborate_cuts(
    protocol: RecursiveProtocol,
    *,
    cuts: Iterable[ObservedCut],
    elaborator: str,
    actualizer: str,
) -> CutElaboration:
    """Derive adjacent possibilities visible across a collection of cuts.

    A single-observer elaboration passes one cut. A rendezvous spanning several
    observer worlds passes several cuts. The union is purely semantic: no global
    frontier is manufactured. Each possibility consumes only the concrete
    projection capabilities required by its rule.
    """

    materialized = tuple(cuts)
    if not materialized:
        raise ValueError("at least one observed cut is required")
    if any(cut.protocol_cid != protocol.cid for cut in materialized):
        raise ValueError("all cuts must commit to the same protocol")

    by_name: dict[str, FrontierProjection] = {}
    by_role: dict[str, FrontierProjection] = {}
    for cut in materialized:
        for projection in cut.projections:
            existing = by_name.get(projection.name)
            if existing is not None and existing != projection:
                raise ValueError("projection identity has inconsistent descriptions")
            by_name[projection.name] = projection

            role_existing = by_role.get(projection.role)
            if role_existing is not None and role_existing.name != projection.name:
                raise ValueError(
                    f"cuts expose different live projections for role "
                    f"{projection.role!r}; reconcile observations first"
                )
            by_role[projection.role] = projection

    possibilities: list[FrontierPossibilitySeed] = []
    for rule in protocol.reactions:
        if not _enabled(rule, by_role):
            continue
        consumes = tuple(by_role[required.role].name for required in rule.requires)
        successors = tuple(
            SuccessorSeed(
                key=(
                    f"cuts:{'+'.join(sorted(cut.name for cut in materialized))}:"
                    f"{rule.name}:successor:{successor.role}"
                ),
                role=successor.role,
                state=successor.state,
                holder=by_role[successor.role].holder,
            )
            for successor in rule.successors
        )
        possibilities.append(
            FrontierPossibilitySeed(
                key=(
                    f"cuts:{'+'.join(sorted(cut.name for cut in materialized))}:"
                    f"reaction:{rule.name}"
                ),
                reaction=rule.name,
                consumes=consumes,
                establishes=successors,
            )
        )

    projections = tuple(sorted(by_name.values(), key=lambda p: (p.role, p.name)))
    return CutElaboration(
        protocol=protocol.name,
        protocol_cid=protocol.cid,
        cuts=tuple(sorted(cut.name for cut in materialized)),
        observers=tuple(sorted({cut.observer for cut in materialized})),
        elaborator=elaborator,
        actualizer=actualizer,
        projections=projections,
        possibilities=tuple(possibilities),
    )


def _enabled(
    rule: ReactionRule,
    by_role: dict[str, FrontierProjection],
) -> bool:
    for required in rule.requires:
        projection = by_role.get(required.role)
        if projection is None or projection.state != required.state:
            return False
    return True
