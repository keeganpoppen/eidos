"""Immutable, reference-based counterfactual experiments over saved investigations.

This trusted-host ledger records descriptions, never execution authority. It has
no dispatcher, host callbacks, filesystem replay, or mutable current investigation.
Native branch execution deliberately remains behind the integrator's admission seam.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Any, Mapping, Sequence

from .context_manifest import ContextManifestStore, ContextObject
from .investigation import InvestigationStore


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be nonempty text")
    return value


def _strings(values: Sequence[str], label: str) -> list[str]:
    if isinstance(values, (str, bytes)):
        raise ValueError(f"{label} must be a sequence")
    return [_text(value, label) for value in values]


@dataclass(frozen=True)
class ExperimentRecord:
    name: str
    kind: str
    content: ContextObject
    experiment: str | None
    parent: str | None

    @property
    def cid(self) -> str:
        return self.content.cid

    @property
    def data(self) -> dict[str, Any]:
        return self.content.data


class ExperimentStore:
    """Append-only local occurrences sharing existing immutable CM objects.

    Equal contents can have different occurrence names. Caller-chosen names are
    idempotency keys, not credentials. Each public write joins a caller transaction
    using the existing manifest store's savepoint semantics.
    """

    def __init__(self, investigations: InvestigationStore) -> None:
        self.investigations = investigations
        self.trace = investigations.trace
        self.objects = ContextManifestStore(self.trace)
        with self.objects._transaction():
            self.trace.db.execute("""CREATE TABLE IF NOT EXISTS exp_records(
                ordinal INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL, kind TEXT NOT NULL,
                cid TEXT NOT NULL REFERENCES cm_objects(cid),
                experiment_name TEXT REFERENCES exp_records(name),
                parent_name TEXT REFERENCES exp_records(name),
                exclusive_key TEXT UNIQUE)""")
            self.trace.db.execute("CREATE INDEX IF NOT EXISTS exp_records_parent ON exp_records(parent_name)")
            self.trace.db.execute("CREATE INDEX IF NOT EXISTS exp_records_experiment ON exp_records(experiment_name)")

    def _content(self, cid: str, kind: str) -> ContextObject:
        obj = self.objects.get(cid)
        if obj.kind != "experiment." + kind + ".v1":
            raise ValueError(f"expected {kind} content")
        return obj

    def _put(self, kind: str, data: Any, refs: Mapping[str, str] | None = None) -> str:
        return self.objects.put_content("experiment." + kind + ".v1", data, refs)

    def get(self, name: str) -> ExperimentRecord:
        with self.trace._lock:
            row = self.trace.db.execute("SELECT * FROM exp_records WHERE name=?", (name,)).fetchone()
            if row is None:
                raise KeyError(name)
            return ExperimentRecord(row["name"], row["kind"], self._content(row["cid"], row["kind"]),
                                    row["experiment_name"], row["parent_name"])

    def list(self, *, kind: str | None = None, parent: str | None = None,
             experiment: str | None = None) -> tuple[ExperimentRecord, ...]:
        with self.trace._lock:
            rows = self.trace.db.execute(
                "SELECT name FROM exp_records WHERE (? IS NULL OR kind=?) "
                "AND (? IS NULL OR parent_name=?) AND (? IS NULL OR experiment_name=?) ORDER BY ordinal",
                (kind, kind, parent, parent, experiment, experiment),
            ).fetchall()
            return tuple(self.get(row["name"]) for row in rows)

    def _record(self, name: str, kind: str, data: Any, refs: Mapping[str, str], *,
                experiment: str | None = None, parent: str | None = None,
                exclusive: str | None = None) -> tuple[ExperimentRecord, bool]:
        _text(name, "occurrence name")
        for other in (experiment, parent):
            if other is not None:
                self.get(other)
        cid = self._put(kind, data, refs)
        row = self.trace.db.execute("SELECT * FROM exp_records WHERE name=?", (name,)).fetchone()
        if row is not None:
            expected = (kind, cid, experiment, parent, exclusive)
            actual = tuple(row[key] for key in ("kind", "cid", "experiment_name", "parent_name", "exclusive_key"))
            if actual != expected:
                raise ValueError("occurrence name already has different content or lineage")
            return self.get(name), False
        if exclusive is not None and self.trace.db.execute(
            "SELECT 1 FROM exp_records WHERE exclusive_key=?", (exclusive,),
        ).fetchone():
            raise ValueError("a terminal decision already exists for this occurrence")
        self.trace.db.execute(
            "INSERT INTO exp_records(name,kind,cid,experiment_name,parent_name,exclusive_key) VALUES (?,?,?,?,?,?)",
            (name, kind, cid, experiment, parent, exclusive),
        )
        return self.get(name), True

    def _named(self, name: str, kind: str) -> ExperimentRecord:
        record = self.get(name)
        if record.kind != kind:
            raise ValueError(f"expected {kind} occurrence")
        return record

    def freeze_horizon(self, seqs: Sequence[int], *, evidence_class: str = "synthetic",
                       rationale: str, artifact_inputs: Sequence[Mapping[str, Any]] = ()) -> str:
        """Freeze an explicit local availability set, not a universal historical clock."""
        if evidence_class not in {"synthetic", "recorded"}:
            raise ValueError("evidence class must be synthetic or recorded")
        if (not seqs and not artifact_inputs) or any(type(seq) is not int or seq < 1 for seq in seqs):
            raise ValueError("horizon requires positive trace sequence IDs")
        if len(set(seqs)) != len(seqs):
            raise ValueError("duplicate horizon records")
        with self.objects._transaction():
            refs = {f"record/{seq}": self.objects.freeze_trace(seq) for seq in sorted(seqs)}
            ceiling = self.trace.db.execute("SELECT MAX(seq) FROM trace_records").fetchone()[0]
            data = {
                "recordIds": sorted(seqs), "localCeiling": ceiling,
                "evidenceClass": evidence_class, "rationale": _text(rationale, "horizon rationale"),
                "meaning": "Explicit locally available records; not proof of an actor's complete knowledge.",
            }
            if artifact_inputs:
                ids = {self._put("artifact-input", {k: v for k, v in artifact.items() if k != "rationale"})
                       for artifact in artifact_inputs}
                refs.update({"artifact/" + cid: cid for cid in ids})
                data["artifactInputIds"] = sorted(ids)
                data["meaning"] = "Explicit frozen records and derived artifacts; no implicit underlying evidence or authority."
            return self._put("horizon", data, refs)

    def snapshot_context(self, investigation_id: str, context_id: str) -> str:
        with self.objects._transaction():
            investigation = self.investigations.get(investigation_id)
            context = next((c for c in investigation["contexts"] if c["id"] == context_id), None)
            if context is None:
                raise ValueError("context is not owned by this investigation")
            if not context.get("manifestId"):
                raise ValueError("context has no captured manifest; derive it through the canonical adapter first")
            manifest = self.objects.get(context["manifestId"])
            if manifest.kind != "cm.manifest":
                raise ValueError("invalid canonical context manifest")
            return self._put("context", {"investigationId": investigation_id, "context": context},
                             {"manifest": manifest.cid})

    def snapshot_baseline(self, investigation_id: str, context_id: str, artifact_id: str) -> str:
        with self.objects._transaction():
            investigation = self.investigations.get(investigation_id)
            artifact = next((a for a in (investigation.get("artifact"), investigation.get("nativeArtifact"),
                                        *investigation.get("artifactHistory", []))
                             if a and a["id"] == artifact_id), None)
            if artifact is None:
                raise ValueError("exact artifact is not owned by this investigation")
            attempt = next((a for a in (investigation.get("attempt"), *investigation.get("attemptHistory", []))
                            if a and a["id"] == artifact.get("attemptId")), None)
            if (not attempt or artifact.get("contextId") != context_id
                    or artifact.get("attemptId") != attempt["id"] or attempt["contextId"] != context_id):
                raise ValueError("artifact/context/attempt provenance mismatch")
            context = self.snapshot_context(investigation_id, context_id)
            artifact_refs = {f"output/{seq}": self.objects.freeze_trace(seq) for seq in artifact["outputSeqs"]}
            frozen_artifact = self._put("artifact", artifact, artifact_refs)
            refs = {"context": context, "artifact": frozen_artifact}
            if attempt.get("manifestId"):
                refs["attemptManifest"] = attempt["manifestId"]
            if attempt.get("contextRequestName"):
                refs["requestPin"] = self.objects.get_request(attempt["contextRequestName"]).cid
            return self._put("baseline", {
                "investigationId": investigation_id, "contextId": context_id,
                "artifactId": artifact_id, "attemptId": attempt["id"],
                "authority": "descriptive reference only; no inherited capability",
            }, refs)

    def version(self, component: str, version: str, definition: Any) -> str:
        with self.objects._transaction():
            return self._put("version", {"component": _text(component, "component"),
                                        "version": _text(version, "version"), "definition": definition})

    def propose(self, name: str, *, before_version: str, after_version: str,
                criteria: Mapping[str, Any], rationale: str) -> ExperimentRecord:
        with self.objects._transaction():
            before = self._content(before_version, "version")
            after = self._content(after_version, "version")
            if before.data["component"] != after.data["component"] or before_version == after_version:
                raise ValueError("proposal must change one bounded component")
            if before.data["version"] == after.data["version"]:
                raise ValueError("changed component requires an explicit new version")
            if not isinstance(criteria.get("cases"), dict) or not criteria["cases"]:
                raise ValueError("proposal requires a fixed nonempty case set")
            _text(criteria.get("version"), "criteria version")
            for case_id, case in criteria["cases"].items():
                _text(case_id, "case ID")
                if not isinstance(case, dict):
                    raise ValueError("case criteria must be an object")
            test_set = self._put("criteria", dict(criteria))
            return self._record(name, "proposal", {"rationale": _text(rationale, "proposal rationale")},
                                {"before": before_version, "after": after_version, "criteria": test_set})[0]

    def _context_within(self, cid: str, horizon: ContextObject) -> dict[str, Any]:
        context = self._content(cid, "context").data["context"]
        allowed = set(horizon.data["recordIds"])
        for record in context["records"]:
            if record["seq"] not in allowed:
                raise ValueError("context contains evidence outside the frozen horizon")
            frozen = self.objects.get(horizon.ref(f"record/{record['seq']}"))
            if (frozen.data["raw_text"] != record["rawText"] or frozen.data["sha256"] != record["sha256"]
                    or hashlib.sha256(record["rawText"].encode()).hexdigest() != record["sha256"]):
                raise ValueError("context evidence differs from the frozen horizon")
        allowed_artifacts = [self._content(horizon.ref("artifact/" + cid), "artifact-input").data
                             for cid in horizon.data.get("artifactInputIds", [])]
        for artifact in context.get("artifactInputs", []):
            if {k: v for k, v in artifact.items() if k != "rationale"} not in allowed_artifacts:
                raise ValueError("context artifact differs from or is outside the frozen horizon")
        return context

    def experiment(self, name: str, *, proposal: str, baseline: str, alternative_context: str,
                   horizon: str, case_id: str, mode: str = "reinterpretation",
                   assumptions: Sequence[str] = (), mock_effects: Mapping[str, Any] | None = None,
                   versions: Mapping[str, Mapping[str, str]] | None = None) -> ExperimentRecord:
        """Describe a comparison. All supplied versions are content refs, never paths.

        `versions` may name model/lens/instructions with explicit before/after refs.
        Context manifests already preserve known ingredients and capture gaps.
        """
        if mode not in {"reinterpretation", "simulation", "native_branch"}:
            raise ValueError("unknown counterfactual mode")
        if mode == "simulation" and not mock_effects:
            raise ValueError("simulation requires explicit mocked effects")
        if mode != "simulation" and mock_effects is not None:
            raise ValueError("mock effects belong only to simulation")
        with self.objects._transaction():
            proposed = self._named(proposal, "proposal")
            base = self._content(baseline, "baseline")
            frozen = self._content(horizon, "horizon")
            criteria = self._content(proposed.content.ref("criteria"), "criteria")
            if case_id not in criteria.data["cases"]:
                raise ValueError("case is not in the predeclared test set")
            before = self._context_within(base.ref("context"), frozen)
            after = self._context_within(alternative_context, frozen)
            question = criteria.data["cases"][case_id]["question"]
            if before["question"] != question or after["question"] != question:
                raise ValueError("controlled comparison must keep the stated question fixed")
            refs = {"proposal": proposed.cid, "baseline": baseline, "alternativeContext": alternative_context,
                    "horizon": horizon, "criteria": criteria.cid,
                    "beforeVersion": proposed.content.ref("before"), "afterVersion": proposed.content.ref("after")}
            for role, pair in (versions or {}).items():
                if role not in {"model", "lens", "instructions"} or set(pair) != {"before", "after"}:
                    raise ValueError("versions must identify model/lens/instructions before and after")
                for side, cid in pair.items():
                    self._content(cid, "version")
                    refs[f"{role}/{side}"] = cid
            data = {
                "caseId": case_id, "mode": mode, "assumptions": _strings(assumptions, "assumption"),
                "mockEffects": dict(mock_effects) if mock_effects is not None else None,
                "isolation": {"workspace": "not accessed by this subsystem", "externalEffects": "none",
                              "historicalAuthority": "never inherited", "nativeAdmission": "unsupported"},
                "interpretation": {"reinterpretation": "Later interpretation of recorded evidence; original history unchanged.",
                                   "simulation": "Mocked continuation; no claim that historical events occurred.",
                                   "native_branch": "Proposed new native work; requires separate live admission and isolation."}[mode],
                "hindsightLimit": "Checks record membership, not hidden leakage in free-text instructions or the evaluator's knowledge.",
                "versionsMeaning": "Declared immutable inputs; this ledger does not attest which implementation produced an outcome.",
                "mockEffectsMeaning": "Descriptions only; no mock runner or external-effect transcript is executed by this ledger.",
            }
            return self._record(name, "experiment", data, refs, parent=proposal)[0]

    def prepare_attempt(self, name: str, *, experiment: str, variant: str) -> tuple[ExperimentRecord, bool]:
        if variant not in {"baseline", "alternative"}:
            raise ValueError("variant must be baseline or alternative")
        with self.objects._transaction():
            exp = self._named(experiment, "experiment")
            if exp.data["mode"] == "native_branch":
                raise ValueError("native branch requires separately admitted execution; not supported by this ledger")
            base = self._content(exp.content.ref("baseline"), "baseline")
            context = base.ref("context") if variant == "baseline" else exp.content.ref("alternativeContext")
            return self._record(name, "attempt", {
                "variant": variant, "mode": exp.data["mode"], "state": "prepared",
                "authority": "none", "externalEffects": "none", "modelCalls": 0,
                "recovery": "Inspect existing outcome; pending does not authorize dispatch or replay.",
            }, {"experiment": exp.cid, "context": context}, experiment=experiment, parent=experiment)

    def finish_attempt(self, name: str, *, attempt: str, answer: str, claims: Sequence[Mapping[str, Any]],
                       assumptions: Sequence[str] = (), failures: Sequence[str] = ()) -> ExperimentRecord:
        with self.objects._transaction():
            prepared = self._named(attempt, "attempt")
            exp = self._named(prepared.experiment, "experiment")
            # No arbitrary result metadata can upgrade this local interpretation
            # into a native/model observation or transfer a historical capability.
            data = {"answer": _text(answer, "answer"), "claims": [dict(c) for c in claims],
                    "assumptions": _strings(assumptions, "assumption"), "failures": _strings(failures, "failure"),
                    "mode": exp.data["mode"], "modelCalls": 0, "externalEffects": "none",
                    "historicalWorldChanged": False}
            return self._record(name, "outcome", data, {"context": prepared.content.ref("context")},
                                experiment=prepared.experiment, parent=attempt, exclusive="outcome/" + attempt)[0]

    def _evaluation_input(self, name: str, experiment: str, variant: str) -> tuple[ExperimentRecord, dict[str, Any]]:
        outcome = self._named(name, "outcome")
        attempt = self._named(outcome.parent, "attempt")
        if outcome.experiment != experiment or attempt.experiment != experiment or attempt.data["variant"] != variant:
            raise ValueError("outcome does not belong to the experiment variant")
        context = self._content(attempt.content.ref("context"), "context").data["context"]
        return outcome, context

    def evaluate(self, name: str, *, experiment: str, baseline_outcome: str,
                 alternative_outcome: str) -> ExperimentRecord:
        from .investigation_evaluation import compare_evaluations, evaluate_outcome

        with self.objects._transaction():
            exp = self._named(experiment, "experiment")
            horizon = self._content(exp.content.ref("horizon"), "horizon")
            if horizon.data["evidenceClass"] != "synthetic":
                raise ValueError("fixture evaluator cannot establish entailment for recorded real-world evidence")
            if horizon.data.get("artifactInputIds"):
                raise ValueError("fixture evaluator does not grade derived artifact inputs")
            criteria = self._content(exp.content.ref("criteria"), "criteria").data["cases"][exp.data["caseId"]]
            evidence = [{"seq": seq, "rawText": self.objects.get(horizon.ref(f"record/{seq}")).data["raw_text"],
                         "sha256": self.objects.get(horizon.ref(f"record/{seq}")).data["sha256"]}
                        for seq in horizon.data["recordIds"]]
            baseline, before = self._evaluation_input(baseline_outcome, experiment, "baseline")
            alternative, after = self._evaluation_input(alternative_outcome, experiment, "alternative")
            reports = []
            for result, context in ((baseline, before), (alternative, after)):
                reports.append(evaluate_outcome(criteria, evidence, [r["seq"] for r in context["records"]],
                                               result.data["claims"], {"projectedPrompt": context["projectedPrompt"], "modelCalls": 0}))
            comparison = compare_evaluations(*reports)
            comparison["checks"]["noReportedExecutionFailures"] = not (
                baseline.data["failures"] or alternative.data["failures"])
            comparison["passes"] = all(comparison["checks"].values())
            if not comparison["passes"]:
                comparison["recommendation"] = "retain_counterexample"
            return self._record(name, "evaluation", {
                "caseId": exp.data["caseId"], "baseline": reports[0], "alternative": reports[1],
                "comparison": comparison, "evidence_class": "synthetic",
                "measured_model_reasoning_improvement": False,
                "evaluatedSurface": "structured_fixture_claims_only", "answerTextEvaluated": False,
                "retainedArtifactEvaluated": False,
                "limitation": "Answer prose and the original baseline artifact are not graded; consistency and usefulness require human review.",
                "outcomes": {"baseline": baseline_outcome, "alternative": alternative_outcome},
                "assumptions": {"baseline": baseline.data["assumptions"], "alternative": alternative.data["assumptions"]},
                "outcomeFailures": {"baseline": baseline.data["failures"], "alternative": alternative.data["failures"]},
            }, {"baselineOutcome": baseline.cid, "alternativeOutcome": alternative.cid,
                "criteria": exp.content.ref("criteria"), "horizon": horizon.cid},
                experiment=experiment, parent=experiment)[0]

    def review(self, name: str, *, proposal: str, evaluations: Sequence[str], decision: str,
               actor: str, rationale: str, review_kind: str = "human") -> ExperimentRecord:
        if decision not in {"adopt", "reject"} or review_kind not in {"human", "synthetic"}:
            raise ValueError("invalid decision or review kind")
        if len(set(evaluations)) != len(evaluations):
            raise ValueError("review requires distinct evaluation names")
        with self.objects._transaction():
            proposed = self._named(proposal, "proposal")
            try:
                prior = self.get(name)
            except KeyError:
                prior = None
            if prior is not None:
                requested = {"decision": decision, "actor": actor, "rationale": rationale,
                             "reviewKind": review_kind, "evaluations": list(evaluations)}
                if (prior.kind != "review" or prior.parent != proposal
                        or any(prior.data.get(key) != value for key, value in requested.items())):
                    raise ValueError("occurrence name already has different content or lineage")
                # Preserve the original review's pending/omitted snapshot even
                # when further experiments finish after that decision.
                return prior
            cases = self._content(proposed.content.ref("criteria"), "criteria").data["cases"]
            covered = set()
            refs = {"proposal": proposed.cid}
            for index, evaluation in enumerate(evaluations):
                report = self._named(evaluation, "evaluation")
                exp = self._named(report.experiment, "experiment")
                if exp.parent != proposal:
                    raise ValueError("review evaluation belongs to another proposal")
                covered.add(exp.data["caseId"])
                refs[f"evaluation/{index}"] = report.cid
            if decision == "adopt" and covered != set(cases):
                raise ValueError("adoption review must cover every predeclared case, including regressions")
            available = [r.name for r in self.list(kind="evaluation")
                         if self._named(r.experiment, "experiment").parent == proposal]
            pending = [r.name for r in self.list(kind="attempt")
                       if self._named(r.experiment, "experiment").parent == proposal
                       and not self.list(kind="outcome", parent=r.name)]
            return self._record(name, "review", {
                "decision": decision, "actor": _text(actor, "review actor"),
                "rationale": _text(rationale, "review rationale"), "reviewKind": review_kind,
                "evaluations": list(evaluations),
                "missingCaseIds": sorted(set(cases) - covered),
                "omittedEvaluationNames": sorted(set(available) - set(evaluations)),
                "pendingAttemptNames": pending,
                "meaning": "Attributed trusted-host review record; actor text is not authentication.",
            }, refs, parent=proposal, exclusive="review/" + proposal)[0]

    def adopt(self, name: str, *, review: str) -> ExperimentRecord:
        with self.objects._transaction():
            reviewed = self._named(review, "review")
            if reviewed.data["decision"] != "adopt":
                raise ValueError("rejected candidate cannot be adopted")
            proposed = self._named(reviewed.parent, "proposal")
            return self._record(name, "adoption", {
                "review": review, "actor": reviewed.data["actor"], "reviewKind": reviewed.data["reviewKind"],
                "scope": "synthetic demonstration only" if reviewed.data["reviewKind"] == "synthetic" else "bounded component decision",
                "activation": "not performed; existing/native configuration remains unchanged",
            }, {"review": reviewed.cid, "version": proposed.content.ref("after"),
                "rollbackVersion": proposed.content.ref("before")},
                parent=review, exclusive="adoption/" + review)[0]

    def rollback(self, name: str, *, adoption: str, actor: str, rationale: str) -> ExperimentRecord:
        with self.objects._transaction():
            adopted = self._named(adoption, "adoption")
            return self._record(name, "rollback", {
                "adoption": adoption, "actor": _text(actor, "rollback actor"),
                "rationale": _text(rationale, "rollback rationale"), "activation": "not performed",
            }, {"adoption": adopted.cid, "version": adopted.content.ref("rollbackVersion")},
                parent=adoption, exclusive="rollback/" + adoption)[0]
