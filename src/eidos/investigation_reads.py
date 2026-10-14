"""Replaceable read projections for saved work; no authority or canonical writes."""
from __future__ import annotations

import base64
from contextlib import contextmanager
import hashlib
import json
from typing import Any, Iterator, Mapping

from .investigation import InvestigationError, InvestigationStore, _json, _text
from .investigation_artifacts import FINDING_KIND, artifacts, resolve_artifact, validate_frozen_finding


USES_SCOPE = "direct-frozen-artifact-inputs/v1"
MAX_USES_BYTES = 128 * 1024
MAX_USES_CURSOR = 16 * 1024


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
                CREATE TABLE IF NOT EXISTS investigation_read_result_search(
                  investigation_id TEXT NOT NULL,
                  artifact_id TEXT NOT NULL,
                  question TEXT NOT NULL,
                  result_text TEXT NOT NULL,
                  search_question TEXT NOT NULL,
                  search_result TEXT NOT NULL,
                  PRIMARY KEY(investigation_id,artifact_id)
                );
                CREATE TABLE IF NOT EXISTS investigation_read_dirty(id TEXT PRIMARY KEY);
                CREATE TABLE IF NOT EXISTS investigation_read_result_uses(
                  source_owner TEXT NOT NULL,
                  artifact_id TEXT NOT NULL,
                  consumer_owner TEXT NOT NULL,
                  context_id TEXT NOT NULL,
                  created_at_ms INTEGER NOT NULL,
                  owner_version TEXT NOT NULL,
                  summary_json TEXT NOT NULL,
                  PRIMARY KEY(source_owner,artifact_id,consumer_owner,context_id)
                );
                CREATE INDEX IF NOT EXISTS investigation_read_result_uses_order
                  ON investigation_read_result_uses(source_owner,artifact_id,created_at_ms DESC,consumer_owner,context_id);
                CREATE TABLE IF NOT EXISTS investigation_read_result_use_owners(
                  owner_id TEXT PRIMARY KEY,
                  projection_version INTEGER NOT NULL,
                  error TEXT
                );
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
                CREATE TRIGGER IF NOT EXISTS investigation_read_result_search_delete
                  AFTER DELETE ON investigations BEGIN
                    DELETE FROM investigation_read_result_search WHERE investigation_id=OLD.id;
                  END;
                CREATE TRIGGER IF NOT EXISTS investigation_read_result_uses_delete
                  AFTER DELETE ON investigations BEGIN
                    DELETE FROM investigation_read_result_uses WHERE consumer_owner=OLD.id;
                    DELETE FROM investigation_read_result_use_owners WHERE owner_id=OLD.id;
                  END;
                INSERT OR IGNORE INTO investigation_read_dirty
                  SELECT id FROM investigations WHERE id NOT IN (SELECT id FROM investigation_read_catalog);
                INSERT OR IGNORE INTO investigation_read_dirty
                  SELECT DISTINCT investigation_id FROM investigation_read_artifacts AS a
                  WHERE NOT EXISTS (SELECT 1 FROM investigation_read_result_search AS s
                    WHERE s.investigation_id=a.investigation_id AND s.artifact_id=a.artifact_id);
                INSERT OR IGNORE INTO investigation_read_dirty
                  SELECT id FROM investigations WHERE NOT EXISTS (
                    SELECT 1 FROM investigation_read_result_use_owners
                    WHERE owner_id=investigations.id AND projection_version=1);
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
        return artifacts(work)

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
            try:
                self._refresh_uses(work, version)
            except InvestigationError as error:
                # Legacy catalogs intentionally ignore frozen input contents.
                # Preserve that behavior; new uses reads refuse incomplete data.
                self.trace.db.execute("DELETE FROM investigation_read_result_uses WHERE consumer_owner=?", (work["id"],))
                self.trace.db.execute("INSERT OR REPLACE INTO investigation_read_result_use_owners VALUES (?,1,?)",
                    (work["id"], error.message))
            artifacts = self._artifacts(work)
            contexts = {context["id"]: context for context in work["contexts"]}
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
            self.trace.db.execute("DELETE FROM investigation_read_result_search WHERE investigation_id=?", (work["id"],))
            for artifact in artifacts:
                item = {
                    "investigationId": work["id"], "investigationTitle": work["title"],
                    "artifactId": artifact["id"], "contextId": artifact["contextId"],
                    "attemptId": artifact.get("attemptId"), "createdAtMs": work["createdAtMs"],
                    **{key: artifact[key] for key in ("kind", "executionEvidence", "continuedFrom") if key in artifact},
                }
                self.trace.db.execute("INSERT INTO investigation_read_artifacts VALUES (?,?,?,?,?)",
                    (work["id"], artifact["id"], work["createdAtMs"], work["title"].casefold(), _json(item)))
                # Only the exact result and its own question are searchable.
                # No raw records, inherited inputs or unknown fields enter here.
                question = contexts.get(artifact["contextId"], {}).get("question", "")
                text = artifact["text"]
                self.trace.db.execute("INSERT INTO investigation_read_result_search VALUES (?,?,?,?,?,?)",
                    (work["id"], artifact["id"], question, text, question.casefold(), text.casefold()))
            self.trace.db.execute("DELETE FROM investigation_read_dirty WHERE id=?", (row["id"],))

    def rebuild(self) -> None:
        """Trusted maintenance: discard projections without rewriting source state."""
        with self._snapshot():
            self.trace.db.execute("DELETE FROM investigation_read_catalog")
            self.trace.db.execute("DELETE FROM investigation_read_artifacts")
            self.trace.db.execute("DELETE FROM investigation_read_result_search")
            self.trace.db.execute("DELETE FROM investigation_read_result_uses")
            self.trace.db.execute("DELETE FROM investigation_read_result_use_owners")
            self.trace.db.execute("INSERT OR IGNORE INTO investigation_read_dirty SELECT id FROM investigations")
            self._refresh()

    @staticmethod
    def _preview(value: Any) -> str:
        if not isinstance(value, str):
            raise InvestigationError(409, "saved result use has malformed text")
        try:
            value.encode("utf-8")
        except UnicodeError:
            raise InvestigationError(409, "saved result use has invalid UTF-8 text") from None
        return value if len(value) <= 240 else value[:239] + "…"

    @staticmethod
    def _use_identity(value: Any) -> str:
        try:
            return _text(value, "saved result-use identity", 200)
        except InvestigationError:
            raise InvestigationError(409, "saved result use has malformed identity") from None

    @staticmethod
    def _use_contexts(work: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
        contexts = work.get("contexts")
        if not isinstance(contexts, list):
            raise InvestigationError(409, "saved result use has malformed contexts")
        found = {}
        for context in contexts:
            if not isinstance(context, dict):
                raise InvestigationError(409, "saved result use has malformed context identity")
            InvestigationReads._use_identity(context.get("id"))
            if context["id"] in found and _json(found[context["id"]]) != _json(context):
                raise InvestigationError(409, "saved context identity is ambiguous")
            found[context["id"]] = context
        return found

    @staticmethod
    def _use_inputs(context: Mapping[str, Any]) -> list[dict[str, Any]]:
        inputs = context.get("artifactInputs", [])
        if not isinstance(inputs, list):
            raise InvestigationError(409, "saved result inputs are malformed")
        required = {"investigationId", "artifactId", "rationale", "artifact", "sourceContextId",
                    "sourceManifestId", "sourceAttemptManifestId", "sourceAdoption"}
        for item in inputs:
            if (not isinstance(item, dict) or not required <= set(item)
                    or any(not isinstance(item[key], str) or not item[key] for key in ("investigationId", "artifactId", "sourceContextId"))
                    or not isinstance(item["rationale"], str)
                    or any(item[key] is not None and not isinstance(item[key], str)
                           for key in ("sourceManifestId", "sourceAttemptManifestId"))):
                raise InvestigationError(409, "saved result input snapshot is malformed")
            for key in ("investigationId", "artifactId", "sourceContextId"):
                InvestigationReads._use_identity(item[key])
            artifact = item["artifact"]
            adoption = item["sourceAdoption"]
            if (not isinstance(artifact, dict) or artifact.get("id") != item["artifactId"]
                    or artifact.get("contextId") != item["sourceContextId"]
                    or not isinstance(artifact.get("text"), str)
                    or not isinstance(artifact.get("citations"), list)
                    or not isinstance(artifact.get("unsupportedCitations"), list)
                    or adoption is not None and (not isinstance(adoption, dict) or adoption.get("artifactId") != item["artifactId"])):
                raise InvestigationError(409, "saved result input snapshot does not match its reference")
            if (any(type(seq) is not int or not 0 <= seq <= 2**63 - 1
                    for key in ("citations", "unsupportedCitations") for seq in artifact[key])
                    or adoption is not None and (adoption.get("decision") not in ("adopt", "reject")
                                                or not isinstance(adoption.get("note"), str))):
                raise InvestigationError(409, "saved result input snapshot is malformed")
            if artifact.get("kind") == FINDING_KIND:
                validate_frozen_finding(item["investigationId"], artifact)
            try:
                _json(item).encode("utf-8")
            except (ValueError, TypeError, UnicodeError, RecursionError):
                raise InvestigationError(409, "saved result input snapshot has invalid text") from None
        return inputs

    def _refresh_uses(self, work: Mapping[str, Any], version: str) -> None:
        """Index consumer-owned frozen values; never resolve their current sources."""
        self._use_identity(work.get("id"))
        if type(work.get("createdAtMs")) is not int or not 0 <= work["createdAtMs"] <= 2**63 - 1:
            raise InvestigationError(409, "saved result use has malformed creation time")
        self.trace.db.execute("DELETE FROM investigation_read_result_uses WHERE consumer_owner=?", (work["id"],))
        for context_id, context in self._use_contexts(work).items():
            grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
            for item in self._use_inputs(context):
                grouped.setdefault((item["investigationId"], item["artifactId"]), []).append(item)
            for (source, artifact), inputs in grouped.items():
                summary = {"investigationId": work["id"], "investigationTitle": self._preview(work.get("title")),
                    "contextId": context_id, "ownerVersion": version, "isCurrent": context_id == work["currentContextId"],
                    "questionExcerpt": self._preview(context.get("question")), "rationaleExcerpt": self._preview(inputs[0]["rationale"]),
                    "matchingInputCount": len(inputs)}
                self.trace.db.execute("INSERT INTO investigation_read_result_uses VALUES (?,?,?,?,?,?,?)",
                    (source, artifact, work["id"], context_id, work["createdAtMs"], version, _json(summary)))
        self.trace.db.execute("INSERT OR REPLACE INTO investigation_read_result_use_owners VALUES (?,1,NULL)", (work["id"],))

    @staticmethod
    def _use_source(identifier: str, artifact_id: str) -> dict[str, str]:
        # Names identify a reference, even when its original owner is unavailable.
        return {"investigationId": _text(identifier, "investigationId", 200),
                "artifactId": _text(artifact_id, "artifactId", 200)}

    @staticmethod
    def _use_cursor(source: Mapping[str, str], limit: int, relation: str, row: Any) -> str:
        return base64.urlsafe_b64encode(_json({"v": 1, "scope": USES_SCOPE, "source": source, "limit": limit,
            "relationVersion": relation, "after": [row["created_at_ms"], row["consumer_owner"], row["context_id"]]}).encode()).decode().rstrip("=")

    @staticmethod
    def _read_use_cursor(value: str, source: Mapping[str, str], limit: int) -> dict[str, Any]:
        _text(value, "cursor", MAX_USES_CURSOR)
        try:
            cursor = json.loads(base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True))
            if (not isinstance(cursor, dict) or set(cursor) != {"v", "scope", "source", "limit", "relationVersion", "after"}
                    or type(cursor["v"]) is not int or cursor["v"] != 1 or cursor["scope"] != USES_SCOPE
                    or cursor["source"] != source or type(cursor["limit"]) is not int or cursor["limit"] != limit
                    or not isinstance(cursor["relationVersion"], str) or not cursor["relationVersion"].startswith("ur1_")
                    or len(cursor["relationVersion"]) != 68
                    or any(c not in "0123456789abcdef" for c in cursor["relationVersion"][4:])
                    or not isinstance(cursor["after"], list) or len(cursor["after"]) != 3
                    or type(cursor["after"][0]) is not int or not 0 <= cursor["after"][0] <= 2**63 - 1
                    or any(not isinstance(v, str) or not v.strip() or len(v) > 200 for v in cursor["after"][1:])):
                raise ValueError
            for value in cursor["after"][1:]:
                value.encode("utf-8")
        except (ValueError, TypeError, KeyError, UnicodeError, RecursionError):
            raise InvestigationError(400, "cursor does not match this result-use query") from None
        return cursor

    def uses(self, identifier: str, artifact_id: str, query: Mapping[str, list[str]]) -> dict[str, Any]:
        self.trace.require_workbench()
        source = self._use_source(identifier, artifact_id)
        params = self._params(query, {"limit", "cursor", "knownVersion"})
        try:
            limit = int(params.get("limit", "20"))
        except ValueError:
            raise InvestigationError(400, "result-use limit must be between 1 and 40") from None
        if not 1 <= limit <= 40:
            raise InvestigationError(400, "result-use limit must be between 1 and 40")
        if "knownVersion" in params:
            _text(params["knownVersion"], "knownVersion", 200)
        cursor = self._read_use_cursor(params["cursor"], source, limit) if "cursor" in params else None
        with self._snapshot():
            self._refresh()
            if self.trace.db.execute("SELECT 1 FROM investigation_read_result_use_owners WHERE error IS NOT NULL LIMIT 1").fetchone():
                raise InvestigationError(409, "saved result uses cannot be listed while a consumer projection is malformed")
            # O(matching contexts) metadata work; no warm canonical-history parse.
            members = self.trace.db.execute("SELECT consumer_owner,context_id,owner_version FROM investigation_read_result_uses "
                "WHERE source_owner=? AND artifact_id=? ORDER BY consumer_owner,context_id", (identifier, artifact_id)).fetchall()
            relation = "ur1_" + hashlib.sha256(_json({"scope": USES_SCOPE, "source": source,
                "members": [list(row) for row in members]}).encode()).hexdigest()
            if cursor and cursor["relationVersion"] != relation:
                raise InvestigationError(409, "saved result uses changed; restart from the first page")
            where, args = "source_owner=? AND artifact_id=?", [identifier, artifact_id]
            if cursor:
                created, owner, context = cursor["after"]
                where += " AND (created_at_ms < ? OR (created_at_ms = ? AND (consumer_owner > ? OR (consumer_owner = ? AND context_id > ?))))"
                args.extend([created, created, owner, owner, context])
            rows = self.trace.db.execute("SELECT * FROM investigation_read_result_uses WHERE " + where
                + " ORDER BY created_at_ms DESC,consumer_owner,context_id LIMIT ?", (*args, limit + 1)).fetchall()
            count = min(limit, len(rows))
            values = [json.loads(row["summary_json"]) for row in rows[:count]]
            while True:
                next_cursor = self._use_cursor(source, limit, relation, rows[count - 1]) if count and len(rows) > count else None
                content = {"scope": USES_SCOPE, "source": source, "uses": values[:count], "nextCursor": next_cursor}
                version = "up1_" + hashlib.sha256(_json({"page": params.get("cursor"), "limit": limit, **content}).encode()).hexdigest()
                envelope = {**content, "version": version, "unchanged": False}
                if len(_json(envelope).encode()) <= MAX_USES_BYTES:
                    break
                if count <= 1:
                    raise InvestigationError(413, "result-use metadata exceeds the 128 KiB response limit")
                count -= 1
            if params.get("knownVersion") == version:
                return {"scope": USES_SCOPE, "source": source, "version": version, "unchanged": True}
            return envelope

    def use_context(self, identifier: str, artifact_id: str, consumer_id: str, context_id: str,
                    query: Mapping[str, list[str]]) -> dict[str, Any]:
        self.trace.require_workbench()
        source = self._use_source(identifier, artifact_id)
        _text(consumer_id, "investigationId", 200)
        _text(context_id, "contextId", 200)
        params = self._params(query, {"expectedVersion"})
        if set(params) != {"expectedVersion"}:
            raise InvestigationError(400, "exact saved use requires expectedVersion")
        expected = _text(params["expectedVersion"], "expectedVersion", 200)
        with self._snapshot():
            version = self._version(consumer_id)
            failure = self.trace.db.execute("SELECT error FROM investigation_read_result_use_owners WHERE owner_id=?", (consumer_id,)).fetchone()
            if failure is not None and failure["error"] is not None:
                raise InvestigationError(409, "saved consumer result inputs are malformed")
            work = self.investigations._load(consumer_id)
            context = self._use_contexts(work).get(context_id)
            if context is None:
                raise InvestigationError(404, "exact saved consumer context not found")
            if expected != version:
                raise InvestigationError(409, "saved consumer changed; refresh its result uses")
            indexes = [index for index, item in enumerate(self._use_inputs(context))
                       if item["investigationId"] == identifier and item["artifactId"] == artifact_id]
            if not indexes:
                raise InvestigationError(409, "exact saved context did not supply this result")
            return {"scope": USES_SCOPE, "source": source, "investigationId": consumer_id,
                    "investigationTitle": work["title"], "contextId": context_id, "ownerVersion": version,
                    "isCurrent": work["currentContextId"] == context_id, "context": context, "matchingInputIndexes": indexes}

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
                    or not isinstance(after, list) or len(after) != (3 if kind in {"artifacts", "artifact-content/1"} else 2)
                    or type(after[0]) is not int or not 0 <= after[0] <= 2**63 - 1
                    or any(not isinstance(item, str) or not 1 <= len(item) <= 200 for item in after[1:])):
                raise ValueError
        except (ValueError, TypeError, KeyError, UnicodeError):
            raise InvestigationError(400, "cursor does not match this catalog query") from None
        return after

    @staticmethod
    def _excerpt(value: str, term: str) -> str:
        """Locate literal casefold text without treating folded offsets as originals."""
        found = value.casefold().find(term)
        if found < 0:
            raise ValueError("search projection does not contain its matched term")
        folded = 0
        start = 0
        end = len(value)
        for index, character in enumerate(value):
            following = folded + len(character.casefold())
            if folded <= found < following:
                start = index
            if following >= found + len(term):
                end = index + 1
                break
            folded = following
        # Reserve two positions for omission markers. A casefold-expanded
        # match may itself exceed this bound; show its beginning honestly.
        left = max(0, start - max(0, 238 - (end - start)) // 2)
        right = min(len(value), left + 238)
        left = max(0, right - 238)
        return ("…" if left else "") + value[left:right] + ("…" if right < len(value) else "")

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
        content_search = artifacts and bool(term)
        cursor_kind = "artifact-content/1" if content_search else kind
        after = self._after(params.get("cursor"), cursor_kind, term)
        owner = "investigation_id" if artifacts else "id"
        table = "investigation_read_artifacts" if artifacts else "investigation_read_catalog"
        clauses, arguments = ["instr(search_title, ?) > 0"], [term]
        if content_search:
            clauses = ["(instr(search_title, ?) > 0 OR instr(search_question, ?) > 0 OR instr(search_result, ?) > 0)"]
            arguments = [term, term, term]
            table += " JOIN investigation_read_result_search USING(investigation_id,artifact_id)"
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
                f"SELECT created_at_ms,{owner},summary_json" + (",artifact_id" if artifacts else "")
                + (",search_title,question,result_text,search_question" if content_search else "")
                + f" FROM {table} WHERE {' AND '.join(clauses)} ORDER BY created_at_ms DESC,{owner}"
                + (",artifact_id" if artifacts else "") + " LIMIT ?", (*arguments, limit + 1),
            ).fetchall()
            values = [json.loads(row["summary_json"]) for row in rows[:limit]]
            if content_search:
                for row, value in zip(rows, values):
                    if term in row["search_title"]:
                        field, text = "title", value["investigationTitle"]
                    elif term in row["search_question"]:
                        field, text = "question", row["question"]
                    else:
                        field, text = "result", row["result_text"]
                    value["match"] = {"field": field, "excerpt": self._excerpt(text, term)}
            next_cursor = None
            if len(rows) > limit:
                last = rows[limit - 1]
                key = [last["created_at_ms"], last[owner]] + ([last["artifact_id"]] if artifacts else [])
                next_cursor = self._cursor(cursor_kind, term, key)
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
            artifact, context, attempt = resolve_artifact(work, artifact_id, expected_context=expected)
            adoption = work.get("adoption") if attempt is not None else None
            return {"version": version, "investigationId": identifier, "investigationTitle": work["title"],
                    "artifact": artifact, "context": context, "attempt": attempt,
                    "adoption": adoption if adoption and adoption["artifactId"] == artifact_id else None}
