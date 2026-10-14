"""Resolve attributed result values without manufacturing execution provenance."""
from __future__ import annotations

import re
from typing import Any, Mapping

from .investigation import InvestigationError, MAX_ARTIFACT_BYTES, _digest, _json, _text


FINDING_KIND = "owner-authored-finding"
FINDING_DOMAIN = "eidos.owner-authored-finding/v1"
FINDING_FIELDS = {"id", "kind", "contextId", "text", "citations", "unsupportedCitations",
                  "artifactCitations", "unsupportedArtifactCitations", "authorship"}


def finding_content(context: Mapping[str, Any], text: Any) -> dict[str, Any]:
    text = _text(text, "finding text", MAX_ARTIFACT_BYTES)
    if not text.replace("\ufeff", "").strip():
        raise InvestigationError(400, "finding text must contain non-whitespace content")
    if len(text.encode("utf-8")) > MAX_ARTIFACT_BYTES:
        raise InvestigationError(400, "finding text exceeds 128 KiB")
    cited = set()
    for token in re.findall(r"\[evidence:([0-9]+)\]", text):
        # Bound conversion before Python's configurable integer-string limit.
        if len(token) > 16 or int(token) > 2**53 - 1:
            raise InvestigationError(400, "evidence citation exceeds the safe integer coordinate limit")
        cited.add(int(token))
    selected = {record["seq"] for record in context["records"]}
    referred = set(re.findall(r"\[artifact:([A-Za-z0-9_-]+)\]", text))
    supplied = {item["artifactId"] for item in context.get("artifactInputs", [])}
    return {"kind": FINDING_KIND, "contextId": context["id"], "text": text,
            "citations": sorted(cited & selected), "unsupportedCitations": sorted(cited - selected),
            "artifactCitations": sorted(referred & supplied), "unsupportedArtifactCitations": sorted(referred - supplied)}


def finding_id(owner_id: str, content: Mapping[str, Any]) -> str:
    return "artifact_" + _digest(_json({"domain": FINDING_DOMAIN, "investigationId": owner_id, **content}))


def _context(work: Mapping[str, Any], context_id: str) -> dict[str, Any]:
    contexts = [c for c in work["contexts"] if c["id"] == context_id]
    if not contexts or any(c != contexts[0] for c in contexts[1:]):
        raise InvestigationError(409, "artifact context is missing or ambiguous")
    return contexts[0]


def validate_finding(work: Mapping[str, Any], finding: Any) -> dict[str, Any]:
    """Validate the host schema and content identity, not an authenticated author."""
    if not isinstance(finding, dict) or set(finding) != FINDING_FIELDS or finding.get("kind") != FINDING_KIND:
        raise InvestigationError(409, "invalid authored finding schema")
    author = finding["authorship"]
    if (not isinstance(author, dict) or set(author) != {"kind", "createdAtMs"}
            or author["kind"] != "local-owner" or type(author["createdAtMs"]) is not int
            or not 0 <= author["createdAtMs"] <= 2**53 - 1):
        raise InvestigationError(409, "invalid authored finding attribution")
    for key in ("citations", "unsupportedCitations"):
        if not isinstance(finding[key], list) or any(type(v) is not int for v in finding[key]):
            raise InvestigationError(409, "invalid authored finding citations")
    context = _context(work, finding["contextId"])
    try:
        content = finding_content(context, finding["text"])
    except InvestigationError:
        raise InvestigationError(409, "invalid authored finding content") from None
    if ({k: finding[k] for k in content} != content
            or finding["id"] != finding_id(work["id"], content)):
        raise InvestigationError(409, "authored finding content identity mismatch")
    return context


def artifacts(work: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Canonical collection membership is part of a result's provenance."""
    found: dict[str, dict[str, Any]] = {}
    for item in (work.get("artifact"), work.get("nativeArtifact"), *work.get("artifactHistory", [])):
        if item is None:
            continue
        if not isinstance(item, dict) or not isinstance(item.get("id"), str) or item.get("kind") == FINDING_KIND:
            raise InvestigationError(409, "invalid native artifact collection membership")
        if item["id"] in found and item != found[item["id"]]:
            raise InvestigationError(409, "ambiguous artifact identity")
        found[item["id"]] = item
    findings = work.get("findings", [])
    if not isinstance(findings, list):
        raise InvestigationError(409, "invalid authored finding collection")
    for item in findings:
        validate_finding(work, item)
        if item["id"] in found:
            raise InvestigationError(409, "ambiguous artifact collection membership")
        found[item["id"]] = item
    return list(found.values())


def resolve_artifact(work: Mapping[str, Any], artifact_id: str, *, expected_context: str | None = None
                     ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any] | None]:
    artifact = next((a for a in artifacts(work) if a["id"] == artifact_id), None)
    if artifact is None:
        raise InvestigationError(404, "exact artifact does not belong to the selected investigation")
    context = _context(work, artifact.get("contextId"))
    if expected_context is not None and context["id"] != expected_context:
        raise InvestigationError(409, "artifact does not belong to this exact context")
    if artifact.get("kind") == FINDING_KIND:
        return artifact, context, None
    attempts = [a for a in (work.get("attempt"), *work.get("attemptHistory", []))
                if a and a["id"] == artifact.get("attemptId")]
    if (not attempts or attempts[0]["contextId"] != context["id"]
            or any(a != attempts[0] for a in attempts[1:])):
        raise InvestigationError(409, "artifact/context/attempt provenance mismatch")
    return artifact, context, attempts[0]
