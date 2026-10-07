from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import sys
import threading
import time

from .codex import AppServerClient, CodexPlace
from .codex_proxy import proxy_stdio
from .serve import serve
from .semantic_tree import SemanticTreeBuilder
from .trace import TraceStore
from .view import render_thread_html


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="eidos")
    sub = parser.add_subparsers(dest="command", required=True)

    p_serve = sub.add_parser("serve", help="serve the persisted trace UI")
    p_serve.add_argument("db")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8765)

    p_render = sub.add_parser("render", help="render one persisted thread to static HTML")
    p_render.add_argument("db")
    p_render.add_argument("thread_id")
    p_render.add_argument("output")

    p_import = sub.add_parser("import-jsonl", help="append native JSONL evidence")
    p_import.add_argument("db")
    p_import.add_argument("file")
    p_import.add_argument("--source", default="codex-app-server")
    p_import.add_argument(
        "--direction",
        default="appserver_to_client",
        choices=["client_to_appserver", "appserver_to_client", "provider_request", "provider_response", "internal"],
    )

    p_sync = sub.add_parser("codex-sync", help="hydrate existing Codex thread history into Eidos")
    p_sync.add_argument("db")
    p_sync.add_argument("thread_ids", nargs="*")
    p_sync.add_argument("--recent", type=int, default=0, help="sync this many recent threads when no IDs are supplied")
    p_sync.add_argument("--page-size", type=int, default=100)
    p_sync.add_argument("--codex", default="codex")

    p_proxy = sub.add_parser("codex-proxy", help="transparent recorded JSONL proxy")
    p_proxy.add_argument("db")
    p_proxy.add_argument("child", nargs=argparse.REMAINDER)

    p_observe = sub.add_parser(
        "codex-observe",
        help="build a hindsight-first semantic tree over a persisted thread",
    )
    p_observe.add_argument("db")
    p_observe.add_argument("thread_id")
    p_observe.add_argument("--codex", default="codex")

    args = parser.parse_args(argv)
    if args.command == "serve":
        serve(args.db, host=args.host, port=args.port)
        return
    if args.command == "render":
        store = TraceStore(args.db)
        try:
            Path(args.output).write_text(render_thread_html(store, args.thread_id))
        finally:
            store.close()
        return
    if args.command == "import-jsonl":
        store = TraceStore(args.db)
        try:
            with open(args.file, encoding="utf-8") as fh:
                count = store.import_jsonl(fh, source=args.source, direction=args.direction)
            print(f"imported {count} records")
        finally:
            store.close()
        return
    if args.command == "codex-proxy":
        child = args.child
        if child and child[0] == "--":
            child = child[1:]
        if not child:
            child = ["codex", "app-server", "--listen", "stdio://"]
        raise SystemExit(proxy_stdio(child, trace_db=args.db))
    if args.command == "codex-sync":
        store = TraceStore(args.db)
        client = AppServerClient([args.codex, "app-server", "--listen", "stdio://"], trace=store)
        try:
            with client:
                place = CodexPlace("local", client).start()
                ids = list(args.thread_ids)
                if not ids:
                    if args.recent <= 0:
                        parser.error("codex-sync requires thread IDs or --recent N")
                    ids = [t["id"] for t in place.list_threads(limit=args.recent) if isinstance(t.get("id"), str)]
                for thread_id in ids:
                    counts = place.sync_thread_history(thread_id, page_size=args.page_size)
                    print(f"{thread_id}: {counts['turns']} turns, {counts['items']} items")
        finally:
            store.close()
        return
    if args.command == "codex-observe":
        store = TraceStore(args.db)
        try:
            builder = SemanticTreeBuilder(
                store,
                command=[args.codex, "app-server", "--listen", "stdio://"],
            )

            started_at = time.monotonic()
            print_lock = threading.Lock()

            def progress(stage: str, current: int, total: int, detail: str) -> None:
                wall = datetime.now().astimezone().strftime("%H:%M:%S")
                elapsed = time.monotonic() - started_at
                with print_lock:
                    print(
                        f"{wall} +{elapsed:7.2f}s [{stage}] "
                        f"{current}/{total} {detail}",
                        file=sys.stderr,
                        flush=True,
                    )

            progress("start", 0, 1, f"thread {args.thread_id}")
            result = builder.build(args.thread_id, progress=progress)
            elapsed = time.monotonic() - started_at
            print(result.revision_id)
            print(
                f"done +{elapsed:.2f}s · "
                f"{result.leaf_windows} windows · "
                f"{result.leaf_episodes} surviving episodes · "
                f"{result.levels} rollup levels · "
                f"leaf-model={result.model or 'default'} · "
                f"synthesis-model={result.synthesis_model or 'default'} · "
                f"effort={result.leaf_effort}->{result.synthesis_effort}",
                file=sys.stderr,
                flush=True,
            )
        finally:
            store.close()
        return
    raise AssertionError(args.command)


if __name__ == "__main__":
    main(sys.argv[1:])
