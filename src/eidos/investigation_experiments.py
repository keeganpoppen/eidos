"""Owner-scoped context comparisons over canonical investigations.

This adapter exposes a bounded part of ExperimentStore. It measures frozen
selection changes; it neither grades model answers nor dispatches native work.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from .investigation import InvestigationError, InvestigationStore, MAX_PROMPT_BYTES, MAX_RECORDS, _body, _text
from .investigation_alternatives import ExperimentStore


class InvestigationExperiments:
    def __init__(self, investigations: InvestigationStore) -> None:
        self.investigations = investigations
        self.ledger = ExperimentStore(investigations)

    @staticmethod
    def _name(identifier: str, request_id: str) -> str:
        digest = hashlib.sha256(json.dumps([identifier, request_id]).encode()).hexdigest()
        return "comparison_" + digest

    def _owned(self, identifier: str, experiment_id: str):
        self.investigations.get(identifier)
        try:
            record = self.ledger.get(experiment_id)
        except KeyError:
            raise InvestigationError(404, "context comparison not found") from None
        if record.kind != "workbench" or record.data.get("investigationId") != identifier:
            raise InvestigationError(404, "context comparison not found in this investigation")
        return record

    def get(self, identifier: str, experiment_id: str) -> dict[str, Any]:
        record = self._owned(identifier, experiment_id)
        value = dict(record.data["view"])
        value.update(review=None, adoption=None, rollback=None, status="evaluated")
        reviews = self.ledger.list(kind="review", parent=value["proposalId"])
        if reviews:
            review = reviews[0]
            value["review"] = {"id": review.name, "decision": review.data["decision"],
                               "rationale": review.data["rationale"], "actor": review.data["actor"],
                               "kind": review.data["reviewKind"]}
            value["status"] = "rejected" if review.data["decision"] == "reject" else "adopted"
            adoptions = self.ledger.list(kind="adoption", parent=review.name)
            if adoptions:
                adoption = adoptions[0]
                value["adoption"] = {"id": adoption.name, "activation": "not-performed"}
                rollbacks = self.ledger.list(kind="rollback", parent=adoption.name)
                if rollbacks:
                    rollback = rollbacks[0]
                    value["rollback"] = {"id": rollback.name, "rationale": rollback.data["rationale"]}
                    value["status"] = "rolled-back"
        return value

    def list(self, identifier: str) -> dict[str, Any]:
        self.investigations.get(identifier)
        return {"experiments": [self.get(identifier, record.name)
                for record in self.ledger.list(kind="workbench")
                if record.data["investigationId"] == identifier]}

    def create(self, identifier: str, body: Mapping[str, Any]) -> dict[str, Any]:
        body = dict(_body(body, {"requestId", "baselineContextId", "baselineArtifactId",
                                 "alternativeContextId", "rationale"}))
        for key in ("requestId", "baselineContextId", "baselineArtifactId", "alternativeContextId"):
            _text(body.get(key), key, 200)
        _text(body.get("rationale"), "rationale", 4000)
        name = self._name(identifier, body["requestId"])
        with self.ledger.objects._transaction():
            try:
                prior = self.ledger.get(name)
            except KeyError:
                prior = None
            if prior is not None:
                if prior.kind != "workbench" or prior.data["request"] != body:
                    raise InvestigationError(409, "comparison request identity already has different content")
                return self.get(identifier, name)
            before_id, after_id = body["baselineContextId"], body["alternativeContextId"]
            if before_id == after_id:
                raise InvestigationError(400, "select two distinct frozen context versions")
            try:
                baseline = self.ledger.snapshot_baseline(identifier, before_id, body["baselineArtifactId"])
                alternative = self.ledger.snapshot_context(identifier, after_id)
            except ValueError as exc:
                raise InvestigationError(409, str(exc)) from exc
            base = self.ledger.objects.get(baseline)
            before = self.ledger.objects.get(base.ref("context")).data["context"]
            after = self.ledger.objects.get(alternative).data["context"]
            if before["question"] != after["question"]:
                raise InvestigationError(409, "controlled comparison requires the same question")
            seqs = sorted({r["seq"] for c in (before, after) for r in c["records"]})
            artifact_inputs = [a for c in (before, after) for a in c.get("artifactInputs", [])]
            method = "context-selection-comparison/v2" if artifact_inputs else "context-selection-comparison/v1"
            # Descriptive evidence remains recorded, even when a fixture made it.
            # Client input cannot select the synthetic entailment evaluator.
            horizon = self.ledger.freeze_horizon(seqs, artifact_inputs=artifact_inputs, evidence_class="recorded",
                rationale="Exact union of the two selected frozen packets; no ambient retrieval.")
            versions = [self.ledger.version("context-selection", c["id"], {
                "contextId": c["id"], "manifestId": c["manifestId"],
                "meaning": "Proposed selection for this investigation; no global policy activation.",
            }) for c in (before, after)]
            proposal = self.ledger.propose(name + "/proposal", before_version=versions[0], after_version=versions[1],
                criteria={"version": method, "cases": {
                    "selected-pair": {"question": before["question"],
                                      "meaning": "Measure retention and size; do not evaluate answer quality."}}},
                rationale=body["rationale"])
            experiment = self.ledger.experiment(name + "/experiment", proposal=proposal.name,
                baseline=baseline, alternative_context=alternative, horizon=horizon, case_id="selected-pair",
                assumptions=["Pure reinterpretation of saved packets; no native/model execution.",
                             "The larger context is a candidate, not an established improvement."])
            outcomes = []
            for variant, context in (("baseline", before), ("alternative", after)):
                attempt, _ = self.ledger.prepare_attempt(name + "/" + variant, experiment=experiment.name, variant=variant)
                outcomes.append(self.ledger.finish_attempt(name + "/" + variant + "/outcome", attempt=attempt.name,
                    answer="Local selection measurement; no model answer generated.", claims=[]))
            def metrics(context):
                value = {"recordIds": sorted(r["seq"] for r in context["records"]),
                        "recordCount": len(context["records"]),
                        "promptBytes": len(context["projectedPrompt"].encode("utf-8"))}
                if artifact_inputs:
                    value.update(artifactIds=sorted(a["artifactId"] for a in context.get("artifactInputs", [])),
                                 artifactCount=len(context.get("artifactInputs", [])))
                return value
            left, right = metrics(before), metrics(after)
            removed = sorted(set(left["recordIds"]) - set(right["recordIds"]))
            checks = {"sameQuestion": True, "baselineEvidenceRetained": not removed,
                      "withinContextBound": right["recordCount"] <= MAX_RECORDS and right["promptBytes"] <= MAX_PROMPT_BYTES}
            artifact_changes = {}
            if artifact_inputs:
                removed_artifacts = sorted(set(left["artifactIds"]) - set(right["artifactIds"]))
                def frozen_inputs(context):
                    return {a["artifactId"]: {k: v for k, v in a.items() if k != "rationale"}
                            for a in context.get("artifactInputs", [])}
                left_inputs, right_inputs = frozen_inputs(before), frozen_inputs(after)
                changed_artifacts = sorted(key for key in left_inputs.keys() & right_inputs.keys()
                                           if left_inputs[key] != right_inputs[key])
                # Same artifact name does not imply the same frozen input: a
                # later adoption/rejection is separately attributable content.
                checks["baselineArtifactsRetained"] = not (removed_artifacts or changed_artifacts)
                artifact_changes = {
                    "addedArtifactIds": sorted(set(right["artifactIds"]) - set(left["artifactIds"])),
                    "removedArtifactIds": removed_artifacts,
                    "changedArtifactIds": changed_artifacts,
                }
            evaluation = {"id": name + "/evaluation", "method": method,
                **artifact_changes,
                "baseline": left, "alternative": right,
                "addedRecordIds": sorted(set(right["recordIds"]) - set(left["recordIds"])),
                "removedRecordIds": removed, "additionalPromptBytes": right["promptBytes"] - left["promptBytes"],
                "checks": checks, "passes": all(checks.values()), "modelCalls": 0,
                "measuredModelReasoningImprovement": False,
                "limitations": ["Measures selected evidence and prompt bytes only; answer quality and entailment are ungraded.",
                    "Follow-up packets may also change instructions, prior-output quotations and response notes; this is not an isolated causal test.",
                    "No held-out generalization, token cost, provider context or native continuation is established.",
                    "Review records a bounded context-selection decision; it does not activate a global policy or send work."]}
            self.ledger._record(evaluation["id"], "evaluation", {
                **evaluation, "caseId": "selected-pair", "evidence_class": "recorded",
            }, {"baselineOutcome": outcomes[0].cid, "alternativeOutcome": outcomes[1].cid,
                "criteria": experiment.content.ref("criteria"), "horizon": horizon},
                experiment=experiment.name, parent=experiment.name)
            artifact = self.ledger.objects.get(base.ref("artifact")).data
            evidence_class = artifact.get("executionEvidence", "unverified")
            if evidence_class == "native-observed":
                evidence_class = "recorded"
            view = {"id": name, "investigationId": identifier, "proposalId": proposal.name,
                "mode": "reinterpretation", "evidenceClass": evidence_class,
                "baseline": {k: base.data[k] for k in ("investigationId", "contextId", "artifactId", "attemptId")},
                "alternative": {"investigationId": identifier, "contextId": after_id},
                "rationale": body["rationale"], "evaluation": evaluation}
            self.ledger._record(name, "workbench", {"investigationId": identifier, "request": body, "view": view},
                {"baseline": baseline, "alternativeContext": alternative}, parent=experiment.name)
            return self.get(identifier, name)

    def decide(self, identifier: str, experiment_id: str, action: str, body: Mapping[str, Any]) -> dict[str, Any]:
        fields = {"requestId", "rationale", "decision"} if action == "review" else {"requestId", "rationale"}
        body = dict(_body(body, fields))
        request_id = _text(body.get("requestId"), "requestId", 200)
        rationale = _text(body.get("rationale"), "rationale", 4000)
        with self.ledger.objects._transaction():
            value = self.get(identifier, experiment_id)
            name = self._name(identifier, request_id) + "/" + action
            try:
                if action == "review":
                    decision = body.get("decision")
                    if decision not in {"adopt", "reject"}:
                        raise InvestigationError(400, "decision must be adopt or reject")
                    review = self.ledger.review(name, proposal=value["proposalId"],
                        evaluations=[value["evaluation"]["id"]], decision=decision,
                        actor="local-owner", rationale=rationale, review_kind="human")
                    if decision == "adopt":
                        self.ledger.adopt(name + "/adoption", review=review.name)
                elif action == "rollback":
                    if value["adoption"] is None:
                        raise InvestigationError(409, "only an adopted comparison can be rolled back")
                    self.ledger.rollback(name, adoption=value["adoption"]["id"], actor="local-owner", rationale=rationale)
                else:
                    raise InvestigationError(404, "unknown comparison action")
            except ValueError as exc:
                if isinstance(exc, InvestigationError):
                    raise
                raise InvestigationError(409, str(exc)) from exc
            return self.get(identifier, experiment_id)
