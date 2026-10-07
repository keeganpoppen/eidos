from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from .trace import TraceStore
from .view import render_index_html, render_thread_html


def serve(db: str | Path, *, host: str = "127.0.0.1", port: int = 8765) -> None:
    store = TraceStore(db)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            path = parsed.path
            if path == "/":
                html = render_index_html(store)
            elif path.startswith("/thread/"):
                revision = parse_qs(parsed.query).get("revision", [None])[0]
                html = render_thread_html(
                    store,
                    unquote(path[len("/thread/") :]),
                    revision_id=revision,
                )
            else:
                self.send_error(404)
                return
            body = html.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, fmt: str, *args: object) -> None:
            pass

    server = ThreadingHTTPServer((host, port), Handler)
    try:
        print(f"Eidos trace surface: http://{host}:{port}")
        server.serve_forever()
    finally:
        store.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Render Eidos persisted traces in a minimal alternate UI")
    parser.add_argument("db")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    serve(args.db, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
