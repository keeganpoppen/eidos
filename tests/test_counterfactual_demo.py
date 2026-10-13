"""Synthetic end-to-end fixture evidence, never a model-quality benchmark."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sqlite3

import pytest

from eidos.investigation import InvestigationStore
from eidos.investigation_alternatives import ExperimentStore
from eidos.trace import TraceStore


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "counterfactual_demo.py"
spec = importlib.util.spec_from_file_location("counterfactual_demo", SCRIPT)
assert spec is not None and spec.loader is not None
demo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(demo)


def test_complete_fixture_proposal_experiment_evaluation_review_adoption_and_rollback(tmp_path: Path):
    path = tmp_path / "experiment.db"
    report = demo.run(path)
    assert report["synthetic"] is True
    assert report["ownerApproval"] is False
    assert report["measured_model_reasoning_improvement"] is False
    assert report["nativeModelCalls"] == report["nativeTurnStarts"] == 0
    assert report["policyActivated"] is False
    assert set(report["cases"]) == {"discovery", "heldout", "irrelevant", "cycle", "posthorizon", "budget"}
    for case_id in ("discovery", "heldout"):
        case = report["cases"][case_id]
        baseline, alternative = case["metrics"]["baseline"], case["metrics"]["alternative"]
        assert baseline["selection"]["recall"]["value"] == 0.5
        assert alternative["selection"]["recall"]["value"] == 1.0
        assert baseline["usefulness"]["coverage"]["value"] == 0.5
        assert alternative["usefulness"]["coverage"]["value"] == 1.0
        assert baseline["grounding"]["groundedClaims"] == 1
        assert alternative["grounding"]["groundedClaims"] == 2
        assert alternative["grounding"]["unsupportedClaimKeys"] == []
        assert case["metrics"]["comparison"]["passes"] is True
        assert alternative["resources"]["observedTokens"] is None
        assert alternative["resources"]["observedCost"] is None
    assert report["cases"]["heldout"]["role"] == "heldout"
    assert report["generalization"]["realWorldGeneralizationEstablished"] is False
    assert set(report["generalization"]["nonregressingCases"]) == set(report["cases"])

    trace = TraceStore(path)
    try:
        store = ExperimentStore(InvestigationStore(trace))
        proposal = store.get(report["records"]["proposal"]["name"])
        criteria = store.objects.get(proposal.content.ref("criteria")).data
        assert set(criteria["cases"]) == set(report["cases"])
        review = store.get(report["records"]["review"]["name"])
        adoption = store.get(report["records"]["adoption"]["name"])
        rollback = store.get(report["records"]["rollback"]["name"])
        assert review.data["decision"] == "adopt"
        assert review.data["reviewKind"] == adoption.data["reviewKind"] == "synthetic"
        assert adoption.content.ref("version") == report["versions"]["alternative"]
        assert adoption.content.ref("rollbackVersion") == rollback.content.ref("version") == report["versions"]["baseline"]
        assert store.objects.get(adoption.content.ref("version")).data["version"] == "P1/v1"
        definition = store.objects.get(adoption.content.ref("version")).data["definition"]
        assert definition["evaluatorVersion"] == demo.EVALUATOR_VERSION
        assert len(definition["extractorSourceSha256"]) == len(definition["evaluatorSelectorSourceSha256"]) == 64
        assert len(store.list(kind="experiment")) == 7
        assert len(store.list(kind="attempt")) == len(store.list(kind="outcome")) == 14
        ordinals = {row["name"]: row["ordinal"] for row in trace.db.execute("SELECT name,ordinal FROM exp_records")}
        first_attempt = min(ordinals[record.name] for record in store.list(kind="attempt"))
        assert ordinals[proposal.name] < first_attempt
        assert max(ordinals[record.name] for record in store.list(kind="evaluation") if record.experiment.startswith("fixture/context-one-hop/")) < ordinals[review.name]
        assert ordinals[review.name] < ordinals[adoption.name] < ordinals[rollback.name]
    finally:
        trace.close()


def test_guardrails_preserve_irrelevance_one_hop_horizon_and_budget_failures(tmp_path: Path):
    report = demo.run(tmp_path / "experiment.db")
    cases = report["cases"]
    assert cases["irrelevant"]["selection"]["P1"]["selectedRecordIds"] == [6]
    assert cases["cycle"]["selection"]["P1"]["selectedRecordIds"] == [8, 9]
    assert 10 not in cases["cycle"]["selection"]["P1"]["selectedRecordIds"]
    assert cases["posthorizon"]["selection"]["P1"]["omissions"] == [
        {"recordId": report["postHorizonRecordId"], "reason": "outside_frozen_horizon"}]
    assert report["postHorizonRecordId"] not in report["frozenRecordIds"]
    assert cases["budget"]["selection"]["P1"]["omissions"] == [{"recordId": 13, "reason": "bytes_budget"}]
    assert cases["budget"]["metrics"]["alternative"]["selection"]["omittedRelevantRecordIds"] == [13]
    assert cases["budget"]["metrics"]["alternative"]["passes"] is False
    assert cases["budget"]["metrics"]["comparison"]["resourceTradeoff"]["additionalBytes"] == 0
    for case in cases.values():
        assert case["metrics"]["alternative"]["hindsight"]["leakageCount"] == 0
        assert case["metrics"]["comparison"]["checks"]["selectionRecallNondecreasing"] is True
        assert case["metrics"]["comparison"]["checks"]["boundedAdditionalContext"] is True


def test_resume_preserves_exact_canonical_history_rejected_outcomes_and_independent_identity(tmp_path: Path):
    path = tmp_path / "experiment.db"
    original = demo.run(path)
    trace = TraceStore(path)
    try:
        investigations = InvestigationStore(trace)
        experiments = ExperimentStore(investigations)
        histories = investigations.list()
        records = [(record.seq, record.raw_text) for record in trace.records()]
        ledger = [(record.name, record.cid, record.parent, record.experiment) for record in experiments.list()]
        for case in original["cases"].values():
            baseline = investigations.get(case["baselineInvestigationId"])
            candidate = investigations.get(case["alternativeInvestigationId"])
            snapshot = experiments.objects.get(case["baselineSnapshotId"])
            assert experiments.objects.get(snapshot.ref("artifact")).data == baseline["artifact"]
            assert experiments.objects.get(snapshot.ref("context")).data["context"] == baseline["contexts"][0]
            assert experiments.objects.get(case["alternativeSnapshotId"]).data["context"] == candidate["contexts"][0]
            assert candidate["attempt"] is None
            assert candidate["artifact"] is None
            assert candidate["status"] == "draft"
            assert json.loads(candidate["contexts"][0]["records"][0]["rawText"])["unknownFutureField"]["preserve"] == "synthetic evidence bytes"
        rejected = experiments.get(original["records"]["rejectedReview"]["name"])
        assert rejected.data["decision"] == "reject"
        rejected_outcome = experiments.get(original["rejectedAlternative"]["outcomes"]["alternative"]["name"])
        first_outcome = experiments.get(original["cases"]["discovery"]["outcomes"]["baseline"]["name"])
        assert rejected_outcome.cid == first_outcome.cid
        assert rejected_outcome.name != first_outcome.name
        assert rejected_outcome.parent != first_outcome.parent
        assert rejected_outcome.experiment != first_outcome.experiment
        assert rejected_outcome.data["historicalWorldChanged"] is False
    finally:
        trace.close()

    resumed = demo.run(path, resume=True)
    assert {**resumed, "mode": original["mode"]} == original
    trace = TraceStore(path)
    try:
        assert InvestigationStore(trace).list() == histories
        assert [(record.seq, record.raw_text) for record in trace.records()] == records
        assert [(record.name, record.cid, record.parent, record.experiment)
                for record in ExperimentStore(InvestigationStore(trace)).list()] == ledger
    finally:
        trace.close()


def test_resume_refuses_unmarked_or_incomplete_database_without_reseeding(tmp_path: Path):
    missing = tmp_path / "missing.db"
    with pytest.raises(ValueError, match="existing synthetic"):
        demo.run(missing, resume=True)
    assert not missing.exists()
    foreign = tmp_path / "foreign.db"
    connection = sqlite3.connect(foreign)
    connection.execute("CREATE TABLE unrelated(value TEXT)")
    connection.close()
    before = foreign.read_bytes()
    with pytest.raises(ValueError, match="valid synthetic"):
        demo.run(foreign, resume=True)
    assert foreign.read_bytes() == before

    incomplete = tmp_path / "incomplete.db"
    trace = TraceStore(incomplete)
    demo.seed(trace)
    records = trace.records()
    trace.close()
    with pytest.raises(ValueError, match="completed synthetic demo marker"):
        demo.run(incomplete, resume=True)
    with pytest.raises(ValueError, match="new path"):
        demo.run(incomplete)
    trace = TraceStore(incomplete)
    try:
        assert trace.records() == records
    finally:
        trace.close()
