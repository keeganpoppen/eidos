from __future__ import annotations

"""Immutable context descriptions and temporal annotations over TraceStore.

This is a trusted-host persistence API, not an instruction loader, native
controller, or authority registry. Evidence validation checks provenance and
boundary, not the truth of a caller's interpretation of a trace. See
docs/agents/CONTEXT_MANIFEST_CONTRACT.md for the integration contract.
"""

from contextlib import contextmanager
from dataclasses import asdict, dataclass
from enum import Enum
import hashlib
import json
import math
from typing import Any, Iterator, Mapping
import uuid

from .core import Name, Role
from .trace import TraceStore


class KnowledgeState(str, Enum):
    AVAILABLE = "AVAILABLE"
    SELECTED = "SELECTED"
    PROJECTED = "PROJECTED"
    OBSERVED = "OBSERVED"
    INFERRED = "INFERRED"


class Boundary(str, Enum):
    LOCAL = "local"
    APP_SERVER = "app_server"
    PROVIDER = "provider"


@dataclass(frozen=True)
class RuntimeIdentity:
    """Captured coordinates; None means unknown, never a synthesized native ID.

    process_name identifies logical work; incarnation_id identifies one host
    lifetime. A turn may contain several requests, each with several attempts.
    All names are descriptive and allocated by the owning runtime, not here.
    """

    process_name: str | None = None
    incarnation_id: str | None = None
    thread_id: str | None = None
    turn_id: str | None = None
    request_id: str | None = None
    attempt_id: str | None = None

    def __post_init__(self) -> None:
        for value in asdict(self).values():
            if value is not None:
                _text(value, "runtime identity")


@dataclass(frozen=True)
class ContextObject:
    cid: str
    kind: str
    data_json: str
    refs: tuple[tuple[str, str], ...]

    @property
    def data(self) -> Any:
        """Return a detached value: callers cannot mutate historical content."""
        return json.loads(self.data_json)

    def ref(self, label: str) -> str:
        return dict(self.refs)[label]


@dataclass(frozen=True)
class ContextManifest:
    cid: str
    root: str


@dataclass(frozen=True)
class ContextChange:
    path: str
    before: str | None
    after: str | None

    @property
    def operation(self) -> str:
        return "add" if self.before is None else "remove" if self.after is None else "replace"


@dataclass(frozen=True)
class Conflict:
    facet: str
    claim_ids: tuple[str, ...]
    scope_uncertain: bool = False


@dataclass(frozen=True)
class SlotInspection:
    claims: tuple[ContextObject, ...]
    gaps: tuple[ContextObject, ...]
    conflicts: tuple[Conflict, ...]

    @property
    def unknown(self) -> bool:
        # Even False is not a completeness claim; observations are field-local.
        return bool(self.gaps) or not any(
            claim.data["state"] == KnowledgeState.OBSERVED.value for claim in self.claims
        )


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be nonempty text")
    value.encode("utf-8")
    return value


def _json(value: Any) -> str:
    # Reject lossy conversions (e.g. int object keys, tuples, NaN). This is a
    # versioned Python/JSON encoding, not a claim of cross-language JCS identity.
    def check(item: Any) -> None:
        if item is None or type(item) in (bool, int, str):
            return
        if type(item) is float and math.isfinite(item):
            return
        if type(item) is list:
            for child in item:
                check(child)
            return
        if type(item) is dict and all(type(key) is str for key in item):
            for child in item.values():
                check(child)
            return
        raise ValueError("context data must be finite JSON with string object keys")

    check(value)
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    encoded.encode("utf-8")
    return encoded


def _cid(kind: str, data_json: str, refs: tuple[tuple[str, str], ...]) -> str:
    envelope = _json({"schema": 1, "kind": kind, "data": json.loads(data_json), "refs": [list(r) for r in refs]})
    return "cm1_" + hashlib.sha256(envelope.encode("utf-8")).hexdigest()


def _path(path: str) -> tuple[str, ...]:
    _text(path, "path")
    segments = tuple(path.split("/"))
    if any(not part or part in (".", "..") for part in segments):
        raise ValueError("context paths use nonempty segments, without '.' or '..'")
    return segments


