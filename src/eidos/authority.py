from __future__ import annotations

"""Generic linear-authority occurrence descriptions.

This module contains no protocol semantics. A ProjectionGrant says exactly what
live projection capability an occurrence may establish if Trusted Machinery
successfully commits it.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ProjectionGrant:
    key: str
    role: str
    state: str
    holder: str
