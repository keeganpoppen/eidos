"""Pure structural/counterexample tests by default; native startup is explicit."""
import copy
from dataclasses import asdict
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tomllib

import pytest

spec = importlib.util.spec_from_file_location(
    "native_derived_catalog_probe", Path(__file__).parents[1] / "scripts/probe_native_derived_catalog.py")
assert spec and spec.loader
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


def test_derivation_changes_only_two_target_fields_and_preserves_original():
    original, _ = probe.catalog.checked_catalog()
    before = json.loads(original)
    derived = probe.derived_catalog(original)
    assert derived == probe.derived_catalog(original)
    after = json.loads(derived)
    assert after["models"][0]["tool_mode"] == "direct"
    assert after["models"][0]["experimental_supported_tools"] == []
    after["models"][0]["tool_mode"] = before["models"][0]["tool_mode"]
    after["models"][0]["experimental_supported_tools"] = before["models"][0]["experimental_supported_tools"]
    assert after == before
    assert hashlib.sha256(original).hexdigest() == probe.catalog.CATALOG_SHA256
    target = json.loads(derived)["models"][0]
    assert target["slug"] == probe.MODEL and target["use_responses_lite"] is True
    assert target["multi_agent_version"] == "v2"
    applied = copy.deepcopy(before)
    for op in probe.POLICY_PATCH:
        _, group, index, key = op["path"].split("/")
        item = applied[group][int(index)]
        if op["op"] == "test":
            assert item[key] == op["value"]
        else:
            assert op["op"] == "replace"
            item[key] = copy.deepcopy(op["value"])
    assert applied == json.loads(derived)


@pytest.mark.parametrize("mutation", ["slug", "lite", "bool-as-int", "agents", "other-model", "unknown", "clock", "mode"])
def test_extra_semantic_changes_are_rejected(mutation):
    original, _ = probe.catalog.checked_catalog()
    changed = json.loads(probe.derived_catalog(original))
    target = changed["models"][0]
    if mutation == "slug": target["slug"] = "different"
    elif mutation == "lite": target["use_responses_lite"] = False
    elif mutation == "bool-as-int": target["use_responses_lite"] = 1
    elif mutation == "agents": target["multi_agent_version"] = "disabled"
    elif mutation == "other-model": changed["models"][1]["tool_mode"] = "direct"
    elif mutation == "unknown": target["futurePolicy"] = "made up"
    elif mutation == "clock": target["experimental_supported_tools"] = ["clock"]
    elif mutation == "mode": target["tool_mode"] = None
    with pytest.raises(ValueError, match="only the two"):
        probe.validate_derivation(original, json.dumps(changed).encode())


def test_changed_original_is_refused_before_compilation_or_startup(tmp_path, monkeypatch):
    original, _ = probe.catalog.checked_catalog()
    with pytest.raises(ValueError, match="exact reviewed"):
        probe.derived_catalog(original + b" ")
    path = tmp_path / "tampered.json"
    path.write_bytes(original + b" ")
    def unexpected(*args, **kwargs):
        pytest.fail("invalid original reached native helper compilation")
    monkeypatch.setattr(probe.boundary, "compile_helper", unexpected)
    with pytest.raises(ValueError, match="exact reviewed"):
        probe.run_probe(path)


def test_controls_are_same_for_both_catalogs_and_provider_stays_local_noauth():
    config = tomllib.loads(probe.fixture_config(probe.MODEL))
    assert config["model_catalog_json"] == "/fixture/models.json"
    assert config["agents"] == {"enabled": False}
    for key in ("multi_agent", "multi_agent_v2", "sleep_tool", "current_time_reminder", "code_mode", "shell_tool"):
        assert config["features"][key] is False
    assert config["mcp_servers"]["fixture"]["enabled"] is False
    provider = config["model_providers"][probe.transport.PROVIDER]
    assert provider["base_url"] == "http://127.0.0.1:FIXTURE_PORT/v1"
    assert provider["requires_openai_auth"] is False
    assert not {"env_key", "experimental_bearer_token"} & provider.keys()
    with pytest.raises(ValueError): probe.fixture_config("gpt-5.5")


def test_shared_runner_gets_explicit_config_and_limits_without_native_startup(monkeypatch):
    def injected(helper, model, data, *, config, limits):
        assert model == probe.MODEL and data == b"fixture"
        assert config == probe.fixture_config(probe.MODEL)
        assert limits == probe.LIMITS
        raise RuntimeError("authored runner failure")
    monkeypatch.setattr(probe.catalog, "run_case", injected)
    with pytest.raises(RuntimeError, match="authored runner failure"):
        probe.run_case(Path("/never-start"), "derived", b"fixture")


def fixture_case():
    """Authored interpretation input; never an observation of native execution."""
    analyses = [{"responsesLiteHeader": "true", "topLevelToolsPresent": False,
                 "exactSelectedPromptOccurrences": 1, "additionalTools": [{"tools": []}]} for _ in range(3)]
    analyses[-1]["functionOutputs"] = [
        {"call_id": probe.catalog.tool_probe.CALL_ID, "output": "unsupported call: read_mcp_resource"},
        {"call_id": probe.catalog.CLOCK_CALL_ID, "output": "unsupported call: clockcurr_time"}]
    limits = asdict(probe.LIMITS)
    return {"failure": None, "nativeReplies": {"config/read": {"config": {
                "agents": {"enabled": False}, "features": {"multi_agent_v2": False,
                "sleep_tool": False, "current_time_reminder": False}}}},
            "nativeCapture": {"failure": None, "diagnosticError": None, "limits": limits},
            "traceRecords": [{"direction": "internal", "rawText": json.dumps({"method": "$transport/limits",
                             "params": {"limits": limits}})}], "nativeTurnRPCs": 1,
            "acceptedProviderRequests": 3, "providerRequests": 3, "fixtureResourceReads": 0,
            "brokerEvents": [], "savedArtifact": {"text": probe.transport.OUTPUT_TEXT, "executionEvidence": "synthetic"},
            "nativeEvents": [], "providerRequestAnalyses": analyses}


