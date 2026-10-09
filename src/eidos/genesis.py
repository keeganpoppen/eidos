from __future__ import annotations

"""Semantic adapter for the explicitly separate authority genesis act."""

from typing import Mapping

from .occurrence import RecursiveProtocol, plan_genesis
from .trusted import TrustedMachinery


def admit_genesis(
    trusted: TrustedMachinery,
    protocol: RecursiveProtocol,
    *,
    holders: Mapping[str, str],
    request_id: str,
) -> dict[str, object]:
    plan = plan_genesis(protocol, holders=holders)
    return trusted.admit_authority_domain(
        description=plan.description,
        establishes=plan.establishes,
        request_id=request_id,
    )
