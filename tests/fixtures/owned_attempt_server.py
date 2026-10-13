"""Authored device-login-shaped stdio server; no native, network or credentials."""
import json
import os
from pathlib import Path
import sys
import threading
import time

mode, directory = sys.argv[1], Path(sys.argv[2])
directory.mkdir(parents=True, exist_ok=True)
with (directory / "launches").open("a") as output:
    output.write("started\n")
lock = threading.Lock()


def send(message):
    with lock:
        print(json.dumps(message), flush=True)


def login_events():
    while not (directory / "release-login").exists():
        time.sleep(0.005)
    send({"method": "account/login/completed", "params": {"loginId": "authored-login", "success": True,
          "future": "PRIVATE_OWNED_LOGIN_CANARY"}})
    send({"method": "account/updated", "params": {"authMode": "chatgpt", "planType": "plus",
          "future": "PRIVATE_OWNED_ACCOUNT_CANARY"}})


for line in sys.stdin:
    request = json.loads(line)
    with (directory / "requests.jsonl").open("a") as output:
        output.write(line)
    ident, method = request.get("id"), request.get("method")
    if method == "initialize":
        send({"id": ident, "result": {"userAgent": "authored-owned-attempt"}})
    elif method == "account/login/start":
        if mode != "blocked-rpc":
            send({"id": ident, "result": {"loginId": "authored-login", "verificationUri": "https://fixture.invalid",
                  "userCode": "PRIVATE_OWNED_CODE_CANARY"}})
            threading.Thread(target=login_events, daemon=True).start()
    elif method == "account/read":
        send({"id": ident, "result": {"account": {"type": "chatgpt", "planType": "plus"}, "requiresOpenaiAuth": True}})
    elif method == "config/read":
        send({"id": ident, "result": {"config": {}, "future": "PRIVATE_OWNED_CONFIG_CANARY"}})
    elif method == "account/login/cancel":
        send({"id": ident, "result": {}})
    elif method == "thread/start":
        send({"id": ident, "result": {"thread": {"id": "owned-thread", "environments": []},
              "cwd": os.getcwd(), "approvalPolicy": "never", "sandbox": {"type": "readOnly", "networkAccess": False}}})
    elif method == "mcpServerStatus/list":
        send({"id": ident, "result": {"data": [], "nextCursor": None}})
    elif method == "turn/start":
        send({"id": ident, "result": {"turn": {"id": "owned-turn", "status": "inProgress", "items": []}}})
        if mode != "waiting-turn":
            send({"method": "item/completed", "params": {"threadId": "owned-thread", "turnId": "owned-turn",
                  "item": {"id": "answer", "type": "agentMessage", "phase": "final", "text": "Authored result [evidence:7]."}}})
            send({"method": "turn/completed", "params": {"threadId": "owned-thread", "turn": {
                  "id": "owned-turn", "status": "completed", "items": []}}})
