#!/usr/bin/env python3
"""Prepare a synthetic native investigation; execute only with explicit consent.

Preparation and inspection do not start Codex. The run command admits one durable
attempt and never retries it. A command-line flag records the operator's choice;
it does not replace the user's separate resource authorization.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from eidos.investigation import InvestigationStore
from eidos.investigation_worker import NativeInvestigationError, NativeInvestigationWorker
from eidos.trace import TraceStore


QUESTION = (
    "Compare the dispatch decision and the crash experiment. Identify the remaining "
    "recovery gap and recommend what to do after a missing acknowledgement. Use only "
    "the supplied synthetic evidence, cite it, and answer in at most 200 words. "
    "Do not invoke tools, request other evidence, or perform external actions."
)
SYNTHETIC_RECORDS = (
    ("smoke-design", "Persist the attempt before sending. A repeated owner request returns the same attempt."),
    ("smoke-design", "A turn/start timeout does not prove non-execution. Automatic resend was rejected."),
    ("smoke-experiment", "The native worker completed before the local artifact commit. Restart must inspect recorded completion; missing evidence leaves an unknown outcome."),
)


def prepare(database: Path) -> dict[str, Any]:
    """Create a fresh, reviewable packet without native execution or credentials."""
    # Exclusive creation prevents reseeding or overwriting a previous live attempt.
    database.parent.mkdir(parents=True, exist_ok=True)
    with database.open("x"):
        pass
    database.chmod(0o600)
    trace = TraceStore(database)
    try:
        selections = []
        for index, (thread_id, text) in enumerate(SYNTHETIC_RECORDS):
            record = trace.append(source="synthetic-specialist-smoke", direction="internal", message={
                "method": "$history/item", "params": {
                    "threadId": thread_id, "turnId": f"smoke-turn-{index}",
                    "item": {"id": f"smoke-item-{index}", "type": "agentMessage", "text": text},
                },
            })
            selections.append({"threadId": thread_id, "startSeq": record.seq,
                               "endSeq": record.seq, "rationale": "Synthetic recovery evidence."})
        investigation = InvestigationStore(trace).create({
            "requestId": "native-specialist-smoke-v1", "title": "Synthetic native specialist smoke",
            "question": QUESTION, "selections": selections,
        })
        return describe(investigation)
    finally:
        trace.close()


def describe(investigation: dict[str, Any]) -> dict[str, Any]:
    context = next(c for c in investigation["contexts"] if c["id"] == investigation["currentContextId"])
    return {
        "schemaVersion": 1, "investigationId": investigation["id"],
        "contextId": context["id"], "status": investigation["status"],
        "attempt": investigation["attempt"], "projectedPrompt": context["projectedPrompt"],
        "promptBytes": len(context["projectedPrompt"].encode()),
        "limits": {"nativeTurns": 1, "wallClockSeconds": 120, "outputCharacters": 131072,
                   "providerTokenOrCostCap": None, "automaticRetry": False},
        "resourceGate": "Requires separate explicit user consent before run; subscription-backed only.",
    }


def _load(trace: TraceStore, investigation_id: str) -> tuple[InvestigationStore, dict[str, Any]]:
    store = InvestigationStore(trace)
    investigation = store.get(investigation_id)
    context = next(c for c in investigation["contexts"] if c["id"] == investigation["currentContextId"])
    content = {key: context[key] for key in (
        "parentContextId", "question", "selections", "records", "projectedPrompt", "coverage")}
    encoded = json.dumps(content, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    if context["id"] != "context_" + hashlib.sha256(encoded).hexdigest():
        raise ValueError("reviewed synthetic context content no longer matches its identity")
    if (investigation["title"] != "Synthetic native specialist smoke"
            or context["question"] != QUESTION
            or len(context["records"]) != len(SYNTHETIC_RECORDS)
            or any(r["source"] != "synthetic-specialist-smoke" for r in context["records"])):
        raise ValueError("database does not contain the reviewed synthetic smoke packet")
    expected = [text for _, text in SYNTHETIC_RECORDS]
    observed = [json.loads(r["rawText"])["params"]["item"]["text"] for r in context["records"]]
    if observed != expected:
        raise ValueError("synthetic evidence was changed")
    return store, investigation


def run(database: Path, investigation_id: str, authorized_context: str | None) -> dict[str, Any]:
    """One admitted native run; an existing attempt always refuses execution."""
    if not authorized_context:
        raise ValueError("run requires --authorize-model with the reviewed context ID and explicit user consent")
    if not database.is_file():
        raise ValueError("prepare a fresh smoke database first")
    trace = TraceStore(database)
    worker = None
    try:
        store, investigation = _load(trace, investigation_id)
        if investigation["currentContextId"] != authorized_context:
            raise ValueError("authorization names a different context")
        investigation, claimed = store.claim(investigation_id, authorized_context)
        if not claimed:
            raise ValueError("smoke attempt already exists; inspect or recover evidence, never resend")
        context = next(c for c in investigation["contexts"] if c["id"] == authorized_context)
        worker = NativeInvestigationWorker(trace)
        try:
            artifact = worker.run(investigation["attempt"], context,
                                  lambda **fields: store.update_attempt(investigation_id, **fields))
            store.complete(investigation_id, artifact)
        except NativeInvestigationError as exc:
            store.update_attempt(investigation_id, status=exc.status, error=str(exc))
        finally:
            store.reconcile_context(investigation_id)
        result = describe(store.get(investigation_id))
        result["modelTurnRequestsRecorded"] = sum(
            r.direction == "client_to_appserver" and r.method == "turn/start" for r in trace.records())
        return result
    finally:
        if worker is not None:
            worker.close()
        trace.close()


def inspect(database: Path, investigation_id: str) -> dict[str, Any]:
    if not database.is_file():
        raise ValueError("smoke database does not exist")
    trace = TraceStore(database)
    try:
        _, investigation = _load(trace, investigation_id)
        return describe(investigation)
    finally:
        trace.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "inspect", "run"))
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--investigation")
    parser.add_argument("--authorize-model", metavar="REVIEWED_CONTEXT_ID")
    args = parser.parse_args()
    if args.operation != "prepare" and not args.investigation:
        parser.error("--investigation is required")
    if args.operation != "run" and args.authorize_model is not None:
        parser.error("--authorize-model is only valid for run")
    if args.operation == "prepare":
        result = prepare(args.db)
    elif args.operation == "inspect":
        result = inspect(args.db, args.investigation)
    else:
        result = run(args.db, args.investigation, args.authorize_model)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
