"""Create synthetic investigation and long-history evidence; optionally serve it.

uv run python scripts/investigation_demo.py --db /tmp/nema-investigation-demo.db --long-history --serve
Then, in ui/: bun run dev -- --host 127.0.0.1
"""
from __future__ import annotations

import argparse
from pathlib import Path

from eidos.serve import serve
from eidos.trace import TraceStore


LONG_HISTORY_THREAD = "fixture-long-history"
LONG_HISTORY_TURNS = 1200


def _seed_long_history(store: TraceStore) -> None:
    """Persist actual selectable evidence, including a large complete tool turn.

    These are authored fixtures, not recordings of executed commands. Keep this
    after the original two histories so their source references stay unchanged.
    """
    support = []
    for index in range(LONG_HISTORY_TURNS):
        turn_id = f"{LONG_HISTORY_THREAD}-turn-{index}"
        store.append(source="synthetic-long-history/v1", direction="internal", message={
            "method": "$history/item", "params": {"threadId": LONG_HISTORY_THREAD, "turnId": turn_id, "item": {
                "id": f"{turn_id}-user", "type": "userMessage", "content": [{"type": "text", "text":
                    "Synthetic long history: recovery through 1,200 turns" if index == 0 else
                    f"Review {index}: inspect the recovery evidence and retain unresolved questions."}],
            }},
        })
        if index == 600:
            item_id = f"{turn_id}-command"
            command = "uv run pytest tests/test_investigation_continuation_failures.py -q"
            store.append(source="synthetic-long-history/v1", direction="internal", message={
                "method": "item/started", "params": {"threadId": LONG_HISTORY_THREAD, "turnId": turn_id,
                    "item": {"id": item_id, "type": "commandExecution", "command": command, "status": "inProgress"}},
            })
            chunks = []
            for part in range(96):
                chunk = f"synthetic recovery case {part:03d}: fixture checkpoint and evidence correlation PASSED\n"
                chunks.append(chunk)
                store.append(source="synthetic-long-history/v1", direction="internal", message={
                    "method": "item/commandExecution/outputDelta", "params": {
                        "threadId": LONG_HISTORY_THREAD, "turnId": turn_id, "itemId": item_id, "delta": chunk},
                })
                if part == 48:
                    # Its global seq lies inside the tool item's extent, but it
                    # belongs to a different thread and must never resolve here.
                    store.append(source="synthetic-long-history/v1", direction="internal", message={
                        "method": "$history/item", "params": {"threadId": "fixture-history-neighbor",
                            "turnId": "fixture-history-neighbor-turn", "item": {
                                "id": "fixture-history-neighbor-answer", "type": "agentMessage",
                                "text": "Synthetic neighboring thread: this record is outside the long history."}},
                    })
            store.append(source="synthetic-long-history/v1", direction="internal", message={
                "method": "item/completed", "params": {"threadId": LONG_HISTORY_THREAD, "turnId": turn_id,
                    "item": {"id": item_id, "type": "commandExecution", "command": command,
                        "status": "completed", "exitCode": 0, "aggregatedOutput": "".join(chunks),
                        "futureField": {"fixture": True, "executed": False}}},
            })
        text = f"Routine review {index}: evidence references remain stable; no new recovery policy was adopted."
        label = None
        if index == 20:
            text = ("Rejected alternative: automatically retry every native timeout. A missing acknowledgement "
                    "does not show that the native turn never ran; retry could duplicate external work.")
            label = "Rejected automatic retry"
        elif index == 1100:
            text = ("Decision: persist the outer dispatch attempt before sending. Recover using its recorded "
                    "native identity and completion evidence; preserve unknown delivery instead of automatically "
                    "retrying. This decision retains the earlier rejected alternative as its counterexample.")
            label = "Adopted dispatch decision"
        record = store.append(source="synthetic-long-history/v1", direction="internal", message={
            "method": "$history/item", "params": {"threadId": LONG_HISTORY_THREAD, "turnId": turn_id, "item": {
                "id": f"{turn_id}-answer", "type": "agentMessage", "text": text,
                "futureField": {"fixture": True, "ordinal": index, "capturedFromNative": False},
            }},
        })
        if label:
            support.append({"start": record.seq, "end": record.seq, "weight": 1.0, "label": label})
    store.put_semantic_revision(thread_id=LONG_HISTORY_THREAD, lens="thread", observer="synthetic-fixture",
        horizon_seq=record.seq, revision_id="synthetic-long-history-recovery-v1",
        note="Authored synthetic navigation case; no native/model execution or measured user benefit.", nodes=[{
            "id": "recovery-decision", "title": "Recovery decision and distant rejected alternative",
            "summary": "Compare the dispatch decision at turn 1,101 with the rejected retry at turn 21. The intervening tool detour is not support for the decision.",
            "support": support,
        }])


