from __future__ import annotations

"""Ordinary Eidos Values for observer / possibility / occurrence semantics.

These constructors are library conventions. Trusted Machinery does not import
or interpret their schemas; it merely persists Core Values by content identity
and optionally binds permanent Names to them.
"""

from typing import Any, Mapping

from .core import Name, RecordValue


def _record(kind: str, **fields: Any) -> RecordValue:
    return RecordValue.from_mapping({"$kind": kind, **fields})


def projection_template_value(
    *,
    key: str,
    role: str,
    state: str,
    holder: str,
) -> RecordValue:
    return _record(
        "ProjectionTemplate",
        key=key,
        role=role,
        state=state,
        holder=holder,
    )


def cut_value(
    *,
    name: str,
    observer: str,
    protocol_cid: str,
    projections: tuple[str, ...],
    elaborator_projection: str,
    parent_cut: str | None,
    parent_occurrence: str | None,
) -> RecordValue:
    return _record(
        "Cut",
        name=Name(name),
        observer=observer,
        protocol=protocol_cid,
        projections=tuple(Name(projection) for projection in projections),
        elaborator=Name(elaborator_projection),
        parent_cut=None if parent_cut is None else Name(parent_cut),
        parent_occurrence=(
            None if parent_occurrence is None else Name(parent_occurrence)
        ),
    )


def possibility_value(
    *,
    name: str,
    key: str,
    elaboration: str,
    proof: str,
    reaction: str,
    cuts: tuple[str, ...],
    inputs: tuple[str, ...],
    outputs: tuple[Mapping[str, str], ...],
    actualizer_projection: str,
) -> RecordValue:
    return _record(
        "Possibility",
        name=Name(name),
        key=key,
        elaboration=Name(elaboration),
        proof=proof,
        reaction=reaction,
        cuts=tuple(Name(cut) for cut in cuts),
        inputs=tuple(Name(projection) for projection in inputs),
        outputs=tuple(
            projection_template_value(
                key=output["key"],
                role=output["role"],
                state=output["state"],
                holder=output["holder"],
            )
            for output in outputs
        ),
        actualizer=Name(actualizer_projection),
    )


def elaboration_value(
    *,
    occurrence: str,
    proof: str,
    protocol_cid: str,
    cuts: tuple[str, ...],
    observers: tuple[str, ...],
    elaborator: str,
    actualizer: str,
    knowledge: tuple[str, ...],
    possibilities: tuple[str, ...],
    consumed: tuple[str, ...],
    established: tuple[str, ...],
) -> RecordValue:
    return _record(
        "Elaboration",
        occurrence=Name(occurrence),
        proof=proof,
        protocol=protocol_cid,
        cuts=tuple(Name(cut) for cut in cuts),
        observers=observers,
        elaborator=elaborator,
        actualizer=actualizer,
        knowledge=knowledge,
        possibilities=tuple(Name(possibility) for possibility in possibilities),
        consumed=tuple(Name(projection) for projection in consumed),
        established=tuple(Name(projection) for projection in established),
    )


def occurrence_value(
    *,
    occurrence: str,
    reaction: str,
    possibility: str,
    actualizer: str,
    cause_cuts: tuple[str, ...],
    successor_cuts: tuple[str, ...],
    observation: Any,
    consumed: tuple[str, ...],
    established: tuple[str, ...],
) -> RecordValue:
    return _record(
        "Occurrence",
        occurrence=Name(occurrence),
        reaction=reaction,
        possibility=Name(possibility),
        actualizer=actualizer,
        cause_cuts=tuple(Name(cut) for cut in cause_cuts),
        successor_cuts=tuple(Name(cut) for cut in successor_cuts),
        observation=observation,
        consumed=tuple(Name(projection) for projection in consumed),
        established=tuple(Name(projection) for projection in established),
    )
