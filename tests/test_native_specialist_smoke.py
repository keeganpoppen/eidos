"""Smoke procedure guards use local synthetic workers only."""
import importlib.util
from pathlib import Path

import pytest

from eidos.investigation import InvestigationStore
from eidos.investigation_worker import NativeInvestigationError
from eidos.trace import TraceStore


SPEC = importlib.util.spec_from_file_location(
    "native_specialist_smoke", Path(__file__).parents[1] / "scripts/native_specialist_smoke.py")
assert SPEC and SPEC.loader
smoke = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(smoke)


def test_prepare_and_inspect_never_create_native_worker(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("preparation must not construct a native worker")
    monkeypatch.setattr(smoke, "NativeInvestigationWorker", forbidden)
    database = tmp_path / "smoke.db"
    packet = smoke.prepare(database)
    assert packet["status"] == "draft"
    assert packet["attempt"] is None
    assert packet["promptBytes"] < 8192
    assert packet["limits"]["nativeTurns"] == 1
    assert packet["limits"]["providerTokenOrCostCap"] is None
    assert smoke.inspect(database, packet["investigationId"]) == packet
    with pytest.raises(FileExistsError):
        smoke.prepare(database)


def test_model_consent_required_before_database_or_worker_access(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("must reject before accessing database")
    monkeypatch.setattr(smoke, "TraceStore", forbidden)
    with pytest.raises(ValueError, match="requires --authorize-model"):
        smoke.run(tmp_path / "absent.db", "unused", None)


def test_wrong_context_never_claims_or_launches(tmp_path, monkeypatch):
    database = tmp_path / "smoke.db"
    packet = smoke.prepare(database)
    def forbidden(*args, **kwargs):
        raise AssertionError("must reject before launch")
    monkeypatch.setattr(smoke, "NativeInvestigationWorker", forbidden)
    with pytest.raises(ValueError, match="different context"):
        smoke.run(database, packet["investigationId"], "context-wrong")
    assert smoke.inspect(database, packet["investigationId"])["attempt"] is None


def test_profile_refusal_is_durable_and_retry_never_launches(tmp_path, monkeypatch):
    database = tmp_path / "smoke.db"
    packet = smoke.prepare(database)
    inv_id, ctx_id = packet["investigationId"], packet["contextId"]
    calls = []
    class RefusingWorker:
        def __init__(self, trace):
            calls.append("constructed")
        def run(self, attempt, context, update):
            assert context["id"] == ctx_id
            raise NativeInvestigationError("synthetic prelaunch profile refusal", status="failed")
        def close(self):
            calls.append("closed")
    monkeypatch.setattr(smoke, "NativeInvestigationWorker", RefusingWorker)
    result = smoke.run(database, inv_id, ctx_id)
    assert result["status"] == "failed"
    assert result["modelTurnRequestsRecorded"] == 0
    assert calls == ["constructed", "closed"]
    with pytest.raises(ValueError, match="already exists"):
        smoke.run(database, inv_id, ctx_id)
    assert calls == ["constructed", "closed"]


def test_modified_synthetic_evidence_is_rejected_without_attempt(tmp_path):
    database = tmp_path / "smoke.db"
    packet = smoke.prepare(database)
    trace = TraceStore(database)
    store = InvestigationStore(trace)
    investigation = store.get(packet["investigationId"])
    investigation["contexts"][0]["records"][0]["source"] = "private-history"
    with store._transaction():
        store._save(investigation)
    trace.close()
    with pytest.raises(ValueError, match="reviewed synthetic"):
        smoke.run(database, packet["investigationId"], packet["contextId"])


def test_changed_prompt_cannot_reuse_authorized_context_identity(tmp_path):
    database = tmp_path / "smoke.db"
    packet = smoke.prepare(database)
    trace = TraceStore(database)
    store = InvestigationStore(trace)
    investigation = store.get(packet["investigationId"])
    investigation["contexts"][0]["projectedPrompt"] = "Different request under the old reviewed identity."
    with store._transaction():
        store._save(investigation)
    trace.close()
    with pytest.raises(ValueError, match="content no longer matches"):
        smoke.run(database, packet["investigationId"], packet["contextId"])
