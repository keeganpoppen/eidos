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
from typing import Any, Callable, Iterable, Mapping

from .model import content_id
from .epistemics import Inference, interpret_context
from .model_execution import ModelAdapter
from .core import RecordValue
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
    knowledge: tuple[str, ...]
    projections: tuple[FrontierProjection, ...]
    possibilities: tuple[FrontierPossibilitySeed, ...]
    context: str | None = None
    facts: tuple[str, ...] = ()
    inferences: tuple[Inference, ...] = ()
    derivations: tuple[RecordValue, ...] = ()

    @property
    def proof(self) -> str:
        return content_id(self)


def elaborate_cuts(
    protocol: RecursiveProtocol,
    *,
    cuts: Iterable[ObservedCut],
    elaborator: str,
    actualizer: str,
    knowledge: Iterable[str] = (),
    context: str | None = None,
    resolve: Callable[[str], Any] | None = None,
    adapters: Mapping[str, ModelAdapter] | None = None,
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

    facts: tuple[str, ...] = ()
    inferences: tuple[Inference, ...] = ()
    derivations: tuple[RecordValue, ...] = ()
    if context is not None:
        if resolve is None:
            raise ValueError("named epistemic contexts require a Value resolver")
        epistemic = interpret_context(
            context,
            resolve=resolve,
            cuts=(cut.name for cut in materialized),
            adapters=adapters,
        )
        facts = epistemic.facts
        inferences = epistemic.inferences
        derivations = epistemic.derivations

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
        if not _enabled(rule, by_role, facts=facts):
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
        knowledge=tuple(sorted(set(knowledge))),
        projections=projections,
        possibilities=tuple(possibilities),
        context=context,
        facts=facts,
        inferences=inferences,
        derivations=derivations,
    )


def _enabled(
    rule: ReactionRule,
    by_role: dict[str, FrontierProjection],
    *,
    facts: tuple[str, ...] = (),
) -> bool:
    if not set(rule.requires_facts) <= set(facts):
        return False
    for required in rule.requires:
        projection = by_role.get(required.role)
        if projection is None or projection.state != required.state:
            return False
    return True
