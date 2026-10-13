#!/usr/bin/env python3
"""Paired local startup policy challenge; all native provider replies are authored.

Reuse the reviewed runner with explicit config and transport-limit arguments.
No production profile, credentials, or upstream route is changed.
"""
from __future__ import annotations

import argparse
import copy
from dataclasses import asdict
import hashlib
import importlib.util
import json
from pathlib import Path
import platform
import re
import tempfile
from typing import Any

from eidos.codex import AppServerLimits

_spec = importlib.util.spec_from_file_location(
    "derived_catalog_fixture", Path(__file__).with_name("probe_native_model_catalog.py"))
assert _spec and _spec.loader
catalog = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(catalog)
transport = catalog.transport
boundary = catalog.boundary
MODEL = "gpt-6-astra"
CASES = ("original", "derived")
LIMITS = AppServerLimits(
    max_stdout_frame_bytes=1048576, max_stderr_frame_bytes=65536,
    max_received_bytes=4194304, max_event_count=128, max_event_bytes=2097152,
    max_stderr_tail_bytes=65536, max_stderr_tail_lines=100)
POLICY_PATCH = [
    {"op": "test", "path": "/models/0/slug", "value": MODEL},
    {"op": "test", "path": "/models/0/tool_mode", "value": "code_mode_only"},
    {"op": "test", "path": "/models/0/experimental_supported_tools",
     "value": ["send_user_message_async", "clock"]},
    {"op": "replace", "path": "/models/0/tool_mode", "value": "direct"},
    {"op": "replace", "path": "/models/0/experimental_supported_tools", "value": []},
]


def original_object(data: bytes) -> dict[str, Any]:
    if len(data) > 600000 or hashlib.sha256(data).hexdigest() != catalog.CATALOG_SHA256:
        raise ValueError("not the exact reviewed original catalog")
    value = json.loads(data)
    entry = value["models"][0]
    if any(entry[op["path"].rsplit("/", 1)[1]] != op["value"] for op in POLICY_PATCH[:3]):
        raise ValueError("catalog patch target differs")
    return value


