from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from .api import EidosAPI
from .trace import TraceStore
from .view import render_index_html, render_thread_html


def local_request_error(method: str, headers: object) -> str | None:
    """Browser-origin admission for the trusted loopback workbench.

    This blocks cross-site form posts and DNS rebinding; it is not user
    authentication or protection from other processes owned by the user.
    """
    host = headers.get("Host", "")  # type: ignore[attr-defined]
    try:
        authority = urlparse(f"http://{host}")
        authority.port
    except ValueError:
        return "invalid loopback Host"
    if authority.hostname not in {"localhost", "127.0.0.1", "::1"} or authority.username or authority.path:
        return "the workbench requires a loopback Host"
    origin = headers.get("Origin")  # type: ignore[attr-defined]
    if origin:
        try:
            parsed = urlparse(origin)
            port = parsed.port
        except ValueError:
            return "invalid request origin"
        if parsed.scheme not in {"http", "https"} or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
            return "cross-origin workbench access is not allowed"
        if parsed.netloc != host and port != 5173:
            return "origin must match the workbench or its local development UI"
    if method == "POST":
        content_type = headers.get("Content-Type", "").split(";", 1)[0].strip().lower()  # type: ignore[attr-defined]
        if content_type != "application/json":
            return "workbench mutations require application/json"
    return None


def serve(
    db: str | Path,
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    codex: str = "codex",
) -> None:
    if host not in {"127.0.0.1", "localhost"}:
        raise ValueError("the unauthenticated workbench must bind to loopback")
    store = TraceStore(db)
    api = EidosAPI(store, codex=codex)

    class Handler(BaseHTTPRequestHandler):
        def _send_json(self, status: int, payload: object) -> None:
            body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_html(self, html: str) -> None:
            body = html.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _dispatch_api(self, method: str, parsed: object) -> bool:
            path = parsed.path  # type: ignore[attr-defined]
            if not path.startswith("/api/"):
                return False
            rejection = local_request_error(method, self.headers)
            if rejection:
                self._send_json(403, {"error": rejection})
                return True
            try:
                status, payload = api.dispatch(
                    self,
                    method,
                    path,
                    parse_qs(parsed.query, keep_blank_values=True),  # type: ignore[attr-defined]
                )
            except json.JSONDecodeError as exc:
                self._send_json(400, {"error": f"invalid JSON: {exc}"})
            except ValueError as exc:
                self._send_json(400, {"error": str(exc)})
            except Exception as exc:
                self._send_json(
                    500,
                    {"error": f"{type(exc).__name__}: {exc}"},
                )
            else:
                self._send_json(status, payload)
            return True

        def do_GET(self) -> None:  # noqa: N802
            rejection = local_request_error("GET", self.headers)
            if rejection:
                self._send_json(403, {"error": rejection})
                return
            parsed = urlparse(self.path)
            if self._dispatch_api("GET", parsed):
                return
            path = parsed.path
            if path == "/":
                self._send_html(render_index_html(store))
            elif path.startswith("/thread/"):
                revision = parse_qs(parsed.query).get("revision", [None])[0]
                self._send_html(
                    render_thread_html(
                        store,
                        unquote(path[len("/thread/") :]),
                        revision_id=revision,
                    )
                )
            else:
                self.send_error(404)

        def do_POST(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if self._dispatch_api("POST", parsed):
                return
            self.send_error(404)

        def log_message(self, fmt: str, *args: object) -> None:
            pass

    server = ThreadingHTTPServer((host, port), Handler)
    try:
        print(f"Eidos API / fallback trace surface: http://{host}:{port}")
        server.serve_forever()
    finally:
        api.close()
        store.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve Eidos persisted traces and live chat API")
    parser.add_argument("db")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--codex", default="codex")
    args = parser.parse_args()
    serve(args.db, host=args.host, port=args.port, codex=args.codex)


if __name__ == "__main__":
    main()
