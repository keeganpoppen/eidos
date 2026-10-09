from __future__ import annotations

"""Generic linear-authority descriptions.

Trusted Machinery interprets only holder and linear disposition. The semantic
description of a projection is an ordinary Eidos Value bound to the projection
Name; TM persists it but does not interpret its fields.
"""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ProjectionGrant:
    key: str
    holder: str
    description: Any
