"""The store role prevents accidental public use; it is not OS authentication."""
from pathlib import Path
import shutil
import sqlite3

import pytest

from eidos.api import EidosAPI, thread_payload
from eidos.cli import main
from eidos.investigation import InvestigationStore
from eidos.trace import PRIVATE_CONTROL_APPLICATION_ID, PrivateTraceAccessError, TraceStore
from eidos.view import render_index_html, render_thread_html


def test_private_marker_precedes_sqlite_open_and_survives_copy(tmp_path, monkeypatch):
    path = tmp_path / "private.db"
    private = TraceStore(path, role="private-control")
    raw = '{ "method":"account/updated", "params":{"future":"CONTROL-CANARY"} }'
    record = private.append_line(source="private", direction="appserver_to_client", raw_text=raw)
    assert private.get(record.seq).raw_text == raw
    header = path.read_bytes()[:100]
    assert int.from_bytes(header[68:72], "big") == PRIVATE_CONTROL_APPLICATION_ID
    private.close()
    copied = tmp_path / "ordinary-name.db"
    shutil.copyfile(path, copied)
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    def forbidden(*args, **kwargs):
        pytest.fail("ordinary private-store rejection must precede sqlite open")
    monkeypatch.setattr(sqlite3, "connect", forbidden)
    for candidate in (path, copied):
        with pytest.raises(PrivateTraceAccessError):
            TraceStore(candidate)
    assert before == {p.name: p.read_bytes() for p in tmp_path.iterdir()}


def test_explicit_private_reopen_preserves_unknown_raw_fields(tmp_path):
    path = tmp_path / "private.db"
    raw = '{"id":7,"error":{"message":"PRIVATE-ERROR","future":[1,{"x":2}]}}'
    private = TraceStore(path, role="private-control")
    seq = private.append_line(source="private", direction="appserver_to_client", raw_text=raw).seq
    private.close()
    reopened = TraceStore(path, role="private-control")
    try:
        assert reopened.get(seq).raw_text == raw
        assert reopened.path == str(path.resolve())
    finally:
        reopened.close()


def test_ordinary_database_cannot_be_relabelled_private(tmp_path):
    path = tmp_path / "ordinary.db"
    ordinary = TraceStore(path)
    ordinary.append(source="fixture", direction="internal", message={"future": True})
    ordinary.close()
    before = path.read_bytes()
    with pytest.raises(ValueError, match="cannot become private"):
        TraceStore(path, role="private-control")
    assert path.read_bytes() == before
    reopened = TraceStore(path)
    try:
        assert reopened.get(1).message == {"future": True}
    finally:
        reopened.close()


@pytest.mark.parametrize("expose", [
    lambda store: EidosAPI(store),
    lambda store: InvestigationStore(store),
    lambda store: thread_payload(store, "private-thread"),
    lambda store: render_thread_html(store, "private-thread"),
    render_index_html,
])
def test_passing_open_private_store_to_public_surface_refused(expose):
    store = TraceStore(role="private-control")
    try:
        store.append(source="private", direction="appserver_to_client", message={
            "method": "account/updated", "params": {"threadId": "private-thread", "future": "CANARY"},
        })
        with pytest.raises(PrivateTraceAccessError):
            expose(store)
    finally:
        store.close()


@pytest.mark.parametrize("command", ["render", "import-jsonl", "serve"])
def test_ordinary_cli_refuses_private_database(tmp_path, command):
    path = tmp_path / "private.db"
    private = TraceStore(path, role="private-control")
    private.close()
    source = tmp_path / "input.jsonl"
    source.write_text('{"method":"untrusted"}\n')
    output = tmp_path / "output.html"
    args = {"render": ["private-thread", str(output)], "import-jsonl": [str(source)], "serve": []}[command]
    with pytest.raises(PrivateTraceAccessError):
        main([command, str(path), *args])
    assert not output.exists()


def test_empty_wal_database_is_marked_in_main_header_before_capture(tmp_path):
    path = tmp_path / "empty.db"
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.close()
    private = TraceStore(path, role="private-control")
    try:
        assert int.from_bytes(path.read_bytes()[68:72], "big") == PRIVATE_CONTROL_APPLICATION_ID
        with pytest.raises(PrivateTraceAccessError):
            TraceStore(path)
    finally:
        private.close()
