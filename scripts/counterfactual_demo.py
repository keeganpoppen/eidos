"""Persist a synthetic context-policy experiment, evaluation, review and rollback.

uv run python scripts/counterfactual_demo.py --db /tmp/nema-counterfactual.db
uv run python scripts/counterfactual_demo.py --db /tmp/nema-counterfactual.db --resume

The fixed annotation extractor is not a model. No native process, filesystem
replay or external effect runs. A synthetic review exercises persistence; it
does not stand in for the owner's approval or activate a context policy.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any

from eidos.investigation import InvestigationStore
from eidos.investigation_alternatives import ExperimentStore
from eidos import investigation_evaluation
from eidos.investigation_evaluation import EVALUATOR_VERSION, select_context
from eidos.trace import TraceStore


DEMO_SOURCE = "synthetic-counterfactual-demo/v1"
PROPOSAL = "fixture/context-one-hop/proposal"
REVIEW = "fixture/context-one-hop/review"
ADOPTION = "fixture/context-one-hop/adoption"
ROLLBACK = "fixture/context-one-hop/rollback"
REJECTED_PROPOSAL = "fixture/context-relabel/proposal"
EXTRACTOR_VERSION = "fixture-annotation-extractor/v1"


def _fact(key: str, value: str) -> dict[str, str]:
    return {"key": key, "value": value, "facet": key}


def _message(thread: str, text: str, facts: list[dict], links: list[int]) -> dict:
    return {
        "method": "$history/item",
        "params": {"threadId": thread, "turnId": thread + "-turn", "item": {
            "id": thread + "-item", "type": "agentMessage", "text": text,
        }},
        "relatedEvidence": links, "fixtureFacts": facts,
        "unknownFutureField": {"preserve": "synthetic evidence bytes"},
    }


def seed(trace: TraceStore) -> tuple[list[dict], dict]:
    """Freeze the test corpus and expected annotations before any attempts."""
    if trace.records():
        raise ValueError("synthetic demo requires an empty trace database")
    messages = [
        _message("fixture-design", "Persist the dispatch attempt before sending; compare the crash experiment.",
                 [_fact("admission", "Persist an attempt before dispatch.")], [2]),
        _message("fixture-crash", "A crash after an external response but before local commit leaves execution uncertain.",
                 [_fact("recovery_gap", "An absent acknowledgement does not justify retrying an external effect.")], []),
        _message("fixture-unrelated", "A color preference is unrelated to recovery.",
                 [_fact("unrelated_color", "Blue.")], []),
        _message("fixture-heldout-context", "A context projection preserves exactly what was selected; inspect the provider-boundary note.",
                 [_fact("projection", "Selected context is an intended local projection.")], [5]),
        _message("fixture-heldout-boundary", "App-server input cannot establish hidden provider instructions.",
                 [_fact("visibility", "Provider instructions remain unknown.")], []),
        _message("fixture-irrelevant", "The answer needs only this record, with no nominated links.",
                 [_fact("immutability", "Historical evidence remains immutable.")], []),
        _message("fixture-distractor", "An unrelated source should not be included merely because it is nearby.",
                 [_fact("distractor", "A larger prompt is not necessarily better.")], []),
        _message("fixture-cycle-a", "Follow the direct supporting reference once.",
                 [_fact("one_hop", "Only seed references nominate additional context.")], [9]),
        _message("fixture-cycle-b", "This source links back to its parent and forward to a transitive distractor.",
                 [_fact("cycle", "Cycles do not recurse or duplicate selected evidence.")], [8, 10]),
        _message("fixture-transitive", "This record lies beyond the single admitted context-expansion hop.",
                 [_fact("transitive", "Do not expand recursively.")], []),
        _message("fixture-horizon", "The linked record has not arrived at the frozen evidence horizon.",
                 [_fact("horizon", "A future record is excluded even when its identifier is known.")], [14]),
        _message("fixture-budget", "An optional linked source exceeds the bounded context allocation.",
                 [_fact("budget", "Retain seed evidence when an additional source exceeds the byte budget.")], [13]),
        _message("fixture-expensive", "Synthetic padding: " + "x" * 6000,
                 [_fact("expensive_detail", "A relevant source can remain omitted because of its cost.")], []),
    ]
    frozen = []
    for expected_seq, message in enumerate(messages, 1):
        record = trace.append(source=DEMO_SOURCE, direction="internal", message=message)
        if record.seq != expected_seq:
            raise ValueError("synthetic fixture sequence allocation changed")
        frozen.append({"seq": record.seq, "threadId": record.thread_id,
                       "source": record.source, "direction": record.direction,
                       "method": record.method, "rawText": record.raw_text,
                       "sha256": hashlib.sha256(record.raw_text.encode()).hexdigest()})
    definitions = [
        ("discovery", "discovery", 1, [1, 2], "What do the design and crash experiment jointly imply about retrying an interrupted dispatch?", 16000),
        ("heldout", "heldout", 4, [4, 5], "What does the context projection establish, and what remains unknown across the provider boundary?", 16000),
        ("irrelevant", "guardrail", 6, [6], "What must happen to historical evidence?", 16000),
        ("cycle", "guardrail", 8, [8, 9], "How far should direct supporting references expand, including cycles?", 16000),
        ("posthorizon", "guardrail", 11, [11], "May this historical investigation use the source recorded after its horizon?", 16000),
        ("budget", "guardrail", 12, [12, 13], "Which evidence remains available when a relevant linked source exceeds the context allocation?", 2048),
    ]
    cases = {}
    for case_id, role, seed_id, relevant, question, max_bytes in definitions:
        facts = {}
        for seq in relevant:
            for fact in messages[seq - 1]["fixtureFacts"]:
                facts[fact["key"]] = {"value": fact["value"], "facet": fact["facet"], "recordIds": [seq]}
        cases[case_id] = {
            "version": "fixture-case/v1", "role": role, "question": question,
            "relevantRecordIds": relevant, "requiredFacets": sorted(facts), "factSupport": facts,
            "maxAdditionalBytes": 4000 if case_id != "budget" else 0,
            "seedRecordIds": [seed_id], "maxRecords": 4, "maxBytes": max_bytes,
        }
    return frozen, {"version": "fixture-suite/v1", "interpreterVersion": EXTRACTOR_VERSION, "cases": cases}


def extract(records: list[dict]) -> tuple[str, list[dict]]:
    """Read only supplied annotations; no expected-answer lookup or model call."""
    claims = []
    for record in records:
        for fact in json.loads(record["rawText"]).get("fixtureFacts", []):
            claims.append({**fact, "citations": [record["seq"]]})
    answer = "Synthetic annotation extraction; no model inference.\n" + "\n".join(
        f"{claim['value']} [evidence:{claim['citations'][0]}]" for claim in claims
    )
    return answer, claims


def _create_context(investigations: InvestigationStore, frozen: list[dict], case_id: str,
                    case: dict, policy: str) -> tuple[dict, dict]:
    projection = select_context(policy, frozen, case["seedRecordIds"],
                                max_records=case["maxRecords"], max_bytes=case["maxBytes"])
    records = {record["seq"]: record for record in frozen}
    investigation = investigations.create({
        "requestId": f"fixture/{case_id}/{policy}/context", "title": f"Synthetic {case_id}: {policy}",
        "question": case["question"],
        "selections": [{"threadId": records[seq]["threadId"], "startSeq": seq, "endSeq": seq,
                        "rationale": "Frozen fixture evidence selected by the recorded policy version."}
                       for seq in projection["selectedRecordIds"]],
    })
    return investigation, projection


def _complete_baseline(investigations: InvestigationStore, investigation: dict) -> dict:
    identifier = investigation["id"]
    context = investigation["contexts"][0]
    answer, _ = extract(context["records"])
    _, admitted = investigations.claim(identifier, context["id"])
    if not admitted:
        raise RuntimeError("new synthetic baseline unexpectedly has an existing attempt")
    thread = "fixture-baseline/" + identifier
    investigations.update_attempt(identifier, source=DEMO_SOURCE, threadId=thread,
                                  turnId=thread + "/turn", status="running")
    output = investigations.trace.append(source=DEMO_SOURCE, direction="internal", message={
        "method": "$history/item", "params": {"threadId": thread, "turnId": thread + "/turn", "item": {
            "id": thread + "/answer", "type": "agentMessage", "text": answer,
            "synthetic": True, "extractorVersion": EXTRACTOR_VERSION,
        }},
    })
    return investigations.complete(identifier, {"text": answer, "outputSeqs": [output.seq]})


def _record_ref(record: Any) -> dict:
    return {"name": record.name, "cid": record.cid, "kind": record.kind}


def _execute(experiments: ExperimentStore, name: str, baseline_records: list[dict],
             alternative_records: list[dict]) -> dict:
    outcomes = {}
    for variant, records in (("baseline", baseline_records), ("alternative", alternative_records)):
        attempt, created = experiments.prepare_attempt(name + "/" + variant + "/attempt",
                                                       experiment=name, variant=variant)
        if not created:
            raise RuntimeError("new synthetic experiment unexpectedly reused an attempt")
        answer, claims = extract(records)
        outcome = experiments.finish_attempt(name + "/" + variant + "/outcome", attempt=attempt.name,
                                             answer=answer, claims=claims,
                                             assumptions=["Fixture annotations are supplied data, not model reasoning."],
                                             failures=[])
        outcomes[variant] = _record_ref(outcome)
        outcomes[variant + "Attempt"] = _record_ref(attempt)
    evaluation = experiments.evaluate(name + "/evaluation", experiment=name,
                                      baseline_outcome=outcomes["baseline"]["name"],
                                      alternative_outcome=outcomes["alternative"]["name"])
    return {"outcomes": outcomes, "evaluation": _record_ref(evaluation)}


def _summary(trace: TraceStore, experiments: ExperimentStore, marker: dict, mode: str) -> dict:
    cases = {}
    for case_id, case in marker["cases"].items():
        evaluation = experiments.get(case["evaluation"]["name"])
        cases[case_id] = {**case, "metrics": evaluation.data}
    refs = {label: _record_ref(experiments.get(name)) for label, name in marker["records"].items()}
    return {
        "mode": mode, "synthetic": True, "extractorVersion": EXTRACTOR_VERSION,
        "comparisonScope": "Controlled annotation extraction under P0/P1; the exact baseline artifact is retained, not evaluated as model reasoning.",
        "measured_model_reasoning_improvement": False, "ownerApproval": False,
        "nativeModelCalls": 0, "nativeTurnStarts": sum(record.method == "turn/start" for record in trace.records()),
        "externalEffects": "none; reinterpretation only", "policyActivated": False,
        "reviewKind": "synthetic", "horizon": marker["horizon"], "versions": marker["versions"],
        "frozenRecordIds": marker["frozenRecordIds"], "postHorizonRecordId": marker["postHorizonRecordId"],
        "records": refs, "cases": cases, "generalization": marker["generalization"],
        "rejectedAlternative": {**marker["rejectedAlternative"],
                                "metrics": experiments.get(marker["rejectedAlternative"]["evaluation"]["name"]).data},
        "limitations": ["Fixture usefulness is required-facet coverage, not human-rated answer quality.",
                        "The heldout case is a predeclared structural fixture, not a blinded benchmark or real-world validation.",
                        "Token figures are estimates; provider token usage and prices were not observed.",
                        "Unlinked relevant sources and relevant over-budget sources can remain omitted.",
                        "Adoption and rollback record synthetic review decisions; no native configuration is changed."],
    }


def validated_marker(path: Path) -> dict:
    """Refuse unknown databases without initializing schemas or writing to them."""
    if not path.is_file():
        raise ValueError("--resume requires this script's existing synthetic demo")
    connection = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        row = connection.execute("SELECT raw_text FROM trace_records WHERE source=? AND method=? ORDER BY seq DESC LIMIT 1",
                                 (DEMO_SOURCE, "$demo/counterfactual")).fetchone()
        if row is None:
            raise ValueError("--resume requires this script's completed synthetic demo marker")
        marker = json.loads(row[0])["params"]
        if marker.get("demoVersion") != 1 or marker.get("proposal") != PROPOSAL:
            raise ValueError("unrecognized synthetic counterfactual demo marker")
        return marker
    except (sqlite3.Error, KeyError, TypeError, json.JSONDecodeError) as error:
        raise ValueError("--resume requires a valid synthetic counterfactual demo") from error
    finally:
        connection.close()


def run(path: Path, *, resume: bool = False) -> dict:
    marker = validated_marker(path) if resume else None
    if not resume and path.exists():
        raise ValueError("--db must be a new path; use --resume for the marked completed demo")
    trace = TraceStore(path)
    try:
        investigations = InvestigationStore(trace)
        experiments = ExperimentStore(investigations)
        if marker is not None:
            return _summary(trace, experiments, marker, "inspect-existing")
        frozen, criteria = seed(trace)
        horizon = experiments.freeze_horizon([record["seq"] for record in frozen], evidence_class="synthetic",
                                             rationale="Fixed multi-thread fixture corpus and heldout case before any attempt.")
        future = trace.append(source=DEMO_SOURCE, direction="internal", message=_message(
            "fixture-future", "This source arrived after the experiment's frozen horizon.",
            [_fact("future", "Later knowledge is not historical input.")], []))
        implementation = {
            "interpreterVersion": EXTRACTOR_VERSION,
            "extractorSourceSha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "evaluatorVersion": EVALUATOR_VERSION,
            "evaluatorSelectorSourceSha256": hashlib.sha256(Path(investigation_evaluation.__file__).read_bytes()).hexdigest(),
        }
        versions = {
            "baseline": experiments.version("context-selection", "P0/v1", {
                "policy": "P0", "rule": "Retain only selected seed records.", **implementation}),
            "alternative": experiments.version("context-selection", "P1/v1", {
                "policy": "P1", "rule": "Add seeds' explicit one-hop relatedEvidence links within frozen horizon and budgets.",
                **implementation}),
        }
        experiments.propose(PROPOSAL, before_version=versions["baseline"], after_version=versions["alternative"],
                            criteria=criteria, rationale="A selected design note can omit the experiment it explicitly cites.")
        marker = {"demoVersion": 1, "proposal": PROPOSAL, "horizon": horizon,
                  "versions": versions, "frozenRecordIds": [record["seq"] for record in frozen],
                  "postHorizonRecordId": future.seq, "cases": {}, "records": {"proposal": PROPOSAL}}
        for case_id, case in criteria["cases"].items():
            baseline, p0 = _create_context(investigations, frozen, case_id, case, "P0")
            alternative, p1 = _create_context(investigations, frozen, case_id, case, "P1")
            baseline = _complete_baseline(investigations, baseline)
            baseline_cid = experiments.snapshot_baseline(baseline["id"], baseline["currentContextId"], baseline["artifact"]["id"])
            alternative_cid = experiments.snapshot_context(alternative["id"], alternative["currentContextId"])
            name = "fixture/context-one-hop/" + case_id
            experiment = experiments.experiment(name, proposal=PROPOSAL, baseline=baseline_cid,
                                                alternative_context=alternative_cid, horizon=horizon, case_id=case_id,
                                                mode="reinterpretation", assumptions=[
                                                    "Recorded evidence is synthetic and immutable; historical authority is absent.",
                                                    "Only local annotation extraction runs; no native or workspace effects are available.",
                                                ])
            execution = _execute(experiments, name, baseline["contexts"][0]["records"], alternative["contexts"][0]["records"])
            marker["cases"][case_id] = {
                "role": case["role"], "question": case["question"], "experiment": _record_ref(experiment),
                "baselineInvestigationId": baseline["id"], "baselineContextId": baseline["currentContextId"],
                "baselineArtifactId": baseline["artifact"]["id"], "baselineSnapshotId": baseline_cid,
                "alternativeInvestigationId": alternative["id"], "alternativeContextId": alternative["currentContextId"],
                "alternativeSnapshotId": alternative_cid, "selection": {"P0": p0, "P1": p1}, **execution,
            }
        comparisons = {case_id: experiments.get(case["evaluation"]["name"]).data["comparison"]
                       for case_id, case in marker["cases"].items()}
        improved = [case_id for case_id, comparison in comparisons.items() if comparison["checks"]["fixtureImprovement"]]
        nonregressing = [case_id for case_id, comparison in comparisons.items()
                         if all(value for name, value in comparison["checks"].items() if name != "fixtureImprovement")]
        if not {"discovery", "heldout"} <= set(improved) or set(nonregressing) != set(comparisons):
            raise RuntimeError("synthetic policy failed the predeclared improvement or regression criteria; ledger retained for review")
        marker["generalization"] = {
            "scope": "Predeclared synthetic structural cases only; not a blinded benchmark.",
            "improvedCases": improved, "nonregressingCases": nonregressing,
            "realWorldGeneralizationEstablished": False,
            "remainingFailure": "The budget guardrail still omits relevant evidence; one-hop selection cannot recover unlinked evidence.",
        }
        experiments.review(REVIEW, proposal=PROPOSAL,
                           evaluations=[case["evaluation"]["name"] for case in marker["cases"].values()],
                           decision="adopt", actor="synthetic-reviewer", review_kind="synthetic",
                           rationale="Fixture discovery and predeclared structural heldout coverage improve; all other checks remain nonregressing. The heldout case is not a blinded benchmark. Synthetic scope only.")
        experiments.adopt(ADOPTION, review=REVIEW)
        experiments.rollback(ROLLBACK, adoption=ADOPTION, actor="synthetic-reviewer",
                             rationale="Exercise explicit rollback to P0; no live policy was activated.")
        marker["records"].update({"review": REVIEW, "adoption": ADOPTION, "rollback": ROLLBACK})
        unchanged = experiments.version("context-selection", "P0-relabel/v1", {
            "policy": "P0", "rule": "Retain only selected seed records.", **implementation})
        experiments.propose(REJECTED_PROPOSAL, before_version=versions["baseline"], after_version=unchanged,
                            criteria={**criteria, "cases": {"discovery": criteria["cases"]["discovery"]}},
                            rationale="Counterexample: renaming a policy alone does not repair omitted evidence.")
        original = marker["cases"]["discovery"]
        baseline = investigations.get(original["baselineInvestigationId"])
        same_context = experiments.snapshot_context(baseline["id"], baseline["currentContextId"])
        rejected_name = "fixture/context-relabel/discovery"
        rejected = experiments.experiment(rejected_name, proposal=REJECTED_PROPOSAL,
                                          baseline=original["baselineSnapshotId"], alternative_context=same_context,
                                          horizon=horizon, case_id="discovery", mode="reinterpretation",
                                          assumptions=["A new description does not change context contents or grant authority."])
        rejected_run = _execute(experiments, rejected_name, baseline["contexts"][0]["records"], baseline["contexts"][0]["records"])
        rejected_review = experiments.review("fixture/context-relabel/review", proposal=REJECTED_PROPOSAL,
                                             evaluations=[rejected_run["evaluation"]["name"]], decision="reject",
                                             actor="synthetic-reviewer", review_kind="synthetic",
                                             rationale="No relevant evidence or answer facet was added; retain the rejected alternative.")
        marker["records"].update({"rejectedProposal": REJECTED_PROPOSAL, "rejectedReview": rejected_review.name})
        marker["rejectedAlternative"] = {"experiment": _record_ref(rejected), **rejected_run}
        trace.append(source=DEMO_SOURCE, direction="internal",
                     message={"method": "$demo/counterfactual", "params": marker})
        return _summary(trace, experiments, marker, "complete-demo")
    finally:
        trace.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, type=Path, help="new SQLite path for this synthetic experiment")
    parser.add_argument("--resume", action="store_true", help="inspect the completed demo without new attempts or evidence")
    args = parser.parse_args()
    try:
        result = run(args.db.expanduser(), resume=args.resume)
    except (ValueError, RuntimeError) as error:
        parser.exit(1, f"{error}\n")
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