def test_authored_assessment_requires_wire_rejection_even_without_native_action_events():
    case = fixture_case()
    assert probe.assess_case(case, "derived") == []
    case["providerRequestAnalyses"][-1]["functionOutputs"][1]["output"] = "It is 2026-10-13 12:00:00 UTC."
    assert "derived-clock-was-not-rejected" in probe.assess_case(case, "derived")


@pytest.mark.parametrize("mutation,problem", [
    ("gap", "incomplete-native-capture"), ("schema", "derived-tools-not-empty"),
    ("mcp", "disabled-mcp-contacted"), ("classification", "synthetic-result-not-recovered"),
    ("correlation", "call-output-correlation-differs"), ("missing-limit", "trusted-capture-record-differs"),
    ("missing-control", "additional-controls-not-confirmed"),
])
def test_candidate_rejects_material_counterexamples(mutation, problem):
    case = fixture_case()
    if mutation == "gap": case["nativeCapture"]["failure"] = {"captureComplete": False}
    elif mutation == "schema": case["providerRequestAnalyses"][1]["additionalTools"][0]["tools"] = [{"name": "unexpected"}]
    elif mutation == "mcp": case["brokerEvents"] = [{"target": "/mcp"}]
    elif mutation == "classification": case["savedArtifact"]["executionEvidence"] = "native"
    elif mutation == "correlation": case["providerRequestAnalyses"][-1]["functionOutputs"][1]["call_id"] = "wrong"
    elif mutation == "missing-limit": case["traceRecords"] = []
    elif mutation == "missing-control": case["nativeReplies"]["config/read"]["config"].pop("agents")
    assert problem in probe.assess_case(case, "derived")


def test_committed_raw_evidence_passes_current_interpretation_without_native_startup():
    path = Path(__file__).parents[1] / "docs/evidence/NATIVE_DERIVED_CATALOG_0_154_0.json"
    report = json.loads(path.read_bytes())
    for variant, case in report["cases"].items():
        assert probe.assess_case(case, variant) == []


@pytest.fixture(scope="module")
def observed():
    if os.environ.get("NEMA_NATIVE_DERIVED_CATALOG_PROBE") != "1":
        pytest.skip("opt in to disconnected native paired startup-catalog challenge")
    report = probe.run_probe()
    if output := os.environ.get("NEMA_NATIVE_DERIVED_CATALOG_EVIDENCE"):
        Path(output).write_text(json.dumps(report, indent=2) + "\n")
    return report


@pytest.mark.parametrize("variant", probe.CASES)
def test_contained_variant_matches_wire_effect_and_capture_contract(observed, variant):
    case = observed["cases"][variant]
    assert case["expectationFailures"] == [], case["expectationFailures"]
    assert case["policy"]["installedBeforeInitialExec"] and case["policy"]["allListenerCopiesClosed"]
    assert case["nativeReplies"]["account/read"] == {"account": None, "requiresOpenaiAuth": False}
    effective = case["nativeReplies"]["config/read"]["config"]
    assert effective["model"] == probe.MODEL and effective["model_catalog_json"] == "/fixture/models.json"
    assert case["catalogSha256"] == observed["catalog"][variant + "Sha256"]
    assert case["httpRequests"] == case["providerRequests"] == case["acceptedProviderRequests"] == 3
    assert 0 < sum(case["nativeCapture"]["receivedBytes"].values()) <= probe.LIMITS.max_received_bytes
    assert case["nativeReplies"]["mcpServerStatus/list"]["data"][0]["runtimeStatus"] == "disabled"
    assert not case["validProviderRequestImpersonationTested"]
    assert {event["params"]["item"]["type"] for event in case["nativeEvents"]
            if event.get("method") in {"item/started", "item/completed"}} == {"userMessage", "agentMessage"}


def test_paired_result_retains_synthetic_classification_and_exact_patch(observed):
    assert observed["candidateAccepted"] is True
    assert observed["nativeTurnRPCs"] == 2 and observed["providerRequests"] == 6
    assert observed["realModelCalls"] == observed["realUpstreamRequests"] == 0
    assert not any(observed[key] for key in ("existingCredentialsMounted", "subscriptionExecution", "callerAuthenticationEstablished", "liveAdmission"))
    assert observed["cases"]["original"]["requestedConfigToml"] == observed["cases"]["derived"]["requestedConfigToml"]
    assert observed["catalog"]["patch"] == probe.POLICY_PATCH
    original, _ = probe.catalog.checked_catalog()
    assert observed["catalog"]["derivedSha256"] == hashlib.sha256(probe.derived_catalog(original)).hexdigest()
    assert observed["authoredResponses"] == [probe.catalog.authored_stream(probe.MODEL, step).decode() for step in range(3)]
