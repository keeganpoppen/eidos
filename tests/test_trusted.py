from pathlib import Path

import pytest

from eidos import Frame, OfferSpec, ProtocolSpec, Transition, TrustedMachinery
from eidos.trusted import Conflict, StaleSocket


def ping_protocol() -> ProtocolSpec:
    return ProtocolSpec(
        roles={
            "alice": {
                "q0": Transition("send", "hello", "q1"),
                "q1": Transition("recv", "world", "End"),
            },
            "bob": {
                "q0": Transition("recv", "hello", "q1"),
                "q1": Transition("send", "world", "End"),
            },
        },
        initial={"alice": "q0", "bob": "q0"},
    )


def create_pair(tm: TrustedMachinery):
    a = tm.create_nema(initial=Frame(), request_id="create-a")
    b = tm.create_nema(initial=Frame(), request_id="create-b")
    s = tm.open_session(
        protocol=ping_protocol(),
        holders={"alice": a["nema"], "bob": b["nema"]},
        request_id="open-ping",
    )
    return a, b, s


def test_name_reservation_is_idempotent_and_conflict_detected():
    tm = TrustedMachinery()
    n1 = tm.reserve_name(kind="thing", request_id="r1")
    n2 = tm.reserve_name(kind="thing", request_id="r1")
    assert n1 == n2
    with pytest.raises(Conflict):
        tm.reserve_name(kind="other", request_id="r1")


def test_frame_rebinding_is_new_immutable_frame():
    f0 = Frame(bindings={"executor": "A"})
    f1 = Frame(bindings={**f0.bindings, "executor": "B"})
    assert f0.bindings["executor"] == "A"
    assert f1.bindings["executor"] == "B"
    assert f0.cid != f1.cid


def test_match_spends_occurrences_and_mints_successors():
    tm = TrustedMachinery()
    a, b, s = create_pair(tm)
    sa = s["sockets"]["alice"]
    sb = s["sockets"]["bob"]

    pa = tm.publish_frame(
        nema=a["nema"], expected_meta_socket=a["meta_socket"], frame=Frame(),
        offers=[OfferSpec(sa, "send", "hello", "hello", {"k": "a"})], request_id="pub-a-1"
    )
    pb = tm.publish_frame(
        nema=b["nema"], expected_meta_socket=b["meta_socket"], frame=Frame(),
        offers=[OfferSpec(sb, "recv", "hello", None, {"k": "b"})], request_id="pub-b-1"
    )
    m = tm.match(left_offer=pa["offers"][0], right_offer=pb["offers"][0], request_id="match-1")

    assert tm.socket(sa)["disposition"] == "spent"
    assert tm.socket(sb)["disposition"] == "spent"
    assert m["successors"]["left"] is not None
    assert m["successors"]["right"] is not None
    assert tm.socket(m["successors"]["left"])["protocol_state"] == "q1"
    assert tm.socket(m["successors"]["right"])["protocol_state"] == "q1"

    with pytest.raises(StaleSocket):
        tm.match(left_offer=pa["offers"][0], right_offer=pb["offers"][0], request_id="match-again")


def test_match_is_durable_before_either_side_incorporates_receipt(tmp_path: Path):
    db = tmp_path / "tm.db"
    tm = TrustedMachinery(db)
    a, b, s = create_pair(tm)
    sa, sb = s["sockets"]["alice"], s["sockets"]["bob"]
    pa = tm.publish_frame(
        nema=a["nema"], expected_meta_socket=a["meta_socket"], frame=Frame(),
        offers=[OfferSpec(sa, "send", "hello", "hello", None)], request_id="pub-a"
    )
    pb = tm.publish_frame(
        nema=b["nema"], expected_meta_socket=b["meta_socket"], frame=Frame(),
        offers=[OfferSpec(sb, "recv", "hello", None, None)], request_id="pub-b"
    )
    match = tm.match(left_offer=pa["offers"][0], right_offer=pb["offers"][0], request_id="match")
    tm.close()

    tm = TrustedMachinery(db)
    ar = tm.receipts(a["nema"])
    br = tm.receipts(b["nema"])
    assert len(ar) == len(br) == 1
    assert ar[0]["match_name"] == br[0]["match_name"] == match["match"]
    assert ar[0]["incorporated"] == br[0]["incorporated"] == 0

    got = tm.incorporate_receipt(holder=a["nema"], receipt=ar[0]["name"], request_id="inc-a")
    assert got["payload"] == "hello"
    assert tm.receipts(a["nema"]) == []
    assert len(tm.receipts(b["nema"])) == 1


def test_socket_transfer_moves_authority_without_changing_occurrence():
    tm = TrustedMachinery()
    a, b, s = create_pair(tm)
    c = tm.create_nema(initial=Frame(), request_id="create-c")
    sb = s["sockets"]["bob"]
    out = tm.transfer_socket(socket=sb, from_holder=b["nema"], to_holder=c["nema"], request_id="handoff")
    assert out["socket"] == sb
    assert tm.socket(sb)["holder"] == c["nema"]
    with pytest.raises(StaleSocket):
        tm.transfer_socket(socket=sb, from_holder=b["nema"], to_holder=a["nema"], request_id="bad-handoff")


def test_two_round_trip_session():
    tm = TrustedMachinery()
    a, b, s = create_pair(tm)
    sa0, sb0 = s["sockets"]["alice"], s["sockets"]["bob"]

    a1 = tm.publish_frame(nema=a["nema"], expected_meta_socket=a["meta_socket"], frame=Frame(), offers=[OfferSpec(sa0,"send","hello","hello",None)], request_id="a1")
    b1 = tm.publish_frame(nema=b["nema"], expected_meta_socket=b["meta_socket"], frame=Frame(), offers=[OfferSpec(sb0,"recv","hello",None,None)], request_id="b1")
    m1 = tm.match(left_offer=a1["offers"][0], right_offer=b1["offers"][0], request_id="m1")
    sa1, sb1 = m1["successors"]["left"], m1["successors"]["right"]

    a_head, b_head = tm.head(a["nema"]), tm.head(b["nema"])
    a2 = tm.publish_frame(nema=a["nema"], expected_meta_socket=a_head["meta_socket"], frame=Frame(), offers=[OfferSpec(sa1,"recv","world",None,None)], request_id="a2")
    b2 = tm.publish_frame(nema=b["nema"], expected_meta_socket=b_head["meta_socket"], frame=Frame(), offers=[OfferSpec(sb1,"send","world","world",None)], request_id="b2")
    m2 = tm.match(left_offer=a2["offers"][0], right_offer=b2["offers"][0], request_id="m2")
    assert m2["successors"]["left"] is None
    assert m2["successors"]["right"] is None
