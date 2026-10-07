from pathlib import Path

from eidos import Frame, Lit, Perform, ProtocolSpec, Transition, Var
from eidos.runtime import Runtime
from eidos.trusted import TrustedMachinery


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


def setup(tm: TrustedMachinery):
    alice = tm.create_nema(initial=Frame(), request_id="alice")
    bob = tm.create_nema(initial=Frame(), request_id="bob")
    session = tm.open_session(
        protocol=ping_protocol(),
        holders={"alice": alice["nema"], "bob": bob["nema"]},
        request_id="session",
    )
    alice_term = Perform(
        Var("peer"),
        "hello",
        Lit("hello"),
        "sent",
        Perform(Var("peer"), "world", Lit(None), "reply", Var("reply")),
    )
    bob_term = Perform(
        Var("peer"),
        "hello",
        Lit(None),
        "greeting",
        Perform(Var("peer"), "world", Lit("world"), "sent", Var("greeting")),
    )
    return alice, bob, session, alice_term, bob_term


def test_runtime_drives_two_round_trip_programs_to_completion():
    tm = TrustedMachinery()
    runtime = Runtime(tm)
    alice, bob, session, alice_term, bob_term = setup(tm)

    runtime.start(nema=alice["nema"], term=alice_term, env={"peer": session["sockets"]["alice"]})
    runtime.start(nema=bob["nema"], term=bob_term, env={"peer": session["sockets"]["bob"]})
    runtime.drive([alice["nema"], bob["nema"]])

    assert runtime.state(alice["nema"]).status == "done"
    assert runtime.state(alice["nema"]).result == "world"
    assert runtime.state(bob["nema"]).status == "done"
    assert runtime.state(bob["nema"]).result == "hello"
    assert tm.receipts(alice["nema"]) == []
    assert tm.receipts(bob["nema"]) == []
    assert len([e for e in tm.events() if e["kind"] == "matched"]) == 2


def test_match_can_survive_restart_then_runtime_resumes(tmp_path: Path):
    db = tmp_path / "runtime.db"
    tm = TrustedMachinery(db)
    runtime = Runtime(tm)
    alice, bob, session, alice_term, bob_term = setup(tm)
    runtime.start(nema=alice["nema"], term=alice_term, env={"peer": session["sockets"]["alice"]})
    runtime.start(nema=bob["nema"], term=bob_term, env={"peer": session["sockets"]["bob"]})
    first = runtime.match_one()
    assert first is not None
    assert len(tm.receipts(alice["nema"])) == 1
    assert len(tm.receipts(bob["nema"])) == 1
    tm.close()

    tm = TrustedMachinery(db)
    runtime = Runtime(tm)
    runtime.drive([alice["nema"], bob["nema"]])
    assert runtime.state(alice["nema"]).result == "world"
    assert runtime.state(bob["nema"]).result == "hello"


def test_receipt_is_only_incorporated_with_successor_frame():
    tm = TrustedMachinery()
    runtime = Runtime(tm)
    alice, bob, session, alice_term, bob_term = setup(tm)
    runtime.start(nema=alice["nema"], term=alice_term, env={"peer": session["sockets"]["alice"]})
    runtime.start(nema=bob["nema"], term=bob_term, env={"peer": session["sockets"]["bob"]})
    runtime.match_one()

    receipt = tm.receipts(alice["nema"])[0]
    # Merely reading/computing from the receipt does not consume it.
    assert tm.receipt(receipt["name"])["incorporated"] == 0
    state = runtime.resume_one(nema=alice["nema"])
    assert state is not None and state.status == "awaiting"
    assert tm.receipt(receipt["name"])["incorporated"] == 1
