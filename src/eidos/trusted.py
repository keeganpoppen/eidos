from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict
import json
import sqlite3
import uuid
from pathlib import Path
from typing import Any, Iterator

from .model import Frame, OfferSpec, ProtocolSpec, Transition, canonical_bytes, content_id
from .core import (
    Name as CoreName,
    RecordValue,
    canonical_bytes as core_canonical_bytes,
    content_id as core_content_id,
    from_data as core_from_data,
)
from .occurrence import FrontierBlueprint, InstanceBlueprint
from .cuts import CutElaboration
from .authority import ProjectionGrant
from .meta import (
    ACTUALIZER_ROLE,
    ELABORATOR_ROLE,
    actualizer_state,
    elaborator_state,
)
from .semantic_values import (
    cut_value,
    elaboration_value,
    occurrence_value,
    possibility_value,
    projection_value,
)


class TrustedError(RuntimeError):
    pass


class StaleSocket(TrustedError):
    pass


class StaleProjection(TrustedError):
    pass


class Conflict(TrustedError):
    pass


class TrustedMachinery:
    """Small durable authority substrate.

    This v0 intentionally exposes several boring methods rather than pretending
    they have already collapsed into one elegant meta protocol. The semantics
    can be compressed later; the guarantees should be explicit first.
    """

    def __init__(self, path: str | Path = ":memory:") -> None:
        self.db = sqlite3.connect(str(path), isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self._schema()

    def close(self) -> None:
        self.db.close()

    def _schema(self) -> None:
        self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS commands(
              request_id TEXT PRIMARY KEY,
              op TEXT NOT NULL,
              digest TEXT NOT NULL,
              result_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS names(
              name TEXT PRIMARY KEY,
              kind TEXT NOT NULL,
              created_seq INTEGER
            );
            CREATE TABLE IF NOT EXISTS frames(
              cid TEXT PRIMARY KEY,
              body_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS eidos_values(
              cid TEXT PRIMARY KEY,
              body_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS named_eidos_values(
              name TEXT PRIMARY KEY REFERENCES names(name),
              cid TEXT NOT NULL REFERENCES eidos_values(cid)
            );
            CREATE TABLE IF NOT EXISTS protocols(
              cid TEXT PRIMARY KEY,
              body_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sessions(
              name TEXT PRIMARY KEY REFERENCES names(name),
              protocol_cid TEXT NOT NULL REFERENCES protocols(cid)
            );
            CREATE TABLE IF NOT EXISTS sockets(
              name TEXT PRIMARY KEY REFERENCES names(name),
              session_name TEXT NOT NULL REFERENCES sessions(name),
              role TEXT NOT NULL,
              protocol_state TEXT NOT NULL,
              holder TEXT NOT NULL,
              disposition TEXT NOT NULL CHECK(disposition IN ('live','offered','spent','closed'))
            );
            CREATE TABLE IF NOT EXISTS nemata(
              name TEXT PRIMARY KEY REFERENCES names(name),
              frame_cid TEXT NOT NULL REFERENCES frames(cid),
              meta_socket TEXT NOT NULL REFERENCES sockets(name)
            );
            CREATE TABLE IF NOT EXISTS offers(
              name TEXT PRIMARY KEY REFERENCES names(name),
              socket_name TEXT NOT NULL REFERENCES sockets(name),
              direction TEXT NOT NULL,
              label TEXT NOT NULL,
              payload_json TEXT NOT NULL,
              continuation_json TEXT NOT NULL,
              state TEXT NOT NULL CHECK(state IN ('open','matched','cancelled'))
            );
            CREATE TABLE IF NOT EXISTS matches(
              name TEXT PRIMARY KEY REFERENCES names(name),
              left_offer TEXT NOT NULL REFERENCES offers(name),
              right_offer TEXT NOT NULL REFERENCES offers(name),
              left_successor TEXT REFERENCES sockets(name),
              right_successor TEXT REFERENCES sockets(name)
            );
            CREATE TABLE IF NOT EXISTS receipts(
              name TEXT PRIMARY KEY REFERENCES names(name),
              holder TEXT NOT NULL,
              match_name TEXT NOT NULL REFERENCES matches(name),
              old_socket TEXT NOT NULL REFERENCES sockets(name),
              successor_socket TEXT REFERENCES sockets(name),
              payload_json TEXT NOT NULL,
              incorporated INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS authority_domains(
              name TEXT PRIMARY KEY REFERENCES names(name)
            );
            CREATE TABLE IF NOT EXISTS projections(
              name TEXT PRIMARY KEY REFERENCES names(name),
              domain_name TEXT NOT NULL REFERENCES authority_domains(name),
              holder TEXT NOT NULL,
              disposition TEXT NOT NULL CHECK(disposition IN ('live','spent'))
            );


            CREATE TABLE IF NOT EXISTS authority_occurrences(
              name TEXT PRIMARY KEY REFERENCES names(name),
              domain_name TEXT NOT NULL REFERENCES authority_domains(name),
              kind TEXT NOT NULL,
              fact_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS authority_occurrence_inputs(
              occurrence_name TEXT NOT NULL REFERENCES authority_occurrences(name),
              projection_name TEXT NOT NULL REFERENCES projections(name),
              ordinal INTEGER NOT NULL,
              PRIMARY KEY(occurrence_name,projection_name)
            );
            CREATE TABLE IF NOT EXISTS authority_occurrence_outputs(
              occurrence_name TEXT NOT NULL REFERENCES authority_occurrences(name),
              projection_name TEXT NOT NULL REFERENCES projections(name),
              output_key TEXT NOT NULL,
              ordinal INTEGER NOT NULL,
              PRIMARY KEY(occurrence_name,output_key),
              UNIQUE(occurrence_name,projection_name)
            );

            CREATE TABLE IF NOT EXISTS events(
              seq INTEGER PRIMARY KEY AUTOINCREMENT,
              kind TEXT NOT NULL,
              body_json TEXT NOT NULL
            );
            """
        )

    @contextmanager
    def _tx(self) -> Iterator[sqlite3.Connection]:
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield self.db
        except Exception:
            self.db.execute("ROLLBACK")
            raise
        else:
            self.db.execute("COMMIT")

    def _new_name(self, db: sqlite3.Connection, kind: str) -> str:
        while True:
            name = f"{kind}_{uuid.uuid4().hex}"
            try:
                db.execute("INSERT INTO names(name,kind) VALUES (?,?)", (name, kind))
                return name
            except sqlite3.IntegrityError:
                pass

    def _event(self, db: sqlite3.Connection, kind: str, body: dict[str, Any]) -> int:
        cur = db.execute(
            "INSERT INTO events(kind,body_json) VALUES (?,?)",
            (kind, json.dumps(body, sort_keys=True, separators=(",", ":"))),
        )
        seq = int(cur.lastrowid)
        for name in body.get("new_names", []):
            db.execute("UPDATE names SET created_seq=? WHERE name=?", (seq, name))
        return seq

    def _idem(self, db: sqlite3.Connection, request_id: str, op: str, payload: Any) -> dict[str, Any] | None:
        digest = core_content_id(payload)
        row = db.execute("SELECT op,digest,result_json FROM commands WHERE request_id=?", (request_id,)).fetchone()
        if row is None:
            return None
        if row["op"] != op or row["digest"] != digest:
            raise Conflict(f"request id {request_id!r} reused with different operation/payload")
        return json.loads(row["result_json"])

    def _idem_put(self, db: sqlite3.Connection, request_id: str, op: str, payload: Any, result: dict[str, Any]) -> None:
        db.execute(
            "INSERT INTO commands(request_id,op,digest,result_json) VALUES (?,?,?,?)",
            (request_id, op, core_content_id(payload), json.dumps(result, sort_keys=True, separators=(",", ":"))),
        )

    def _commit_projection_occurrence(
        self,
        db: sqlite3.Connection,
        *,
        kind: str,
        consumes: tuple[str, ...],
        establishes: tuple[ProjectionGrant, ...],
        fact: Any,
        occurrence: str | None = None,
    ) -> dict[str, Any]:
        """Mechanical atomic transition over live projection capabilities."""

        if not consumes:
            raise TrustedError("an authority occurrence must consume capability")
        if len(set(consumes)) != len(consumes):
            raise Conflict("an authority occurrence cannot consume capability twice")
        output_keys = [grant.key for grant in establishes]
        if len(set(output_keys)) != len(output_keys):
            raise Conflict("authority occurrence output keys must be unique")

        rows: list[sqlite3.Row] = []
        for projection in consumes:
            row = db.execute(
                "SELECT * FROM projections WHERE name=?",
                (projection,),
            ).fetchone()
            if row is None or row["disposition"] != "live":
                raise StaleProjection(
                    f"projection {projection!r} is not live"
                )
            rows.append(row)

        domains = {row["domain_name"] for row in rows}
        if len(domains) != 1:
            raise Conflict(
                "one atomic authority occurrence must stay within one authority domain"
            )
        domain = next(iter(domains))

        if occurrence is None:
            occurrence = self._new_name(db, "occurrence")
        elif db.execute(
            "SELECT 1 FROM names WHERE name=?",
            (occurrence,),
        ).fetchone() is None:
            raise KeyError(occurrence)

        for projection in consumes:
            db.execute(
                "UPDATE projections SET disposition='spent' WHERE name=?",
                (projection,),
            )

        outputs: dict[str, str] = {}
        new_names = [occurrence]
        for ordinal, grant in enumerate(establishes):
            projection = self._new_name(db, "projection")
            new_names.append(projection)
            outputs[grant.key] = projection
            db.execute(
                "INSERT INTO projections(name,domain_name,holder,disposition) "
                "VALUES (?,?,?,?)",
                (projection, domain, grant.holder, "live"),
            )
            self._bind_eidos_value(
                db,
                name=projection,
                value=grant.description,
            )

        db.execute(
            "INSERT INTO authority_occurrences("
            "name,domain_name,kind,fact_json"
            ") VALUES (?,?,?,?)",
            (
                occurrence,
                domain,
                kind,
                json.dumps(fact, sort_keys=True, separators=(",", ":")),
            ),
        )
        for ordinal, projection in enumerate(consumes):
            db.execute(
                "INSERT INTO authority_occurrence_inputs("
                "occurrence_name,projection_name,ordinal"
                ") VALUES (?,?,?)",
                (occurrence, projection, ordinal),
            )
        for ordinal, grant in enumerate(establishes):
            db.execute(
                "INSERT INTO authority_occurrence_outputs("
                "occurrence_name,projection_name,output_key,ordinal"
                ") VALUES (?,?,?,?)",
                (occurrence, outputs[grant.key], grant.key, ordinal),
            )

        self._event(
            db,
            "authority_occurrence_committed",
            {
                "occurrence": occurrence,
                "kind": kind,
                "domain": domain,
                "consumed": list(consumes),
                "established": outputs,
                "fact": fact,
                "new_names": new_names,
            },
        )
        return {
            "occurrence": occurrence,
            "domain": domain,
            "instance": domain,
            "kind": kind,
            "consumed": list(consumes),
            "established": outputs,
        }

    def commit_projection_occurrence(
        self,
        *,
        kind: str,
        consumes: tuple[str, ...],
        establishes: tuple[ProjectionGrant, ...],
        fact: Any,
        request_id: str,
    ) -> dict[str, Any]:
        """Public generic Trusted Machinery occurrence primitive."""

        payload = {
            "kind": kind,
            "consumes": list(consumes),
            "establishes": [
                {
                    "key": grant.key,
                    "holder": grant.holder,
                    "description": grant.description,
                }
                for grant in establishes
            ],
            "fact": fact,
        }
        with self._tx() as db:
            old = self._idem(
                db, request_id, "commit_projection_occurrence", payload
            )
            if old is not None:
                return old
            result = self._commit_projection_occurrence(
                db,
                kind=kind,
                consumes=consumes,
                establishes=establishes,
                fact=fact,
            )
            self._idem_put(
                db,
                request_id,
                "commit_projection_occurrence",
                payload,
                result,
            )
            return result

    def _put_eidos_value(
        self,
        db: sqlite3.Connection,
        value: Any,
    ) -> str:
        cid = core_content_id(value)
        db.execute(
            "INSERT OR IGNORE INTO eidos_values(cid,body_json) VALUES (?,?)",
            (cid, core_canonical_bytes(value).decode("utf-8")),
        )
        return cid

    def _bind_eidos_value(
        self,
        db: sqlite3.Connection,
        *,
        name: str,
        value: Any,
    ) -> str:
        if db.execute(
            "SELECT 1 FROM names WHERE name=?",
            (name,),
        ).fetchone() is None:
            raise KeyError(name)

        cid = self._put_eidos_value(db, value)
        existing = db.execute(
            "SELECT cid FROM named_eidos_values WHERE name=?",
            (name,),
        ).fetchone()
        if existing is not None and existing["cid"] != cid:
            raise Conflict(
                f"Name {name!r} is already bound to another immutable Value"
            )
        db.execute(
            "INSERT OR IGNORE INTO named_eidos_values(name,cid) VALUES (?,?)",
            (name, cid),
        )
        return cid

    def put_eidos_value(self, value: Any) -> str:
        """Persist any ordinary immutable Eidos Core value by content identity."""

        return self._put_eidos_value(self.db, value)

    def eidos_value(self, cid: str) -> Any:
        row = self.db.execute(
            "SELECT body_json FROM eidos_values WHERE cid=?",
            (cid,),
        ).fetchone()
        if row is None:
            raise KeyError(cid)
        return core_from_data(json.loads(row["body_json"]))

    def bind_eidos_value(
        self,
        *,
        name: str,
        value: Any,
        request_id: str,
    ) -> dict[str, str]:
        """Immutably bind a permanent Name to one persisted Eidos Value."""

        payload = {
            "name": name,
            "cid": core_content_id(value),
        }
        with self._tx() as db:
            old = self._idem(db, request_id, "bind_eidos_value", payload)
            if old is not None:
                return old
            cid = self._bind_eidos_value(db, name=name, value=value)
            self._event(
                db,
                "eidos_value_bound",
                {"name": name, "cid": cid},
            )
            result = {"name": name, "cid": cid}
            self._idem_put(db, request_id, "bind_eidos_value", payload, result)
            return result

    def _named_eidos_value(
        self,
        db: sqlite3.Connection,
        name: str,
    ) -> dict[str, Any]:
        row = db.execute(
            "SELECT nev.cid,ev.body_json "
            "FROM named_eidos_values nev "
            "JOIN eidos_values ev ON ev.cid=nev.cid "
            "WHERE nev.name=?",
            (name,),
        ).fetchone()
        if row is None:
            raise KeyError(name)
        return {
            "name": name,
            "cid": row["cid"],
            "value": core_from_data(json.loads(row["body_json"])),
        }

    def named_eidos_value(self, name: str) -> dict[str, Any]:
        return self._named_eidos_value(self.db, name)

    def _named_values(
        self,
        db: sqlite3.Connection,
    ) -> list[tuple[str, Any]]:
        rows = db.execute(
            "SELECT nev.name,ev.body_json "
            "FROM named_eidos_values nev "
            "JOIN eidos_values ev ON ev.cid=nev.cid "
            "ORDER BY nev.rowid"
        ).fetchall()
        return [
            (row["name"], core_from_data(json.loads(row["body_json"])))
            for row in rows
        ]

    def named_values(self) -> tuple[tuple[str, Any], ...]:
        """Return the canonical Name -> Value relation for derived indexing/lenses."""

        return tuple(self._named_values(self.db))

    def _named_values_of_kind(
        self,
        db: sqlite3.Connection,
        kind: str,
    ) -> list[tuple[str, RecordValue]]:
        out: list[tuple[str, RecordValue]] = []
        for name, value in self._named_values(db):
            if (
                isinstance(value, RecordValue)
                and value.get("$kind") == kind
            ):
                out.append((name, value))
        return out

    def _authority_occurrence_consuming(
        self,
        db: sqlite3.Connection,
        projection: str,
    ) -> sqlite3.Row | None:
        return db.execute(
            "SELECT ao.* FROM authority_occurrence_inputs aoi "
            "JOIN authority_occurrences ao ON ao.name=aoi.occurrence_name "
            "WHERE aoi.projection_name=? ORDER BY aoi.rowid LIMIT 1",
            (projection,),
        ).fetchone()

    def _cut_state(
        self,
        db: sqlite3.Connection,
        *,
        cut: str,
        semantic: RecordValue,
    ) -> str:
        for _, occurrence in self._named_values_of_kind(db, "Occurrence"):
            causes = {
                reference.value
                for reference in occurrence.get("cause_cuts")
                if isinstance(reference, CoreName)
            }
            if cut in causes:
                return "historical"

        elaborator = semantic.get("elaborator")
        if not isinstance(elaborator, CoreName):
            raise Conflict("Cut Value must name its Elaborator projection")
        row = db.execute(
            "SELECT disposition FROM projections WHERE name=?",
            (elaborator.value,),
        ).fetchone()
        if row is None:
            raise KeyError(elaborator.value)
        return "open" if row["disposition"] == "live" else "elaborated"

    def _possibility_state(
        self,
        db: sqlite3.Connection,
        *,
        possibility: str,
        semantic: RecordValue,
    ) -> str:
        actualizer = semantic.get("actualizer")
        if not isinstance(actualizer, CoreName):
            raise Conflict("Possibility Value must name its Actualizer projection")
        actualizer_row = db.execute(
            "SELECT disposition FROM projections WHERE name=?",
            (actualizer.value,),
        ).fetchone()
        if actualizer_row is None:
            raise KeyError(actualizer.value)

        if actualizer_row["disposition"] == "live":
            for reference in semantic.get("inputs"):
                if not isinstance(reference, CoreName):
                    raise Conflict("Possibility inputs must be Names")
                row = db.execute(
                    "SELECT disposition FROM projections WHERE name=?",
                    (reference.value,),
                ).fetchone()
                if row is None or row["disposition"] != "live":
                    return "precluded"
            return "open"

        occurrence = self._authority_occurrence_consuming(
            db, actualizer.value
        )
        if occurrence is None:
            return "precluded"
        fact = json.loads(occurrence["fact_json"])
        if (
            occurrence["kind"] == "Actualize"
            and fact.get("possibility") == possibility
        ):
            return "occurred"
        return "precluded"

    def _preclude_competing_possibilities(
        self,
        db: sqlite3.Connection,
        *,
        selected: str,
        instance: str,
        consumed_inputs: tuple[str, ...],
        because: str,
    ) -> list[str]:
        consumed_set = set(consumed_inputs)
        precluded: list[str] = []
        for name, semantic in self._named_values_of_kind(db, "Possibility"):
            if name == selected:
                continue
            actualizer = semantic.get("actualizer")
            if not isinstance(actualizer, CoreName):
                continue
            actualizer_row = db.execute(
                "SELECT domain_name,disposition FROM projections WHERE name=?",
                (actualizer.value,),
            ).fetchone()
            if (
                actualizer_row is None
                or actualizer_row["domain_name"] != instance
                or actualizer_row["disposition"] != "live"
            ):
                continue
            inputs = {
                reference.value
                for reference in semantic.get("inputs")
                if isinstance(reference, CoreName)
            }
            shared = sorted(inputs & consumed_set)
            if not shared:
                continue
            self._commit_projection_occurrence(
                db,
                kind="Preclude",
                consumes=(actualizer.value,),
                establishes=(),
                fact={
                    "possibility": name,
                    "because": because,
                    "shared_inputs": shared,
                },
            )
            precluded.append(name)
        return precluded

    def reserve_name(self, *, kind: str, request_id: str) -> str:
        payload = {"kind": kind}
        with self._tx() as db:
            old = self._idem(db, request_id, "reserve_name", payload)
            if old is not None:
                return old["name"]
            name = self._new_name(db, kind)
            self._event(db, "name_reserved", {"name": name, "kind": kind, "new_names": [name]})
            result = {"name": name}
            self._idem_put(db, request_id, "reserve_name", payload, result)
            return name

    def create_nema(self, *, initial: Frame, request_id: str) -> dict[str, str]:
        payload = asdict(initial)
        with self._tx() as db:
            old = self._idem(db, request_id, "create_nema", payload)
            if old is not None:
                return old
            nema = self._new_name(db, "nema")
            session = self._new_name(db, "session")
            meta = self._new_name(db, "socket")
            protocol = ProtocolSpec(
                roles={"self": {"q": Transition("send", "realize", "q")}, "trusted": {"q": Transition("recv", "realize", "q")}},
                initial={"self": "q", "trusted": "q"},
            )
            pcid = self._put_protocol(db, protocol)
            fcid = self._put_frame(db, initial)
            db.execute("INSERT INTO sessions(name,protocol_cid) VALUES (?,?)", (session, pcid))
            db.execute(
                "INSERT INTO sockets(name,session_name,role,protocol_state,holder,disposition) VALUES (?,?,?,?,?,?)",
                (meta, session, "self", "q", nema, "live"),
            )
            db.execute("INSERT INTO nemata(name,frame_cid,meta_socket) VALUES (?,?,?)", (nema, fcid, meta))
            self._event(db, "nema_created", {"nema": nema, "frame": fcid, "meta": meta, "new_names": [nema, session, meta]})
            result = {"nema": nema, "frame": fcid, "meta_socket": meta}
            self._idem_put(db, request_id, "create_nema", payload, result)
            return result

    def _put_frame(self, db: sqlite3.Connection, frame: Frame) -> str:
        cid = frame.cid
        db.execute("INSERT OR IGNORE INTO frames(cid,body_json) VALUES (?,?)", (cid, canonical_bytes(frame).decode()))
        return cid

    def _put_protocol(self, db: sqlite3.Connection, protocol: ProtocolSpec) -> str:
        cid = content_id(protocol)
        db.execute("INSERT OR IGNORE INTO protocols(cid,body_json) VALUES (?,?)", (cid, canonical_bytes(protocol).decode()))
        return cid

    def _load_protocol(self, db: sqlite3.Connection, cid: str) -> ProtocolSpec:
        raw = json.loads(db.execute("SELECT body_json FROM protocols WHERE cid=?", (cid,)).fetchone()[0])
        roles = {
            role: {state: Transition(**transition) for state, transition in states.items()}
            for role, states in raw["roles"].items()
        }
        return ProtocolSpec(roles=roles, initial=raw["initial"])

    def open_session(self, *, protocol: ProtocolSpec, holders: dict[str, str], request_id: str) -> dict[str, Any]:
        payload = {"protocol": asdict(protocol), "holders": holders}
        if set(holders) != set(protocol.initial):
            raise ValueError("holders must name every protocol role exactly once")
        with self._tx() as db:
            old = self._idem(db, request_id, "open_session", payload)
            if old is not None:
                return old
            session = self._new_name(db, "session")
            pcid = self._put_protocol(db, protocol)
            db.execute("INSERT INTO sessions(name,protocol_cid) VALUES (?,?)", (session, pcid))
            sockets: dict[str, str] = {}
            new_names = [session]
            for role, state in protocol.initial.items():
                socket = self._new_name(db, "socket")
                new_names.append(socket)
                sockets[role] = socket
                db.execute(
                    "INSERT INTO sockets(name,session_name,role,protocol_state,holder,disposition) VALUES (?,?,?,?,?,?)",
                    (socket, session, role, state, holders[role], "live"),
                )
            self._event(db, "session_opened", {"session": session, "sockets": sockets, "new_names": new_names})
            result = {"session": session, "sockets": sockets}
            self._idem_put(db, request_id, "open_session", payload, result)
            return result

    def publish_frame(
        self,
        *,
        nema: str,
        expected_meta_socket: str,
        frame: Frame,
        offers: list[OfferSpec],
        request_id: str,
        consume_receipts: list[str] | None = None,
    ) -> dict[str, Any]:
        consume_receipts = list(consume_receipts or [])
        payload = {
            "nema": nema,
            "expected_meta_socket": expected_meta_socket,
            "frame": asdict(frame),
            "offers": [asdict(o) for o in offers],
            "consume_receipts": consume_receipts,
        }
        with self._tx() as db:
            old = self._idem(db, request_id, "publish_frame", payload)
            if old is not None:
                return old
            head = db.execute("SELECT frame_cid,meta_socket FROM nemata WHERE name=?", (nema,)).fetchone()
            if head is None or head["meta_socket"] != expected_meta_socket:
                raise StaleSocket("meta socket is not current")
            meta_row = db.execute("SELECT disposition,session_name FROM sockets WHERE name=?", (expected_meta_socket,)).fetchone()
            if meta_row is None or meta_row["disposition"] != "live":
                raise StaleSocket("meta socket is not live")

            receipt_rows: list[sqlite3.Row] = []
            for receipt_name in consume_receipts:
                receipt = db.execute("SELECT * FROM receipts WHERE name=?", (receipt_name,)).fetchone()
                if receipt is None or receipt["holder"] != nema:
                    raise TrustedError(f"receipt {receipt_name} is not available to {nema}")
                if receipt["incorporated"]:
                    raise Conflict(f"receipt {receipt_name} was already incorporated")
                receipt_rows.append(receipt)

            fcid = self._put_frame(db, frame)
            offer_names: list[str] = []
            new_names: list[str] = []
            for spec in offers:
                row = db.execute(
                    "SELECT s.*, se.protocol_cid FROM sockets s JOIN sessions se ON se.name=s.session_name WHERE s.name=?",
                    (spec.socket,),
                ).fetchone()
                if row is None or row["holder"] != nema or row["disposition"] != "live":
                    raise StaleSocket(f"socket {spec.socket} not live and held by {nema}")
                protocol = self._load_protocol(db, row["protocol_cid"])
                expected = protocol.transition(row["role"], row["protocol_state"])
                if expected.direction != spec.direction or expected.label != spec.label:
                    raise TrustedError(f"illegal operation at socket {spec.socket}")
                offer = self._new_name(db, "offer")
                new_names.append(offer)
                offer_names.append(offer)
                db.execute(
                    "INSERT INTO offers(name,socket_name,direction,label,payload_json,continuation_json,state) VALUES (?,?,?,?,?,?,?)",
                    (
                        offer,
                        spec.socket,
                        spec.direction,
                        spec.label,
                        json.dumps(spec.payload, sort_keys=True, separators=(",", ":")),
                        json.dumps(spec.continuation, sort_keys=True, separators=(",", ":")),
                        "open",
                    ),
                )
                db.execute("UPDATE sockets SET disposition='offered' WHERE name=?", (spec.socket,))

            next_meta = self._new_name(db, "socket")
            new_names.append(next_meta)
            db.execute("UPDATE sockets SET disposition='spent' WHERE name=?", (expected_meta_socket,))
            db.execute(
                "INSERT INTO sockets(name,session_name,role,protocol_state,holder,disposition) VALUES (?,?,?,?,?,?)",
                (next_meta, meta_row["session_name"], "self", "q", nema, "live"),
            )
            db.execute("UPDATE nemata SET frame_cid=?,meta_socket=? WHERE name=?", (fcid, next_meta, nema))
            for receipt in receipt_rows:
                db.execute("UPDATE receipts SET incorporated=1 WHERE name=?", (receipt["name"],))
            self._event(
                db,
                "frame_published",
                {
                    "nema": nema,
                    "previous_meta": expected_meta_socket,
                    "next_meta": next_meta,
                    "frame": fcid,
                    "offers": offer_names,
                    "consumed_receipts": consume_receipts,
                    "new_names": new_names,
                },
            )
            result = {
                "frame": fcid,
                "meta_socket": next_meta,
                "offers": offer_names,
                "consumed_receipts": consume_receipts,
            }
            self._idem_put(db, request_id, "publish_frame", payload, result)
            return result

    def match(self, *, left_offer: str, right_offer: str, request_id: str) -> dict[str, Any]:
        payload = {"left_offer": left_offer, "right_offer": right_offer}
        with self._tx() as db:
            old = self._idem(db, request_id, "match", payload)
            if old is not None:
                return old
            l = db.execute(
                "SELECT o.*, s.session_name,s.role,s.protocol_state,s.holder,s.disposition,se.protocol_cid FROM offers o JOIN sockets s ON s.name=o.socket_name JOIN sessions se ON se.name=s.session_name WHERE o.name=?",
                (left_offer,),
            ).fetchone()
            r = db.execute(
                "SELECT o.*, s.session_name,s.role,s.protocol_state,s.holder,s.disposition,se.protocol_cid FROM offers o JOIN sockets s ON s.name=o.socket_name JOIN sessions se ON se.name=s.session_name WHERE o.name=?",
                (right_offer,),
            ).fetchone()
            if l is None or r is None:
                raise TrustedError("offer not found")
            if l["state"] != "open" or r["state"] != "open" or l["disposition"] != "offered" or r["disposition"] != "offered":
                raise StaleSocket("offer or socket already consumed")
            if l["session_name"] != r["session_name"] or l["protocol_cid"] != r["protocol_cid"]:
                raise TrustedError("offers are not in the same session/protocol")
            if l["direction"] == r["direction"] or l["label"] != r["label"]:
                raise TrustedError("offers are not complementary")

            protocol = self._load_protocol(db, l["protocol_cid"])
            lt = protocol.transition(l["role"], l["protocol_state"])
            rt = protocol.transition(r["role"], r["protocol_state"])
            if (lt.direction, lt.label) != (l["direction"], l["label"]) or (rt.direction, rt.label) != (r["direction"], r["label"]):
                raise TrustedError("offer no longer agrees with protocol state")

            send = l if l["direction"] == "send" else r
            payload_json = send["payload_json"]
            match_name = self._new_name(db, "match")
            new_names = [match_name]

            successors: dict[str, str | None] = {}
            receipt_rows: list[tuple[str, sqlite3.Row, str, str | None]] = []
            for side, row, transition in (("left", l, lt), ("right", r, rt)):
                old_socket = row["socket_name"]
                db.execute("UPDATE sockets SET disposition='spent' WHERE name=?", (old_socket,))
                successor: str | None = None
                if transition.next_state != "End":
                    successor = self._new_name(db, "socket")
                    new_names.append(successor)
                    db.execute(
                        "INSERT INTO sockets(name,session_name,role,protocol_state,holder,disposition) VALUES (?,?,?,?,?,?)",
                        (successor, row["session_name"], row["role"], transition.next_state, row["holder"], "live"),
                    )
                successors[side] = successor
                receipt = self._new_name(db, "receipt")
                new_names.append(receipt)
                receipt_rows.append((receipt, row, old_socket, successor))

            db.execute("UPDATE offers SET state='matched' WHERE name IN (?,?)", (left_offer, right_offer))
            db.execute(
                "INSERT INTO matches(name,left_offer,right_offer,left_successor,right_successor) VALUES (?,?,?,?,?)",
                (match_name, left_offer, right_offer, successors["left"], successors["right"]),
            )
            for receipt, row, old_socket, successor in receipt_rows:
                db.execute(
                    "INSERT INTO receipts(name,holder,match_name,old_socket,successor_socket,payload_json) VALUES (?,?,?,?,?,?)",
                    (receipt, row["holder"], match_name, old_socket, successor, payload_json),
                )
            self._event(
                db,
                "matched",
                {
                    "match": match_name,
                    "left_offer": left_offer,
                    "right_offer": right_offer,
                    "successors": successors,
                    "new_names": new_names,
                },
            )
            result = {"match": match_name, "successors": successors}
            self._idem_put(db, request_id, "match", payload, result)
            return result


    def admit_authority_domain(
        self,
        *,
        description: Any,
        establishes: tuple[ProjectionGrant, ...],
        request_id: str,
    ) -> dict[str, Any]:
        """Explicit genesis for one authority-local domain."""

        keys = [grant.key for grant in establishes]
        if len(set(keys)) != len(keys):
            raise Conflict("genesis projection keys must be unique")
        payload = {
            "description": description,
            "establishes": [
                {
                    "key": grant.key,
                    "holder": grant.holder,
                    "description": grant.description,
                }
                for grant in establishes
            ],
        }
        with self._tx() as db:
            old = self._idem(db, request_id, "admit_authority_domain", payload)
            if old is not None:
                return old

            domain = self._new_name(db, "domain")
            db.execute("INSERT INTO authority_domains(name) VALUES (?)", (domain,))
            description_cid = self._bind_eidos_value(
                db,
                name=domain,
                value=description,
            )

            projections: dict[str, str] = {}
            new_names = [domain]
            for grant in establishes:
                projection = self._new_name(db, "projection")
                new_names.append(projection)
                projections[grant.key] = projection
                db.execute(
                    "INSERT INTO projections(name,domain_name,holder,disposition) "
                    "VALUES (?,?,?,?)",
                    (projection, domain, grant.holder, "live"),
                )
                self._bind_eidos_value(
                    db,
                    name=projection,
                    value=grant.description,
                )

            self._event(
                db,
                "authority_domain_admitted",
                {
                    "domain": domain,
                    "description": description_cid,
                    "projections": projections,
                    "new_names": new_names,
                },
            )
            result = {
                "domain": domain,
                "instance": domain,
                "description": description_cid,
                "projections": projections,
            }
            self._idem_put(db, request_id, "admit_authority_domain", payload, result)
            return result

    def authority_domain(self, domain: str) -> dict[str, Any]:
        row = self.db.execute(
            "SELECT name FROM authority_domains WHERE name=?",
            (domain,),
        ).fetchone()
        if row is None:
            raise KeyError(domain)
        bound = self.named_eidos_value(domain)
        return {
            "name": domain,
            "description_cid": bound["cid"],
            "description": bound["value"],
        }

    def projection(self, projection: str) -> dict[str, Any]:
        row = self.db.execute(
            "SELECT * FROM projections WHERE name=?",
            (projection,),
        ).fetchone()
        if row is None:
            raise KeyError(projection)
        bound = self.named_eidos_value(projection)
        description = bound["value"]
        item = dict(row)
        item["instance_name"] = item["domain_name"]
        item["description_cid"] = bound["cid"]
        item["description"] = description
        if (
            isinstance(description, RecordValue)
            and description.get("$kind") == "Projection"
        ):
            item["seed_key"] = str(description.get("key"))
            item["role"] = str(description.get("role"))
            item["protocol_state"] = str(description.get("state"))
        return item


    def create_observed_cut(
        self,
        *,
        instance: str,
        observer: str,
        protocol_cid: str,
        projections: list[str],
        request_id: str,
        parent_cut: str | None = None,
        parent_occurrence: str | None = None,
        elaborator: str | None = None,
    ) -> dict[str, Any]:
        """Create one observer-relative causal cut as an ordinary named Value."""

        elaborator = observer if elaborator is None else elaborator
        payload = {
            "instance": instance,
            "observer": observer,
            "protocol_cid": protocol_cid,
            "projections": sorted(projections),
            "parent_cut": parent_cut,
            "parent_occurrence": parent_occurrence,
            "elaborator": elaborator,
        }
        with self._tx() as db:
            old = self._idem(db, request_id, "create_observed_cut", payload)
            if old is not None:
                return old

            if db.execute(
                "SELECT 1 FROM authority_domains WHERE name=?",
                (instance,),
            ).fetchone() is None:
                raise KeyError(instance)

            unique = sorted(set(projections))
            if len(unique) != len(projections):
                raise ValueError("cut projection names must be unique")

            for projection in unique:
                row = db.execute(
                    "SELECT * FROM projections WHERE name=?",
                    (projection,),
                ).fetchone()
                if (
                    row is None
                    or row["domain_name"] != instance
                    or row["disposition"] != "live"
                ):
                    raise StaleProjection(
                        f"projection {projection!r} is not live in instance {instance!r}"
                    )

            cut = self._new_name(db, "cut")
            authority = self._new_name(db, "projection")
            db.execute(
                "INSERT INTO projections(name,domain_name,holder,disposition) "
                "VALUES (?,?,?,?)",
                (authority, instance, elaborator, "live"),
            )
            self._bind_eidos_value(
                db,
                name=authority,
                value=projection_value(
                    key=f"meta:elaborator:{cut}",
                    role=ELABORATOR_ROLE,
                    state=elaborator_state(cut),
                ),
            )

            cut_cid = self._bind_eidos_value(
                db,
                name=cut,
                value=cut_value(
                    name=cut,
                    observer=observer,
                    protocol_cid=protocol_cid,
                    projections=tuple(unique),
                    elaborator_projection=authority,
                    parent_cut=parent_cut,
                    parent_occurrence=parent_occurrence,
                ),
            )
            self._event(
                db,
                "causal_cut_created",
                {
                    "cut": cut,
                    "observer": observer,
                    "instance": instance,
                    "protocol_cid": protocol_cid,
                    "parent_cut": parent_cut,
                    "parent_occurrence": parent_occurrence,
                    "projections": unique,
                    "elaborator": elaborator,
                    "elaborator_projection": authority,
                    "value": cut_cid,
                    "new_names": [cut, authority],
                },
            )
            result = {
                "cut": cut,
                "observer": observer,
                "authority": authority,
                "elaborator_projection": authority,
                "value": cut_cid,
            }
            self._idem_put(db, request_id, "create_observed_cut", payload, result)
            return result

    def causal_cut(self, cut: str) -> dict[str, Any]:
        semantic = self.named_eidos_value(cut)["value"]
        if (
            not isinstance(semantic, RecordValue)
            or semantic.get("$kind") != "Cut"
        ):
            raise Conflict(f"Name {cut!r} does not denote a Cut Value")

        elaborator = semantic.get("elaborator")
        if not isinstance(elaborator, CoreName):
            raise Conflict("Cut Value must name its Elaborator projection")
        authority_row = self.db.execute(
            "SELECT * FROM projections WHERE name=?",
            (elaborator.value,),
        ).fetchone()
        if authority_row is None:
            raise KeyError(elaborator.value)

        parent_cut = semantic.get("parent_cut")
        parent_occurrence = semantic.get("parent_occurrence")
        item: dict[str, Any] = {
            "name": cut,
            "instance_name": authority_row["domain_name"],
            "observer": str(semantic.get("observer")),
            "protocol_cid": str(semantic.get("protocol")),
            "parent_cut": None if parent_cut is None else parent_cut.value,
            "parent_occurrence": (
                None if parent_occurrence is None else parent_occurrence.value
            ),
            "state": self._cut_state(
                self.db,
                cut=cut,
                semantic=semantic,
            ),
            "elaborator_projection": elaborator.value,
            "projections": [],
        }
        for reference in semantic.get("projections"):
            if not isinstance(reference, CoreName):
                raise Conflict("Cut projection references must be Names")
            item["projections"].append(self.projection(reference.value))
        return item

    def admit_cut_elaboration(
        self,
        *,
        blueprint: CutElaboration,
        authorities: dict[str, str],
        request_id: str,
    ) -> dict[str, Any]:
        """Admit possibilities derived from named Cut Values."""

        payload = {
            "blueprint": asdict(blueprint),
            "proof": blueprint.proof,
            "authorities": dict(sorted(authorities.items())),
        }
        with self._tx() as db:
            old = self._idem(db, request_id, "admit_cut_elaboration", payload)
            if old is not None:
                return old

            if set(authorities) != set(blueprint.cuts):
                raise Conflict("elaboration authority must be supplied for every cut")

            observed_projection_names: set[str] = set()
            instance_names: set[str] = set()
            for cut in blueprint.cuts:
                semantic = self._named_eidos_value(db, cut)["value"]
                if (
                    not isinstance(semantic, RecordValue)
                    or semantic.get("$kind") != "Cut"
                ):
                    raise Conflict(f"Name {cut!r} does not denote a Cut Value")
                if semantic.get("protocol") != blueprint.protocol_cid:
                    raise Conflict("cut names a different protocol commitment")

                authority = authorities[cut]
                semantic_authority = semantic.get("elaborator")
                if (
                    not isinstance(semantic_authority, CoreName)
                    or semantic_authority.value != authority
                ):
                    raise Conflict(
                        "Elaborator projection does not match Cut Value"
                    )

                try:
                    authority_row = self.projection(authority)
                except KeyError:
                    authority_row = None
                if (
                    authority_row is None
                    or authority_row.get("role") != ELABORATOR_ROLE
                    or authority_row.get("protocol_state") != elaborator_state(cut)
                    or authority_row["holder"] != blueprint.elaborator
                    or authority_row["disposition"] != "live"
                ):
                    raise Conflict(
                        "Elaborator projection is not live/bound for this cut"
                    )

                instance = authority_row["domain_name"]
                instance_names.add(instance)

                for reference in semantic.get("projections"):
                    if not isinstance(reference, CoreName):
                        raise Conflict("Cut projection references must be Names")
                    projection_row = db.execute(
                        "SELECT domain_name FROM projections WHERE name=?",
                        (reference.value,),
                    ).fetchone()
                    if (
                        projection_row is None
                        or projection_row["domain_name"] != instance
                    ):
                        raise Conflict(
                            "Cut Value references projection outside its authority instance"
                        )
                    observed_projection_names.add(reference.value)

            supplied = {projection.name for projection in blueprint.projections}
            if supplied != observed_projection_names:
                raise Conflict(
                    "elaboration does not name exactly the union of observed Cut Values"
                )

            if len(instance_names) != 1:
                raise Conflict("joined cuts must belong to one protocol instance")
            instance = next(iter(instance_names))

            possibilities: dict[str, str] = {}
            possibility_seeds: dict[str, Any] = {}
            grants: list[ProjectionGrant] = []
            possibility_names: list[str] = []
            for seed in blueprint.possibilities:
                if not set(seed.consumes) <= observed_projection_names:
                    raise Conflict(
                        f"possibility {seed.key!r} consumes projections outside observed cuts"
                    )
                possibility = self._new_name(db, "observed_possibility")
                possibility_names.append(possibility)
                possibilities[seed.key] = possibility
                possibility_seeds[possibility] = seed
                grants.append(
                    ProjectionGrant(
                        key=f"actualizer:{possibility}",
                        holder=blueprint.actualizer,
                        description=projection_value(
                            key=f"meta:actualizer:{possibility}",
                            role=ACTUALIZER_ROLE,
                            state=actualizer_state(possibility),
                        ),
                    )
                )

            committed = self._commit_projection_occurrence(
                db,
                kind="Elaborate",
                consumes=tuple(
                    authorities[cut] for cut in sorted(blueprint.cuts)
                ),
                establishes=tuple(grants),
                fact={
                    "proof": blueprint.proof,
                    "cuts": list(blueprint.cuts),
                    "observers": list(blueprint.observers),
                    "elaborator": blueprint.elaborator,
                    "actualizer": blueprint.actualizer,
                    "knowledge": list(blueprint.knowledge),
                    "possibilities": possibilities,
                },
            )
            actualizers = {
                possibility: committed["established"][f"actualizer:{possibility}"]
                for possibility in possibilities.values()
            }

            possibility_values: dict[str, str] = {}
            for possibility, projection in actualizers.items():
                seed = possibility_seeds[possibility]
                possibility_values[possibility] = self._bind_eidos_value(
                    db,
                    name=possibility,
                    value=possibility_value(
                        name=possibility,
                        key=seed.key,
                        elaboration=committed["occurrence"],
                        proof=blueprint.proof,
                        reaction=seed.reaction,
                        cuts=tuple(blueprint.cuts),
                        inputs=tuple(seed.consumes),
                        outputs=tuple(
                            {
                                "key": successor.key,
                                "role": successor.role,
                                "state": successor.state,
                                "holder": successor.holder,
                            }
                            for successor in seed.establishes
                        ),
                        actualizer_projection=projection,
                    ),
                )

            elaboration_cid = self._bind_eidos_value(
                db,
                name=committed["occurrence"],
                value=elaboration_value(
                    occurrence=committed["occurrence"],
                    proof=blueprint.proof,
                    protocol_cid=blueprint.protocol_cid,
                    cuts=tuple(blueprint.cuts),
                    observers=tuple(blueprint.observers),
                    elaborator=blueprint.elaborator,
                    actualizer=blueprint.actualizer,
                    knowledge=tuple(blueprint.knowledge),
                    possibilities=tuple(possibilities.values()),
                    consumed=tuple(committed["consumed"]),
                    established=tuple(committed["established"].values()),
                ),
            )

            self._event(
                db,
                "cut_elaboration_admitted",
                {
                    "occurrence": committed["occurrence"],
                    "proof": blueprint.proof,
                    "cuts": list(blueprint.cuts),
                    "observers": list(blueprint.observers),
                    "elaborator": blueprint.elaborator,
                    "actualizer": blueprint.actualizer,
                    "knowledge": list(blueprint.knowledge),
                    "possibilities": possibilities,
                    "actualizer_projections": actualizers,
                    "value": elaboration_cid,
                    "possibility_values": possibility_values,
                    "new_names": possibility_names,
                },
            )
            result = {
                "occurrence": committed["occurrence"],
                "proof": blueprint.proof,
                "possibilities": possibilities,
                "actualizers": actualizers,
                "value": elaboration_cid,
                "possibility_values": possibility_values,
            }
            self._idem_put(db, request_id, "admit_cut_elaboration", payload, result)
            return result

    def actualize_observed(
        self,
        *,
        possibility: str,
        actualizer: str,
        authority: str,
        observation: Any,
        request_id: str,
    ) -> dict[str, Any]:
        """Actualize one named Possibility Value over live authority."""

        payload = {
            "possibility": possibility,
            "actualizer": actualizer,
            "authority": authority,
            "observation": observation,
        }
        with self._tx() as db:
            old = self._idem(db, request_id, "actualize_observed", payload)
            if old is not None:
                return old

            semantic = self._named_eidos_value(db, possibility)["value"]
            if (
                not isinstance(semantic, RecordValue)
                or semantic.get("$kind") != "Possibility"
            ):
                raise Conflict(
                    f"Name {possibility!r} does not denote a Possibility Value"
                )

            actualizer_ref = semantic.get("actualizer")
            if (
                not isinstance(actualizer_ref, CoreName)
                or actualizer_ref.value != authority
            ):
                raise Conflict(
                    "Actualizer projection does not match Possibility Value"
                )

            try:
                actualizer_row = self.projection(authority)
            except KeyError:
                actualizer_row = None
            if (
                actualizer_row is None
                or actualizer_row.get("role") != ACTUALIZER_ROLE
                or actualizer_row.get("protocol_state") != actualizer_state(possibility)
                or actualizer_row["holder"] != actualizer
                or actualizer_row["disposition"] != "live"
            ):
                raise Conflict(
                    "Actualizer projection is not live/bound for this possibility"
                )
            instance = actualizer_row["domain_name"]

            input_names: list[str] = []
            for reference in semantic.get("inputs"):
                if not isinstance(reference, CoreName):
                    raise Conflict("Possibility inputs must be projection Names")
                projection_row = db.execute(
                    "SELECT * FROM projections WHERE name=?",
                    (reference.value,),
                ).fetchone()
                if (
                    projection_row is None
                    or projection_row["domain_name"] != instance
                    or projection_row["disposition"] != "live"
                ):
                    raise StaleProjection(
                        f"possibility input {reference.value!r} is not live"
                    )
                input_names.append(reference.value)

            cause_cuts: list[str] = []
            cut_semantics: dict[str, RecordValue] = {}
            for reference in semantic.get("cuts"):
                if not isinstance(reference, CoreName):
                    raise Conflict("Possibility cause cuts must be Names")
                cut = reference.value
                cut_value_ = self._named_eidos_value(db, cut)["value"]
                if (
                    not isinstance(cut_value_, RecordValue)
                    or cut_value_.get("$kind") != "Cut"
                ):
                    raise Conflict(f"Name {cut!r} does not denote a Cut Value")
                cause_cuts.append(cut)
                cut_semantics[cut] = cut_value_

            reaction = str(semantic.get("reaction"))
            occurrence = self._new_name(db, "observed_occurrence")
            successor_cuts = {
                old_cut: self._new_name(db, "cut")
                for old_cut in cause_cuts
            }

            output_templates: list[dict[str, str]] = []
            grants: list[ProjectionGrant] = []
            for output in semantic.get("outputs"):
                if (
                    not isinstance(output, RecordValue)
                    or output.get("$kind") != "ProjectionTemplate"
                ):
                    raise Conflict(
                        "Possibility outputs must be ProjectionTemplate Values"
                    )
                template = {
                    "key": str(output.get("key")),
                    "role": str(output.get("role")),
                    "state": str(output.get("state")),
                    "holder": str(output.get("holder")),
                }
                output_templates.append(template)
                grants.append(
                    ProjectionGrant(
                        key=template["key"],
                        holder=template["holder"],
                        description=projection_value(
                            key=template["key"],
                            role=template["role"],
                            state=template["state"],
                        ),
                    )
                )

            for old_cut, new_cut in successor_cuts.items():
                cut_value_ = cut_semantics[old_cut]
                grants.append(
                    ProjectionGrant(
                        key=f"elaborator:{new_cut}",
                        holder=str(cut_value_.get("observer")),
                        description=projection_value(
                            key=f"meta:elaborator:{new_cut}",
                            role=ELABORATOR_ROLE,
                            state=elaborator_state(new_cut),
                        ),
                    )
                )

            committed = self._commit_projection_occurrence(
                db,
                kind="Actualize",
                consumes=(authority, *tuple(input_names)),
                establishes=tuple(grants),
                fact={
                    "possibility": possibility,
                    "reaction": reaction,
                    "actualizer": actualizer,
                    "observation": observation,
                    "cause_cuts": cause_cuts,
                    "successor_cuts": successor_cuts,
                },
                occurrence=occurrence,
            )

            successors = {
                template["key"]: committed["established"][template["key"]]
                for template in output_templates
            }
            successor_by_role = {
                template["role"]: successors[template["key"]]
                for template in output_templates
            }
            elaborators = {
                new_cut: committed["established"][f"elaborator:{new_cut}"]
                for new_cut in successor_cuts.values()
            }

            precluded = self._preclude_competing_possibilities(
                db,
                selected=possibility,
                instance=instance,
                consumed_inputs=tuple(input_names),
                because=occurrence,
            )

            successor_cut_values: dict[str, str] = {}
            consumed_set = set(input_names)
            for old_cut in cause_cuts:
                old_value = cut_semantics[old_cut]
                new_cut = successor_cuts[old_cut]

                new_members: list[str] = []
                for reference in old_value.get("projections"):
                    if not isinstance(reference, CoreName):
                        raise Conflict("Cut projection references must be Names")
                    projection = reference.value
                    if projection in consumed_set:
                        projection_row = self.projection(projection)
                        projection = successor_by_role.get(projection_row["role"])
                        if projection is None:
                            continue
                    new_members.append(projection)

                successor_cut_values[new_cut] = self._bind_eidos_value(
                    db,
                    name=new_cut,
                    value=cut_value(
                        name=new_cut,
                        observer=str(old_value.get("observer")),
                        protocol_cid=str(old_value.get("protocol")),
                        projections=tuple(new_members),
                        elaborator_projection=elaborators[new_cut],
                        parent_cut=old_cut,
                        parent_occurrence=occurrence,
                    ),
                )

            occurrence_cid = self._bind_eidos_value(
                db,
                name=occurrence,
                value=occurrence_value(
                    occurrence=occurrence,
                    reaction=reaction,
                    possibility=possibility,
                    actualizer=actualizer,
                    cause_cuts=tuple(cause_cuts),
                    successor_cuts=tuple(successor_cuts.values()),
                    observation=observation,
                    consumed=tuple(committed["consumed"]),
                    established=tuple(committed["established"].values()),
                ),
            )

            self._event(
                db,
                "observed_occurrence_actualized",
                {
                    "occurrence": occurrence,
                    "authority_occurrence": committed["occurrence"],
                    "possibility": possibility,
                    "reaction": reaction,
                    "actualizer": actualizer,
                    "actualizer_projection": authority,
                    "cause_cuts": cause_cuts,
                    "successor_cuts": successor_cuts,
                    "elaborator_projections": elaborators,
                    "consumed": input_names,
                    "successors": successors,
                    "precluded": precluded,
                    "observation": observation,
                    "value": occurrence_cid,
                    "successor_cut_values": successor_cut_values,
                    "new_names": list(successor_cuts.values()),
                },
            )
            result = {
                "occurrence": occurrence,
                "reaction": reaction,
                "actualizer": actualizer,
                "actualizer_projection": authority,
                "cause_cuts": cause_cuts,
                "successor_cuts": successor_cuts,
                "elaboration_authorities": elaborators,
                "elaborators": elaborators,
                "consumed": input_names,
                "successors": successors,
                "precluded": precluded,
                "value": occurrence_cid,
                "successor_cut_values": successor_cut_values,
            }
            self._idem_put(db, request_id, "actualize_observed", payload, result)
            return result

    def observed_possibility(self, possibility: str) -> dict[str, Any]:
        semantic = self.named_eidos_value(possibility)["value"]
        if (
            not isinstance(semantic, RecordValue)
            or semantic.get("$kind") != "Possibility"
        ):
            raise Conflict(
                f"Name {possibility!r} does not denote a Possibility Value"
            )

        actualizer = semantic.get("actualizer")
        if not isinstance(actualizer, CoreName):
            raise Conflict("Possibility actualizer reference must be a Name")
        actualizer_row = self.projection(actualizer.value)

        item: dict[str, Any] = {
            "name": possibility,
            "instance_name": actualizer_row["domain_name"],
            "proof": str(semantic.get("proof")),
            "seed_key": str(semantic.get("key")),
            "reaction": str(semantic.get("reaction")),
            "state": self._possibility_state(
                self.db,
                possibility=possibility,
                semantic=semantic,
            ),
            "cuts": [
                reference.value
                for reference in semantic.get("cuts")
                if isinstance(reference, CoreName)
            ],
            "inputs": [
                reference.value
                for reference in semantic.get("inputs")
                if isinstance(reference, CoreName)
            ],
            "actualizer_projection": actualizer.value,
            "actualizer": actualizer_row["holder"],
        }

        elaboration = semantic.get("elaboration")
        if isinstance(elaboration, CoreName):
            item["elaboration"] = elaboration.value
            elaboration_value_ = self.named_eidos_value(elaboration.value)["value"]
            if (
                isinstance(elaboration_value_, RecordValue)
                and elaboration_value_.get("$kind") == "Elaboration"
            ):
                item["elaborator"] = str(
                    elaboration_value_.get("elaborator")
                )
        return item

    def observed_occurrence(self, occurrence: str) -> dict[str, Any]:
        semantic = self.named_eidos_value(occurrence)["value"]
        if (
            not isinstance(semantic, RecordValue)
            or semantic.get("$kind") != "Occurrence"
        ):
            raise Conflict(
                f"Name {occurrence!r} does not denote an Occurrence Value"
            )

        authority = self.authority_occurrence(occurrence)
        possibility = semantic.get("possibility")
        if not isinstance(possibility, CoreName):
            raise Conflict("Occurrence possibility reference must be a Name")

        item: dict[str, Any] = {
            "name": occurrence,
            "instance_name": authority["instance_name"],
            "possibility_name": possibility.value,
            "actualizer": str(semantic.get("actualizer")),
            "observation": semantic.get("observation"),
            "cuts": [
                reference.value
                for reference in semantic.get("cause_cuts")
                if isinstance(reference, CoreName)
            ],
            "successor_cuts": [
                reference.value
                for reference in semantic.get("successor_cuts")
                if isinstance(reference, CoreName)
            ],
            "consumed": [
                reference.value
                for reference in semantic.get("consumed")
                if isinstance(reference, CoreName)
            ],
            "established": [
                reference.value
                for reference in semantic.get("established")
                if isinstance(reference, CoreName)
            ],
        }

        possibility_value_ = self.named_eidos_value(possibility.value)["value"]
        if (
            not isinstance(possibility_value_, RecordValue)
            or possibility_value_.get("$kind") != "Possibility"
        ):
            raise Conflict(
                "Occurrence Possibility does not resolve to a Possibility Value"
            )

        actualizer_ref = possibility_value_.get("actualizer")
        actualizer_name = (
            actualizer_ref.value
            if isinstance(actualizer_ref, CoreName)
            else None
        )
        item["inputs"] = [
            name
            for name in item["consumed"]
            if name != actualizer_name
        ]

        output_roles = {
            str(template.get("role"))
            for template in possibility_value_.get("outputs")
            if isinstance(template, RecordValue)
            and template.get("$kind") == "ProjectionTemplate"
        }
        outputs: list[str] = []
        for projection in item["established"]:
            try:
                row = self.projection(projection)
            except KeyError:
                row = None
            if row is not None and row.get("role") in output_roles:
                outputs.append(projection)
        item["outputs"] = outputs
        return item

    def authority_occurrence(self, occurrence: str) -> dict[str, Any]:
        row = self.db.execute(
            "SELECT * FROM authority_occurrences WHERE name=?",
            (occurrence,),
        ).fetchone()
        if row is None:
            raise KeyError(occurrence)
        item = dict(row)
        item["instance_name"] = item["domain_name"]
        item["fact"] = json.loads(item.pop("fact_json"))
        item["inputs"] = [
            r["projection_name"]
            for r in self.db.execute(
                "SELECT projection_name FROM authority_occurrence_inputs "
                "WHERE occurrence_name=? ORDER BY ordinal",
                (occurrence,),
            ).fetchall()
        ]
        item["outputs"] = {
            r["output_key"]: r["projection_name"]
            for r in self.db.execute(
                "SELECT output_key,projection_name FROM authority_occurrence_outputs "
                "WHERE occurrence_name=? ORDER BY ordinal",
                (occurrence,),
            ).fetchall()
        }
        return item

    def transfer_projection(
        self,
        *,
        projection: str,
        from_holder: str,
        to_holder: str,
        request_id: str,
    ) -> dict[str, Any]:
        """Delegate any live projection capability without changing its identity."""

        payload = {
            "projection": projection,
            "from_holder": from_holder,
            "to_holder": to_holder,
        }
        with self._tx() as db:
            old = self._idem(db, request_id, "transfer_projection", payload)
            if old is not None:
                return old
            row = db.execute(
                "SELECT holder,disposition FROM projections WHERE name=?",
                (projection,),
            ).fetchone()
            if (
                row is None
                or row["holder"] != from_holder
                or row["disposition"] != "live"
            ):
                raise StaleProjection(
                    "only the holder of a live projection may delegate it"
                )
            db.execute(
                "UPDATE projections SET holder=? WHERE name=?",
                (to_holder, projection),
            )
            semantic = self.projection(projection)
            self._event(
                db,
                "projection_transferred",
                {
                    "projection": projection,
                    "role": semantic.get("role"),
                    "protocol_state": semantic.get("protocol_state"),
                    "from": from_holder,
                    "to": to_holder,
                },
            )
            result = {
                "projection": projection,
                "holder": to_holder,
                "role": semantic.get("role"),
                "protocol_state": semantic.get("protocol_state"),
            }
            self._idem_put(db, request_id, "transfer_projection", payload, result)
            return result

    def transfer_socket(self, *, socket: str, from_holder: str, to_holder: str, request_id: str) -> dict[str, Any]:
        payload = {"socket": socket, "from_holder": from_holder, "to_holder": to_holder}
        with self._tx() as db:
            old = self._idem(db, request_id, "transfer_socket", payload)
            if old is not None:
                return old
            row = db.execute("SELECT holder,disposition FROM sockets WHERE name=?", (socket,)).fetchone()
            if row is None or row["holder"] != from_holder or row["disposition"] != "live":
                raise StaleSocket("only the holder of a live, unoffered socket may transfer it")
            db.execute("UPDATE sockets SET holder=? WHERE name=?", (to_holder, socket))
            self._event(db, "socket_transferred", {"socket": socket, "from": from_holder, "to": to_holder})
            result = {"socket": socket, "holder": to_holder}
            self._idem_put(db, request_id, "transfer_socket", payload, result)
            return result

    def head(self, nema: str) -> dict[str, str]:
        row = self.db.execute("SELECT frame_cid,meta_socket FROM nemata WHERE name=?", (nema,)).fetchone()
        if row is None:
            raise KeyError(nema)
        return dict(row)

    def frame(self, cid: str) -> Frame:
        row = self.db.execute("SELECT body_json FROM frames WHERE cid=?", (cid,)).fetchone()
        if row is None:
            raise KeyError(cid)
        raw = json.loads(row["body_json"])
        return Frame(bindings=raw.get("bindings", {}), residuals=tuple(raw.get("residuals", [])))

    def socket(self, socket: str) -> dict[str, Any]:
        row = self.db.execute("SELECT * FROM sockets WHERE name=?", (socket,)).fetchone()
        if row is None:
            raise KeyError(socket)
        return dict(row)

    def expected_transition(self, socket: str) -> Transition:
        row = self.db.execute(
            "SELECT s.role,s.protocol_state,se.protocol_cid FROM sockets s "
            "JOIN sessions se ON se.name=s.session_name WHERE s.name=?",
            (socket,),
        ).fetchone()
        if row is None:
            raise KeyError(socket)
        protocol = self._load_protocol(self.db, row["protocol_cid"])
        return protocol.transition(row["role"], row["protocol_state"])

    def open_offers(self) -> list[dict[str, Any]]:
        rows = self.db.execute(
            "SELECT o.*,s.session_name,s.role,s.holder,s.protocol_state "
            "FROM offers o JOIN sockets s ON s.name=o.socket_name "
            "WHERE o.state='open' AND s.disposition='offered' ORDER BY o.rowid"
        ).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["payload"] = json.loads(item.pop("payload_json"))
            item["continuation"] = json.loads(item.pop("continuation_json"))
            out.append(item)
        return out

    def receipt(self, receipt: str) -> dict[str, Any]:
        row = self.db.execute("SELECT * FROM receipts WHERE name=?", (receipt,)).fetchone()
        if row is None:
            raise KeyError(receipt)
        item = dict(row)
        item["payload"] = json.loads(item.pop("payload_json"))
        return item

    def receipts(self, holder: str, *, unincorporated_only: bool = True) -> list[dict[str, Any]]:
        sql = "SELECT * FROM receipts WHERE holder=?"
        args: tuple[Any, ...] = (holder,)
        if unincorporated_only:
            sql += " AND incorporated=0"
        sql += " ORDER BY rowid"
        return [dict(r) for r in self.db.execute(sql, args).fetchall()]

    def incorporate_receipt(self, *, holder: str, receipt: str, request_id: str) -> dict[str, Any]:
        payload = {"holder": holder, "receipt": receipt}
        with self._tx() as db:
            old = self._idem(db, request_id, "incorporate_receipt", payload)
            if old is not None:
                return old
            row = db.execute("SELECT * FROM receipts WHERE name=?", (receipt,)).fetchone()
            if row is None or row["holder"] != holder:
                raise TrustedError("receipt not available to holder")
            if not row["incorporated"]:
                db.execute("UPDATE receipts SET incorporated=1 WHERE name=?", (receipt,))
                self._event(db, "receipt_incorporated", {"receipt": receipt, "holder": holder})
            result = {
                "receipt": receipt,
                "match": row["match_name"],
                "old_socket": row["old_socket"],
                "successor_socket": row["successor_socket"],
                "payload": json.loads(row["payload_json"]),
            }
            self._idem_put(db, request_id, "incorporate_receipt", payload, result)
            return result

    def events(self) -> list[dict[str, Any]]:
        return [
            {"seq": r["seq"], "kind": r["kind"], "body": json.loads(r["body_json"])}
            for r in self.db.execute("SELECT * FROM events ORDER BY seq").fetchall()
        ]
