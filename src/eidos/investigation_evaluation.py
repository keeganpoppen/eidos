"""Pure, deterministic checks for explicitly synthetic counterfactual fixtures.

Fact support is a fixture annotation, not an entailment oracle. No function here
calls a model, dispatches work, changes a workspace, or admits live authority.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
import hashlib
import json
import math
from typing import Any


EVALUATOR_VERSION = "fixture-grounding/v1"


def _json(value: Any) -> str:
    def check(item: Any) -> None:
        if isinstance(item, Mapping):
            if any(not isinstance(key, str) for key in item):
                raise ValueError("JSON object keys must be strings")
            for child in item.values():
                check(child)
        elif isinstance(item, list):
            for child in item:
                check(child)
        elif item is not None and not isinstance(item, (str, int, float, bool)):
            raise ValueError("expected finite JSON content")
    check(value)
    try:
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
        encoded.encode("utf-8")
        return encoded
    except (TypeError, ValueError, UnicodeError) as error:
        raise ValueError("expected finite UTF-8 JSON content") from error


def _copy(value: Any) -> Any:
    return json.loads(_json(value))


def _identity(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_json(value).encode()).hexdigest()


def _mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return _copy(dict(value))


def _integer(value: Any, label: str, *, minimum: int = 1) -> int:
    if type(value) is not int or value < minimum:
        raise ValueError(f"{label} must be an integer >= {minimum}")
    return value


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be nonempty text")
    value.encode("utf-8")
    return value


def _sequence(value: Any, label: str) -> list:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise ValueError(f"{label} must be a sequence")
    return list(value)


def _ids(value: Any, label: str, *, nonempty: bool = False) -> list[int]:
    values = [_integer(item, label) for item in _sequence(value, label)]
    if len(values) != len(set(values)):
        raise ValueError(f"{label} contains duplicate IDs")
    if nonempty and not values:
        raise ValueError(f"{label} must not be empty")
    return sorted(values)


def _texts(value: Any, label: str) -> list[str]:
    values = [_text(item, label) for item in _sequence(value, label)]
    if not values or len(values) != len(set(values)):
        raise ValueError(f"{label} must be nonempty and unique")
    return sorted(values)


def _evidence(value: Any) -> dict[int, dict]:
    records = {}
    for item in _sequence(value, "frozen_evidence"):
        record = _mapping(item, "evidence record")
        seq = _integer(record.get("seq"), "evidence seq")
        if seq in records:
            raise ValueError("frozen_evidence contains duplicate IDs")
        raw = record.get("rawText")
        if not isinstance(raw, str):
            raise ValueError("rawText must be text")
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        if record.get("sha256") != digest:
            raise ValueError("frozen evidence sha256 does not match rawText")
        records[seq] = record
    return records


def _ratio(numerator: int, denominator: int) -> dict:
    return {"numerator": numerator, "denominator": denominator,
            "value": numerator / denominator if denominator else None}


def evaluate_outcome(
    criteria: Mapping, frozen_evidence: Sequence[Mapping],
    selected_record_ids: Sequence[int], claims: Sequence[Mapping], resources: Mapping,
) -> dict:
    """Evaluate fixture claims against jointly required, frozen support records.

    Unknown fact keys and wrong values/facets are failed claims. Malformed or
    duplicate claims are rejected. A selected citation alone is not grounding;
    every annotated supporting record must be selected and cited, with no extra
    citations. This strict fixture protocol makes no natural-language judgment.
    """
    criteria = _mapping(criteria, "criteria")
    version = _text(criteria.get("version"), "criteria version")
    question = _text(criteria.get("question"), "question")
    records = _evidence(frozen_evidence)
    selected = set(_ids(selected_record_ids, "selected_record_ids"))
    relevant = set(_ids(criteria.get("relevantRecordIds"), "relevantRecordIds", nonempty=True))
    facets = set(_texts(criteria.get("requiredFacets"), "requiredFacets"))
    budget = _integer(criteria.get("maxAdditionalBytes"), "maxAdditionalBytes", minimum=0)
    if not relevant <= records.keys():
        raise ValueError("relevantRecordIds must belong to the frozen evidence horizon")
    support = _mapping(criteria.get("factSupport"), "factSupport")
    if not support:
        raise ValueError("factSupport must not be empty")
    for key, fact in support.items():
        _text(key, "claim key")
        fact = _mapping(fact, "fact support")
        if "value" not in fact:
            raise ValueError("fact support requires value")
        ids = _ids(fact.get("recordIds"), "support recordIds", nonempty=True)
        if not set(ids) <= records.keys():
            raise ValueError("support recordIds must belong to the frozen evidence horizon")
        _text(fact.get("facet"), "support facet")
        fact["recordIds"] = ids
        support[key] = fact
    resources = _mapping(resources, "resources")
    prompt = resources.get("projectedPrompt")
    if not isinstance(prompt, str):
        raise ValueError("projectedPrompt must be text")
    if type(resources.get("modelCalls")) is not int or resources["modelCalls"] != 0:
        raise ValueError("synthetic evaluator requires modelCalls=0")
    size = len(prompt.encode("utf-8"))

    results, failures, seen, satisfied, cited = [], [], set(), set(), set()
    for item in _sequence(claims, "claims"):
        claim = _mapping(item, "claim")
        key = _text(claim.get("key"), "claim key")
        if key in seen:
            raise ValueError("duplicate or contradictory claim key")
        seen.add(key)
        if "value" not in claim:
            raise ValueError("claim requires value")
        facet = _text(claim.get("facet"), "claim facet")
        citations = set(_ids(claim.get("citations"), "claim citations"))
        cited.update(citations)
        reasons = []
        fact = support.get(key)
        if fact is None:
            reasons.append("unknown_claim")
        else:
            if _json(claim["value"]) != _json(fact["value"]):
                reasons.append("incorrect_value")
            if facet != fact["facet"]:
                reasons.append("incorrect_facet")
            if citations != set(fact["recordIds"]):
                reasons.append("incorrect_support")
        if not citations:
            reasons.append("empty_support")
        if not citations <= selected:
            reasons.append("unselected_citation")
        if not citations <= records.keys():
            reasons.append("hindsight_citation")
        grounded = not reasons
        if grounded:
            satisfied.add(facet)
        else:
            failures.extend({"code": reason, "claimKey": key} for reason in reasons)
        results.append({**claim, "citations": sorted(citations), "grounded": grounded, "failures": reasons})
    omitted, irrelevant = relevant - selected, selected - relevant
    leaked_selected, leaked_cited = selected - records.keys(), cited - records.keys()
    missing = facets - satisfied
    failures.extend({"code": "omitted_relevant_evidence", "recordId": seq} for seq in sorted(omitted))
    failures.extend({"code": "hindsight_selection", "recordId": seq} for seq in sorted(leaked_selected))
    failures.extend({"code": "missing_required_facet", "facet": facet} for facet in sorted(missing))
    unsupported = [claim["key"] for claim in results if not claim["grounded"]]
    return {
        "schemaVersion": 1, "evaluatorVersion": EVALUATOR_VERSION,
        "evidence_class": "synthetic", "measured_model_reasoning_improvement": False,
        "evaluatedSurface": "structured_fixture_claims_only", "answerTextEvaluated": False,
        "criteriaId": _identity(criteria), "criteriaVersion": version, "question": question,
        "evidenceHorizonId": _identity([records[seq] for seq in sorted(records)]),
        "selection": {"selectedRecordIds": sorted(selected),
                      "relevantSelectedRecordIds": sorted(selected & relevant),
                      "omittedRelevantRecordIds": sorted(omitted),
                      "irrelevantSelectedRecordIds": sorted(irrelevant),
                      "precision": _ratio(len(selected & relevant), len(selected)),
                      "recall": _ratio(len(selected & relevant), len(relevant))},
        "grounding": {"claims": results, "groundedClaims": len(results) - len(unsupported),
                      "totalClaims": len(results), "unsupportedClaimKeys": unsupported},
        "usefulness": {"kind": "grounded-required-facet-coverage-proxy",
                       "satisfiedFacets": sorted(facets & satisfied), "missingFacets": sorted(missing),
                       "coverage": _ratio(len(facets & satisfied), len(facets))},
        "hindsight": {"selectedOutsideHorizon": sorted(leaked_selected),
                      "citedOutsideHorizon": sorted(leaked_cited),
                      "leakageCount": len(leaked_selected | leaked_cited)},
        "resources": {"projectedBytes": size, "tokenEstimate": math.ceil(size / 4),
                      "tokenEstimateMethod": "ceil(UTF-8 bytes / 4); not measured model tokens",
                      "modelCalls": 0, "observedTokens": None, "observedCost": None,
                      "maxAdditionalBytes": budget},
        "failures": failures, "passes": not failures,
    }


def compare_evaluations(baseline: Mapping, candidate: Mapping) -> dict:
    """Compare the same fixture criteria/horizon; never approve live adoption."""
    baseline, candidate = _mapping(baseline, "baseline"), _mapping(candidate, "candidate")
    for report in (baseline, candidate):
        if (report.get("schemaVersion") != 1 or report.get("evaluatorVersion") != EVALUATOR_VERSION
                or report.get("evidence_class") != "synthetic"
                or report.get("measured_model_reasoning_improvement") is not False):
            raise ValueError("comparison requires synthetic evaluator reports")
    for field in ("criteriaId", "evidenceHorizonId"):
        if not baseline.get(field) or baseline[field] != candidate.get(field):
            raise ValueError(f"comparison requires identical {field}")
    try:
        metric_paths = {"selectionRecall": ("selection", "recall"),
                        "selectionPrecision": ("selection", "precision"),
                        "usefulnessCoverage": ("usefulness", "coverage")}
        deltas = {}
        for name, (group, metric) in metric_paths.items():
            before, after = baseline[group][metric]["value"], candidate[group][metric]["value"]
            # Empty selection has undefined precision; count it as zero only for
            # this comparison, while retaining None in the original report.
            deltas[name] = (after if after is not None else 0) - (before if before is not None else 0)
        deltas["groundedClaims"] = candidate["grounding"]["groundedClaims"] - baseline["grounding"]["groundedClaims"]
        deltas["unsupportedClaims"] = len(candidate["grounding"]["unsupportedClaimKeys"]) - len(baseline["grounding"]["unsupportedClaimKeys"])
        additional = candidate["resources"]["projectedBytes"] - baseline["resources"]["projectedBytes"]
        budget = candidate["resources"]["maxAdditionalBytes"]
        checks = {
            "noHindsightLeakage": candidate["hindsight"]["leakageCount"] == 0,
            "noUnsupportedClaims": not candidate["grounding"]["unsupportedClaimKeys"],
            "selectionRecallNondecreasing": deltas["selectionRecall"] >= 0,
            "selectionPrecisionNondecreasing": deltas["selectionPrecision"] >= 0,
            "usefulnessNondecreasing": deltas["usefulnessCoverage"] >= 0,
            "boundedAdditionalContext": additional <= budget,
            "fixtureImprovement": deltas["selectionRecall"] > 0 or deltas["usefulnessCoverage"] > 0,
        }
    except (KeyError, TypeError) as error:
        raise ValueError("malformed evaluator report") from error
    passed = all(checks.values())
    return {"schemaVersion": 1, "evaluatorVersion": EVALUATOR_VERSION,
            "evidence_class": "synthetic", "measured_model_reasoning_improvement": False,
            "evaluatedSurface": "structured_fixture_claims_only", "answerTextEvaluated": False,
            "criteriaId": candidate["criteriaId"], "evidenceHorizonId": candidate["evidenceHorizonId"],
            "deltas": deltas, "checks": checks, "passes": passed,
            "recommendation": "review_bounded_fixture_improvement" if passed else "retain_counterexample",
            "resourceTradeoff": {"additionalBytes": additional, "maxAdditionalBytes": budget,
                                 "additionalEstimatedTokens": candidate["resources"]["tokenEstimate"] - baseline["resources"]["tokenEstimate"],
                                 "observedAdditionalTokens": None, "observedAdditionalCost": None}}


def select_context(
    policy: str, frozen_evidence: Sequence[Mapping], seed_record_ids: Sequence[int], *,
    max_records: int, max_bytes: int,
) -> dict:
    """P0 retains seeds; P1 adds their explicit one-hop relatedEvidence links.

    The fixture link lives at the top level of raw JSON. It is untrusted data:
    it can nominate only already frozen evidence and never authorize execution.
    Seeds are retained or the whole operation fails; only added links truncate.
    """
    if policy not in {"P0", "P1"}:
        raise ValueError("policy must be P0 or P1")
    records = _evidence(frozen_evidence)
    selected = _ids(seed_record_ids, "seed_record_ids", nonempty=True)
    if not set(selected) <= records.keys():
        raise ValueError("seed records must belong to the frozen evidence horizon")
    max_records = _integer(max_records, "max_records")
    max_bytes = _integer(max_bytes, "max_bytes")

    def project(ids: list[int]) -> str:
        return "\n\n".join(f"[evidence:{seq}]\n{records[seq]['rawText']}" for seq in sorted(ids))

    if len(selected) > max_records or len(project(selected).encode()) > max_bytes:
        raise ValueError("seed records exceed context budget")
    omissions = []
    if policy == "P1":
        related = set()
        for seq in selected:
            try:
                payload = json.loads(records[seq]["rawText"])
            except (ValueError, TypeError) as error:
                raise ValueError("P1 fixture records require JSON objects") from error
            if not isinstance(payload, dict):
                raise ValueError("P1 fixture records require JSON objects")
            related.update(_ids(payload.get("relatedEvidence", []), "relatedEvidence"))
        for seq in sorted(related - set(selected)):
            if seq not in records:
                omissions.append({"recordId": seq, "reason": "outside_frozen_horizon"})
            elif len(selected) == max_records:
                omissions.append({"recordId": seq, "reason": "record_budget"})
            elif len(project([*selected, seq]).encode()) > max_bytes:
                omissions.append({"recordId": seq, "reason": "bytes_budget"})
            else:
                selected.append(seq)
    prompt = project(selected)
    return {"policy": policy, "selectedRecordIds": sorted(selected), "projectedPrompt": prompt,
            "omissions": omissions, "inputBytes": len(prompt.encode("utf-8"))}
