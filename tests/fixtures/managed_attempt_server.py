"""Authored managed preparation/turn packets. No native binary or network."""
import json
import os
from pathlib import Path
import sys
import threading
import time

directory = Path(sys.argv[1])
config = json.loads((directory / "config.json").read_text())
# Native config/read reports this resolved default although startup TOML omits
# the override. Keep the authored reply distinct from the requested bytes.
config.setdefault("chatgpt_base_url", "https://chatgpt.com/backend-api/")
mode = (directory / "mode").read_text() if (directory / "mode").exists() else "complete"
lock = threading.Lock()
reads = 0
with (directory / "launches").open("a") as stream:
    stream.write("authored process\n")


def send(message):
    with lock:
        print(json.dumps(message), flush=True)


def login_events():
    while not (directory / "release-login").exists():
        time.sleep(0.01)
    send({"method": "account/login/completed", "params": {"loginId": "authored-login", "success": True,
          "future": "PRIVATE_MANAGED_LOGIN_CANARY"}})
    send({"method": "account/updated", "params": {"authMode": "chatgpt", "planType": "free" if mode == "free" else "plus",
          "future": "PRIVATE_MANAGED_ACCOUNT_CANARY"}})


for line in sys.stdin:
    request = json.loads(line)
    with (directory / "requests.jsonl").open("a") as stream:
        stream.write(line)
    ident, method = request.get("id"), request.get("method")
    if method == "initialize":
        send({"id": ident, "result": {"userAgent": "authored-managed-attempt"}})
    elif method == "account/read":
        reads += 1
        send({"id": ident, "result": {"account": None if reads == 1 else {
            "type": "chatgpt", "planType": "free" if mode == "free" else "plus", "email": "fixture@example.invalid"},
            "requiresOpenaiAuth": True}})
    elif method == "config/read":
        send({"id": ident, "result": {"config": config, "future": "PRIVATE_MANAGED_CONFIG_CANARY"}})
    elif method == "account/login/start":
        send({"id": ident, "result": {"type": "chatgptDeviceCode", "loginId": "authored-login",
            "verificationUrl": "https://auth.openai.com/codex/device", "userCode": "NEMA-FIXTURE"}})
        threading.Thread(target=login_events, daemon=True).start()
    elif method == "thread/start":
        send({"id": ident, "result": {"thread": {"id": "managed-thread", "environments": []}, "cwd": os.getcwd(),
            "approvalPolicy": "never", "sandbox": {"type": "readOnly", "networkAccess": False}}})
    elif method == "mcpServerStatus/list":
        send({"id": ident, "result": {"data": [], "nextCursor": None}})
    elif method == "turn/start":
        send({"id": ident, "result": {"turn": {"id": "managed-turn", "status": "inProgress", "items": []}}})
        if mode != "waiting-turn":
            send({"method": "item/completed", "params": {"threadId": "managed-thread", "turnId": "managed-turn", "item": {
                "id": "answer", "type": "agentMessage", "phase": "final", "text": "Authored managed result [evidence:7].",
                "future": "PRIVATE_MANAGED_RESULT_CANARY"}}})
            send({"method": "turn/completed", "params": {"threadId": "managed-thread", "turn": {
                "id": "managed-turn", "status": "completed", "items": []}}})
