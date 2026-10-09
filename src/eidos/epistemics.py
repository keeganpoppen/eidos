from __future__ import annotations

"""Situated epistemic elaboration over ordinary addressable Eidos Values.

Knowledge, Model, Attention, and Context are library-level RecordValues. Roles
select their occupants for one elaboration; Name references make those
occupants independently inspectable. No capability authority is created here.

This first model interpreter deliberately supports only bounded, positive
propositional implications. It is a small pressure test for progressive
understanding, not a general proof system or a claim of factual truth.
"""

from dataclasses import dataclass
from typing import Any, Callable, Iterable, Mapping

from .core import Bindings, Closure, Name, RecordValue, Role, content_id as core_content_id
from .model_execution import ModelAdapter, ModelCandidate, execute_model, model_input


KNOWLEDGE_ROLE = Role("elaboration", "knowledge")
MODELS_ROLE = Role("elaboration", "models")
ATTENTION_ROLE = Role("elaboration", "attention")

Resolver = Callable[[str], Any]


def _name(value: Name | str) -> Name:
    return value if isinstance(value, Name) else Name(value)


def _names(values: Iterable[Name | str]) -> tuple[Name, ...]:
    return tuple(_name(value) for value in values)


def knowledge_value(
    fact: str,
    *,
    grounds: Iterable[Name | str] = (),
) -> RecordValue:
    """A claimed fact with explicit, addressable provenance."""

    if not fact:
        raise ValueError("a knowledge fact must be nonempty")
    return RecordValue.from_mapping({
        "$kind": "Knowledge",
        "fact": fact,
        "grounds": _names(grounds),
    })


def implication_value(
    premises: Iterable[str],
    conclusion: str,
) -> RecordValue:
    """One positive inference rule represented as ordinary data."""

    premises = tuple(premises)
    if not premises or not conclusion or any(not fact for fact in premises):
        raise ValueError("implication requires premises and a conclusion")
    if len(set(premises)) != len(premises):
        raise ValueError("implication premises must be distinct")
    return RecordValue.from_mapping({
        "$kind": "Implication",
        "premises": premises,
        "conclusion": conclusion,
    })


def model_value(
    title: str,
    *,
    rules: Iterable[RecordValue] = (),
    sources: Iterable[Name | str] = (),
    implementation: Closure | Name | str | None = None,
    process: bool = False,
) -> RecordValue:
    """Bind the same Model Role to rules, Eidos code, or a delegated executor.

    A delegated implementation is only a Name of an executor description. The
    runtime must separately register an adapter before that model can run;
    knowing an executor Name does not grant execution authority.
    """

    if not title:
        raise ValueError("model title must be nonempty")
    rules = tuple(rules)
    for rule in rules:
        _require_kind(rule, "Implication")
    if implementation is not None and rules:
        raise ValueError("a Model has one implementation, not rules and an executor")
    if process and not isinstance(implementation, Closure):
        raise ValueError("process Models require a first-class Eidos Closure")
    if implementation is None:
        engine = "rules"
    elif isinstance(implementation, Closure):
        engine = "process" if process else "closure"
    else:
        engine = "delegated"
        implementation = _name(implementation)

    return RecordValue.from_mapping({
        "$kind": "Model",
        "title": title,
        "engine": engine,
        "implementation": implementation,
        "rules": rules,
        "sources": _names(sources),
    })


def attention_value(
    *,
    inference_budget: int,
    focus_models: Iterable[Name | str] = (),
) -> RecordValue:
    """A situated inference budget and optional model selection."""

    if isinstance(inference_budget, bool) or not isinstance(inference_budget, int) or inference_budget < 0:
        raise ValueError("inference_budget must be a nonnegative integer")
    return RecordValue.from_mapping({
        "$kind": "Attention",
        "inference_budget": inference_budget,
        "focus_models": _names(focus_models),
    })


