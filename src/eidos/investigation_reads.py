"""Replaceable read projections for saved work; no authority or canonical writes."""
from __future__ import annotations

import base64
from contextlib import contextmanager
import hashlib
import json
from typing import Any, Iterator, Mapping

from .investigation import InvestigationError, InvestigationStore, _json, _text


class InvestigationReads:
    """Catalog metadata and conditional views over canonical investigation rows.

    SQLite triggers mark changed rows, including another connection's writes.
    Refresh parses each dirty owner once, then hot catalogs and unchanged views
    read only derived metadata. First migration and dirty-owner projection work
    are not constant-time. A source detail still parses its owning canonical row.
    """

    def __init__(self, investigations: InvestigationStore) -> None:
        self.investigations = investigations
        self.trace = investigations.trace
        with self.trace._lock:
            self.trace.db.executescript("""
                CREATE TABLE IF NOT EXISTS investigation_read_catalog(
                  id TEXT PRIMARY KEY,
                  created_at_ms INTEGER NOT NULL,
                  search_title TEXT NOT NULL,
                  version TEXT NOT NULL,
                  summary_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS investigation_read_catalog_order
                  ON investigation_read_catalog(created_at_ms DESC,id);
                CREATE TABLE IF NOT EXISTS investigation_read_artifacts(
                  investigation_id TEXT NOT NULL,
                  artifact_id TEXT NOT NULL,
                  created_at_ms INTEGER NOT NULL,
                  search_title TEXT NOT NULL,
                  summary_json TEXT NOT NULL,
                  PRIMARY KEY(investigation_id,artifact_id)
                );
                CREATE INDEX IF NOT EXISTS investigation_read_artifact_order
                  ON investigation_read_artifacts(created_at_ms DESC,investigation_id,artifact_id);
                CREATE TABLE IF NOT EXISTS investigation_read_dirty(id TEXT PRIMARY KEY);
                CREATE TRIGGER IF NOT EXISTS investigation_read_insert
                  AFTER INSERT ON investigations BEGIN
                    INSERT OR IGNORE INTO investigation_read_dirty VALUES(NEW.id);
                  END;
                CREATE TRIGGER IF NOT EXISTS investigation_read_update
                  AFTER UPDATE OF state_json ON investigations
                  WHEN OLD.state_json IS NOT NEW.state_json BEGIN
                    INSERT OR IGNORE INTO investigation_read_dirty VALUES(NEW.id);
                  END;
                CREATE TRIGGER IF NOT EXISTS investigation_read_delete
                  AFTER DELETE ON investigations BEGIN
                    DELETE FROM investigation_read_catalog WHERE id=OLD.id;
                    DELETE FROM investigation_read_artifacts WHERE investigation_id=OLD.id;
                    DELETE FROM investigation_read_dirty WHERE id=OLD.id;
                  END;
                INSERT OR IGNORE INTO investigation_read_dirty
                  SELECT id FROM investigations WHERE id NOT IN (SELECT id FROM investigation_read_catalog);
            """)

    @contextmanager
    def _snapshot(self) -> Iterator[None]:
        # The write transaction admits only replaceable projection maintenance;
        # it also binds metadata and canonical detail across independent writers.
        with self.trace._lock:
            self.trace.db.execute("BEGIN IMMEDIATE")
            try:
                yield
                self.trace.db.execute("COMMIT")
            except BaseException:
                self.trace.db.execute("ROLLBACK")
                raise

    @staticmethod
    def _artifacts(work: Mapping[str, Any]) -> list[dict[str, Any]]:
        values = (work.get("artifact"), work.get("nativeArtifact"), *work.get("artifactHistory", []))
        found = {}
        for value in values:
            if value and value["id"] not in found:
                found[value["id"]] = value
        return list(found.values())

    def _refresh(self, identifier: str | None = None) -> None:
        dirty = self.trace.db.execute(
            "SELECT id FROM investigation_read_dirty" + (" WHERE id=?" if identifier is not None else ""),
            (identifier,) if identifier is not None else (),
        ).fetchall()
        for item in dirty:
            row = self.trace.db.execute("SELECT id,state_json FROM investigations WHERE id=?", (item["id"],)).fetchone()
            if row is None:
                self.trace.db.execute("DELETE FROM investigation_read_dirty WHERE id=?", (item["id"],))
                continue
            work = json.loads(row["state_json"])
            version = "iv1_" + hashlib.sha256(row["state_json"].encode()).hexdigest()
            artifacts = self._artifacts(work)
            summary = {
                "id": work["id"], "title": work["title"], "status": work["status"],
                "createdAtMs": work["createdAtMs"], "currentContextId": work["currentContextId"],
                "contextCount": len(work["contexts"]), "artifactCount": len(artifacts),
                "attemptStatus": (work.get("attempt") or {}).get("status"),
                "hasInquiry": bool((work.get("continuation") or {}).get("inquiry")), "version": version,
            }
            self.trace.db.execute("INSERT OR REPLACE INTO investigation_read_catalog VALUES (?,?,?,?,?)",
                (work["id"], work["createdAtMs"], work["title"].casefold(), version, _json(summary)))
            self.trace.db.execute("DELETE FROM investigation_read_artifacts WHERE investigation_id=?", (work["id"],))
            for artifact in artifacts:
                item = {
                    "investigationId": work["id"], "investigationTitle": work["title"],
                    "artifactId": artifact["id"], "contextId": artifact["contextId"],
                    "attemptId": artifact["attemptId"], "createdAtMs": work["createdAtMs"],
                    **{key: artifact[key] for key in ("kind", "executionEvidence", "continuedFrom") if key in artifact},
                }
                self.trace.db.execute("INSERT INTO investigation_read_artifacts VALUES (?,?,?,?,?)",
                    (work["id"], artifact["id"], work["createdAtMs"], work["title"].casefold(), _json(item)))
            self.trace.db.execute("DELETE FROM investigation_read_dirty WHERE id=?", (row["id"],))

    def rebuild(self) -> None:
        """Trusted maintenance: discard projections without rewriting source state."""
        with self._snapshot():
            self.trace.db.execute("DELETE FROM investigation_read_catalog")
            self.trace.db.execute("DELETE FROM investigation_read_artifacts")
            self.trace.db.execute("INSERT OR IGNORE INTO investigation_read_dirty SELECT id FROM investigations")
            self._refresh()

    @staticmethod
    def _cursor(kind: str, query: str, after: list[Any]) -> str:
        raw = _json({"v": 1, "kind": kind, "query": query, "after": after}).encode()
        return base64.urlsafe_b64encode(raw).decode().rstrip("=")

    @staticmethod
    def _after(value: str | None, kind: str, query: str) -> list[Any] | None:
        if value is None:
            return None
        _text(value, "cursor", 2048)
        try:
            decoded = json.loads(base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True))
            after = decoded["after"]
            if (set(decoded) != {"v", "kind", "query", "after"} or type(decoded["v"]) is not int or decoded["v"] != 1
                    or decoded["kind"] != kind or decoded["query"] != query
                    or not isinstance(after, list) or len(after) != (3 if kind == "artifacts" else 2)
                    or type(after[0]) is not int or not 0 <= after[0] <= 2**63 - 1
                    or any(not isinstance(item, str) or not 1 <= len(item) <= 200 for item in after[1:])):
                raise ValueError
        except (ValueError, TypeError, KeyError, UnicodeError):
            raise InvestigationError(400, "cursor does not match this catalog query") from None
        return after

    @staticmethod
    def _params(query: Mapping[str, list[str]], allowed: set[str]) -> dict[str, str]:
        if set(query) - allowed or any(not isinstance(values, list) or len(values) != 1
                                      or not isinstance(values[0], str) for values in query.values()):
            raise InvestigationError(400, "unexpected or repeated read query parameter")
        return {key: values[0] for key, values in query.items()}

    def catalog(self, query: Mapping[str, list[str]], *, artifacts: bool = False) -> dict[str, Any]:
        params = self._params(query, {"limit", "q", "cursor", "knownVersion"})
        try:
            limit = int(params.get("limit", "20"))
        except ValueError:
            raise InvestigationError(400, "catalog limit must be between 1 and 40") from None
        if not 1 <= limit <= 40:
            raise InvestigationError(400, "catalog limit must be between 1 and 40")
        term = _text(params.get("q", ""), "q", 200, empty=True).strip().casefold()
        known = params.get("knownVersion")
        if known is not None:
            _text(known, "knownVersion", 200)
        kind = "artifacts" if artifacts else "investigations"
        after = self._after(params.get("cursor"), kind, term)
        owner = "investigation_id" if artifacts else "id"
        table = "investigation_read_artifacts" if artifacts else "investigation_read_catalog"
        clauses, arguments = ["instr(search_title, ?) > 0"], [term]
        if after:
            if artifacts:
                clauses.append(f"(created_at_ms < ? OR (created_at_ms = ? AND ({owner} > ? OR ({owner} = ? AND artifact_id > ?))))")
                arguments.extend([after[0], after[0], after[1], after[1], after[2]])
            else:
                clauses.append("(created_at_ms < ? OR (created_at_ms = ? AND id > ?))")
                arguments.extend([after[0], after[0], after[1]])
        with self._snapshot():
            self._refresh()
            rows = self.trace.db.execute(
                f"SELECT * FROM {table} WHERE {' AND '.join(clauses)} ORDER BY created_at_ms DESC,{owner}"
                + (",artifact_id" if artifacts else "") + " LIMIT ?", (*arguments, limit + 1),
            ).fetchall()
            values = [json.loads(row["summary_json"]) for row in rows[:limit]]
            next_cursor = None
            if len(rows) > limit:
                last = rows[limit - 1]
                key = [last["created_at_ms"], last[owner]] + ([last["artifact_id"]] if artifacts else [])
                next_cursor = self._cursor(kind, term, key)
            content = {kind: values, "nextCursor": next_cursor}
            version = "ic1_" + hashlib.sha256(_json({
                "kind": kind, "query": term, "cursor": params.get("cursor"), "limit": limit, **content,
            }).encode()).hexdigest()
            if known == version:
                return {"version": version, "unchanged": True}
            return {"version": version, "unchanged": False, **content}

    def _version(self, identifier: str) -> str:
        self._refresh(identifier)
        row = self.trace.db.execute("SELECT version FROM investigation_read_catalog WHERE id=?", (identifier,)).fetchone()
        if row is None:
            raise InvestigationError(404, "investigation not found")
        return row["version"]

    def view(self, identifier: str, query: Mapping[str, list[str]]) -> dict[str, Any]:
        params = self._params(query, {"knownVersion"})
        known = params.get("knownVersion")
        if known is not None:
            _text(known, "knownVersion", 200)
        with self._snapshot():
            version = self._version(identifier)
            if known == version:
                return {"version": version, "unchanged": True}
            return {"version": version, "unchanged": False, "investigation": self.investigations._load(identifier)}

    def source(self, identifier: str, artifact_id: str, query: Mapping[str, list[str]]) -> dict[str, Any]:
        params = self._params(query, {"contextId"})
        expected = params.get("contextId")
        if expected is not None:
            _text(expected, "contextId", 200)
        with self._snapshot():
            version = self._version(identifier)
            work = self.investigations._load(identifier)
            artifact = next((value for value in self._artifacts(work) if value["id"] == artifact_id), None)
            if artifact is None:
                raise InvestigationError(404, "exact artifact does not belong to the selected investigation")
            context = next((c for c in work["contexts"] if c["id"] == artifact["contextId"]), None)
            attempt = next((a for a in (work.get("attempt"), *work.get("attemptHistory", []))
                            if a and a["id"] == artifact["attemptId"]), None)
            if (not context or not attempt or attempt["contextId"] != context["id"]
                    or expected is not None and expected != context["id"]):
                raise InvestigationError(409, "artifact/context/attempt provenance mismatch")
            adoption = work.get("adoption")
            return {"version": version, "investigationId": identifier, "investigationTitle": work["title"],
                    "artifact": artifact, "context": context, "attempt": attempt,
                    "adoption": adoption if adoption and adoption["artifactId"] == artifact_id else None}
