"""Immutable, reference-only arrangements over the local evidence world.

A saved composition is a description, not an execution or disclosure grant.
Source relationships are checked when saving; later missing sources never rewrite
its content. Browser opening/resolution is separate from this persistence adapter.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
import time
from typing import Any, Mapping
import uuid

from .context_manifest import ContextManifestStore
from .investigation import InvestigationError, InvestigationStore, _body, _json, _text
from .investigation_experiments import InvestigationExperiments

KIND = "workbench.composition.v1"
MAX_BODY_BYTES = 16384


def _shape(value: Any, allowed: set[str], required: set[str]) -> dict[str, Any]:
    body = dict(_body(value, allowed))
    if required - body.keys():
        raise InvestigationError(400, "missing composition fields: " + ", ".join(sorted(required - body.keys())))
    return body


def _target(value: Any, *, focus: bool = False) -> dict[str, Any]:
    fields = {"investigationId", "contextId", "artifactId"}
    if focus:
        fields |= {"blockId", "seq", "threadId"}
    target = _shape(value, fields, {"investigationId", "contextId"})
    for key in fields - {"seq"}:
        if key in target:
            _text(target[key], key, 200)
    if focus:
        if ("seq" in target) != ("threadId" in target):
            raise InvestigationError(400, "focus seq and threadId must occur together")
        if "seq" in target and (type(target["seq"]) is not int or not 1 <= target["seq"] <= 2**53 - 1):
            raise InvestigationError(400, "focus seq must be a positive safe integer")
        if "blockId" in target and ("artifactId" not in target or not re.fullmatch(r"block-(0|[1-9][0-9]{0,15})", target["blockId"])):
            raise InvestigationError(400, "block focus requires an artifact and an offset selector")
    return target


def _artifacts(work: Mapping[str, Any]) -> list[dict[str, Any]]:
    found = {}
    for item in (work.get("artifact"), work.get("nativeArtifact"), *work.get("artifactHistory", [])):
        if item and item["id"] not in found:
            found[item["id"]] = item
    return list(found.values())


class Compositions:
    def __init__(self, investigations: InvestigationStore) -> None:
        self.investigations = investigations
        self.trace = investigations.trace
        self.objects = ContextManifestStore(self.trace)
        self.experiments = InvestigationExperiments(investigations)
        with self.objects._transaction():
            self.trace.db.execute("""CREATE TABLE IF NOT EXISTS workbench_compositions(
                id TEXT PRIMARY KEY, cid TEXT NOT NULL REFERENCES cm_objects(cid),
                request_id TEXT UNIQUE NOT NULL, fingerprint TEXT NOT NULL,
                created_at_ms INTEGER NOT NULL, title TEXT NOT NULL, search_title TEXT NOT NULL,
                renderer_version TEXT NOT NULL, copied_from TEXT REFERENCES workbench_compositions(id))""")
            self.trace.db.execute("CREATE INDEX IF NOT EXISTS workbench_composition_order ON workbench_compositions(created_at_ms DESC,id)")

    def get(self, identifier: str) -> dict[str, Any]:
        with self.trace._lock:
            row = self.trace.db.execute("SELECT cid FROM workbench_compositions WHERE id=?", (identifier,)).fetchone()
            if row is None:
                raise InvestigationError(404, "saved arrangement not found")
            value = self.objects.get(row["cid"])
            if value.kind != KIND or value.data["id"] != identifier:
                raise InvestigationError(409, "saved arrangement content identity mismatch")
            return {**value.data, "contentId": value.cid}

    @staticmethod
    def _params(query: Mapping[str, list[str]]) -> dict[str, str]:
        if set(query) - {"limit", "q", "cursor"} or any(not isinstance(v, list) or len(v) != 1 or not isinstance(v[0], str) for v in query.values()):
            raise InvestigationError(400, "unexpected or repeated composition query parameter")
        return {k: v[0] for k, v in query.items()}

    def list(self, query: Mapping[str, list[str]]) -> dict[str, Any]:
        params = self._params(query)
        try:
            limit = int(params.get("limit", "20"))
        except ValueError:
            raise InvestigationError(400, "composition limit must be between 1 and 40") from None
        if not 1 <= limit <= 40:
            raise InvestigationError(400, "composition limit must be between 1 and 40")
        term = _text(params.get("q", ""), "q", 200, empty=True).strip().casefold()
        clauses, arguments = ["instr(search_title,?) > 0"], [term]
        if "cursor" in params:
            cursor = _text(params["cursor"], "cursor", 2048)
            try:
                value = json.loads(base64.b64decode(cursor + "=" * (-len(cursor) % 4), altchars=b"-_", validate=True))
                if (set(value) != {"v", "kind", "query", "after"} or type(value["v"]) is not int or value["v"] != 1
                        or value["kind"] != "compositions" or value["query"] != term
                        or not isinstance(value["after"], list) or len(value["after"]) != 2
                        or type(value["after"][0]) is not int or not 0 <= value["after"][0] <= 2**63 - 1
                        or not isinstance(value["after"][1], str) or not 1 <= len(value["after"][1]) <= 200):
                    raise ValueError
                created, identifier = value["after"]
            except (KeyError, TypeError, ValueError, UnicodeError):
                raise InvestigationError(400, "cursor does not match this composition query") from None
            clauses.append("(created_at_ms < ? OR (created_at_ms = ? AND id > ?))")
            arguments.extend([created, created, identifier])
        with self.trace._lock:
            rows = self.trace.db.execute(
                "SELECT id,title,created_at_ms,renderer_version,copied_from FROM workbench_compositions WHERE "
                + " AND ".join(clauses) + " ORDER BY created_at_ms DESC,id LIMIT ?", (*arguments, limit + 1),
            ).fetchall()
        items = [{"id": row["id"], "title": row["title"], "createdAtMs": row["created_at_ms"],
                  "rendererVersion": row["renderer_version"], "copiedFrom": row["copied_from"]} for row in rows[:limit]]
        cursor = None
        if len(rows) > limit:
            last = rows[limit - 1]
            cursor = base64.urlsafe_b64encode(_json({"v": 1, "kind": "compositions", "query": term,
                "after": [last["created_at_ms"], last["id"]]}).encode()).decode().rstrip("=")
        return {"compositions": items, "nextCursor": cursor}

    def _resolve(self, target: Mapping[str, Any], owners: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any] | None]:
        identifier = target["investigationId"]
        if identifier not in owners:
            owners[identifier] = self.investigations._load(identifier)
        work = owners[identifier]
        inquiry = (work.get("continuation") or {}).get("inquiry") or {}
        contexts = [*work["contexts"], *(r["evidenceContext"] for r in inquiry.get("responses", [])
                    if r.get("decision") == "offer" and r.get("evidenceContext"))]
        context = next((c for c in contexts if c["id"] == target["contextId"]), None)
        if context is None:
            raise InvestigationError(409, "saved context does not belong to this investigation")
        artifact = None
        if "artifactId" in target:
            artifact = next((a for a in _artifacts(work) if a["id"] == target["artifactId"] and a["contextId"] == context["id"]), None)
            if artifact is None:
                raise InvestigationError(409, "saved artifact does not belong to this exact context")
        if "seq" in target:
            if not any(r["seq"] == target["seq"] and r["threadId"] == target["threadId"] for r in context["records"]):
                raise InvestigationError(409, "focused record does not belong to this exact context and thread")
            if artifact is not None and target["seq"] not in artifact.get("citations", []):
                raise InvestigationError(409, "focused record is not cited by this artifact")
        return work, context, artifact

    @staticmethod
    def _inquiry(arrangement: dict[str, Any], left: tuple, right: tuple) -> None:
        binding = arrangement["inquiry"]
        work, context, original = left
        continuation = work.get("continuation") or {}
        inquiry = continuation.get("inquiry") or {}
        attempts = [a for a in (work.get("attempt"), *work.get("attemptHistory", [])) if a]
        attempt = next((a for a in attempts if a["id"] == continuation.get("attemptId")), None)
        if (continuation.get("id") != binding["continuationId"] or inquiry.get("id") != binding["inquiryId"]
                or attempt is None):
            raise InvestigationError(409, "inquiry does not belong to the original attempt")
        response = next((r for r in inquiry.get("responses", []) if r["id"] == binding.get("responseId")), None)
        if "responseId" in binding and response is None:
            raise InvestigationError(409, "response does not belong to this inquiry")
        offered = (response or {}).get("evidenceContext")
        if (binding.get("evidenceContextId") != (offered or {}).get("id")
                or offered and response["decision"] != "offer"):
            raise InvestigationError(409, "offered context does not match the exact inquiry response")
        if context["id"] != attempt["contextId"] and context["id"] != (offered or {}).get("id"):
            raise InvestigationError(409, "context is outside this exact inquiry binding")
        if arrangement.get("intent") != "evidence-chain":
            return
        right_work, _, result = right
        expected_original = work.get("nativeArtifact") or work.get("artifact")
        if (arrangement["lens"] != "result" or not original or not expected_original
                or original["id"] != expected_original["id"] or right_work["id"] != work["id"]):
            raise InvestigationError(409, "evidence chain must retain its exact original result and owner")
        if result is None:
            return
        if response is None or response["decision"] == "defer":
            raise InvestigationError(409, "an inquiry result requires an exact terminal response")
        if result.get("kind") == "eidos-evidence-review":
            if (result.get("nativeArtifactId") != original["id"] or result.get("continuationId") != continuation["id"]
                    or result.get("inquiryId") != inquiry["id"] or result.get("responseId") != response["id"]
                    or result.get("decisionOccurrenceId") != response.get("occurrenceId") or result.get("attemptId") != attempt["id"]
                    or result["contextId"] != context["id"] or result.get("evidenceContextId") != binding.get("evidenceContextId")):
                raise InvestigationError(409, "result is not the receipt for this inquiry")
        else:
            lineage = result.get("continuedFrom") or {}
            actual_attempt = next((a for a in attempts if a["id"] == result["attemptId"]), None)
            expected = {"investigationId": work["id"], "continuationId": continuation["id"], "inquiryId": inquiry["id"],
                        "responseId": response["id"], "nativeArtifactId": original["id"], "attemptId": attempt["id"]}
            if (any(lineage.get(k) != v for k, v in expected.items())
                    or lineage.get("evidenceContextId") != binding.get("evidenceContextId") or actual_attempt is None
                    or actual_attempt["contextId"] != result["contextId"]
                    or (actual_attempt.get("continuedFrom") or {}).get("responseId") != response["id"]):
                raise InvestigationError(409, "result is not the separately admitted follow-up for this inquiry")

    def create(self, value: Any) -> dict[str, Any]:
        body = _shape(value, {"requestId", "title", "rendererVersion", "arrangement", "focus", "copiedFrom"},
                      {"requestId", "title", "rendererVersion", "arrangement", "focus"})
        encoded = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
        if len(encoded) > MAX_BODY_BYTES:
            raise InvestigationError(400, "saved arrangement exceeds 16 KiB")
        for key, limit in (("requestId", 200), ("title", 160), ("rendererVersion", 120)):
            _text(body[key], key, limit)
        if body.get("copiedFrom") is not None:
            _text(body["copiedFrom"], "copiedFrom", 200)
        arrangement = _shape(body["arrangement"], {"left", "right", "lens", "layout", "intent", "inquiry", "experimentId"},
                             {"left", "right", "lens", "layout"})
        arrangement["left"], arrangement["right"] = _target(arrangement["left"]), _target(arrangement["right"])
        if arrangement["lens"] not in ("result", "context") or arrangement["layout"] not in ("beside", "stacked"):
            raise InvestigationError(400, "unsupported saved arrangement lens or layout")
        if "intent" in arrangement and arrangement["intent"] not in ("evidence-chain", "alternative-review"):
            raise InvestigationError(400, "unsupported saved arrangement intent")
        if "experimentId" in arrangement:
            _text(arrangement["experimentId"], "experimentId", 200)
        if "inquiry" in arrangement:
            binding = _shape(arrangement["inquiry"], {"continuationId", "inquiryId", "responseId", "evidenceContextId"}, {"continuationId", "inquiryId"})
            for key, val in binding.items():
                _text(val, key, 200)
            if "evidenceContextId" in binding and "responseId" not in binding:
                raise InvestigationError(400, "offered context needs its response reference")
            arrangement["inquiry"] = binding
        if arrangement.get("intent") == "evidence-chain" and "inquiry" not in arrangement:
            raise InvestigationError(400, "evidence chain requires exact inquiry references")
        if arrangement.get("intent") == "alternative-review" and "experimentId" not in arrangement:
            raise InvestigationError(400, "alternative review requires an experiment reference")
        focus = None if body["focus"] is None else _target(body["focus"], focus=True)
        fingerprint = hashlib.sha256(encoded).hexdigest()
        with self.objects._transaction():
            prior = self.trace.db.execute("SELECT id,fingerprint FROM workbench_compositions WHERE request_id=?", (body["requestId"],)).fetchone()
            if prior:
                if prior["fingerprint"] != fingerprint:
                    raise InvestigationError(409, "requestId already has a different saved arrangement")
                return self.get(prior["id"])
            owners: dict[str, Any] = {}
            left, right = (self._resolve(arrangement[side], owners) for side in ("left", "right"))
            if focus is not None:
                self._resolve(focus, owners)
            if "inquiry" in arrangement:
                self._inquiry(arrangement, left, right)
            if "experimentId" in arrangement:
                experiment = self.experiments.get(left[0]["id"], arrangement["experimentId"])
                for side, target in (("left", "baseline"), ("right", "alternative")):
                    expected = {k: experiment[target][k] for k in ("investigationId", "contextId", "artifactId") if k in experiment[target]}
                    if arrangement[side] != expected:
                        raise InvestigationError(409, "arrangement does not match the named experiment's exact targets")
            refs = {}
            if body.get("copiedFrom"):
                refs["copiedFrom"] = self.get(body["copiedFrom"])["contentId"]
            identifier = "composition_" + uuid.uuid4().hex
            created = int(time.time() * 1000)
            saved = {"schemaVersion": 1, "id": identifier, "title": body["title"], "createdAtMs": created,
                     "rendererVersion": body["rendererVersion"], "arrangement": arrangement, "focus": focus,
                     "copiedFrom": body.get("copiedFrom")}
            cid = self.objects.put_content(KIND, saved, refs)
            self.trace.db.execute("INSERT INTO workbench_compositions VALUES (?,?,?,?,?,?,?,?,?)", (
                identifier, cid, body["requestId"], fingerprint, created, body["title"], body["title"].casefold(),
                body["rendererVersion"], body.get("copiedFrom")))
            return self.get(identifier)
