#!/usr/bin/env python3
"""Synthetic native boundary for tests/demo. Never contacts a model/provider."""
import json
import re
import sys
import uuid


def emit(value):
    print(json.dumps(value), flush=True)


thread_id = "fixture-worker-" + uuid.uuid4().hex
for line in sys.stdin:
    message = json.loads(line)
    method, ident = message.get("method"), message.get("id")
    params = message.get("params", {})
    if method == "initialize":
        result = {"userAgent": "nema-synthetic-app-server"}
    elif method == "thread/start":
        result = {
            "thread": {"id": thread_id, "turns": [], "status": {"type": "idle"}, "environments": []},
            "sandbox": {"type": "readOnly", "networkAccess": False},
            "approvalPolicy": "never", "cwd": params["cwd"],
        }
    elif method == "mcpServerStatus/list":
        result = {"data": [], "nextCursor": None}
    elif method == "turn/start":
        turn_id = "fixture-turn-" + uuid.uuid4().hex
        emit({"id": ident, "result": {"turn": {"id": turn_id, "status": "inProgress"}}})
        prompt = params["input"][0]["text"]
        refs = sorted(set(re.findall(r"\[evidence:(\d+)\]", prompt)), key=int)
        citations = " ".join(f"[evidence:{value}]" for value in refs[:3])
        text = (
            "Synthetic specialist result — no model was called.\n\n"
            "Preserve the dispatch identity before sending native work. Recover a result "
            "from matching recorded completion; when delivery is uncertain, retain that "
            "uncertainty and require a separate deliberate investigation. An inner prepared "
            "checkpoint alone cannot prevent a second external call. " + citations
        )
        if "[synthetic-needs-evidence]" in prompt and "Explicit new native attempt in the same outer investigation." not in prompt:
            text = json.dumps({
                "schemaVersion": 1, "kind": "nema-needs-evidence",
                "question": "Which recorded acknowledgement or completion supports recovery after the missing reply?",
                "cause": "The selected design and crash records leave the observed recovery outcome unspecified.",
            })
        elif "[synthetic-needs-evidence]" in prompt and "Synthetic recovery observation:" in prompt:
            text = ("Synthetic specialist follow-up — no model was called.\n\n"
                    "The newly supplied fixture observation records a matching acknowledgement and completed turn. "
                    "That supports reconstructing the retained artifact from recorded evidence in this case. "
                    "It does not justify resending an uncertain attempt or establish exactly-once external execution. "
                    + citations)
        emit({"method": "item/completed", "params": {
            "threadId": thread_id, "turnId": turn_id,
            "item": {"id": "fixture-answer", "type": "agentMessage", "phase": "final_answer", "text": text},
            "futureNativeField": {"retained": True},
        }})
        emit({"method": "turn/completed", "params": {
            "threadId": thread_id,
            "turn": {"id": turn_id, "status": "completed", "error": None},
        }})
        continue
    elif method == "initialized" or ident is None:
        continue
    else:
        emit({"id": ident, "error": {"code": -32601, "message": "unsupported synthetic method"}})
        continue
    emit({"id": ident, "result": result})
