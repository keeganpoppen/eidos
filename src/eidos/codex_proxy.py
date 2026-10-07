from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys
import threading

from .trace import TraceStore


def proxy_stdio(command: list[str], *, trace_db: str | Path) -> int:
    """Transparent JSONL recorder/proxy around a child app-server process."""

    trace = TraceStore(trace_db)
    child = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        bufsize=1,
        env=os.environ.copy(),
    )
    assert child.stdin and child.stdout and child.stderr

    def stdout() -> None:
        for line in child.stdout:
            trace.append_line(source="codex-app-server", direction="appserver_to_client", raw_text=line)
            sys.stdout.write(line)
            sys.stdout.flush()

    def stderr() -> None:
        for line in child.stderr:
            sys.stderr.write(line)
            sys.stderr.flush()

    t_out = threading.Thread(target=stdout, daemon=True)
    t_err = threading.Thread(target=stderr, daemon=True)
    t_out.start()
    t_err.start()
    try:
        for line in sys.stdin:
            trace.append_line(source="codex-app-server", direction="client_to_appserver", raw_text=line)
            child.stdin.write(line)
            child.stdin.flush()
    finally:
        try:
            child.stdin.close()
        except OSError:
            pass
        code = child.wait()
        t_out.join(timeout=1)
        trace.close()
    return code


def main() -> None:
    parser = argparse.ArgumentParser(description="Record and proxy Codex app-server JSONL stdio")
    parser.add_argument("trace_db")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        command = ["codex", "app-server", "--listen", "stdio://"]
    raise SystemExit(proxy_stdio(command, trace_db=args.trace_db))


if __name__ == "__main__":
    main()