def derived_catalog(data: bytes) -> bytes:
    value = original_object(data)
    for op in POLICY_PATCH[3:]:
        value["models"][0][op["path"].rsplit("/", 1)[1]] = copy.deepcopy(op["value"])
    derived = (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode()
    validate_derivation(data, derived)
    return derived


def validate_derivation(original: bytes, derived: bytes) -> None:
    expected = original_object(original)
    expected["models"][0]["tool_mode"] = "direct"
    expected["models"][0]["experimental_supported_tools"] = []
    # Python container equality aliases True with 1. Canonical JSON comparison
    # retains JSON type distinctions as well as every unknown field.
    if len(derived) > 600000 or json.dumps(json.loads(derived), sort_keys=True, allow_nan=False) != json.dumps(
            expected, sort_keys=True, allow_nan=False):
        raise ValueError("derived catalog must contain only the two reviewed semantic changes")


def fixture_config(model: str) -> str:
    if model != MODEL:
        raise ValueError("only the fixed Astra model is allowed")
    return catalog.fixture_config(model).replace(
        "[features]\n", "[features]\nmulti_agent_v2=false\nsleep_tool=false\ncurrent_time_reminder=false\n"
    ) + "\n[agents]\nenabled=false\n"


def assess_case(case: dict[str, Any], variant: str) -> list[str]:
    """A result interpretation, never a pre-effect admission check."""
    problems = []
    if case["failure"] is not None:
        problems.append("native-case-failed")
    effective = case["nativeReplies"].get("config/read", {}).get("config", {})
    if (effective.get("agents", {}).get("enabled") is not False
            or any(effective.get("features", {}).get(key) is not False for key in
                   ("multi_agent_v2", "sleep_tool", "current_time_reminder"))):
        problems.append("additional-controls-not-confirmed")
    capture = case["nativeCapture"]
    if capture["failure"] is not None or capture["diagnosticError"] is not None:
        problems.append("incomplete-native-capture")
    if capture["limits"] != asdict(LIMITS):
        problems.append("transport-limits-differ")
    messages = [json.loads(row["rawText"]) for row in case["traceRecords"] if row["direction"] == "internal"]
    recorded = [m.get("params", {}).get("limits") for m in messages if m.get("method") == "$transport/limits"]
    if recorded != [asdict(LIMITS)] or any(m.get("method") == "$transport/captureGap" for m in messages):
        problems.append("trusted-capture-record-differs")
    if case["nativeTurnRPCs"] != 1 or case["acceptedProviderRequests"] != 3 or case["providerRequests"] != 3:
        problems.append("turn-or-provider-count-differs")
    if case["fixtureResourceReads"] or any(e.get("target") == "/mcp" for e in case["brokerEvents"]):
        problems.append("disabled-mcp-contacted")
    artifact = case.get("savedArtifact") or {}
    if artifact.get("text") != transport.OUTPUT_TEXT or artifact.get("executionEvidence") != "synthetic":
        problems.append("synthetic-result-not-recovered")
    if any("fallback" in event.get("params", {}).get("message", "").lower()
           for event in case["nativeEvents"] if event.get("method") == "warning"):
        problems.append("model-fallback-warning")
    analyses = case["providerRequestAnalyses"]
    if len(analyses) != 3:
        problems.append("provider-sequence-incomplete")
        return problems
    for analysis in analyses:
        additional = analysis["additionalTools"]
        if (analysis["responsesLiteHeader"] != "true" or analysis["topLevelToolsPresent"]
                or analysis["exactSelectedPromptOccurrences"] != 1 or len(additional) != 1):
            problems.append("lite-envelope-differs")
            continue
        tools = additional[0]["tools"]
        if variant == "derived":
            if tools != []:
                problems.append("derived-tools-not-empty")
        else:
            names = {tool["name"]: {nested["name"] for nested in tool.get("tools", [])} for tool in tools}
            if names != {"functions": {"exec", "wait", "request_user_input_async"}}:
                problems.append("original-registration-differs")
            if "clock__curr_time" not in json.dumps(tools):
                problems.append("original-nested-clock-absent")
    outputs = analyses[-1]["functionOutputs"]
    if [item.get("call_id") for item in outputs] != [catalog.tool_probe.CALL_ID, catalog.CLOCK_CALL_ID]:
        problems.append("call-output-correlation-differs")
    elif outputs[0].get("output") != "unsupported call: read_mcp_resource":
        problems.append("disabled-resource-was-not-rejected")
    else:
        clock = outputs[1].get("output")
        if variant == "derived" and clock != "unsupported call: clockcurr_time":
            problems.append("derived-clock-was-not-rejected")
        if variant == "original" and (not isinstance(clock, str) or not re.fullmatch(
                r"It is \d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} UTC\.", clock)):
            problems.append("original-clock-did-not-complete")
    return problems


def run_case(helper: Path, variant: str, data: bytes) -> dict[str, Any]:
    if variant not in CASES:
        raise ValueError("unknown fixed fixture variant")
    result = catalog.run_case(helper, MODEL, data, config=fixture_config(MODEL), limits=LIMITS)
    result["variant"] = variant
    effective = result["nativeReplies"].get("config/read", {}).get("config", {})
    result["effectiveAdditionalControls"] = {
        "agents": effective.get("agents"),
        "features": {key: effective.get("features", {}).get(key) for key in
                     ("multi_agent_v2", "sleep_tool", "current_time_reminder")},
        "missingMeans": "config/read omission, not confirmation of effective value",
    }
    result["expectationFailures"] = assess_case(result, variant)
    return result


def run_probe(catalog_path: Path = catalog.CATALOG_PATH) -> dict[str, Any]:
    original, _ = catalog.checked_catalog(catalog_path)
    derived = derived_catalog(original)
    with tempfile.TemporaryDirectory(prefix="nema-derived-catalog-helper-") as temporary:
        helper = boundary.compile_helper(Path(temporary))
        cases = {variant: run_case(helper, variant, data)
                 for variant, data in zip(CASES, (original, derived), strict=True)}
    user_agent = cases["original"]["nativeReplies"].get("initialize", {}).get("userAgent", "")
    return {
        "schemaVersion": "nema-native-derived-catalog/1", "implementationBase": "555a317",
        "classification": "NATIVE_TRANSPORT_SYNTHETIC_DERIVED_CATALOG_CHALLENGE",
        "cases": cases, "candidateAccepted": all(not c["expectationFailures"] for c in cases.values()),
        "catalog": {"source": catalog.CATALOG_URL, "originalSha256": catalog.CATALOG_SHA256,
                    "derivedSha256": hashlib.sha256(derived).hexdigest(),
                    "originalBytes": len(original), "derivedBytes": len(derived),
                    "patch": POLICY_PATCH, "derivationLabel": "Nema local startup policy",
                    "serialization": "json.dumps(value, indent=2, ensure_ascii=False) + newline, UTF-8",
                    "onlyTwoSemanticChangesVerified": True},
        "authoredResponses": [catalog.authored_stream(MODEL, step).decode() for step in range(3)],
        "nativeUserAgent": user_agent, "nativeVersionSource": "contained initialize.userAgent",
        "binarySha256": hashlib.sha256(Path("/usr/bin/codex").read_bytes()).hexdigest(),
        "processFilterSourceSha256": hashlib.sha256(boundary.HELPER_C.encode()).hexdigest(),
        "kernel": platform.release(), "architecture": platform.machine(),
        "nativeTurnRPCs": sum(c["nativeTurnRPCs"] for c in cases.values()),
        "providerRequests": sum(c["providerRequests"] for c in cases.values()),
        "realModelCalls": 0, "realUpstreamRequests": 0, "existingCredentialsMounted": False,
        "subscriptionExecution": False, "callerAuthenticationEstablished": False, "liveAdmission": False,
        "limits": {"transport": asdict(LIMITS), "requestsPerCase": transport.MAX_REQUESTS,
                   "acceptedProviderRequestsPerCase": catalog.MAX_PROVIDER_REQUESTS,
                   "headerBytes": transport.MAX_HEADER, "bodyBytes": transport.MAX_BODY,
                   "responseBytes": transport.MAX_RESPONSE, "requestSeconds": transport.REQUEST_SECONDS,
                   "nativeWatchdogSeconds": transport.CASE_SECONDS, "completionEventsConsumed": 100,
                   "traceDatabaseByteQuota": False, "aggregateResourceQuota": False},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=catalog.CATALOG_PATH)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    text = json.dumps(run_probe(args.catalog), indent=2) + "\n"
    if args.output:
        args.output.write_text(text)
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