class ContextManifestStore:
    """Additive description storage sharing TraceStore's database and lock.

    cm_objects are content-addressed Values; cm_requests and cm_events are
    append-only indexes binding caller-owned record names to those Values.
    They do not allocate Eidos Names or admit live TM occurrences. Savepoints
    allow pins/events to join a future caller-owned dispatch transaction.
    """

    def __init__(self, trace: TraceStore) -> None:
        self.trace = trace
        # Do not use executescript: it commits an existing caller transaction.
        with self._transaction():
            trace.db.execute("""CREATE TABLE IF NOT EXISTS cm_objects(
                cid TEXT PRIMARY KEY, kind TEXT NOT NULL,
                data_json TEXT NOT NULL, refs_json TEXT NOT NULL)""")
            trace.db.execute("""CREATE TABLE IF NOT EXISTS cm_requests(
                name TEXT PRIMARY KEY, cid TEXT NOT NULL REFERENCES cm_objects(cid),
                manifest TEXT NOT NULL REFERENCES cm_objects(cid))""")
            trace.db.execute("""CREATE TABLE IF NOT EXISTS cm_events(
                ordinal INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL,
                cid TEXT NOT NULL REFERENCES cm_objects(cid),
                manifest TEXT NOT NULL REFERENCES cm_objects(cid))""")
            trace.db.execute("CREATE INDEX IF NOT EXISTS cm_requests_manifest ON cm_requests(manifest)")
            trace.db.execute("CREATE INDEX IF NOT EXISTS cm_events_manifest ON cm_events(manifest)")

    @contextmanager
    def _transaction(self) -> Iterator[None]:
        with self.trace._lock:
            own_transaction = not self.trace.db.in_transaction
            if own_transaction:
                # Serialize writers before reading their replay keys. A deferred
                # read followed by a write can fail to upgrade under WAL races.
                self.trace.db.execute("BEGIN IMMEDIATE")
            savepoint = "cm_" + uuid.uuid4().hex
            self.trace.db.execute(f"SAVEPOINT {savepoint}")
            try:
                yield
                self.trace.db.execute(f"RELEASE {savepoint}")
            except BaseException:
                if own_transaction:
                    self.trace.db.execute("ROLLBACK")
                else:
                    self.trace.db.execute(f"ROLLBACK TO {savepoint}")
                    self.trace.db.execute(f"RELEASE {savepoint}")
                raise
            if own_transaction:
                try:
                    self.trace.db.execute("COMMIT")
                except BaseException:
                    self.trace.db.execute("ROLLBACK")
                    raise

    def _put(self, kind: str, data: Any, refs: Mapping[str, str] | None = None) -> str:
        _text(kind, "kind")
        frozen_refs = tuple(sorted((refs or {}).items()))
        for label, target in frozen_refs:
            _text(label, "reference label")
            self.get(target)
        data_json = _json(data)
        cid = _cid(kind, data_json, frozen_refs)
        self.trace.db.execute(
            "INSERT OR IGNORE INTO cm_objects(cid,kind,data_json,refs_json) VALUES (?,?,?,?)",
            (cid, kind, data_json, _json([list(r) for r in frozen_refs])),
        )
        if self.get(cid) != ContextObject(cid, kind, data_json, frozen_refs):
            raise ValueError("context content identity collision or database corruption")
        return cid

    def put_content(self, kind: str, data: Any, refs: Mapping[str, str] | None = None) -> str:
        """Store JSON ingredients and explicit edges; unknown fields survive.

        cm.* kinds are reserved so data cannot masquerade as a verified trace
        reference, manifest, claim, or request through this public constructor.
        """
        _text(kind, "kind")
        if kind.startswith("cm."):
            raise ValueError("cm.* kinds are reserved")
        with self._transaction():
            return self._put(kind, data, refs)

    def get(self, cid: str) -> ContextObject:
        with self.trace._lock:
            row = self.trace.db.execute("SELECT * FROM cm_objects WHERE cid=?", (cid,)).fetchone()
            if row is None:
                raise KeyError(cid)
            obj = ContextObject(row["cid"], row["kind"], row["data_json"], tuple(tuple(r) for r in json.loads(row["refs_json"])))
            if _cid(obj.kind, obj.data_json, obj.refs) != cid:
                raise ValueError("context content digest mismatch")
            return obj

    def freeze_trace(self, seq: int) -> str:
        """Freeze exact raw evidence, never later hydrated coordinate indexes."""
        if type(seq) is not int or seq < 1:
            raise ValueError("trace sequence must be a positive integer")
        with self._transaction():
            row = self.trace.db.execute("SELECT * FROM trace_records WHERE seq=?", (seq,)).fetchone()
            if row is None:
                raise KeyError(seq)
            raw = row["raw_text"]
            return self._put("cm.trace", {
                "seq": seq, "source": row["source"], "direction": row["direction"],
                "observed_at_ms": row["observed_at_ms"], "raw_text": raw,
                "sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
            })

    def _evidence(self, evidence: tuple[str, ...], boundary: Boundary, *, required: bool = False,
                  adoption: bool = False) -> dict[str, str]:
        if required and not evidence:
            raise ValueError("observed information requires captured trace evidence")
        allowed = {
            Boundary.LOCAL: {"internal"},
            Boundary.APP_SERVER: {"client_to_appserver", "appserver_to_client"},
            Boundary.PROVIDER: {"provider_request", "provider_response"},
        }[boundary]
        if adoption:
            if boundary == Boundary.LOCAL:
                raise ValueError("local file/config observations do not establish native adoption")
            if boundary == Boundary.APP_SERVER:
                allowed = {"appserver_to_client"}
        refs = {}
        for index, cid in enumerate(sorted(set(evidence))):
            obj = self.get(cid)
            if obj.kind != "cm.trace":
                raise ValueError("evidence must be frozen with freeze_trace")
            # Supporting evidence for SELECTED/INFERRED may come from another
            # boundary, but an observation must match its claimed boundary.
            if required and obj.data["direction"] not in allowed:
                raise ValueError("evidence does not observe the claimed boundary")
            refs[f"evidence:{index}"] = cid
        return refs

    def claim(self, content_cid: str, *, state: KnowledgeState, boundary: Boundary,
              facet: str = "included", evidence: tuple[str, ...] = (), rationale: str = "",
              scope: RuntimeIdentity = RuntimeIdentity()) -> str:
        """Assert one single-valued facet, with attribution and explicit scope.

        Multiple incompatible observations coexist; no last-write-wins rule.
        States are independent assertions, not steps of an automatic pipeline.
        """
        state, boundary = KnowledgeState(state), Boundary(boundary)
        _text(facet, "facet")
        with self._transaction():
            refs = self._evidence(evidence, boundary, required=state == KnowledgeState.OBSERVED)
            refs["content"] = content_cid
            return self._put("cm.claim", {
                "state": state.value, "boundary": boundary.value, "facet": facet,
                "rationale": rationale, "scope": asdict(scope),
            }, refs)

    def unknown(self, reason: str, *, boundary: Boundary, details: Any = None) -> str:
        _text(reason, "unknown reason")
        with self._transaction():
            return self._put("cm.unknown", {"boundary": Boundary(boundary).value, "reason": reason, "details": details})

    def slot(self, *claim_or_gap_cids: str) -> str:
        """An unordered set of retained claims/gaps about one context path."""
        if not claim_or_gap_cids:
            raise ValueError("a slot needs an explicit claim or unknown reason")
        with self._transaction():
            refs = {}
            for index, cid in enumerate(sorted(set(claim_or_gap_cids))):
                if self.get(cid).kind not in ("cm.claim", "cm.unknown"):
                    raise ValueError("slots contain claims or explicit unknowns")
                refs[str(index)] = cid
            return self._put("cm.slot", {}, refs)

    def put_binding(self, role: Role, target: str, *, name: Name | None = None,
                    target_kind: str = "content", capture: str = "situated",
                    entity_name: Name | None = None, placement: Any = None) -> str:
        """Descriptive Eidos projection; never resolve a Name or import a Socket."""
        if target_kind not in ("content", "name") or capture not in ("situated", "lexical", "snapshot"):
            raise ValueError("invalid binding target/capture kind")
        _text(target, "binding target")
        with self._transaction():
            return self._put("cm.binding", {
                "role": list(role.path), "binding_name": None if name is None else name.value,
                "entity_name": None if entity_name is None else entity_name.value,
                "target_kind": target_kind, "target_name": target if target_kind == "name" else None,
                "capture": capture, "placement": placement,
            }, {"target": target} if target_kind == "content" else {})

    def _manifest(self, manifest: ContextManifest | str) -> ContextManifest:
        cid = manifest.cid if isinstance(manifest, ContextManifest) else manifest
        obj = self.get(cid)
        if obj.kind != "cm.manifest":
            raise ValueError("expected a context manifest")
        result = ContextManifest(cid, obj.ref("root"))
        if isinstance(manifest, ContextManifest) and result != manifest:
            raise ValueError("manifest root does not match its content identity")
        return result

    def manifest(self, entries: Mapping[str, str]) -> ContextManifest:
        """Build a path trie. Paths cannot be both a slot and a directory."""
        with self._transaction():
            tree: dict[str, Any] = {}
            for path, cid in sorted(entries.items()):
                if self.get(cid).kind != "cm.slot":
                    raise ValueError("manifest paths must reference slots")
                parts = _path(path)
                node = tree
                for part in parts[:-1]:
                    child = node.setdefault(part, {})
                    if not isinstance(child, dict):
                        raise ValueError("manifest path overlaps a slot")
                    node = child
                if parts[-1] in node:
                    raise ValueError("manifest path overlaps a directory")
                node[parts[-1]] = cid

            def freeze(node: dict[str, Any]) -> str:
                return self._put("cm.tree", {}, {
                    key: freeze(value) if isinstance(value, dict) else value for key, value in node.items()
                })

            root = freeze(tree)
            return ContextManifest(self._put("cm.manifest", {}, {"root": root}), root)

    def replace(self, manifest: ContextManifest | str, path: str, slot_or_none: str | None) -> ContextManifest:
        """Path-copy only changed ancestors. None removes an existing slot."""
        parts = _path(path)
        with self._transaction():
            current = self._manifest(manifest)
            if slot_or_none is not None and self.get(slot_or_none).kind != "cm.slot":
                raise ValueError("replacement must be a slot")

            def update(cid: str | None, depth: int) -> str:
                obj = self.get(cid) if cid is not None else None
                if obj is not None and obj.kind != "cm.tree":
                    raise ValueError("manifest path overlaps a slot")
                refs = dict(obj.refs) if obj else {}
                key = parts[depth]
                old = refs.get(key)
                if depth == len(parts) - 1:
                    if old is not None and self.get(old).kind != "cm.slot":
                        raise ValueError("replace a slot, not a directory")
                    if slot_or_none is None:
                        if old is None:
                            raise KeyError(path)
                        del refs[key]
                    else:
                        refs[key] = slot_or_none
                else:
                    if old is None and slot_or_none is None:
                        raise KeyError(path)
                    child = update(old, depth + 1)
                    if self.get(child).refs:
                        refs[key] = child
                    else:
                        refs.pop(key, None)
                return self._put("cm.tree", {}, refs)

            root = update(current.root, 0)
            return ContextManifest(self._put("cm.manifest", {}, {"root": root}), root)

    def at(self, manifest: ContextManifest | str, path: str) -> str | None:
        cid = self._manifest(manifest).root
        for segment in _path(path):
            obj = self.get(cid)
            if obj.kind != "cm.tree":
                return None
            child = dict(obj.refs).get(segment)
            if child is None:
                return None
            cid = child
        return cid if self.get(cid).kind == "cm.slot" else None

    def entries(self, manifest: ContextManifest | str) -> dict[str, str]:
        result: dict[str, str] = {}

        def walk(cid: str, path: tuple[str, ...]) -> None:
            obj = self.get(cid)
            if obj.kind == "cm.slot":
                result["/".join(path)] = cid
            else:
                for name, child in obj.refs:
                    walk(child, (*path, name))

        walk(self._manifest(manifest).root, ())
        return result

    def diff(self, before: ContextManifest | str, after: ContextManifest | str) -> tuple[ContextChange, ...]:
        """Compare changed branches; identical subtree CIDs stop traversal."""
        result = []

        def compare(left: str | None, right: str | None, path: tuple[str, ...]) -> None:
            if left == right:
                return
            a, b = self.get(left) if left else None, self.get(right) if right else None
            if (a is None or a.kind == "cm.slot") and (b is None or b.kind == "cm.slot"):
                result.append(ContextChange("/".join(path), left, right))
                return
            # A slot may become a directory across independently built roots.
            if a and a.kind == "cm.slot":
                compare(left, None, path)
                a = None
            if b and b.kind == "cm.slot":
                compare(None, right, path)
                b = None
            ar, br = dict(a.refs) if a else {}, dict(b.refs) if b else {}
            for key in sorted(ar.keys() | br.keys()):
                compare(ar.get(key), br.get(key), (*path, key))

        compare(self._manifest(before).root, self._manifest(after).root, ())
        return tuple(result)

    def inspect(self, manifest: ContextManifest | str, path: str, *,
                boundary: Boundary = Boundary.PROVIDER) -> SlotInspection:
        boundary = Boundary(boundary)
        cid = self.at(manifest, path)
        objects = [self.get(child) for _, child in self.get(cid).refs] if cid else []
        claims = tuple(obj for obj in objects if obj.kind == "cm.claim" and obj.data["boundary"] == boundary.value)
        gaps = tuple(obj for obj in objects if obj.kind == "cm.unknown" and obj.data["boundary"] == boundary.value)
        observed = [claim for claim in claims if claim.data["state"] == KnowledgeState.OBSERVED.value]
        conflicts = []
        for index, left in enumerate(observed):
            for right in observed[index + 1:]:
                a, b = left.data, right.data
                if a["facet"] != b["facet"] or left.ref("content") == right.ref("content"):
                    continue
                x, y = a["scope"], b["scope"]
                if any(x[key] is not None and y[key] is not None and x[key] != y[key] for key in x):
                    continue
                # Missing coordinates do not silently separate observations.
                # Compatible partial scopes overlap, but only a shared attempt
                # anchors a definite conflict; a request can contain retries.
                anchored = x["attempt_id"] is not None and x["attempt_id"] == y["attempt_id"]
                conflicts.append(Conflict(a["facet"], (left.cid, right.cid), scope_uncertain=not anchored))
        return SlotInspection(claims, gaps, tuple(conflicts))

    def _named(self, table: str, name: str, cid: str, manifest: str) -> ContextObject:
        # Table comes exclusively from internal literals, never caller input.
        existing = self.trace.db.execute(f"SELECT cid FROM {table} WHERE name=?", (name,)).fetchone()
        if existing is not None:
            if existing["cid"] != cid:
                raise ValueError(f"{name!r} already identifies different context data")
        else:
            self.trace.db.execute(f"INSERT INTO {table}(name,cid,manifest) VALUES (?,?,?)", (name, cid, manifest))
        return self.get(cid)

    def pin_request(self, name: str, manifest: ContextManifest | str, *,
                    identity: RuntimeIdentity = RuntimeIdentity(), boundary: Boundary = Boundary.APP_SERVER,
                    state: KnowledgeState = KnowledgeState.PROJECTED, evidence: tuple[str, ...] = ()) -> ContextObject:
        """Persist the local attempt's immutable snapshot before an external send.

        A native observation arriving later is a separate correlation event; it
        cannot upgrade or repoint this pin. This does not dispatch anything.
        """
        _text(name, "request association name")
        state, boundary = KnowledgeState(state), Boundary(boundary)
        if state not in (KnowledgeState.PROJECTED, KnowledgeState.OBSERVED):
            raise ValueError("request associations must be projected or observed")
        with self._transaction():
            manifest = self._manifest(manifest)
            refs = self._evidence(evidence, boundary, required=state == KnowledgeState.OBSERVED)
            refs["manifest"] = manifest.cid
            cid = self._put("cm.request", {"name": name, "identity": asdict(identity),
                            "boundary": boundary.value, "state": state.value}, refs)
            return self._named("cm_requests", name, cid, manifest.cid)

    def get_request(self, name: str) -> ContextObject:
        return self._get_named("cm_requests", name)

    def _get_named(self, table: str, name: str) -> ContextObject:
        with self.trace._lock:
            row = self.trace.db.execute(f"SELECT cid FROM {table} WHERE name=?", (name,)).fetchone()
            if row is None:
                raise KeyError(name)
            return self.get(row["cid"])

    def requests_for(self, manifest: ContextManifest | str) -> tuple[ContextObject, ...]:
        manifest = self._manifest(manifest)
        with self.trace._lock:
            rows = self.trace.db.execute("SELECT cid FROM cm_requests WHERE manifest=? ORDER BY name", (manifest.cid,)).fetchall()
            return tuple(self.get(row["cid"]) for row in rows)

    def record_event(self, name: str, *, kind: str, manifest: ContextManifest | str,
                     previous_manifest: ContextManifest | str | None = None,
                     identity: RuntimeIdentity = RuntimeIdentity(), boundary: Boundary = Boundary.LOCAL,
                     evidence: tuple[str, ...] = (), parents: tuple[str, ...] = (),
                     request_name: str | None = None,
                     supplemental_manifest: ContextManifest | str | None = None,
                     details: Any = None) -> ContextObject:
        """Record attribution, not a TM occurrence or proof of native adoption.

        Parent names identify known local annotations. External causal refs can
        be preserved in details but are not verified edges. Append order only
        records local insertion; it is not a universal clock or applicability.
        """
        _text(name, "event name")
        boundary = Boundary(boundary)
        if kind not in ("revision", "activation_requested", "adoption_observed", "correlation"):
            raise ValueError("unsupported context event kind")
        with self._transaction():
            manifest = self._manifest(manifest)
            observed = kind in ("adoption_observed", "correlation")
            refs = self._evidence(evidence, boundary, required=observed, adoption=kind == "adoption_observed")
            refs["manifest"] = manifest.cid
            if previous_manifest is not None:
                refs["previous_manifest"] = self._manifest(previous_manifest).cid
            if request_name is not None:
                request = self.get_request(request_name)
                if request.ref("manifest") != manifest.cid:
                    raise ValueError("request event must retain the pinned manifest")
                refs["request"] = request.cid
            if kind == "correlation" and request_name is None:
                raise ValueError("correlation needs an existing request association")
            if supplemental_manifest is not None:
                if kind != "correlation":
                    raise ValueError("a supplemental view belongs to a request correlation")
                refs["supplemental_manifest"] = self._manifest(supplemental_manifest).cid
            for index, parent in enumerate(sorted(set(parents))):
                if parent == name:
                    raise ValueError("event cannot parent itself")
                refs[f"parent:{index}"] = self.get_event(parent).cid
            cid = self._put("cm.event", {"name": name, "kind": kind, "identity": asdict(identity),
                            "boundary": boundary.value, "details": details}, refs)
            return self._named("cm_events", name, cid, manifest.cid)

    def get_event(self, name: str) -> ContextObject:
        return self._get_named("cm_events", name)

    def events(self, manifest: ContextManifest | str | None = None) -> tuple[ContextObject, ...]:
        with self.trace._lock:
            if manifest is None:
                rows = self.trace.db.execute("SELECT cid FROM cm_events ORDER BY ordinal").fetchall()
            else:
                cid = self._manifest(manifest).cid
                rows = self.trace.db.execute("SELECT cid FROM cm_events WHERE manifest=? ORDER BY ordinal", (cid,)).fetchall()
            return tuple(self.get(row["cid"]) for row in rows)
