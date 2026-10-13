"""Authored stdio fixture. No native executable, account, provider or network."""
import json
import os
from pathlib import Path
import sys
import time

mode = sys.argv[1]
if len(sys.argv) > 2:
    with Path(sys.argv[2]).open("a") as marker:
        marker.write("started\n")


def send(message):
    print(json.dumps(message), flush=True)


for line in sys.stdin:
    request = json.loads(line)
    ident, method = request.get("id"), request.get("method")
    if method == "initialize":
        os.write(2, b"PRIVATE_STDERR_CANARY  unknown bytes\t\n")
        print(' { "method" : "account/login/completed", "params": {"loginId":"PRIVATE_LOGIN_CANARY", "future": [1, {"code":"PRIVATE_CODE_CANARY"}]}} ', flush=True)
        send({"method": "account/updated", "params": {"account": {"futureIdentity": "PRIVATE_ACCOUNT_CANARY"}}})
        if mode in {"error", "rpc-error"}:
            send({"id": ident, "error": {"message": "PRIVATE_ERROR_CANARY", "future": ["preserve"]}})
        else:
            send({"id": ident, "result": {"userAgent": "authored-private-fixture", "futureConfig": "PRIVATE_CONFIG_CANARY"}})
    elif method == "thread/start":
        send({"id": ident, "result": {"thread": {"id": "private-fixture-thread", "environments": []},
              "cwd": os.getcwd(), "approvalPolicy": "never", "sandbox": {"type": "readOnly", "networkAccess": False}}})
    elif method == "mcpServerStatus/list":
        send({"id": ident, "result": {"data": [], "nextCursor": None}})
    elif method == "turn/start":
        if mode == "waiting":
            send({"id": ident, "result": {"turn": {"id": "private-fixture-turn", "status": "inProgress", "items": []}}})
            continue
        if mode == "malformed":
            os.write(1, b'{"PRIVATE_MALFORMED_CANARY":\xff}\n')
            continue
        turn = {"id": "private-fixture-turn", "status": "inProgress", "items": []}
        send({"id": ident, "result": {"turn": turn}})
        send({"method": "account/updated", "params": {"threadId": "private-fixture-thread", "turnId": turn["id"],
              "future": {"account": "PRIVATE_LATE_CANARY"}}})
        text = "Authored conclusion [evidence:7] [evidence:999]."
        if mode == "inquiry":
            text = json.dumps({"kind": "nema-needs-evidence", "schemaVersion": 1,
                               "question": "Which retained record supports the choice?", "cause": "The selected record is insufficient."})
        item = {"id": "private-fixture-answer", "type": "agentMessage", "phase": "final", "text": text,
                "futureControl": "PRIVATE_OUTPUT_UNKNOWN_CANARY"}
        send({"method": "item/completed", "params": {"threadId": "private-fixture-thread", "turnId": turn["id"], "item": item}})
        ending = {**turn, "status": "completed"}
        if mode == "failed":
            ending.update(status="failed", error={"message": "PRIVATE_TERMINAL_ERROR_CANARY"})
        send({"method": "turn/completed", "params": {"threadId": "private-fixture-thread", "turn": ending}})
        if mode == "late-failed":
            deadline = time.monotonic() + 3
            while not Path(sys.argv[3]).exists() and time.monotonic() < deadline:
                time.sleep(0.005)
            if Path(sys.argv[3]).exists():
                send({"method": "turn/completed", "params": {"threadId": "private-fixture-thread",
                      "turn": {**turn, "status": "failed", "error": {"message": "PRIVATE_LATE_FAILURE_CANARY"}}}})
