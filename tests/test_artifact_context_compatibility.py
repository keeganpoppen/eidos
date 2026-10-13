"""Compatibility and continuation checks; all work and native traffic are synthetic."""
import hashlib

import pytest

from eidos.api import EidosAPI
from eidos.investigation import InvestigationStore
from eidos.investigation_experiments import InvestigationExperiments
from eidos.trace import TraceStore
from test_specialist_inquiries import SpecialistWorker, answer, call, create_body, next_body, successful, wait_for


def legacy_body(trace):
    record = trace.append(source="compatibility-fixture", direction="internal", message={
        "method": "$history/item", "params": {"threadId": "source", "turnId": "turn",
        "item": {"id": "answer", "type": "agentMessage", "text": "Retain uncertain delivery.",
                 "futureField": {"kept": True}}},
    })
    return {"requestId": "legacy", "title": "Legacy context", "question": "What was decided?",
            "selections": [{"threadId": "source", "startSeq": record.seq, "endSeq": record.seq,
                            "rationale": "decision"}]}


def result(store, work, text="Synthetic conclusion [evidence:1]."):
    work, _ = store.claim(work["id"], work["currentContextId"])
    output = store.trace.append(source="synthetic-result", direction="internal", message={
        "method": "$fixture/result", "text": text,
    })
    return store.complete(work["id"], {"text": text, "outputSeqs": [output.seq],
                                      "executionEvidence": "synthetic"})


def using(source, name="derived", *, selections=None):
    return {"requestId": name, "title": name, "question": "What was decided?",
            "selections": selections or [], "artifactInputs": [{
                "investigationId": source["id"], "artifactId": source["artifact"]["id"],
                "rationale": "Review this exact derived claim.",
            }]}


@pytest.mark.parametrize("explicit_empty", [False, True])
def test_legacy_packet_and_request_manifest_match_prechange_revision(explicit_empty):
    # Independently generated using unchanged main 29a164a source in a worktree.
    trace = TraceStore()
    store = InvestigationStore(trace)
    body = legacy_body(trace)
    if explicit_empty:
        body["artifactInputs"] = []
    work = store.create(body)
    context = work["contexts"][0]
    assert context["id"] == "context_4848399aa9e758896c491cbfb4a8766fba930efe02eb4e93c472a1d5d25ef366"
    assert context["manifestId"] == "cm1_1294c8f13a03bdbfdec8f04b8fbc2cf4eca020d84be4342c944625e1181bc6d7"
    assert hashlib.sha256(context["projectedPrompt"].encode()).hexdigest() == "b5fe15a2f34665369f3743741c80c386be511b905da413cc5cafb9d6ac7f629b"
    work, _ = store.claim(work["id"], context["id"])
    assert work["attempt"]["manifestId"] == "cm1_b1953980f1a76f53535171b9f2796c0d6dc431e9cff37a1465f4b1af428d0438"
    assert "artifactInputs" not in context
    trace.close()


def test_unsupported_artifact_citation_is_visible_even_in_record_only_context():
    trace = TraceStore()
    store = InvestigationStore(trace)
    work = result(store, store.create(legacy_body(trace)), "Unsupported [artifact:invented].")
    assert work["artifact"]["artifactCitations"] == []
    assert work["artifact"]["unsupportedArtifactCitations"] == ["invented"]
    trace.close()


def test_artifact_binding_survives_terminal_inquiry_offer_followup_and_reopen(tmp_path):
    path = tmp_path / "chain.db"
    trace = TraceStore(path)
    api = EidosAPI(trace)
    store = api.investigations
    original = result(store, store.create(legacy_body(trace)))
    work = store.create(using(original))
    base = work["contexts"][0]
    assert base["records"] == []
    api.investigation_worker = SpecialistWorker(trace)
    try:
        successful(call(api, f"/{work['id']}/dispatch", {"contextId": work["currentContextId"]}))
        pending = wait_for(api, work["id"], lambda value: bool(value.get("continuation", {}).get("inquiry")))
        # This later decision must not be smuggled into the already frozen B input.
        store.adopt(original["id"], {"artifactId": original["artifact"]["id"], "decision": "reject",
                                      "note": "Reconsider the claim."})
        expanded = answer(api, pending, create_body(trace, "offered"))
        successor = next(c for c in expanded["contexts"] if c["id"] == expanded["continuation"]["nativeNext"]["contextId"])
        assert successor["artifactInputs"] == base["artifactInputs"]
        assert successor["artifactInputs"][0]["sourceAdoption"] is None
        assert successor["coverage"] == base["coverage"]
        before = store.contexts.store.entries(base["manifestId"])
        after = store.contexts.store.entries(successor["manifestId"])
        for key in before:
            if key.startswith("artifact/"):
                assert after[key] == before[key]
        api.investigation_worker = SpecialistWorker(trace, question=False)
        successful(call(api, f"/{work['id']}/continue", next_body(expanded)))
        finished = wait_for(api, work["id"], lambda value: value["attempt"].get("continuedFrom") and value["status"] == "completed")
        assert finished["contexts"][0] == base
        assert finished["artifact"]["artifactCitations"] == []
        assert finished["attempt"]["manifestId"] != finished["attemptHistory"][0]["manifestId"]
    finally:
        api.close()
        trace.close()
    reopened = TraceStore(path)
    assert InvestigationStore(reopened).get(work["id"]) == finished
    reopened.close()


