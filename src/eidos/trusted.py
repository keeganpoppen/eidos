from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict
import json
import sqlite3
import uuid
from pathlib import Path
from typing import Any, Iterator

from .model import Frame, OfferSpec, ProtocolSpec, Transition, canonical_bytes, content_id


class TrustedError(RuntimeError):
    pass


class StaleSocket(TrustedError):
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