def context_value(
    *,
    cuts: Iterable[Name | str],
    knowledge: Iterable[Name | str] = (),
    models: Iterable[Name | str] = (),
    attention: Name | str | None = None,
    parent: Name | str | None = None,
    acquisition: Name | str | None = None,
) -> RecordValue:
    """An immutable situated context, optionally extending a prior context.

    The Knowledge and Models roles contain additional references; interpreting
    the parent chain accumulates them. Attention, when provided, rebinds the
    effective attention role for this realization.
    """

    cut_names = _names(cuts)
    if not cut_names or len(set(cut_names)) != len(cut_names):
        raise ValueError("a context needs distinct causal cuts")
    bindings = Bindings().bind(KNOWLEDGE_ROLE, _names(knowledge)).bind(
        MODELS_ROLE, _names(models)
    )
    if attention is not None:
        bindings = bindings.bind(ATTENTION_ROLE, _name(attention))
    return RecordValue.from_mapping({
        "$kind": "ElaborationContext",
        "cuts": tuple(sorted(cut_names)),
        "parent": None if parent is None else _name(parent),
        "acquisition": None if acquisition is None else _name(acquisition),
        "bindings": bindings,
    })


@dataclass(frozen=True)
class Inference:
    """One attributed claim accepted into a bounded situated derivation."""

    fact: str
    model: str
    rule: int
    premises: tuple[str, ...]
    engine: str = "rules"
    derivation: str | None = None
    witness: Any = None


@dataclass(frozen=True)
class EpistemicResult:
    context: str
    ancestry: tuple[str, ...]
    knowledge: tuple[str, ...]
    models: tuple[str, ...]
    attention: str | None
    facts: tuple[str, ...]
    inferences: tuple[Inference, ...]
    derivations: tuple[RecordValue, ...] = ()


