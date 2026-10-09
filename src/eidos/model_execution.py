from __future__ import annotations

"""One value-level contract for declarative, Eidos Closure, and delegated Models.

The semantic Model Value names its implementation, but it never authorizes
execution. External execution requires an adapter explicitly registered by the
host. None of the adapters is given a Trusted Machinery capability.

A returned ModelProposal is an attributable epistemic assertion. Its premises
are checked against the known facts before any proposal becomes a derived fact.
For external/closure models, this is NOT a proof that the conclusion follows
logically from the premises.
"""

from dataclasses import dataclass
import json
import subprocess
from typing import Any, Callable, Mapping

from .core import (
    Apply,
    Bindings,
    Closure,
    Done,
    Lit,
    Name,
    PraxisCore,
    RecordValue,
    Role,
    canonical_bytes,
    from_data,
)


MODEL_ROLE = Role("elaboration", "model")
MODEL_INPUT_ROLE = Role("elaboration", "model-input")
MODEL_CONTEXT_ROLE = Role("elaboration", "context")

ModelAdapter = Callable[[RecordValue], RecordValue]


class ModelExecutionError(ValueError):
    pass


@dataclass(frozen=True)
class ModelCandidate:
    fact: str
    premises: tuple[str, ...]
    rule: int
    witness: Any = None


def executor_value(placement: str, *, label: str) -> RecordValue:
    """Inspectible executor description, not authority to run a program."""

    if not placement or not label:
        raise ValueError("executor placement and label must be nonempty")
    return RecordValue.from_mapping({
        "$kind": "ModelExecutor",
        "placement": placement,
        "label": label,
    })


def model_claim(
    fact: str,
    *,
    premises: tuple[str, ...],
    witness: Any = None,
) -> RecordValue:
    if not fact or not premises or any(not p for p in premises):
        raise ValueError("a model claim needs a fact and explicit premises")
    if len(set(premises)) != len(premises):
        raise ValueError("claim premises must be distinct")
    return RecordValue.from_mapping({
        "$kind": "ModelClaim",
        "fact": fact,
        "premises": tuple(premises),
        "witness": witness,
    })


def model_proposal(
    context: Name,
    claims: tuple[RecordValue, ...],
    *,
    receipt: Any = None,
) -> RecordValue:
    for claim in claims:
        _kind(claim, "ModelClaim")
    return RecordValue.from_mapping({
        "$kind": "ModelProposal",
        "context": context,
        "claims": claims,
        "receipt": receipt,
    })


def model_input(
    *,
    context: Name,
    model: Name,
    cuts: tuple[Name, ...],
    facts: tuple[str, ...],
    knowledge: tuple[Name, ...],
    remaining_budget: int,
) -> RecordValue:
    return RecordValue.from_mapping({
        "$kind": "ModelInput",
        "context": context,
        "model": model,
        "cuts": cuts,
        "facts": facts,
        "knowledge": knowledge,
        "remaining_budget": remaining_budget,
    })


