from __future__ import annotations

"""Values shared by contained resources and managed preparation, never authority."""

from dataclasses import asdict, dataclass, field
import hashlib
import json
import math
import re
from typing import Any, Mapping

from .codex import AppServerLimits, NativeExecutionProfileError


MANAGED_VERSION = "nema-managed-native/1"
MANAGED_BINARY_SHA256 = "9b7c1c7abdc26fc3c4f47c77656a8e9121def5483dbae830ef1ee561758448a9"
DEVICE_VERIFICATION_URL = "https://auth.openai.com/codex/device"
ISSUER_AUTHORITY = "auth.openai.com:443"
PROVIDER_AUTHORITY = "chatgpt.com:443"


class ManagedLaunchError(NativeExecutionProfileError):
    """An owned managed attempt cannot proceed; private capture keeps diagnostics."""


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(",", ":"), allow_nan=False).encode()).hexdigest()


@dataclass(frozen=True)
class ManagedAttemptIdentity:
    attempt_id: str
    context_id: str
    context_sha256: str
    projected_prompt_sha256: str
    source: str

    def __post_init__(self) -> None:
        for name in ("attempt_id", "context_id", "source"):
            value = getattr(self, name)
            if not isinstance(value, str) or not 0 < len(value) <= 512 or any(ord(c) < 32 for c in value):
                raise ValueError("invalid managed attempt identity")
        for name in ("context_sha256", "projected_prompt_sha256"):
            if not isinstance(getattr(self, name), str) or not re.fullmatch(r"[0-9a-f]{64}", getattr(self, name)):
                raise ValueError("invalid managed context digest")

    @classmethod
    def from_attempt(cls, attempt: Mapping[str, Any], context: Mapping[str, Any], source: str) -> ManagedAttemptIdentity:
        if attempt.get("contextId") != context.get("id") or not isinstance(context.get("projectedPrompt"), str):
            raise ValueError("managed identity requires the exact pinned context")
        return cls(attempt.get("id"), context.get("id"), canonical_sha256(context),
                   hashlib.sha256(context["projectedPrompt"].encode()).hexdigest(), source)

    def as_dict(self) -> dict[str, str]:
        return {"attemptId": self.attempt_id, "contextId": self.context_id,
                "contextSha256": self.context_sha256, "projectedPromptSha256": self.projected_prompt_sha256,
                "source": self.source}


@dataclass(frozen=True)
class ManagedPolicy:
    """Finite initial product choices. No HTTP caller can override these values."""

    preparation_seconds: float = 180
    turn_seconds: float = 120
    lifetime_seconds: float = 305
    resolve_seconds: float = 3
    dial_seconds: float = 5
    header_seconds: float = 2
    idle_seconds: float = 60
    max_connections: int = 256
    max_active: int = 2
    max_received_bytes: int = 8 * 1024 * 1024
    buffer_bytes: int = 8192
    header_bytes: int = 8192
    max_resolved_addresses: int = 16
    capture: AppServerLimits = field(default_factory=lambda: AppServerLimits(max_received_bytes=8 * 1024 * 1024))

    def __post_init__(self) -> None:
        for name, value in asdict(self).items():
            if name == "capture":
                continue
            if name.endswith("seconds"):
                if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
                    raise ValueError("managed time bounds must be positive and finite")
            elif type(value) is not int or value <= 0:
                raise ValueError("managed count and byte bounds must be positive integers")
        if not isinstance(self.capture, AppServerLimits):
            raise ValueError("managed capture bounds must be AppServerLimits")

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)