def interpret_context(
    context: Name | str,
    *,
    resolve: Resolver,
    cuts: Iterable[str],
    adapters: Mapping[str, ModelAdapter] | None = None,
    process_runner: Any | None = None,
    inference_limit: int | None = None,
) -> EpistemicResult:
    """Interpret a situated Context, optionally invoking registered executors.

    Declarative rules and local Eidos Closures run without effects; delegated
    executors may be external and are NOT assumed pure or retry-idempotent.
    Returned claims remain epistemic, not causal authority. Actualization
    always requires a separate live capability transaction.
    """

    name = _name(context).value
    expected_cuts = set(cuts)
    if not expected_cuts:
        raise ValueError("elaboration requires a causal cut")

    chain: list[tuple[str, RecordValue]] = []
    visited: set[str] = set()
    cursor: str | None = name
    while cursor is not None:
        if cursor in visited:
            raise ValueError("cyclic elaboration context ancestry")
        visited.add(cursor)
        value = _require_kind(resolve(cursor), "ElaborationContext")
        refs = value.get("cuts")
        if (
            not isinstance(refs, tuple)
            or any(not isinstance(ref, Name) for ref in refs)
            or not {ref.value for ref in refs} <= expected_cuts
        ):
            raise ValueError("context causal cuts differ from the current elaboration")
        chain.append((cursor, value))
        parent = value.get("parent")
        if parent is not None and not isinstance(parent, Name):
            raise ValueError("context parent must be a Name")
        cursor = None if parent is None else parent.value

    # Contexts may progressively incorporate new Cuts, but may not discard
    # causal evidence acquired by their ancestors. A named acquisition edge
    # records the causal disclosure that justified any expansion.
    ancestral: set[str] = set()
    for _, value in reversed(chain):
        current = {reference.value for reference in value.get("cuts")}
        if not ancestral <= current:
            raise ValueError("context ancestry cannot discard causal Cuts")
        if ancestral and current != ancestral and value.get("acquisition") is None:
            raise ValueError("context Cut expansion requires acquisition provenance")
        ancestral = current
    if ancestral != expected_cuts:
        raise ValueError("context causal cuts differ from the current elaboration")

    knowledge: list[str] = []
    models: list[str] = []
    attention_name: str | None = None
    for _, value in reversed(chain):
        bindings = value.get("bindings")
        if not isinstance(bindings, Bindings):
            raise ValueError("epistemic role bindings must be ordinary Eidos Bindings")
        for role, bucket in ((KNOWLEDGE_ROLE, knowledge), (MODELS_ROLE, models)):
            refs = bindings.lookup(role)
            if not isinstance(refs, tuple) or any(not isinstance(ref, Name) for ref in refs):
                raise ValueError("epistemic knowledge/model bindings must contain Names")
            for ref in refs:
                if ref.value not in bucket:
                    bucket.append(ref.value)
        try:
            bound_attention = bindings.lookup(ATTENTION_ROLE)
        except KeyError:
            continue
        if not isinstance(bound_attention, Name):
            raise ValueError("attention binding must contain a Name")
        attention_name = bound_attention.value

    known: set[str] = set()
    for ref in knowledge:
        claim = _require_kind(resolve(ref), "Knowledge")
        fact = claim.get("fact")
        if not isinstance(fact, str) or not fact:
            raise ValueError("knowledge fact must be nonempty")
        grounds = claim.get("grounds")
        if not isinstance(grounds, tuple) or any(not isinstance(g, Name) for g in grounds):
            raise ValueError("knowledge grounds must be Names")
        for ground in grounds:
            resolve(ground.value)  # A dangling evidence reference is not a valid grounding.
        known.add(fact)

    budget = 0
    focus: set[str] = set()
    if attention_name is not None:
        attention = _require_kind(resolve(attention_name), "Attention")
        budget = attention.get("inference_budget")
        if isinstance(budget, bool) or not isinstance(budget, int) or budget < 0:
            raise ValueError("attention budget must be a nonnegative integer")
        focus_refs = attention.get("focus_models")
        if not isinstance(focus_refs, tuple) or any(not isinstance(ref, Name) for ref in focus_refs):
            raise ValueError("attention focus must contain Model Names")
        focus = {ref.value for ref in focus_refs}
        if focus and not focus <= set(models):
            raise ValueError("attention focuses on a model outside its context")

    if inference_limit is not None:
        if (
            isinstance(inference_limit, bool)
            or not isinstance(inference_limit, int)
            or inference_limit < 0
        ):
            raise ValueError("inference_limit must be a nonnegative integer")
        budget = min(budget, inference_limit)

    selected_models: list[tuple[str, RecordValue]] = []
    for ref in models:
        model = _require_kind(resolve(ref), "Model")
        for source in model.get("sources"):
            if not isinstance(source, Name):
                raise ValueError("model sources must be Names")
            resolve(source.value)
        if focus and ref not in focus:
            continue
        selected_models.append((ref, model))

    # Execute each model at most once for this elaboration. Evaluation is lazy:
    # a small Attention budget must not invoke unrelated external executors.
    # Candidates from all implementations share the same bounded acceptance
    # logic, so no Model may bypass grounded premises to mint authority.
    evaluated: dict[str, tuple[ModelCandidate, ...]] = {}
    derivations: list[RecordValue] = []
    derivation_by_model: dict[str, RecordValue] = {}
    inferred: list[Inference] = []
    for _ in range(budget):
        enabled: tuple[str, ModelCandidate] | None = None
        for ref, model in selected_models:
            if ref not in evaluated:
                request = model_input(
                    context=Name(name),
                    model=Name(ref),
                    cuts=tuple(Name(cut) for cut in sorted(expected_cuts)),
                    facts=tuple(sorted(known)),
                    knowledge=tuple(Name(item) for item in knowledge),
                    remaining_budget=budget - len(inferred),
                )
                candidates, derivation = execute_model(
                    name=ref,
                    model=model,
                    request=request,
                    resolve=resolve,
                    adapters=adapters,
                    process_runner=process_runner,
                )
                evaluated[ref] = candidates
                derivations.append(derivation)
                derivation_by_model[ref] = derivation

            for candidate in evaluated[ref]:
                if candidate.fact in known:
                    continue
                if all(premise in known for premise in candidate.premises):
                    enabled = (ref, candidate)
                    break
            if enabled is not None:
                break

        if enabled is None:
            break
        ref, candidate = enabled
        derivation = derivation_by_model[ref]
        known.add(candidate.fact)
        inferred.append(
            Inference(
                fact=candidate.fact,
                model=ref,
                rule=candidate.rule,
                premises=candidate.premises,
                engine=derivation.get("engine"),
                derivation=core_content_id(derivation),
                witness=candidate.witness,
            )
        )

    return EpistemicResult(
        context=name,
        ancestry=tuple(ref for ref, _ in reversed(chain)),
        knowledge=tuple(knowledge),
        models=tuple(models),
        attention=attention_name,
        facts=tuple(sorted(known)),
        inferences=tuple(inferred),
        derivations=tuple(derivations),
    )


def _require_kind(value: Any, kind: str) -> RecordValue:
    if not isinstance(value, RecordValue):
        raise ValueError(f"expected a {kind} Eidos RecordValue")
    try:
        actual = value.get("$kind")
    except KeyError as exc:
        raise ValueError(f"expected a {kind} Eidos RecordValue") from exc
    if actual != kind:
        raise ValueError(f"expected {kind}, got {actual!r}")
    return value