def execute_model(
    *,
    name: str,
    model: RecordValue,
    request: RecordValue,
    resolve: Callable[[str], Any],
    adapters: Mapping[str, ModelAdapter] | None = None,
) -> tuple[tuple[ModelCandidate, ...], RecordValue]:
    """Run one Model through its chosen realization and return a Derivation Value."""

    _kind(model, "Model")
    _kind(request, "ModelInput")
    mode = _field(model, "engine", "rules")
    implementation = _field(model, "implementation", None)
    context = request.get("context")
    if not isinstance(context, Name):
        raise ModelExecutionError("ModelInput.context must be a Name")
    executor_name: Name | None = None

    if mode == "rules":
        if implementation is not None:
            raise ModelExecutionError("declarative Model must not name an executor")
        claims = tuple(
            model_claim(
                str(rule.get("conclusion")),
                premises=tuple(rule.get("premises")),
                witness=RecordValue.from_mapping({
                    "$kind": "RuleWitness",
                    "rule": i,
                }),
            )
            for i, rule in enumerate(model.get("rules"))
        )
        proposal = model_proposal(
            context, claims, receipt="declarative rules"
        )
    elif mode == "closure":
        if not isinstance(implementation, Closure):
            raise ModelExecutionError("Closure Model implementation must be an Eidos Closure")
        situated = (
            Bindings()
            .bind(MODEL_ROLE, Name(name))
            .bind(MODEL_INPUT_ROLE, request)
            .bind(MODEL_CONTEXT_ROLE, context)
        )
        result = PraxisCore().realize(
            Apply(Lit(implementation), (Lit(request),)),
            bindings=situated,
        )
        if not isinstance(result, Done):
            raise ModelExecutionError(
                "a local Model Closure must finish without unbound Roles or perform"
            )
        proposal = result.value
    elif mode == "delegated":
        if not isinstance(implementation, Name):
            raise ModelExecutionError("delegated Model must name its executor")
        executor_name = implementation
        _kind(resolve(executor_name.value), "ModelExecutor")
        adapter = None if adapters is None else adapters.get(executor_name.value)
        if adapter is None:
            raise ModelExecutionError(
                "delegated Model requires an explicitly registered executor"
            )
        proposal = adapter(request)
    else:
        raise ModelExecutionError(f"unknown Model engine {mode!r}")

    _kind(proposal, "ModelProposal")
    if proposal.get("context") != context:
        raise ModelExecutionError("Model proposal names the wrong Context")
    claims = proposal.get("claims")
    if not isinstance(claims, tuple) or len(claims) > 128:
        raise ModelExecutionError("Model proposal must contain at most 128 claims")

    candidates: list[ModelCandidate] = []
    for i, claim in enumerate(claims):
        _kind(claim, "ModelClaim")
        fact = claim.get("fact")
        premises = claim.get("premises")
        if not isinstance(fact, str) or not fact:
            raise ModelExecutionError("Model claim fact must be a nonempty string")
        if (
            not isinstance(premises, tuple)
            or not premises
            or any(not isinstance(p, str) or not p for p in premises)
            or len(set(premises)) != len(premises)
        ):
            raise ModelExecutionError("Model claim must have distinct, nonempty premises")
        candidates.append(
            ModelCandidate(
                fact=fact,
                premises=premises,
                rule=i,
                witness=claim.get("witness"),
            )
        )
    # Fail before any authority operation if an executor returned something
    # outside the serializable Eidos world.
    derivation = RecordValue.from_mapping({
        "$kind": "ModelDerivation",
        "model": Name(name),
        "executor": executor_name,
        "engine": mode,
        "input": request,
        "proposal": proposal,
    })
    canonical_bytes(derivation)
    return tuple(candidates), derivation


@dataclass(frozen=True)
class SubprocessModelAdapter:
    """Explicitly configured, bounded JSON/stdin model process adapter.

    This is NOT a sandbox. The host must deliberately choose/authorize argv.
    The subprocess never receives a Trusted Machinery handle. The wire format
    uses the ordinary Eidos Core to_data/from_data encoding, one request and
    one response per invocation.
    """

    argv: tuple[str, ...]
    timeout_seconds: float = 5.0
    max_output_bytes: int = 256 * 1024

    def __call__(self, request: RecordValue) -> RecordValue:
        if not self.argv or self.timeout_seconds <= 0 or self.max_output_bytes <= 0:
            raise ModelExecutionError("invalid subprocess model adapter configuration")
        try:
            result = subprocess.run(
                self.argv,
                input=canonical_bytes(request),
                capture_output=True,
                timeout=self.timeout_seconds,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ModelExecutionError("model process failed to complete") from exc
        if result.returncode != 0:
            raise ModelExecutionError("model process exited unsuccessfully")
        if len(result.stdout) > self.max_output_bytes:
            raise ModelExecutionError("model response exceeded output budget")
        try:
            value = from_data(json.loads(result.stdout))
        except (ValueError, TypeError, UnicodeDecodeError) as exc:
            raise ModelExecutionError("invalid Eidos model response") from exc
        _kind(value, "ModelProposal")
        return value


def _kind(value: Any, expected: str) -> RecordValue:
    if not isinstance(value, RecordValue) or _field(value, "$kind", None) != expected:
        raise ModelExecutionError(f"expected {expected} Eidos Value")
    return value


def _field(value: RecordValue, key: str, default: Any) -> Any:
    try:
        return value.get(key)
    except KeyError:
        return default