def seed(store: TraceStore, *, long_history: bool = False) -> dict:
    if store.records():
        raise ValueError("demo needs an empty trace database; choose a new /tmp path")
    selected = []
    for thread_id, title in [
        ("fixture-design", "Synthetic design: recovering a delegated investigation"),
        ("fixture-experiment", "Synthetic experiment: prepared response crash window"),
    ]:
        support = []
        for index in range(24):
            turn_id = f"{thread_id}-turn-{index}"
            request = store.append(source="synthetic-history", direction="internal", message={
                "method": "$history/item", "params": {"threadId": thread_id, "turnId": turn_id, "item": {
                    "id": f"{turn_id}-user", "type": "userMessage", "content": [{"type": "text", "text": title if index == 0 else f"Review step {index}: preserve evidence and identify the next gap."}],
                }},
            })
            text = f"Routine build note {index}. No change to the recovery decision."
            important = False
            if thread_id == "fixture-design" and index == 5:
                text = "Decision: persist a dispatch attempt before sending. A repeated browser request must return the same attempt, not launch another worker."
                important = True
            elif thread_id == "fixture-design" and index == 6:
                text = ("Synthetic recovery observation: the saved turn/start acknowledgement names fixture-turn-recovered; "
                        "a matching final item and completed turn were recorded before the crash. Reopening reconstructed "
                        "the same artifact from those records with zero new sends. This fixture demonstrates the "
                        "recorded-completion recovery case, not exactly-once external execution.")
            elif thread_id == "fixture-design" and index == 18:
                text = "Rejected alternative: automatically retry when turn/start times out. The native turn may already exist; missing acknowledgement is not evidence of non-execution."
                important = True
            elif thread_id == "fixture-experiment" and index == 11:
                text = "Experiment: the worker returned before ModelPreparedStep was saved. Killing the process here caused a second external call on retry. Prepared-step recovery only protects the later local commit/resume seam. Open question: can recorded native completion recover the outer artifact?"
                important = True
            record = store.append(source="synthetic-history", direction="internal", message={
                "method": "$history/item", "params": {"threadId": thread_id, "turnId": turn_id, "item": {
                    "id": f"{turn_id}-answer", "type": "agentMessage", "text": text,
                    "futureField": {"fixture": True, "ordinal": index},
                }},
            })
            if important:
                selected.append({"threadId": thread_id, "startSeq": record.seq, "endSeq": record.seq, "rationale": text.split(":", 1)[0]})
                support.append({"start": record.seq, "end": record.seq, "weight": 1.0})
        store.register_semantic_observer(name="synthetic-fixture", lens="thread")
        store.put_semantic_revision(thread_id=thread_id, lens="thread", observer="synthetic-fixture", horizon_seq=record.seq, nodes=[{
            "id": "recovery-decision", "title": "Dispatch recovery and its counterexample", "summary": "Synthetic navigation to the decision, rejected retry, and experiment.", "support": support,
        }])
    if long_history:
        _seed_long_history(store)
    return {"requestId": "synthetic-two-thread-investigation", "title": "Recover without duplicate work", "question": "Compare the design decision with the earlier crash experiment. Which recovery seam remains unprotected, and what should the outer investigation do? Cite selected evidence.", "selections": selected}


def append_long_history(store: TraceStore) -> dict:
    """Append authored evidence while an independent browser holds an old page."""
    threads = {row["thread_id"]: row for row in store.threads()}
    if threads.get(LONG_HISTORY_THREAD, {}).get("turn_count") != LONG_HISTORY_TURNS:
        raise ValueError("--append-history requires an unextended synthetic long-history demo")
    late = store.append(source="synthetic-long-history/v1", direction="internal", message={
        "method": "$history/item", "params": {
            "threadId": LONG_HISTORY_THREAD, "turnId": f"{LONG_HISTORY_THREAD}-turn-20", "item": {
                "id": "fixture-long-history-late-note", "type": "agentMessage",
                "text": "Synthetic late observation: the rejected retry remains historical evidence.",
                "futureField": {"fixture": True, "capturedFromNative": False},
            }},
    })
    started = store.append(source="synthetic-long-history/v1", direction="internal", message={
        "method": "turn/started", "params": {"threadId": LONG_HISTORY_THREAD,
            "turn": {"id": f"{LONG_HISTORY_THREAD}-turn-{LONG_HISTORY_TURNS}"}},
    })
    added = store.append(source="synthetic-long-history/v1", direction="internal", message={
        "method": "$history/item", "params": {
            "threadId": LONG_HISTORY_THREAD, "turnId": f"{LONG_HISTORY_THREAD}-turn-{LONG_HISTORY_TURNS}", "item": {
                "id": "fixture-long-history-appended-answer", "type": "agentMessage",
                "text": "Synthetic appended turn: older saved pages keep their evidence anchors.",
                "futureField": {"fixture": True, "capturedFromNative": False},
            }},
    })
    return {"lateSeq": late.seq, "appendedTurnSeq": started.seq, "appendedSeq": added.seq,
            "totalTurns": LONG_HISTORY_TURNS + 1}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True)
    parser.add_argument("--serve", action="store_true", help="serve on 8765 with a synthetic worker; no model calls")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--resume", action="store_true", help="reopen an existing synthetic demo without reseeding")
    mode.add_argument("--append-history", action="store_true", help="append synthetic late evidence and one new turn; print record coordinates")
    parser.add_argument("--long-history", action="store_true", help="include the persisted 1,200-turn navigation fixture")
    args = parser.parse_args()
    store = TraceStore(args.db)
    if args.append_history:
        import json
        print(json.dumps(append_long_history(store)))
    elif args.resume:
        threads = {row["thread_id"] for row in store.threads()}
        expected = {"fixture-design", "fixture-experiment"}
        if args.long_history:
            expected.add(LONG_HISTORY_THREAD)
        if not expected <= threads:
            raise ValueError("--resume requires an existing synthetic investigation demo")
        print("Reopening synthetic demo; worker remains synthetic.")
    else:
        packet = seed(store, long_history=args.long_history)
        print("Synthetic histories created. Suggested source selections:")
        for selection in packet["selections"]:
            print(f"  {selection['threadId']} record {selection['startSeq']}: {selection['rationale']}")
        if args.long_history:
            print(f"  {LONG_HISTORY_THREAD}: {LONG_HISTORY_TURNS:,} persisted turns, including distant decision support.")
    store.close()
    if args.serve:
        fake = Path(__file__).resolve().parents[1] / "tests/fixtures/investigation_appserver.py"
        serve(args.db, codex=str(fake))


if __name__ == "__main__":
    main()
