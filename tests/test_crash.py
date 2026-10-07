import json
from pathlib import Path
import subprocess
import sys

from eidos import Frame, OfferSpec, ProtocolSpec, Transition
from eidos.trusted import TrustedMachinery


def protocol() -> ProtocolSpec:
    return ProtocolSpec(
        roles={
            "a": {"q": Transition("send", "x", "End")},
            "b": {"q": Transition("recv", "x", "End")},
        },
        initial={"a": "q", "b": "q"},
    )


def test_abrupt_exit_after_match_commit_keeps_objective_match_and_receipts(tmp_path: Path):
    db = tmp_path / "tm.db"
    tm = TrustedMachinery(db)
    a = tm.create_nema(initial=Frame(), request_id="a")
    b = tm.create_nema(initial=Frame(), request_id="b")
    s = tm.open_session(protocol=protocol(), holders={"a": a["nema"], "b": b["nema"]}, request_id="s")
    pa = tm.publish_frame(
        nema=a["nema"], expected_meta_socket=a["meta_socket"], frame=Frame(),
        offers=[OfferSpec(s["sockets"]["a"], "send", "x", "payload", None)], request_id="pa"
    )
    pb = tm.publish_frame(
        nema=b["nema"], expected_meta_socket=b["meta_socket"], frame=Frame(),
        offers=[OfferSpec(s["sockets"]["b"], "recv", "x", None, None)], request_id="pb"
    )
    tm.close()

    script = tmp_path / "die_after_match.py"
    script.write_text(
        "from eidos.trusted import TrustedMachinery\n"
        f"tm=TrustedMachinery({str(db)!r})\n"
        f"tm.match(left_offer={pa['offers'][0]!r}, right_offer={pb['offers'][0]!r}, request_id='match')\n"
        "import os; os._exit(71)\n"
    )
    proc = subprocess.run([sys.executable, str(script)], env={**__import__('os').environ, "PYTHONPATH": str(Path(__file__).parents[1] / "src")})
    assert proc.returncode == 71

    tm = TrustedMachinery(db)
    matches = [e for e in tm.events() if e["kind"] == "matched"]
    assert len(matches) == 1
    assert len(tm.receipts(a["nema"])) == 1
    assert len(tm.receipts(b["nema"])) == 1
    assert tm.socket(s["sockets"]["a"])["disposition"] == "spent"
    assert tm.socket(s["sockets"]["b"])["disposition"] == "spent"
