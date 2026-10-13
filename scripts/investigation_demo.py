"""Create only synthetic two-thread evidence; optionally serve with a fake worker.

uv run python scripts/investigation_demo.py --db /tmp/nema-investigation-demo.db --serve
Then, in ui/: bun run dev -- --host 127.0.0.1
"""
from __future__ import annotations

import argparse
from pathlib import Path

from eidos.serve import serve
from eidos.trace import TraceStore


def seed(store: TraceStore) -> dict:
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
    return {"requestId": "synthetic-two-thread-investigation", "title": "Recover without duplicate work", "question": "Compare the design decision with the earlier crash experiment. Which recovery seam remains unprotected, and what should the outer investigation do? Cite selected evidence.", "selections": selected}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True)
    parser.add_argument("--serve", action="store_true", help="serve on 8765 with a synthetic worker; no model calls")
    parser.add_argument("--resume", action="store_true", help="reopen an existing synthetic demo without reseeding")
    args = parser.parse_args()
    store = TraceStore(args.db)
    if args.resume:
        threads = {row["thread_id"] for row in store.threads()}
        if not {"fixture-design", "fixture-experiment"} <= threads:
            raise ValueError("--resume requires an existing synthetic investigation demo")
        print("Reopening synthetic demo; worker remains synthetic.")
    else:
        packet = seed(store)
        print("Synthetic histories created. Suggested source selections:")
        for selection in packet["selections"]:
            print(f"  {selection['threadId']} record {selection['startSeq']}: {selection['rationale']}")
    store.close()
    if args.serve:
        fake = Path(__file__).resolve().parents[1] / "tests/fixtures/investigation_appserver.py"
        serve(args.db, codex=str(fake))


if __name__ == "__main__":
    main()
