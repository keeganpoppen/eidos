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
            CREATE TABLE IF NOT EXISTS occurrence_instances(
              name TEXT PRIMARY KEY REFERENCES names(name),
              protocol TEXT NOT NULL,
              blueprint_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS projections(
              name TEXT PRIMARY KEY REFERENCES names(name),
              instance_name TEXT NOT NULL REFERENCES occurrence_instances(name),
              seed_key TEXT NOT NULL,
              role TEXT NOT NULL,
              protocol_state TEXT NOT NULL,
              holder TEXT NOT NULL,
              disposition TEXT NOT NULL CHECK(disposition IN ('live','spent'))
            );
            CREATE TABLE IF NOT EXISTS protocol_frontiers(
              name TEXT PRIMARY KEY REFERENCES names(name),
              instance_name TEXT NOT NULL REFERENCES occurrence_instances(name),
              protocol_cid TEXT NOT NULL,
              parent_occurrence TEXT,
              generation INTEGER NOT NULL,
              state TEXT NOT NULL CHECK(state IN ('open','elaborated','spent'))
            );
            CREATE TABLE IF NOT EXISTS frontier_members(
              frontier_name TEXT NOT NULL REFERENCES protocol_frontiers(name),
              projection_name TEXT NOT NULL REFERENCES projections(name),
              PRIMARY KEY(frontier_name,projection_name)
            );
            CREATE TABLE IF NOT EXISTS elaboration_authorities(
              token TEXT PRIMARY KEY REFERENCES names(name),
              frontier_name TEXT NOT NULL UNIQUE REFERENCES protocol_frontiers(name),
              disposition TEXT NOT NULL CHECK(disposition IN ('live','spent'))
            );
            CREATE TABLE IF NOT EXISTS reaction_possibilities(
              name TEXT PRIMARY KEY REFERENCES names(name),
              instance_name TEXT NOT NULL REFERENCES occurrence_instances(name),
              seed_key TEXT NOT NULL,
              reaction TEXT NOT NULL,
              state TEXT NOT NULL CHECK(state IN ('open','occurred','precluded'))
            );
            CREATE TABLE IF NOT EXISTS possibility_frontiers(
              possibility_name TEXT PRIMARY KEY REFERENCES reaction_possibilities(name),
              frontier_name TEXT NOT NULL REFERENCES protocol_frontiers(name)
            );
            CREATE TABLE IF NOT EXISTS frontier_admissions(
              frontier_name TEXT PRIMARY KEY REFERENCES protocol_frontiers(name),
              proof TEXT NOT NULL,
              blueprint_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS reaction_inputs(
              possibility_name TEXT NOT NULL REFERENCES reaction_possibilities(name),
              projection_name TEXT NOT NULL REFERENCES projections(name),
              PRIMARY KEY(possibility_name,projection_name)
            );
            CREATE TABLE IF NOT EXISTS reaction_outputs(
              possibility_name TEXT NOT NULL REFERENCES reaction_possibilities(name),
              ordinal INTEGER NOT NULL,
              output_key TEXT NOT NULL,
              role TEXT NOT NULL,
              protocol_state TEXT NOT NULL,
              holder TEXT NOT NULL,
              PRIMARY KEY(possibility_name,output_key)
            );
            CREATE TABLE IF NOT EXISTS occurrences(
              name TEXT PRIMARY KEY REFERENCES names(name),
              instance_name TEXT NOT NULL REFERENCES occurrence_instances(name),
              possibility_name TEXT NOT NULL REFERENCES reaction_possibilities(name),
              observation_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS occurrence_inputs(
              occurrence_name TEXT NOT NULL REFERENCES occurrences(name),
              projection_name TEXT NOT NULL REFERENCES projections(name),
              PRIMARY KEY(occurrence_name,projection_name)
            );
            CREATE TABLE IF NOT EXISTS occurrence_outputs(
              occurrence_name TEXT NOT NULL REFERENCES occurrences(name),
              projection_name TEXT NOT NULL REFERENCES projections(name),
              ordinal INTEGER NOT NULL,
              PRIMARY KEY(occurrence_name,projection_name)
            );
            CREATE TABLE IF NOT EXISTS occurrence_frontiers(
              occurrence_name TEXT PRIMARY KEY REFERENCES occurrences(name),
              frontier_name TEXT NOT NULL REFERENCES protocol_frontiers(name)
            );

            CREATE TABLE IF NOT EXISTS causal_cuts(
              name TEXT PRIMARY KEY REFERENCES names(name),
              instance_name TEXT NOT NULL REFERENCES occurrence_instances(name),
              observer TEXT NOT NULL,
              protocol_cid TEXT NOT NULL,
              parent_cut TEXT REFERENCES causal_cuts(name),
              parent_occurrence TEXT,
              state TEXT NOT NULL CHECK(state IN ('open','elaborated','historical'))
            );
            CREATE TABLE IF NOT EXISTS cut_members(
              cut_name TEXT NOT NULL REFERENCES causal_cuts(name),
              projection_name TEXT NOT NULL REFERENCES projections(name),
              PRIMARY KEY(cut_name,projection_name)
            );
            CREATE TABLE IF NOT EXISTS cut_elaboration_authorities(
              token TEXT PRIMARY KEY REFERENCES names(name),
              cut_name TEXT NOT NULL UNIQUE REFERENCES causal_cuts(name),
              disposition TEXT NOT NULL CHECK(disposition IN ('live','spent'))
            );
            CREATE TABLE IF NOT EXISTS cut_admissions(
              proof TEXT PRIMARY KEY,
              elaborator TEXT NOT NULL,
              actualizer TEXT NOT NULL,
              blueprint_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS cut_admission_cuts(
              proof TEXT NOT NULL REFERENCES cut_admissions(proof),
              cut_name TEXT NOT NULL REFERENCES causal_cuts(name),
              PRIMARY KEY(proof,cut_name)
            );
            CREATE TABLE IF NOT EXISTS observed_possibilities(
              name TEXT PRIMARY KEY REFERENCES names(name),
              instance_name TEXT NOT NULL REFERENCES occurrence_instances(name),
              proof TEXT NOT NULL REFERENCES cut_admissions(proof),
              seed_key TEXT NOT NULL,
              reaction TEXT NOT NULL,
              elaborator TEXT NOT NULL,
              actualizer TEXT NOT NULL,
              state TEXT NOT NULL CHECK(state IN ('open','occurred','precluded'))
            );
            CREATE TABLE IF NOT EXISTS observed_possibility_cuts(
              possibility_name TEXT NOT NULL REFERENCES observed_possibilities(name),
              cut_name TEXT NOT NULL REFERENCES causal_cuts(name),
              PRIMARY KEY(possibility_name,cut_name)
            );
            CREATE TABLE IF NOT EXISTS observed_possibility_actualizers(
              possibility_name TEXT PRIMARY KEY REFERENCES observed_possibilities(name),
              projection_name TEXT NOT NULL UNIQUE REFERENCES projections(name)
            );
            CREATE TABLE IF NOT EXISTS observed_reaction_inputs(
              possibility_name TEXT NOT NULL REFERENCES observed_possibilities(name),
              projection_name TEXT NOT NULL REFERENCES projections(name),
              PRIMARY KEY(possibility_name,projection_name)
            );
            CREATE TABLE IF NOT EXISTS observed_reaction_outputs(
              possibility_name TEXT NOT NULL REFERENCES observed_possibilities(name),
              ordinal INTEGER NOT NULL,
              output_key TEXT NOT NULL,
              role TEXT NOT NULL,
              protocol_state TEXT NOT NULL,
              holder TEXT NOT NULL,
              PRIMARY KEY(possibility_name,output_key)
            );
            CREATE TABLE IF NOT EXISTS observed_occurrences(
              name TEXT PRIMARY KEY REFERENCES names(name),
              instance_name TEXT NOT NULL REFERENCES occurrence_instances(name),
              possibility_name TEXT NOT NULL REFERENCES observed_possibilities(name),
              actualizer TEXT NOT NULL,
              observation_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS observed_occurrence_cuts(
              occurrence_name TEXT NOT NULL REFERENCES observed_occurrences(name),
              cut_name TEXT NOT NULL REFERENCES causal_cuts(name),
              PRIMARY KEY(occurrence_name,cut_name)
            );
            CREATE TABLE IF NOT EXISTS observed_occurrence_inputs(
              occurrence_name TEXT NOT NULL REFERENCES observed_occurrences(name),
              projection_name TEXT NOT NULL REFERENCES projections(name),
              PRIMARY KEY(occurrence_name,projection_name)
            );
            CREATE TABLE IF NOT EXISTS observed_occurrence_outputs(
              occurrence_name TEXT NOT NULL REFERENCES observed_occurrences(name),
              projection_name TEXT NOT NULL REFERENCES projections(name),
              ordinal INTEGER NOT NULL,
              PRIMARY KEY(occurrence_name,projection_name)
            );

            CREATE TABLE IF NOT EXISTS authority_occurrences(
              name TEXT PRIMARY KEY REFERENCES names(name),
              instance_name TEXT NOT NULL REFERENCES occurrence_instances(name),
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
        digest = content_id(payload)
        row = db.execute("SELECT op,digest,result_json FROM commands WHERE request_id=?", (request_id,)).fetchone()
        if row is None:
            return None
        if row["op"] != op or row["digest"] != digest:
            raise Conflict(f"request id {request_id!r} reused with different operation/payload")
        return json.loads(row["result_json"])

    def _idem_put(self, db: sqlite3.Connection, request_id: str, op: str, payload: Any, result: dict[str, Any]) -> None:
        db.execute(
            "INSERT INTO commands(request_id,op,digest,result_json) VALUES (?,?,?,?)",
            (request_id, op, content_id(payload), json.dumps(result, sort_keys=True, separators=(",", ":"))),
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

        instances = {row["instance_name"] for row in rows}
        if len(instances) != 1:
            raise Conflict(
                "one atomic authority occurrence must stay within one instance"
            )
        instance = next(iter(instances))

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
                "INSERT INTO projections("
                "name,instance_name,seed_key,role,protocol_state,holder,disposition"
                ") VALUES (?,?,?,?,?,?,?)",
                (
                    projection,
                    instance,
                    grant.key,
                    grant.role,
                    grant.state,
                    grant.holder,
                    "live",
                ),
            )

        db.execute(
            "INSERT INTO authority_occurrences("
            "name,instance_name,kind,fact_json"
            ") VALUES (?,?,?,?)",
            (
                occurrence,
                instance,
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
                "instance": instance,
                "consumed": list(consumes),
                "established": outputs,
                "fact": fact,
                "new_names": new_names,
            },
        )
        return {
            "occurrence": occurrence,
            "instance": instance,
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
            "establishes": [asdict(grant) for grant in establishes],
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


    def install_occurrence_blueprint(
        self,
        *,
        blueprint: InstanceBlueprint,
        request_id: str,
    ) -> dict[str, Any]:
        """Install generation zero and its already-elaborated possibility space.

        The semantic dual supplies a protocol commitment plus the exact initial
        projections and latent Reactions. Trusted Machinery materializes those
        capabilities and creates one linear protocol-frontier capability whose
        state is already elaborated for generation zero.
        """

        payload = asdict(blueprint)
        with self._tx() as db:
            old = self._idem(db, request_id, "install_occurrence_blueprint", payload)
            if old is not None:
                return old

            projection_seeds = {seed.key: seed for seed in blueprint.projections}
            if len(projection_seeds) != len(blueprint.projections):
                raise ValueError("projection seed keys must be unique")

            possibility_seeds = {seed.key: seed for seed in blueprint.possibilities}
            if len(possibility_seeds) != len(blueprint.possibilities):
                raise ValueError("possibility seed keys must be unique")

            for possibility in blueprint.possibilities:
                unknown = set(possibility.consumes) - set(projection_seeds)
                if unknown:
                    raise ValueError(
                        f"possibility {possibility.key!r} consumes unknown projections "
                        f"{sorted(unknown)!r}"
                    )

            protocol_cid = blueprint.protocol_cid or content_id(blueprint)
            instance = self._new_name(db, "instance")
            frontier = self._new_name(db, "frontier")
            db.execute(
                "INSERT INTO occurrence_instances(name,protocol,blueprint_json) VALUES (?,?,?)",
                (
                    instance,
                    blueprint.protocol,
                    json.dumps(payload, sort_keys=True, separators=(",", ":")),
                ),
            )
            db.execute(
                "INSERT INTO protocol_frontiers("
                "name,instance_name,protocol_cid,parent_occurrence,generation,state"
                ") VALUES (?,?,?,?,?,?)",
                (frontier, instance, protocol_cid, None, 0, "elaborated"),
            )

            projections: dict[str, str] = {}
            new_names = [instance, frontier]
            for seed in blueprint.projections:
                projection = self._new_name(db, "projection")
                projections[seed.key] = projection
                new_names.append(projection)
                db.execute(
                    "INSERT INTO projections("
                    "name,instance_name,seed_key,role,protocol_state,holder,disposition"
                    ") VALUES (?,?,?,?,?,?,?)",
                    (
                        projection,
                        instance,
                        seed.key,
                        seed.role,
                        seed.state,
                        seed.holder,
                        "live",
                    ),
                )
                db.execute(
                    "INSERT INTO frontier_members(frontier_name,projection_name) "
                    "VALUES (?,?)",
                    (frontier, projection),
                )

            possibilities: dict[str, str] = {}
            for seed in blueprint.possibilities:
                possibility = self._new_name(db, "possibility")
                possibilities[seed.key] = possibility
                new_names.append(possibility)
                db.execute(
                    "INSERT INTO reaction_possibilities("
                    "name,instance_name,seed_key,reaction,state"
                    ") VALUES (?,?,?,?,?)",
                    (
                        possibility,
                        instance,
                        seed.key,
                        seed.reaction,
                        "open",
                    ),
                )
                db.execute(
                    "INSERT INTO possibility_frontiers(possibility_name,frontier_name) "
                    "VALUES (?,?)",
                    (possibility, frontier),
                )
                for projection_key in seed.consumes:
                    db.execute(
                        "INSERT INTO reaction_inputs(possibility_name,projection_name) "
                        "VALUES (?,?)",
                        (possibility, projections[projection_key]),
                    )
                for ordinal, successor in enumerate(seed.establishes):
                    db.execute(
                        "INSERT INTO reaction_outputs("
                        "possibility_name,ordinal,output_key,role,protocol_state,holder"
                        ") VALUES (?,?,?,?,?,?)",
                        (
                            possibility,
                            ordinal,
                            successor.key,
                            successor.role,
                            successor.state,
                            successor.holder,
                        ),
                    )

            self._event(
                db,
                "possibility_space_installed",
                {
                    "instance": instance,
                    "protocol": blueprint.protocol,
                    "protocol_cid": protocol_cid,
                    "frontier": frontier,
                    "generation": 0,
                    "projections": projections,
                    "possibilities": possibilities,
                    "new_names": new_names,
                },
            )
            result = {
                "instance": instance,
                "frontier": frontier,
                "protocol_cid": protocol_cid,
                "projections": projections,
                "possibilities": possibilities,
            }
            self._idem_put(
                db,
                request_id,
                "install_occurrence_blueprint",
                payload,
                result,
            )
            return result

    def admit_frontier(
        self,
        *,
        blueprint: FrontierBlueprint,
        authority: str,
        request_id: str,
    ) -> dict[str, Any]:
        """Admit one recursively elaborated possibility space.

        The previous occurrence mints a one-shot elaboration authority for a
        freely referable frontier Name. The semantic elaborator presents that
        authority alongside a proof-shaped blueprint anchored to the same
        protocol commitment.

        Trusted Machinery does not re-run protocol semantics. It checks
        provenance, freshness, and exact frontier membership, records the proof,
        and materializes the latent possibilities.
        """

        payload = asdict(blueprint)
        payload["proof"] = blueprint.proof
        payload["authority"] = authority
        with self._tx() as db:
            old = self._idem(db, request_id, "admit_frontier", payload)
            if old is not None:
                return old

            row = db.execute(
                "SELECT * FROM protocol_frontiers WHERE name=?",
                (blueprint.frontier,),
            ).fetchone()
            if row is None:
                raise KeyError(blueprint.frontier)
            authority_row = db.execute(
                "SELECT frontier_name,disposition FROM elaboration_authorities "
                "WHERE token=?",
                (authority,),
            ).fetchone()
            if (
                authority_row is None
                or authority_row["frontier_name"] != blueprint.frontier
                or authority_row["disposition"] != "live"
            ):
                raise Conflict("elaboration authority is not live for this frontier")

            if row["state"] != "open":
                raise Conflict(
                    f"frontier {blueprint.frontier!r} is {row['state']}, not open"
                )
            if row["protocol_cid"] != blueprint.protocol_cid:
                raise Conflict("frontier proof names a different protocol commitment")
            if row["parent_occurrence"] != blueprint.parent_occurrence:
                raise Conflict("frontier proof names the wrong parent occurrence")

            expected = [
                dict(r)
                for r in db.execute(
                    "SELECT p.name,p.role,p.protocol_state,p.holder,p.disposition "
                    "FROM frontier_members fm "
                    "JOIN projections p ON p.name=fm.projection_name "
                    "WHERE fm.frontier_name=? ORDER BY p.role,p.name",
                    (blueprint.frontier,),
                ).fetchall()
            ]
            supplied = sorted(
                [
                    {
                        "name": p.name,
                        "role": p.role,
                        "protocol_state": p.state,
                        "holder": p.holder,
                        "disposition": "live",
                    }
                    for p in blueprint.projections
                ],
                key=lambda item: (item["role"], item["name"]),
            )
            if expected != supplied:
                raise Conflict("frontier proof does not match authoritative live frontier")

            live_names = {item["name"] for item in expected}
            possibilities: dict[str, str] = {}
            actualizers: dict[str, str] = {}
            new_names: list[str] = []
            for seed in blueprint.possibilities:
                if not set(seed.consumes) <= live_names:
                    raise Conflict(
                        f"possibility {seed.key!r} consumes projections outside frontier"
                    )
                possibility = self._new_name(db, "possibility")
                possibilities[seed.key] = possibility
                new_names.append(possibility)
                db.execute(
                    "INSERT INTO reaction_possibilities("
                    "name,instance_name,seed_key,reaction,state"
                    ") VALUES (?,?,?,?,?)",
                    (
                        possibility,
                        row["instance_name"],
                        seed.key,
                        seed.reaction,
                        "open",
                    ),
                )
                db.execute(
                    "INSERT INTO possibility_frontiers(possibility_name,frontier_name) "
                    "VALUES (?,?)",
                    (possibility, blueprint.frontier),
                )
                for projection in seed.consumes:
                    db.execute(
                        "INSERT INTO reaction_inputs(possibility_name,projection_name) "
                        "VALUES (?,?)",
                        (possibility, projection),
                    )
                for ordinal, successor in enumerate(seed.establishes):
                    db.execute(
                        "INSERT INTO reaction_outputs("
                        "possibility_name,ordinal,output_key,role,protocol_state,holder"
                        ") VALUES (?,?,?,?,?,?)",
                        (
                            possibility,
                            ordinal,
                            successor.key,
                            successor.role,
                            successor.state,
                            successor.holder,
                        ),
                    )

            db.execute(
                "UPDATE elaboration_authorities SET disposition='spent' WHERE token=?",
                (authority,),
            )
            db.execute(
                "INSERT INTO frontier_admissions(frontier_name,proof,blueprint_json) "
                "VALUES (?,?,?)",
                (
                    blueprint.frontier,
                    blueprint.proof,
                    json.dumps(payload, sort_keys=True, separators=(",", ":")),
                ),
            )
            db.execute(
                "UPDATE protocol_frontiers SET state='elaborated' WHERE name=?",
                (blueprint.frontier,),
            )
            self._event(
                db,
                "frontier_elaborated",
                {
                    "frontier": blueprint.frontier,
                    "instance": row["instance_name"],
                    "protocol_cid": blueprint.protocol_cid,
                    "parent_occurrence": blueprint.parent_occurrence,
                    "proof": blueprint.proof,
                    "possibilities": possibilities,
                    "new_names": new_names,
                },
            )
            result = {
                "frontier": blueprint.frontier,
                "proof": blueprint.proof,
                "possibilities": possibilities,
            }
            self._idem_put(db, request_id, "admit_frontier", payload, result)
            return result

    def commit_occurrence(
        self,
        *,
        possibility: str,
        observation: Any,
        request_id: str,
    ) -> dict[str, Any]:
        """Atomically turn one latent possibility into a causal occurrence.

        Participant projections and the protocol-frontier capability are both
        linear. A successful occurrence spends the current frontier and mints
        exactly one successor frontier in the open, not-yet-elaborated state.
        """

        payload = {"possibility": possibility, "observation": observation}
        with self._tx() as db:
            old = self._idem(db, request_id, "commit_occurrence", payload)
            if old is not None:
                return old

            possibility_row = db.execute(
                "SELECT rp.*,pf.frontier_name "
                "FROM reaction_possibilities rp "
                "JOIN possibility_frontiers pf ON pf.possibility_name=rp.name "
                "WHERE rp.name=?",
                (possibility,),
            ).fetchone()
            if possibility_row is None:
                raise KeyError(possibility)
            if possibility_row["state"] != "open":
                raise Conflict(
                    f"reaction possibility {possibility!r} is "
                    f"{possibility_row['state']}, not open"
                )

            frontier_row = db.execute(
                "SELECT * FROM protocol_frontiers WHERE name=?",
                (possibility_row["frontier_name"],),
            ).fetchone()
            if frontier_row is None or frontier_row["state"] != "elaborated":
                raise Conflict(
                    "reaction possibility does not belong to a live elaborated frontier"
                )

            input_rows = db.execute(
                "SELECT p.* FROM reaction_inputs i "
                "JOIN projections p ON p.name=i.projection_name "
                "WHERE i.possibility_name=? ORDER BY p.rowid",
                (possibility,),
            ).fetchall()
            if not input_rows:
                raise TrustedError("reaction possibility has no input projections")
            stale = [
                row["name"] for row in input_rows if row["disposition"] != "live"
            ]
            if stale:
                raise StaleProjection(
                    f"reaction input projections are no longer live: {stale!r}"
                )

            occurrence = self._new_name(db, "occurrence")
            new_frontier = self._new_name(db, "frontier")
            elaboration_authority = self._new_name(db, "elaboration")
            new_names = [occurrence, new_frontier]
            consumed = [row["name"] for row in input_rows]

            for projection in consumed:
                db.execute(
                    "UPDATE projections SET disposition='spent' WHERE name=?",
                    (projection,),
                )

            output_rows = db.execute(
                "SELECT * FROM reaction_outputs WHERE possibility_name=? "
                "ORDER BY ordinal",
                (possibility,),
            ).fetchall()
            successors: list[str] = []
            successor_by_key: dict[str, str] = {}
            for output in output_rows:
                projection = self._new_name(db, "projection")
                new_names.append(projection)
                successors.append(projection)
                successor_by_key[output["output_key"]] = projection
                db.execute(
                    "INSERT INTO projections("
                    "name,instance_name,seed_key,role,protocol_state,holder,disposition"
                    ") VALUES (?,?,?,?,?,?,?)",
                    (
                        projection,
                        possibility_row["instance_name"],
                        output["output_key"],
                        output["role"],
                        output["protocol_state"],
                        output["holder"],
                        "live",
                    ),
                )

            db.execute(
                "UPDATE reaction_possibilities SET state='precluded' "
                "WHERE name IN ("
                "SELECT possibility_name FROM possibility_frontiers "
                "WHERE frontier_name=?"
                ") AND state='open' AND name<>?",
                (frontier_row["name"], possibility),
            )
            db.execute(
                "UPDATE reaction_possibilities SET state='occurred' WHERE name=?",
                (possibility,),
            )
            db.execute(
                "UPDATE protocol_frontiers SET state='spent' WHERE name=?",
                (frontier_row["name"],),
            )

            db.execute(
                "INSERT INTO occurrences("
                "name,instance_name,possibility_name,observation_json"
                ") VALUES (?,?,?,?)",
                (
                    occurrence,
                    possibility_row["instance_name"],
                    possibility,
                    json.dumps(observation, sort_keys=True, separators=(",", ":")),
                ),
            )
            for projection in consumed:
                db.execute(
                    "INSERT INTO occurrence_inputs(occurrence_name,projection_name) "
                    "VALUES (?,?)",
                    (occurrence, projection),
                )
            for ordinal, projection in enumerate(successors):
                db.execute(
                    "INSERT INTO occurrence_outputs("
                    "occurrence_name,projection_name,ordinal"
                    ") VALUES (?,?,?)",
                    (occurrence, projection, ordinal),
                )

            db.execute(
                "INSERT INTO protocol_frontiers("
                "name,instance_name,protocol_cid,parent_occurrence,generation,state"
                ") VALUES (?,?,?,?,?,?)",
                (
                    new_frontier,
                    possibility_row["instance_name"],
                    frontier_row["protocol_cid"],
                    occurrence,
                    int(frontier_row["generation"]) + 1,
                    "open",
                ),
            )

            live_rows = db.execute(
                "SELECT name FROM projections "
                "WHERE instance_name=? AND disposition='live' ORDER BY role,name",
                (possibility_row["instance_name"],),
            ).fetchall()
            for row in live_rows:
                db.execute(
                    "INSERT INTO frontier_members(frontier_name,projection_name) "
                    "VALUES (?,?)",
                    (new_frontier, row["name"]),
                )
            db.execute(
                "INSERT INTO occurrence_frontiers(occurrence_name,frontier_name) "
                "VALUES (?,?)",
                (occurrence, new_frontier),
            )
            db.execute(
                "INSERT INTO elaboration_authorities(token,frontier_name,disposition) "
                "VALUES (?,?,?)",
                (elaboration_authority, new_frontier, "live"),
            )

            self._event(
                db,
                "occurrence_committed",
                {
                    "occurrence": occurrence,
                    "instance": possibility_row["instance_name"],
                    "possibility": possibility,
                    "reaction": possibility_row["reaction"],
                    "previous_frontier": frontier_row["name"],
                    "next_frontier": new_frontier,
                    "generation": int(frontier_row["generation"]) + 1,
                    "consumed": consumed,
                    "successors": successor_by_key,
                    "observation": observation,
                    "new_names": new_names,
                },
            )
            result = {
                "occurrence": occurrence,
                "instance": possibility_row["instance_name"],
                "reaction": possibility_row["reaction"],
                "consumed": consumed,
                "successors": successor_by_key,
                "frontier": new_frontier,
                "elaboration_authority": elaboration_authority,
            }
            self._idem_put(
                db,
                request_id,
                "commit_occurrence",
                payload,
                result,
            )
            return result

    def frontier(self, frontier: str) -> dict[str, Any]:
        row = self.db.execute(
            "SELECT * FROM protocol_frontiers WHERE name=?",
            (frontier,),
        ).fetchone()
        if row is None:
            raise KeyError(frontier)
        item = dict(row)
        item["projections"] = [
            dict(r)
            for r in self.db.execute(
                "SELECT p.name,p.role,p.protocol_state,p.holder,p.disposition "
                "FROM frontier_members fm "
                "JOIN projections p ON p.name=fm.projection_name "
                "WHERE fm.frontier_name=? ORDER BY p.role,p.name",
                (frontier,),
            ).fetchall()
        ]
        admission = self.db.execute(
            "SELECT proof FROM frontier_admissions WHERE frontier_name=?",
            (frontier,),
        ).fetchone()
        item["proof"] = None if admission is None else admission["proof"]
        return item

    def projection(self, projection: str) -> dict[str, Any]:
        row = self.db.execute(
            "SELECT * FROM projections WHERE name=?",
            (projection,),
        ).fetchone()
        if row is None:
            raise KeyError(projection)
        return dict(row)

    def reaction_possibility(self, possibility: str) -> dict[str, Any]:
        row = self.db.execute(
            "SELECT * FROM reaction_possibilities WHERE name=?",
            (possibility,),
        ).fetchone()
        if row is None:
            raise KeyError(possibility)
        item = dict(row)
        item["inputs"] = [
            r["projection_name"]
            for r in self.db.execute(
                "SELECT projection_name FROM reaction_inputs "
                "WHERE possibility_name=? ORDER BY rowid",
                (possibility,),
            ).fetchall()
        ]
        item["outputs"] = [
            dict(r)
            for r in self.db.execute(
                "SELECT output_key,role,protocol_state,holder,ordinal "
                "FROM reaction_outputs WHERE possibility_name=? ORDER BY ordinal",
                (possibility,),
            ).fetchall()
        ]
        return item

    def occurrence_record(self, occurrence: str) -> dict[str, Any]:
        row = self.db.execute(
            "SELECT * FROM occurrences WHERE name=?",
            (occurrence,),
        ).fetchone()
        if row is None:
            raise KeyError(occurrence)
        item = dict(row)
        item["observation"] = json.loads(item.pop("observation_json"))
        item["inputs"] = [
            r["projection_name"]
            for r in self.db.execute(
                "SELECT projection_name FROM occurrence_inputs "
                "WHERE occurrence_name=? ORDER BY rowid",
                (occurrence,),
            ).fetchall()
        ]
        item["outputs"] = [
            r["projection_name"]
            for r in self.db.execute(
                "SELECT projection_name FROM occurrence_outputs "
                "WHERE occurrence_name=? ORDER BY ordinal",
                (occurrence,),
            ).fetchall()
        ]
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
        """Create one observer-relative causal cut over live projections.

        The authority to elaborate from the cut is itself an ordinary live
        projection occupying the Elaborator role. It may later be delegated.
        """

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
                "SELECT 1 FROM occurrence_instances WHERE name=?",
                (instance,),
            ).fetchone() is None:
                raise KeyError(instance)

            unique = sorted(set(projections))
            if len(unique) != len(projections):
                raise ValueError("cut projection names must be unique")
            rows = []
            for projection in unique:
                row = db.execute(
                    "SELECT * FROM projections WHERE name=?",
                    (projection,),
                ).fetchone()
                if (
                    row is None
                    or row["instance_name"] != instance
                    or row["disposition"] != "live"
                ):
                    raise StaleProjection(
                        f"projection {projection!r} is not live in instance {instance!r}"
                    )
                rows.append(row)

            cut = self._new_name(db, "cut")
            authority = self._new_name(db, "projection")
            db.execute(
                "INSERT INTO causal_cuts("
                "name,instance_name,observer,protocol_cid,parent_cut,parent_occurrence,state"
                ") VALUES (?,?,?,?,?,?,?)",
                (
                    cut,
                    instance,
                    observer,
                    protocol_cid,
                    parent_cut,
                    parent_occurrence,
                    "open",
                ),
            )
            for row in rows:
                db.execute(
                    "INSERT INTO cut_members(cut_name,projection_name) VALUES (?,?)",
                    (cut, row["name"]),
                )
            db.execute(
                "INSERT INTO projections("
                "name,instance_name,seed_key,role,protocol_state,holder,disposition"
                ") VALUES (?,?,?,?,?,?,?)",
                (
                    authority,
                    instance,
                    f"meta:elaborator:{cut}",
                    ELABORATOR_ROLE,
                    elaborator_state(cut),
                    elaborator,
                    "live",
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
        row = self.db.execute(
            "SELECT * FROM causal_cuts WHERE name=?",
            (cut,),
        ).fetchone()
        if row is None:
            raise KeyError(cut)
        item = dict(row)
        item["projections"] = [
            dict(r)
            for r in self.db.execute(
                "SELECT p.name,p.role,p.protocol_state,p.holder,p.disposition "
                "FROM cut_members cm "
                "JOIN projections p ON p.name=cm.projection_name "
                "WHERE cm.cut_name=? ORDER BY p.role,p.name",
                (cut,),
            ).fetchall()
        ]
        return item

    def admit_cut_elaboration(
        self,
        *,
        blueprint: CutElaboration,
        authorities: dict[str, str],
        request_id: str,
    ) -> dict[str, Any]:
        """Admit possibilities derived from observer-relative cuts.

        Semantic validation remains here. The authority transition itself is
        delegated to the generic projection-occurrence commit primitive.
        """

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

            cut_rows: dict[str, sqlite3.Row] = {}
            observed_projection_names: set[str] = set()
            for cut in blueprint.cuts:
                row = db.execute(
                    "SELECT * FROM causal_cuts WHERE name=?",
                    (cut,),
                ).fetchone()
                if row is None:
                    raise KeyError(cut)
                if row["state"] != "open":
                    raise Conflict(f"cut {cut!r} is {row['state']}, not open")
                if row["protocol_cid"] != blueprint.protocol_cid:
                    raise Conflict("cut names a different protocol commitment")

                authority = authorities[cut]
                authority_row = db.execute(
                    "SELECT instance_name,role,protocol_state,holder,disposition "
                    "FROM projections WHERE name=?",
                    (authority,),
                ).fetchone()
                if (
                    authority_row is None
                    or authority_row["instance_name"] != row["instance_name"]
                    or authority_row["role"] != ELABORATOR_ROLE
                    or authority_row["protocol_state"] != elaborator_state(cut)
                    or authority_row["holder"] != blueprint.elaborator
                    or authority_row["disposition"] != "live"
                ):
                    raise Conflict(
                        "Elaborator projection is not live/bound for this cut"
                    )

                cut_rows[cut] = row
                for member in db.execute(
                    "SELECT projection_name FROM cut_members WHERE cut_name=?",
                    (cut,),
                ).fetchall():
                    observed_projection_names.add(member["projection_name"])

            supplied = {projection.name for projection in blueprint.projections}
            if supplied != observed_projection_names:
                raise Conflict(
                    "elaboration does not name exactly the union of observed cut projections"
                )

            instance_names = {row["instance_name"] for row in cut_rows.values()}
            if len(instance_names) != 1:
                raise Conflict("joined cuts must belong to one protocol instance")
            instance = next(iter(instance_names))

            db.execute(
                "INSERT INTO cut_admissions(proof,elaborator,actualizer,blueprint_json) "
                "VALUES (?,?,?,?)",
                (
                    blueprint.proof,
                    blueprint.elaborator,
                    blueprint.actualizer,
                    json.dumps(payload, sort_keys=True, separators=(",", ":")),
                ),
            )
            for cut in blueprint.cuts:
                db.execute(
                    "INSERT INTO cut_admission_cuts(proof,cut_name) VALUES (?,?)",
                    (blueprint.proof, cut),
                )
                db.execute(
                    "UPDATE causal_cuts SET state='elaborated' WHERE name=?",
                    (cut,),
                )

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
                db.execute(
                    "INSERT INTO observed_possibilities("
                    "name,instance_name,proof,seed_key,reaction,elaborator,actualizer,state"
                    ") VALUES (?,?,?,?,?,?,?,?)",
                    (
                        possibility,
                        instance,
                        blueprint.proof,
                        seed.key,
                        seed.reaction,
                        blueprint.elaborator,
                        blueprint.actualizer,
                        "open",
                    ),
                )
                for cut in blueprint.cuts:
                    db.execute(
                        "INSERT INTO observed_possibility_cuts("
                        "possibility_name,cut_name"
                        ") VALUES (?,?)",
                        (possibility, cut),
                    )
                for projection in seed.consumes:
                    db.execute(
                        "INSERT INTO observed_reaction_inputs("
                        "possibility_name,projection_name"
                        ") VALUES (?,?)",
                        (possibility, projection),
                    )
                for ordinal, successor in enumerate(seed.establishes):
                    db.execute(
                        "INSERT INTO observed_reaction_outputs("
                        "possibility_name,ordinal,output_key,role,protocol_state,holder"
                        ") VALUES (?,?,?,?,?,?)",
                        (
                            possibility,
                            ordinal,
                            successor.key,
                            successor.role,
                            successor.state,
                            successor.holder,
                        ),
                    )
                grants.append(
                    ProjectionGrant(
                        key=f"actualizer:{possibility}",
                        role=ACTUALIZER_ROLE,
                        state=actualizer_state(possibility),
                        holder=blueprint.actualizer,
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
                db.execute(
                    "INSERT INTO observed_possibility_actualizers("
                    "possibility_name,projection_name"
                    ") VALUES (?,?)",
                    (possibility, projection),
                )
                seed = possibility_seeds[possibility]
                possibility_values[possibility] = self._bind_eidos_value(
                    db,
                    name=possibility,
                    value=possibility_value(
                        name=possibility,
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
        """Actualize one possibility without imposing a global frontier.

        Semantic cut bookkeeping remains here. The linear authority transition
        is delegated to the generic projection-occurrence commit primitive.
        """

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

            row = db.execute(
                "SELECT * FROM observed_possibilities WHERE name=?",
                (possibility,),
            ).fetchone()
            if row is None:
                raise KeyError(possibility)
            if row["state"] != "open":
                raise Conflict(
                    f"observed possibility {possibility!r} is {row['state']}, not open"
                )
            if row["actualizer"] != actualizer:
                raise Conflict("wrong Actualizer role for this possibility")

            actualizer_row = db.execute(
                "SELECT p.*,opa.possibility_name "
                "FROM observed_possibility_actualizers opa "
                "JOIN projections p ON p.name=opa.projection_name "
                "WHERE opa.possibility_name=?",
                (possibility,),
            ).fetchone()
            if (
                actualizer_row is None
                or actualizer_row["name"] != authority
                or actualizer_row["role"] != ACTUALIZER_ROLE
                or actualizer_row["protocol_state"] != actualizer_state(possibility)
                or actualizer_row["holder"] != actualizer
                or actualizer_row["disposition"] != "live"
            ):
                raise Conflict(
                    "Actualizer projection is not live/bound for this possibility"
                )

            input_rows = db.execute(
                "SELECT p.* FROM observed_reaction_inputs i "
                "JOIN projections p ON p.name=i.projection_name "
                "WHERE i.possibility_name=? ORDER BY p.rowid",
                (possibility,),
            ).fetchall()
            stale = [
                input_row["name"]
                for input_row in input_rows
                if input_row["disposition"] != "live"
            ]
            if stale:
                raise StaleProjection(
                    f"observed possibility input projections are stale: {stale!r}"
                )
            consumed = [input_row["name"] for input_row in input_rows]

            cause_cuts = [
                cut_row["cut_name"]
                for cut_row in db.execute(
                    "SELECT cut_name FROM observed_possibility_cuts "
                    "WHERE possibility_name=? ORDER BY cut_name",
                    (possibility,),
                ).fetchall()
            ]

            occurrence = self._new_name(db, "observed_occurrence")
            successor_cuts: dict[str, str] = {}
            cut_rows: dict[str, sqlite3.Row] = {}
            cut_names: list[str] = []
            for old_cut in cause_cuts:
                cut_row = db.execute(
                    "SELECT * FROM causal_cuts WHERE name=?",
                    (old_cut,),
                ).fetchone()
                if cut_row is None:
                    raise KeyError(old_cut)
                cut_rows[old_cut] = cut_row
                new_cut = self._new_name(db, "cut")
                cut_names.append(new_cut)
                successor_cuts[old_cut] = new_cut

            output_rows = db.execute(
                "SELECT * FROM observed_reaction_outputs "
                "WHERE possibility_name=? ORDER BY ordinal",
                (possibility,),
            ).fetchall()
            grants: list[ProjectionGrant] = [
                ProjectionGrant(
                    key=output["output_key"],
                    role=output["role"],
                    state=output["protocol_state"],
                    holder=output["holder"],
                )
                for output in output_rows
            ]
            for old_cut, new_cut in successor_cuts.items():
                cut_row = cut_rows[old_cut]
                grants.append(
                    ProjectionGrant(
                        key=f"elaborator:{new_cut}",
                        role=ELABORATOR_ROLE,
                        state=elaborator_state(new_cut),
                        holder=cut_row["observer"],
                    )
                )

            committed = self._commit_projection_occurrence(
                db,
                kind="Actualize",
                consumes=(authority, *tuple(consumed)),
                establishes=tuple(grants),
                fact={
                    "possibility": possibility,
                    "reaction": row["reaction"],
                    "actualizer": actualizer,
                    "observation": observation,
                    "cause_cuts": cause_cuts,
                    "successor_cuts": successor_cuts,
                },
                occurrence=occurrence,
            )

            successors = {
                output["output_key"]: committed["established"][output["output_key"]]
                for output in output_rows
            }
            successor_by_role = {
                output["role"]: successors[output["output_key"]]
                for output in output_rows
            }
            ordered_successors = [
                successors[output["output_key"]]
                for output in output_rows
            ]
            elaborators = {
                new_cut: committed["established"][f"elaborator:{new_cut}"]
                for new_cut in successor_cuts.values()
            }

            db.execute(
                "UPDATE observed_possibilities SET state='occurred' WHERE name=?",
                (possibility,),
            )

            if consumed:
                placeholders = ",".join("?" for _ in consumed)
                competitors = db.execute(
                    "SELECT DISTINCT op.name FROM observed_possibilities op "
                    "JOIN observed_reaction_inputs oi ON oi.possibility_name=op.name "
                    f"WHERE op.state='open' AND oi.projection_name IN ({placeholders})",
                    tuple(consumed),
                ).fetchall()
                for competitor in competitors:
                    db.execute(
                        "UPDATE observed_possibilities SET state='precluded' "
                        "WHERE name=?",
                        (competitor["name"],),
                    )
                    db.execute(
                        "UPDATE projections SET disposition='spent' "
                        "WHERE name IN ("
                        "SELECT projection_name "
                        "FROM observed_possibility_actualizers "
                        "WHERE possibility_name=?"
                        ")",
                        (competitor["name"],),
                    )

            db.execute(
                "INSERT INTO observed_occurrences("
                "name,instance_name,possibility_name,actualizer,observation_json"
                ") VALUES (?,?,?,?,?)",
                (
                    occurrence,
                    row["instance_name"],
                    possibility,
                    actualizer,
                    json.dumps(observation, sort_keys=True, separators=(",", ":")),
                ),
            )
            for projection in consumed:
                db.execute(
                    "INSERT INTO observed_occurrence_inputs("
                    "occurrence_name,projection_name"
                    ") VALUES (?,?)",
                    (occurrence, projection),
                )
            for ordinal, projection in enumerate(ordered_successors):
                db.execute(
                    "INSERT INTO observed_occurrence_outputs("
                    "occurrence_name,projection_name,ordinal"
                    ") VALUES (?,?,?)",
                    (occurrence, projection, ordinal),
                )

            consumed_set = set(consumed)
            successor_cut_members: dict[str, list[str]] = {}
            for old_cut in cause_cuts:
                cut_row = cut_rows[old_cut]
                new_cut = successor_cuts[old_cut]

                db.execute(
                    "UPDATE causal_cuts SET state='historical' WHERE name=?",
                    (old_cut,),
                )
                db.execute(
                    "INSERT INTO causal_cuts("
                    "name,instance_name,observer,protocol_cid,"
                    "parent_cut,parent_occurrence,state"
                    ") VALUES (?,?,?,?,?,?,?)",
                    (
                        new_cut,
                        cut_row["instance_name"],
                        cut_row["observer"],
                        cut_row["protocol_cid"],
                        old_cut,
                        occurrence,
                        "open",
                    ),
                )

                members = db.execute(
                    "SELECT p.* FROM cut_members cm "
                    "JOIN projections p ON p.name=cm.projection_name "
                    "WHERE cm.cut_name=? ORDER BY p.role,p.name",
                    (old_cut,),
                ).fetchall()
                successor_cut_members[new_cut] = []
                for member in members:
                    projection = member["name"]
                    if projection in consumed_set:
                        projection = successor_by_role.get(member["role"])
                        if projection is None:
                            continue
                    db.execute(
                        "INSERT INTO cut_members(cut_name,projection_name) VALUES (?,?)",
                        (new_cut, projection),
                    )
                    successor_cut_members[new_cut].append(projection)
                db.execute(
                    "INSERT INTO observed_occurrence_cuts("
                    "occurrence_name,cut_name"
                    ") VALUES (?,?)",
                    (occurrence, old_cut),
                )

            successor_cut_values: dict[str, str] = {}
            for old_cut, new_cut in successor_cuts.items():
                cut_row = cut_rows[old_cut]
                successor_cut_values[new_cut] = self._bind_eidos_value(
                    db,
                    name=new_cut,
                    value=cut_value(
                        name=new_cut,
                        observer=cut_row["observer"],
                        protocol_cid=cut_row["protocol_cid"],
                        projections=tuple(successor_cut_members[new_cut]),
                        parent_cut=old_cut,
                        parent_occurrence=occurrence,
                    ),
                )

            occurrence_cid = self._bind_eidos_value(
                db,
                name=occurrence,
                value=occurrence_value(
                    occurrence=occurrence,
                    reaction=row["reaction"],
                    possibility=possibility,
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
                    "reaction": row["reaction"],
                    "actualizer": actualizer,
                    "actualizer_projection": authority,
                    "cause_cuts": cause_cuts,
                    "successor_cuts": successor_cuts,
                    "elaborator_projections": elaborators,
                    "consumed": consumed,
                    "successors": successors,
                    "observation": observation,
                    "value": occurrence_cid,
                    "successor_cut_values": successor_cut_values,
                    "new_names": cut_names,
                },
            )
            result = {
                "occurrence": occurrence,
                "reaction": row["reaction"],
                "actualizer": actualizer,
                "actualizer_projection": authority,
                "cause_cuts": cause_cuts,
                "successor_cuts": successor_cuts,
                "elaboration_authorities": elaborators,
                "elaborators": elaborators,
                "consumed": consumed,
                "successors": successors,
                "value": occurrence_cid,
                "successor_cut_values": successor_cut_values,
            }
            self._idem_put(db, request_id, "actualize_observed", payload, result)
            return result

    def observed_possibility(self, possibility: str) -> dict[str, Any]:
        row = self.db.execute(
            "SELECT * FROM observed_possibilities WHERE name=?",
            (possibility,),
        ).fetchone()
        if row is None:
            raise KeyError(possibility)
        item = dict(row)
        item["cuts"] = [
            r["cut_name"]
            for r in self.db.execute(
                "SELECT cut_name FROM observed_possibility_cuts "
                "WHERE possibility_name=? ORDER BY cut_name",
                (possibility,),
            ).fetchall()
        ]
        item["inputs"] = [
            r["projection_name"]
            for r in self.db.execute(
                "SELECT projection_name FROM observed_reaction_inputs "
                "WHERE possibility_name=? ORDER BY rowid",
                (possibility,),
            ).fetchall()
        ]
        actualizer = self.db.execute(
            "SELECT projection_name FROM observed_possibility_actualizers "
            "WHERE possibility_name=?",
            (possibility,),
        ).fetchone()
        item["actualizer_projection"] = (
            None if actualizer is None else actualizer["projection_name"]
        )
        return item

    def observed_occurrence(self, occurrence: str) -> dict[str, Any]:
        row = self.db.execute(
            "SELECT * FROM observed_occurrences WHERE name=?",
            (occurrence,),
        ).fetchone()
        if row is None:
            raise KeyError(occurrence)
        item = dict(row)
        item["observation"] = json.loads(item.pop("observation_json"))
        item["cuts"] = [
            r["cut_name"]
            for r in self.db.execute(
                "SELECT cut_name FROM observed_occurrence_cuts "
                "WHERE occurrence_name=? ORDER BY cut_name",
                (occurrence,),
            ).fetchall()
        ]
        item["inputs"] = [
            r["projection_name"]
            for r in self.db.execute(
                "SELECT projection_name FROM observed_occurrence_inputs "
                "WHERE occurrence_name=? ORDER BY rowid",
                (occurrence,),
            ).fetchall()
        ]
        item["outputs"] = [
            r["projection_name"]
            for r in self.db.execute(
                "SELECT projection_name FROM observed_occurrence_outputs "
                "WHERE occurrence_name=? ORDER BY ordinal",
                (occurrence,),
            ).fetchall()
        ]
        return item

    def authority_occurrence(self, occurrence: str) -> dict[str, Any]:
        row = self.db.execute(
            "SELECT * FROM authority_occurrences WHERE name=?",
            (occurrence,),
        ).fetchone()
        if row is None:
            raise KeyError(occurrence)
        item = dict(row)
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
                "SELECT holder,disposition,role,protocol_state "
                "FROM projections WHERE name=?",
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
            self._event(
                db,
                "projection_transferred",
                {
                    "projection": projection,
                    "role": row["role"],
                    "protocol_state": row["protocol_state"],
                    "from": from_holder,
                    "to": to_holder,
                },
            )
            result = {
                "projection": projection,
                "holder": to_holder,
                "role": row["role"],
                "protocol_state": row["protocol_state"],
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
