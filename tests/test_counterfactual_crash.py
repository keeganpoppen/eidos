"""Actual abrupt-process-exit checks for the local experiment ledger only."""
from __future__ import annotations

import subprocess
import sys

import pytest

from eidos.investigation import InvestigationStore
from eidos.investigation_alternatives import ExperimentStore
from eidos.trace import TraceStore
from test_investigation_alternatives import _experiment, _world


@pytest.mark.parametrize("phase", ["prepared", "outcome_uncommitted", "outcome_committed"])
def test_abrupt_exit_retains_admission_without_automatic_execution(tmp_path, phase):
    path = tmp_path / "crash.db"
    trace, _, ledger, bundle = _world(path)
    _experiment(ledger, bundle)
    before_raw = [(r.seq, r.raw_text) for r in trace.records()]
    trace.close()
    process = subprocess.run([
        sys.executable, "-c", """
import os, sys
from eidos.trace import TraceStore
from eidos.investigation import InvestigationStore
from eidos.investigation_alternatives import ExperimentStore
trace = TraceStore(sys.argv[1])
ledger = ExperimentStore(InvestigationStore(trace))
ledger.prepare_attempt('crashed-attempt', experiment='experiment', variant='alternative')
phase = sys.argv[2]
if phase == 'outcome_uncommitted':
    trace.db.execute('BEGIN IMMEDIATE')
if phase != 'prepared':
    ledger.finish_attempt('crashed-outcome', attempt='crashed-attempt', answer='Synthetic result', claims=[])
os._exit(73)
""", str(path), phase,
    ], capture_output=True, text=True, timeout=20)
    assert process.returncode == 73, process.stderr
    reopened = TraceStore(path)
    try:
        recovered = ExperimentStore(InvestigationStore(reopened))
        attempt, created = recovered.prepare_attempt(
            "crashed-attempt", experiment="experiment", variant="alternative")
        assert not created and attempt.data["authority"] == "none"
        assert len(recovered.list(kind="outcome")) == (phase == "outcome_committed")
        # Reading/repreparing does not append native traffic or call an executor.
        assert [(r.seq, r.raw_text) for r in reopened.records()] == before_raw
        if phase == "outcome_committed":
            assert recovered.finish_attempt(
                "crashed-outcome", attempt="crashed-attempt", answer="Synthetic result", claims=[]
            ) == recovered.get("crashed-outcome")
    finally:
        reopened.close()
