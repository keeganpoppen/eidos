"""Reopen the joined synthetic demonstration without rerunning work."""
import importlib.util
from pathlib import Path
import sys


def test_round3_demo_reopens_identically(tmp_path, monkeypatch):
    scripts = Path(__file__).parents[1] / "scripts"
    monkeypatch.syspath_prepend(str(scripts))
    spec = importlib.util.spec_from_file_location("round3_demo", scripts / "round3_demo.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    database = tmp_path / "round3.db"
    first = module.run(database)
    second = module.run(database, resume=True)
    assert first == second
    assert first["fixtureTurns"] == 2 and first["nativeModelCalls"] == 0
    assert len(set(first["attemptIds"])) == len(set(first["requestPins"])) == 2
    assert len({first[k] for k in ("baselineArtifactId", "receiptArtifactId", "returnedArtifactId")}) == 3
    assert first["experiment"]["review"]["kind"] == "synthetic"
    assert first["experiment"]["status"] == "rolled-back"
    assert first["rejectedExperiment"]["status"] == "rejected"
