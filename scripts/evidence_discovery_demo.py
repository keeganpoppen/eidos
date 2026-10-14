"""Authored unmapped history for text discovery acceptance; never launch native work."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

from eidos.serve import serve
from eidos.trace import TraceStore

spec = importlib.util.spec_from_file_location("unmapped_history", Path(__file__).with_name("investigation_demo.py"))
assert spec and spec.loader
history = importlib.util.module_from_spec(spec)
spec.loader.exec_module(history)
MARKER = "synthetic-evidence-discovery/v1"


def raw_digest(store: TraceStore) -> str:
    digest = hashlib.sha256()
    for record in store.records():
        digest.update(f"{record.seq}:".encode())
        digest.update(record.raw_text.encode())
        digest.update(b"\n")
    return digest.hexdigest()


def seed(store: TraceStore) -> dict:
    history.seed(store, long_history=True)
    before = raw_digest(store)
    # Remove derived maps only. The raw imported-style evidence stays exact.
    for table in ("semantic_support", "semantic_nodes", "semantic_revisions", "semantic_observers"):
        store.db.execute(f"DELETE FROM {table}")
    assert raw_digest(store) == before

    def append(method, params, direction="internal"):
        return store.append(source=MARKER, direction=direction, message={"method": method, "params": params})

    thread, turn, item = "fixture-discovery-stream", "discovery-turn", "discovery-streamed-answer"
    coords = {"threadId": thread, "turnId": turn}
    append("item/started", {**coords, "item": {"id": item, "type": "agentMessage", "text": ""}})
    first = append("item/agentMessage/delta", {**coords, "itemId": item, "delta": "A phosphor "})
    unrelated = append("$history/item", {**coords, "item": {"id": "unrelated-interleaved", "type": "agentMessage",
        "text": "UNRELATED_INTERLEAVED: this nearby record is not part of the streamed answer."}})
    second = append("item/agentMessage/delta", {**coords, "itemId": item,
        "delta": "bridge failure requires preserving uncertain delivery, not automatic retry."})
    append("item/completed", {**coords, "item": {"id": item, "type": "agentMessage", "text": "",
        "futureField": {"retained": "UNKNOWN_SEARCH_CANARY"}}})
    replacement = {"threadId": thread, "turnId": "replacement-turn", "itemId": "replaced-answer"}
    append("item/agentMessage/delta", {**replacement, "delta": "SUPERSEDED_SEARCH_CANARY"})
    append("item/completed", {"threadId": thread, "turnId": "replacement-turn", "item": {
        "id": "replaced-answer", "type": "agentMessage", "text": "Current completed text supersedes its draft."}})
    append("account/updated", {"threadId": thread, "turnId": "control-turn", "text": "CONTROL_SEARCH_CANARY"})
    append("item/completed", {"threadId": "fixture-provider-shaped", "turnId": "provider-turn", "item": {
        "id": "provider-shaped", "type": "agentMessage", "text": "PROVIDER_SEARCH_CANARY"}}, "provider_response")
    append("$history/item", {"threadId": "fixture-hidden-internal", "turnId": "hidden-turn", "item": {
        "id": "hidden-answer", "type": "agentMessage", "text": "HIDDEN_SEARCH_CANARY"}})
    store.annotate_thread("fixture-hidden-internal", kind="synthetic-internal")
    assert all(store.semantic_outline(row['thread_id']) is None for row in store.threads())
    records = store.records()
    return {"schemaVersion": MARKER, "classification": "authored-unmapped-history", "nativeOrModelCalls": 0,
        "rawDigestBeforeMapRemoval": before, "rawDigest": raw_digest(store), "recordCount": len(records),
        "longThread": history.LONG_HISTORY_THREAD, "longTurns": history.LONG_HISTORY_TURNS,
        "queries": {"decision": "persist the outer dispatch attempt", "counterexample": "automatically retry every native timeout",
                    "split": "phosphor bridge", "absent": "NEVER_RECORDED_SEARCH_CANARY"},
        "expected": {"decision": next(r.seq for r in records if r.item_id == "fixture-long-history-turn-1100-answer"),
                     "counterexample": next(r.seq for r in records if r.item_id == "fixture-long-history-turn-20-answer"),
                     "split": [first.seq, second.seq], "interleaved": unrelated.seq},
        "excludedQueries": ["UNKNOWN_SEARCH_CANARY", "SUPERSEDED_SEARCH_CANARY", "CONTROL_SEARCH_CANARY",
                            "PROVIDER_SEARCH_CANARY", "HIDDEN_SEARCH_CANARY"],
        "humanBenefitMeasured": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--port", type=int, default=8767)
    args = parser.parse_args()
    if args.resume:
        marker = json.loads(args.output.read_text())
        assert marker["schemaVersion"] == MARKER and args.db.is_file()
        store = TraceStore(args.db)
        try:
            if raw_digest(store) != marker["rawDigest"]:
                raise ValueError("Resume source does not match this authored fixture marker.")
        finally:
            store.close()
    else:
        if args.db.exists():
            raise ValueError("Use a fresh authored fixture database.")
        store = TraceStore(args.db)
        try:
            marker = seed(store)
        finally:
            store.close()
        args.output.write_text(json.dumps(marker, indent=2) + "\n")
    print(json.dumps(marker, indent=2), flush=True)
    if args.serve:
        serve(args.db, port=args.port)


if __name__ == "__main__":
    main()