def test_artifact_only_comparison_counts_removed_inputs_without_claiming_improvement():
    trace = TraceStore()
    store = InvestigationStore(trace)
    source = result(store, store.create(legacy_body(trace)))
    other = result(store, store.create({**legacy_body(trace), "requestId": "other"}), "Another synthetic claim.")
    body = using(other)
    work = store.create(body)
    original_context = work["contexts"][0]
    work = store.revise(work["id"], {"requestId": "add-source", "parentContextId": work["currentContextId"],
        "question": body["question"], "selections": [],
        "artifactInputs": using(other)["artifactInputs"] + using(source)["artifactInputs"]})
    work = result(store, work, f"Derived inputs [artifact:{other['artifact']['id']}] [artifact:{source['artifact']['id']}].")
    # Compare the produced two-input baseline against the retained one-input draft.
    experiments = InvestigationExperiments(store)
    compared = experiments.create(work["id"], {"requestId": "drop", "baselineContextId": work["currentContextId"],
        "baselineArtifactId": work["artifact"]["id"], "alternativeContextId": original_context["id"],
        "rationale": "Smaller bytes must not hide dropped derived evidence."})
    assert compared["evaluation"]["method"] == "context-selection-comparison/v2"
    assert compared["evaluation"]["baseline"]["recordIds"] == []
    assert compared["evaluation"]["removedArtifactIds"] == [source["artifact"]["id"]]
    assert not compared["evaluation"]["checks"]["baselineArtifactsRetained"]
    assert not compared["evaluation"]["passes"]
    assert not compared["evaluation"]["measuredModelReasoningImprovement"]
    ledger = experiments.ledger
    horizon = ledger.freeze_horizon([], evidence_class="recorded", rationale="Derived inputs only.",
                                    artifact_inputs=original_context["artifactInputs"])
    absent = ledger.snapshot_context(work["id"], work["currentContextId"])
    with pytest.raises(ValueError, match="artifact.*outside"):
        ledger._context_within(absent, ledger.objects.get(horizon))
    trace.close()


def test_comparison_cannot_count_dropped_rejection_snapshot_as_retained_input():
    trace = TraceStore()
    store = InvestigationStore(trace)
    source = result(store, store.create(legacy_body(trace)))
    body = using(source)
    work = store.create(body)
    before_review = work["currentContextId"]
    store.adopt(source["id"], {"artifactId": source["artifact"]["id"], "decision": "reject",
                               "note": "The derived claim omitted an important caveat."})
    work = store.revise(work["id"], {"requestId": "after-review", "parentContextId": before_review,
        "question": body["question"], "selections": [], "artifactInputs": body["artifactInputs"]})
    work = result(store, work)
    compared = InvestigationExperiments(store).create(work["id"], {
        "requestId": "retain-review", "baselineContextId": work["currentContextId"],
        "baselineArtifactId": work["artifact"]["id"], "alternativeContextId": before_review,
        "rationale": "Compare the same artifact with its separately frozen review omitted."})
    evaluation = compared["evaluation"]
    assert evaluation["baseline"]["artifactIds"] == evaluation["alternative"]["artifactIds"]
    assert evaluation["removedArtifactIds"] == []
    assert evaluation["changedArtifactIds"] == [source["artifact"]["id"]]
    assert evaluation["additionalPromptBytes"] < 0
    assert not evaluation["checks"]["baselineArtifactsRetained"]
    assert not evaluation["passes"]
    trace.close()
