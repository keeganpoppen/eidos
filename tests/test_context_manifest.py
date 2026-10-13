"""Synthetic, local context-boundary tests; no native/provider calls are made."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError
import hashlib
from pathlib import Path
from threading import Barrier

import pytest

from eidos.context_manifest import (
    Boundary,
    ContextManifestStore,
    KnowledgeState,
    RuntimeIdentity,
)
from eidos.core import Name, Role
from eidos.trace import TraceStore


@pytest.fixture
def context():
    trace = TraceStore()
    try:
        yield trace, ContextManifestStore(trace)
    finally:
        trace.close()


def ingredient(store, text, *, state=KnowledgeState.SELECTED, boundary=Boundary.LOCAL):
    content = store.put_content("instruction", {"text": text})
    claim = store.claim(content, state=state, boundary=boundary)
    return store.slot(claim)


def evidence(trace, store, direction="internal", *, message=None):
    record = trace.append(
        source="synthetic/context-test",
        direction=direction,
        message=message or {"method": "synthetic/context", "params": {"ingredient": "fixture"}},
    )
    return store.freeze_trace(record.seq)


def object_count(trace):
    return trace.db.execute("SELECT COUNT(*) FROM cm_objects").fetchone()[0]


def test_content_snapshots_nested_input_output_and_reference_mapping(context):
    _, store = context
    original = {"layers": [{"text": "preserve", "future": [None, {"x": 1}]}]}
    child = store.put_content("instruction", original)
    references = {"root": child}
    collection = store.put_content("instructions", {"order": ["root"]}, references)
    original["layers"][0]["future"][1]["x"] = 99
    references["root"] = "caller-mutation"

    snapshot = store.get(child)
    returned = snapshot.data
    returned["layers"][0]["text"] = "caller-mutation"
    assert snapshot.data == {"layers": [{"text": "preserve", "future": [None, {"x": 1}]}]}
    assert store.get(collection).ref("root") == child
    assert store.get(collection).refs == (("root", child),)
    with pytest.raises(FrozenInstanceError):
        snapshot.cid = "caller-mutation"
    with pytest.raises(KeyError):
        snapshot.ref("absent")


def test_content_identity_canonicalizes_order_but_preserves_missing_null_empty_and_kind(context):
    _, store = context
    first = store.put_content("config", {"future": {"b": 2, "a": 1}, "model": "synthetic"})
    second = store.put_content("config", {"model": "synthetic", "future": {"a": 1, "b": 2}})
    assert first == second
    distinctions = [{}, {"value": None}, {"value": ""}, {"value": []}, {"value": {}}, {"value": False}]
    ids = [store.put_content("config", value) for value in distinctions]
    assert len(set(ids)) == len(distinctions)
    assert [store.get(cid).data for cid in ids] == distinctions
    assert store.put_content("instruction", store.get(first).data) != first


@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), b"bytes", {1: "not a JSON key"}])
def test_non_json_content_is_rejected_instead_of_silently_rewritten(context, invalid):
    _, store = context
    with pytest.raises(ValueError):
        store.put_content("config", {"invalid": invalid})


def test_dangling_content_and_evidence_references_are_rejected(context):
    _, store = context
    with pytest.raises(KeyError):
        store.put_content("instructions", {}, {"missing": "no-such-cid"})
    with pytest.raises(KeyError):
        store.claim("no-such-cid", state=KnowledgeState.SELECTED, boundary=Boundary.LOCAL)
    content = store.put_content("instruction", {"text": "fixture"})
    with pytest.raises((ValueError, KeyError)):
        store.claim(content, state=KnowledgeState.OBSERVED, boundary=Boundary.PROVIDER, evidence=(content,))


def test_descriptive_json_cannot_forge_frozen_boundary_evidence(context):
    _, store = context
    with pytest.raises(ValueError):
        store.put_content("cm.trace", {"direction": "provider_request", "raw_text": "{}", "seq": 1})
    fake = store.put_content("synthetic_receipt", {"direction": "provider_request", "raw_text": "{}", "seq": 1})
    content = store.put_content("instruction", {"text": "claimed provider input"})
    with pytest.raises(ValueError):
        store.claim(content, state=KnowledgeState.OBSERVED, boundary=Boundary.PROVIDER, evidence=(fake,))


def test_one_skill_change_shares_unrelated_subtrees_and_does_not_copy_the_graph(context):
    trace, store = context
    slots = {
        **{f"tools/tool-{index}": ingredient(store, f"tool {index}") for index in range(40)},
        "instructions/root": ingredient(store, "root"),
        "instructions/workspace": ingredient(store, "workspace"),
        "skills/current": ingredient(store, "skill S7"),
        "skills/other": ingredient(store, "unchanged skill"),
    }
    before = store.manifest(slots)
    replacement = ingredient(store, "skill S8")
    count_before = object_count(trace)
    after = store.replace(before, "skills/current", replacement)

    assert before.cid != after.cid
    assert store.at(before, "skills/current") == slots["skills/current"]
    assert store.at(after, "skills/current") == replacement
    assert store.get(before.root).ref("tools") == store.get(after.root).ref("tools")
    assert store.get(before.root).ref("instructions") == store.get(after.root).ref("instructions")
    assert store.at(before, "skills/other") == store.at(after, "skills/other")
    assert object_count(trace) - count_before <= 5
    assert store.manifest(dict(reversed(list(slots.items())))).cid == before.cid
    assert store.replace(before, "skills/current", slots["skills/current"]).cid == before.cid


def test_version_diff_add_remove_replace_and_revert(context):
    _, store = context
    old = ingredient(store, "S7")
    new = ingredient(store, "S8")
    removed = ingredient(store, "old tool")
    added = ingredient(store, "new config")
    before = store.manifest({"skills/current": old, "tools/retired": removed})
    after = store.replace(before, "skills/current", new)
    after = store.replace(after, "tools/retired", None)
    after = store.replace(after, "config/model", added)

    changes = store.diff(before, after)
    assert [(item.path, item.operation, item.before, item.after) for item in changes] == [
        ("config/model", "add", None, added),
        ("skills/current", "replace", old, new),
        ("tools/retired", "remove", removed, None),
    ]
    reverted = after
    for change in changes:
        reverted = store.replace(reverted, change.path, change.before)
    assert reverted.cid == before.cid
    assert store.diff(before, reverted) == ()
    with pytest.raises(KeyError):
        store.replace(before, "absent/path", None)


def test_historical_request_snapshot_survives_revision_late_native_metadata_and_reopen(tmp_path: Path):
    path = tmp_path / "synthetic-trace.db"
    trace = TraceStore(path)
    store = ContextManifestStore(trace)
    raw = '{"id":7, "method":"turn/start", "params":{"threadId":"t","input":[]}, "future":{"keep":"spacing"}}'
    record = trace.append_line(source="synthetic/appserver", direction="client_to_appserver", raw_text=raw)
    frozen = store.freeze_trace(record.seq)
    original_evidence = store.get(frozen).data
    selected = ingredient(store, "old instruction")
    before = store.manifest({"instructions/root": selected})
    original_request = store.pin_request("request/old", before, identity=RuntimeIdentity(process_name="worker", attempt_id="a1"))
    original_data = original_request.data
    after = store.replace(before, "instructions/root", ingredient(store, "new instruction"))
    store.pin_request("request/new", after, identity=RuntimeIdentity(process_name="worker", attempt_id="a2"))
    trace.append(source="synthetic/appserver", direction="appserver_to_client", message={"id": 7, "result": {"turn": {"id": "late-turn"}}})
    assert trace.get(record.seq).turn_id == "late-turn"
    trace.close()

    reopened = TraceStore(path)
    try:
        restored = ContextManifestStore(reopened)
        assert restored.get_request("request/old").data == original_data
        assert restored.get_request("request/old").ref("manifest") == before.cid
        assert restored.at(before, "instructions/root") == selected
        assert restored.get(frozen).data == original_evidence
        assert restored.get(frozen).data["raw_text"] == raw
        assert restored.get(frozen).data["sha256"] == hashlib.sha256(raw.encode()).hexdigest()
        assert restored.get(frozen).data["source"] == "synthetic/appserver"
        assert restored.get(frozen).data["direction"] == "client_to_appserver"
        assert restored.get(frozen).data["seq"] == record.seq
        assert {request.cid for request in restored.requests_for(before)} == {original_request.cid}
    finally:
        reopened.close()


def test_available_selected_projected_observed_and_inferred_are_distinct_claims(context):
    trace, store = context
    content = store.put_content("skill", {"name": "synthetic skill", "text": "check sources"})
    receipt = evidence(trace, store)
    claims = [
        store.claim(content, state=state, boundary=Boundary.LOCAL, evidence=(receipt,) if state is KnowledgeState.OBSERVED else ())
        for state in KnowledgeState
    ]
    assert len(set(claims)) == 5
    manifest = store.manifest({"skills/source": store.slot(*claims)})
    local = store.inspect(manifest, "skills/source", boundary=Boundary.LOCAL)
    assert {claim.cid for claim in local.claims} == set(claims)
    assert not local.unknown
    assert store.inspect(manifest, "skills/source").unknown
    assert store.inspect(manifest, "missing/path").unknown


@pytest.mark.parametrize("state", [KnowledgeState.AVAILABLE, KnowledgeState.SELECTED, KnowledgeState.PROJECTED, KnowledgeState.INFERRED])
def test_planned_or_inferred_provider_ingredient_is_still_unknown(context, state):
    _, store = context
    slot = ingredient(store, "intended instruction", state=state, boundary=Boundary.PROVIDER)
    manifest = store.manifest({"instructions/root": slot})
    inspection = store.inspect(manifest, "instructions/root")
    assert inspection.unknown
    assert len(inspection.claims) == 1


@pytest.mark.parametrize("boundary", list(Boundary))
def test_observation_without_boundary_evidence_is_rejected(context, boundary):
    _, store = context
    content = store.put_content("instruction", {"text": "fixture"})
    with pytest.raises(ValueError):
        store.claim(content, state=KnowledgeState.OBSERVED, boundary=boundary)


@pytest.mark.parametrize("direction,allowed", [
    ("internal", Boundary.LOCAL),
    ("client_to_appserver", Boundary.APP_SERVER),
    ("appserver_to_client", Boundary.APP_SERVER),
    ("provider_request", Boundary.PROVIDER),
    ("provider_response", Boundary.PROVIDER),
])
def test_observation_cannot_promote_evidence_across_boundaries(context, direction, allowed):
    trace, store = context
    receipt = evidence(trace, store, direction)
    content = store.put_content("instruction", {"text": "fixture"})
    for boundary in Boundary:
        if boundary is allowed:
            assert store.claim(content, state=KnowledgeState.OBSERVED, boundary=boundary, evidence=(receipt,))
        else:
            with pytest.raises(ValueError):
                store.claim(content, state=KnowledgeState.OBSERVED, boundary=boundary, evidence=(receipt,))


def test_partial_provider_visibility_does_not_hide_an_explicit_gap(context):
    trace, store = context
    provider_evidence = evidence(trace, store, "provider_request")
    prompt = store.put_content("user_prompt", {"text": "synthetic question"})
    observed = store.claim(prompt, state=KnowledgeState.OBSERVED, boundary=Boundary.PROVIDER, evidence=(provider_evidence,))
    gap = store.unknown("provider preprocessing not captured", boundary=Boundary.PROVIDER, details={"fields": ["system", "tools"], "future": None})
    manifest = store.manifest({"native/context": store.slot(observed, gap)})
    inspection = store.inspect(manifest, "native/context")
    assert inspection.unknown
    assert {item.cid for item in inspection.claims} == {observed}
    assert {item.cid for item in inspection.gaps} == {gap}
    assert inspection.conflicts == ()


def test_conflicting_observations_are_retained_without_last_writer_wins(context):
    trace, store = context
    first_evidence = evidence(trace, store, "provider_request", message={"model": "model-a"})
    second_evidence = evidence(trace, store, "provider_response", message={"model": "model-b"})
    scope = RuntimeIdentity(process_name="worker", incarnation_id="boot-1", thread_id="thread", turn_id="turn", request_id="request", attempt_id="attempt")
    a = store.put_content("model_config", {"model": "model-a"})
    b = store.put_content("model_config", {"model": "model-b"})
    first = store.claim(a, state=KnowledgeState.OBSERVED, boundary=Boundary.PROVIDER, facet="model", scope=scope, evidence=(first_evidence,))
    second = store.claim(b, state=KnowledgeState.OBSERVED, boundary=Boundary.PROVIDER, facet="model", scope=scope, evidence=(second_evidence,))
    inferred = store.claim(b, state=KnowledgeState.INFERRED, boundary=Boundary.PROVIDER, facet="model", scope=scope, rationale="synthetic inference")
    manifest = store.manifest({"config/model": store.slot(first, second, inferred)})
    inspection = store.inspect(manifest, "config/model")
    assert {item.cid for item in inspection.claims} == {first, second, inferred}
    assert len(inspection.conflicts) == 1
    assert inspection.conflicts[0].facet == "model"
    assert set(inspection.conflicts[0].claim_ids) == {first, second}
    assert store.get(first).ref("content") == a
    assert store.get(second).ref("content") == b


def test_different_attempts_and_facets_are_not_false_observation_conflicts(context):
    trace, store = context
    receipt = evidence(trace, store, "provider_request")
    first = store.put_content("model_config", {"model": "a"})
    second = store.put_content("model_config", {"model": "b"})
    claims = [
        store.claim(first, state=KnowledgeState.OBSERVED, boundary=Boundary.PROVIDER, facet="model", scope=RuntimeIdentity(attempt_id="a1"), evidence=(receipt,)),
        store.claim(second, state=KnowledgeState.OBSERVED, boundary=Boundary.PROVIDER, facet="model", scope=RuntimeIdentity(attempt_id="a2"), evidence=(receipt,)),
        store.claim(second, state=KnowledgeState.OBSERVED, boundary=Boundary.PROVIDER, facet="fallback-model", scope=RuntimeIdentity(attempt_id="a1"), evidence=(receipt,)),
    ]
    manifest = store.manifest({"config/model": store.slot(*claims)})
    assert store.inspect(manifest, "config/model").conflicts == ()


@pytest.mark.parametrize("anchored", [False, True])
def test_missing_identity_fields_do_not_silently_hide_possible_conflicts(context, anchored):
    trace, store = context
    receipt = evidence(trace, store, "provider_request")
    first = store.put_content("model_config", {"model": "a"})
    second = store.put_content("model_config", {"model": "b"})
    first_scope = RuntimeIdentity(attempt_id="a1" if anchored else None)
    enriched_scope = RuntimeIdentity(attempt_id="a1" if anchored else None, thread_id="thread")
    claims = [
        store.claim(first, state=KnowledgeState.OBSERVED, boundary=Boundary.PROVIDER, facet="model", scope=first_scope, evidence=(receipt,)),
        store.claim(second, state=KnowledgeState.OBSERVED, boundary=Boundary.PROVIDER, facet="model", scope=enriched_scope, evidence=(receipt,)),
    ]
    manifest = store.manifest({"config/model": store.slot(*claims)})
    conflicts = store.inspect(manifest, "config/model").conflicts
    assert len(conflicts) == 1
    assert set(conflicts[0].claim_ids) == set(claims)
    assert conflicts[0].scope_uncertain is not anchored


def test_skill_availability_and_loading_have_independent_evidence(context):
    trace, store = context
    skill = store.put_content("skill_source", {"name": "source-review", "revision": "S7", "text": "Read selected evidence."})
    available = store.claim(skill, state=KnowledgeState.AVAILABLE, boundary=Boundary.LOCAL, facet="catalogued")
    selected = store.claim(skill, state=KnowledgeState.SELECTED, boundary=Boundary.LOCAL, facet="requested")
    before = store.manifest({"skills/current": store.slot(available, selected)})
    loaded_evidence = evidence(trace, store, message={"method": "skill/read", "params": {"content": skill}})
    loaded = store.claim(skill, state=KnowledgeState.OBSERVED, boundary=Boundary.LOCAL, facet="loaded", evidence=(loaded_evidence,))
    after = store.replace(before, "skills/current", store.slot(available, selected, loaded))
    assert {claim.cid for claim in store.inspect(before, "skills/current", boundary=Boundary.LOCAL).claims} == {available, selected}
    assert store.inspect(before, "skills/current", boundary=Boundary.LOCAL).unknown
    assert not store.inspect(after, "skills/current", boundary=Boundary.LOCAL).unknown
    assert store.inspect(after, "skills/current", boundary=Boundary.PROVIDER).unknown


def test_context_recipe_preserves_ordered_agents_layers_and_full_boundary_ingredients(context):
    trace, store = context
    global_source = store.put_content("instruction_source", {"path": "/synthetic/global/AGENTS.md", "revision": "g1", "text": "global rule"})
    repo_source = store.put_content("instruction_source", {"path": "/synthetic/worktree/AGENTS.md", "revision": "r1", "text": "repository rule"})
    leaf_source = store.put_content("instruction_source", {"path": "/synthetic/worktree/src/AGENTS.md", "revision": "l1", "text": "nearest rule"})
    layers = store.put_content("agents_layers", {"order": ["global", "repository", "nearest"], "scope": "src/example.py"}, {"global": global_source, "repository": repo_source, "nearest": leaf_source})
    tool = store.put_content("tool_description", {"name": "synthetic/read", "description": "Read selected synthetic content", "configured": {"enabled": True, "scope": "workspace"}, "future": {"limit": 4}})
    config = store.put_content("model_config", {"model": "synthetic-model", "reasoning": "high", "sandbox": "fixture"})
    workspace = store.put_content("workspace", {"name": "workspace/name", "revision": "synthetic-revision-1", "dirty": False, "root": "/synthetic/worktree"})
    selected_evidence = evidence(trace, store)
    selection = store.put_content("context_decision", {"rationale": "selected the recorded decision", "excluded": [{"source": "other-thread", "reason": "outside question"}]}, {"selected": selected_evidence})
    projected_binding = store.put_binding(Role("context", "instructions"), layers, name=Name("binding/instructions"), capture="snapshot")
    ingredients = {"instructions/layers": layers, "tools/read": tool, "config/model": config, "workspace/identity": workspace, "selection/decision": selection, "bindings/instructions": projected_binding}
    slots = {path: store.slot(store.claim(cid, state=KnowledgeState.PROJECTED, boundary=Boundary.LOCAL)) for path, cid in ingredients.items()}
    slots["native/unknown"] = store.slot(store.unknown("provider system prompt unavailable", boundary=Boundary.PROVIDER))
    manifest = store.manifest(slots)
    identity = RuntimeIdentity(process_name="process/p", incarnation_id="boot/1", thread_id="t", turn_id="u", request_id="r", attempt_id="a")
    request = store.pin_request("request/recipe", manifest, identity=identity)

    assert store.entries(manifest) == slots
    assert store.get(layers).data["order"] == ["global", "repository", "nearest"]
    assert store.get(layers).ref("nearest") == leaf_source
    assert store.get(tool).data["future"] == {"limit": 4}
    assert request.ref("manifest") == manifest.cid
    assert store.inspect(manifest, "native/unknown").unknown
    changed = store.replace(manifest, "tools/read", ingredient(store, "new synthetic tool description"))
    assert [change.path for change in store.diff(manifest, changed)] == ["tools/read"]


def test_binding_name_target_role_capture_and_placement_do_not_collapse(context):
    _, store = context
    target = store.put_content("executor_description", {"socket_name": "historical/socket", "executable": False})
    binding_name = Name("binding/executor")
    entity_name = Name("entity/executor")
    role = Role("worker", "executor")
    common = {"name": binding_name, "entity_name": entity_name, "capture": "situated"}
    first = store.put_binding(role, target, placement={"workspace": "one"}, **common)
    moved = store.put_binding(role, target, placement={"workspace": "two"}, **common)
    renamed = store.put_binding(role, target, name=Name("binding/other"), entity_name=entity_name, capture="situated", placement={"workspace": "one"})
    lexical = store.put_binding(role, target, name=binding_name, entity_name=entity_name, capture="lexical", placement={"workspace": "one"})
    another_role = store.put_binding(Role("reviewer", "executor"), target, placement={"workspace": "one"}, **common)
    named_target = store.put_binding(role, "entity/executor", target_kind="name", name=binding_name)
    assert len({first, moved, renamed, lexical, another_role, named_target}) == 6
    assert store.get(first).ref("target") == store.get(moved).ref("target") == target
    assert store.get(first).data["binding_name"] == store.get(moved).data["binding_name"] == binding_name.value
    assert store.get(first).data["entity_name"] == entity_name.value
    assert store.get(target).data == {"socket_name": "historical/socket", "executable": False}
    assert store.get(named_target).data["target_kind"] == "name"
    assert not store.get(named_target).refs


def test_request_name_replay_is_idempotent_and_repin_is_rejected(context):
    _, store = context
    before = store.manifest({"skills/current": ingredient(store, "S7")})
    after = store.replace(before, "skills/current", ingredient(store, "S8"))
    identity = RuntimeIdentity(process_name="worker", attempt_id="attempt-1")
    request = store.pin_request("request/one", before, identity=identity)
    assert store.pin_request("request/one", before, identity=identity).cid == request.cid
    with pytest.raises(ValueError):
        store.pin_request("request/one", after, identity=identity)
    with pytest.raises(ValueError):
        store.pin_request("request/one", before, identity=RuntimeIdentity(process_name="worker", attempt_id="attempt-2"))
    assert store.get_request("request/one").ref("manifest") == before.cid
    assert store.requests_for(after) == ()


def test_attempts_and_runtime_incarnations_do_not_rewrite_earlier_request_identity(context):
    _, store = context
    manifest = store.manifest({"instructions/root": ingredient(store, "instruction")})
    identities = [
        RuntimeIdentity(process_name="worker", incarnation_id="boot-1", thread_id="thread", turn_id="turn", request_id="request", attempt_id="attempt-1"),
        RuntimeIdentity(process_name="worker", incarnation_id="boot-1", thread_id="thread", turn_id="turn", request_id="request", attempt_id="attempt-2"),
        RuntimeIdentity(process_name="worker", incarnation_id="boot-2", thread_id="thread", turn_id="turn", request_id="request", attempt_id="attempt-3"),
    ]
    requests = [store.pin_request(f"request/{index}", manifest, identity=identity) for index, identity in enumerate(identities)]
    assert len({request.cid for request in requests}) == 3
    assert len(store.requests_for(manifest)) == 3
    assert {request.data["identity"]["attempt_id"] for request in requests} == {"attempt-1", "attempt-2", "attempt-3"}
    assert {request.data["identity"]["incarnation_id"] for request in requests} == {"boot-1", "boot-2"}
    unknown = RuntimeIdentity(process_name="worker")
    assert unknown.thread_id is unknown.turn_id is unknown.request_id is unknown.attempt_id is None
    uncorrelated = store.pin_request("request/unknown-native", manifest, identity=unknown)
    assert uncorrelated.data["identity"]["thread_id"] is None


def test_equal_manifest_content_can_participate_in_distinct_causal_occurrences(context):
    _, store = context
    manifest = store.manifest({"instructions/root": ingredient(store, "instruction")})
    first = store.record_event("occurrence/one", kind="activation_requested", manifest=manifest)
    second = store.record_event("occurrence/two", kind="activation_requested", manifest=manifest)
    assert first.cid != second.cid
    assert first.ref("manifest") == second.ref("manifest") == manifest.cid
    assert store.record_event("occurrence/one", kind="activation_requested", manifest=manifest).cid == first.cid
    assert {event.cid for event in store.events(manifest)} == {first.cid, second.cid}
    assert store.get_event("occurrence/one").cid == first.cid


def test_activation_request_is_not_adoption_and_correlation_does_not_repin(context):
    trace, store = context
    before = store.manifest({"skills/current": ingredient(store, "S7")})
    after = store.replace(before, "skills/current", ingredient(store, "S8"))
    request = store.pin_request("request/old", before, identity=RuntimeIdentity(attempt_id="a1"))
    revision = store.record_event("occurrence/revision", kind="revision", manifest=after, previous_manifest=before)
    activation = store.record_event("occurrence/activation", kind="activation_requested", manifest=after, parents=("occurrence/revision",))
    with pytest.raises(ValueError):
        store.record_event("occurrence/adoption-missing", kind="adoption_observed", manifest=after, boundary=Boundary.APP_SERVER)
    local_receipt = evidence(trace, store)
    with pytest.raises(ValueError):
        store.record_event("occurrence/adoption-local", kind="adoption_observed", manifest=after, boundary=Boundary.LOCAL, evidence=(local_receipt,))
    outbound_receipt = evidence(trace, store, "client_to_appserver")
    with pytest.raises(ValueError):
        store.record_event("occurrence/adoption-outbound", kind="adoption_observed", manifest=after, boundary=Boundary.APP_SERVER, evidence=(outbound_receipt,))
    response = evidence(trace, store, "appserver_to_client", message={
        "id": 9, "result": {"turn": {"id": "native-turn"}, "syntheticContextReceipt": {"manifest": after.cid}},
    })
    adoption = store.record_event("occurrence/adoption", kind="adoption_observed", manifest=after, boundary=Boundary.APP_SERVER, evidence=(response,), parents=("occurrence/activation",))
    correlation = store.record_event("occurrence/correlation", kind="correlation", manifest=before, request_name="request/old", identity=RuntimeIdentity(turn_id="native-turn", attempt_id="a1"), evidence=(response,), boundary=Boundary.APP_SERVER)

    assert len({revision.cid, activation.cid, adoption.cid, correlation.cid}) == 4
    assert store.get_request("request/old").cid == request.cid
    assert store.get_request("request/old").data["identity"]["turn_id"] is None
    assert store.get_request("request/old").ref("manifest") == before.cid
    assert store.inspect(after, "skills/current", boundary=Boundary.PROVIDER).unknown


def test_later_provider_observation_can_be_linked_without_rewriting_the_request_snapshot(context):
    trace, store = context
    content = store.put_content("user_prompt", {"text": "synthetic question"})
    projected = store.claim(content, state=KnowledgeState.PROJECTED, boundary=Boundary.APP_SERVER)
    before = store.manifest({"request/prompt": store.slot(projected)})
    request = store.pin_request("request/one", before, identity=RuntimeIdentity(attempt_id="a1"))
    receipt = evidence(trace, store, "provider_request", message={"input": "synthetic question"})
    observed = store.claim(content, state=KnowledgeState.OBSERVED, boundary=Boundary.PROVIDER, scope=RuntimeIdentity(attempt_id="a1"), evidence=(receipt,))
    enriched = store.replace(before, "request/prompt", store.slot(projected, observed))
    correlation = store.record_event(
        "occurrence/later-observation",
        kind="correlation",
        manifest=before,
        supplemental_manifest=enriched,
        request_name="request/one",
        identity=RuntimeIdentity(attempt_id="a1"),
        boundary=Boundary.PROVIDER,
        evidence=(receipt,),
        details={"interpretation": "later captured provider request"},
    )
    assert correlation.ref("manifest") == before.cid
    assert correlation.ref("supplemental_manifest") == enriched.cid
    assert store.get_request("request/one").cid == request.cid
    assert store.get_request("request/one").ref("manifest") == before.cid
    assert store.inspect(before, "request/prompt").unknown
    assert not store.inspect(enriched, "request/prompt").unknown
    with pytest.raises(ValueError):
        store.record_event("occurrence/wrong-primary", kind="correlation", manifest=enriched, request_name="request/one", boundary=Boundary.PROVIDER, evidence=(receipt,))
    with pytest.raises(ValueError):
        store.record_event("occurrence/wrong-kind", kind="activation_requested", manifest=before, supplemental_manifest=enriched)


def test_event_replay_rejects_changed_body_and_missing_causal_parent(context):
    _, store = context
    first = store.manifest({"instructions/root": ingredient(store, "old")})
    second = store.replace(first, "instructions/root", ingredient(store, "new"))
    event = store.record_event("occurrence/one", kind="revision", manifest=second, previous_manifest=first)
    with pytest.raises(ValueError):
        store.record_event("occurrence/one", kind="revision", manifest=first, previous_manifest=second)
    with pytest.raises((KeyError, ValueError)):
        store.record_event("occurrence/unfounded", kind="activation_requested", manifest=second, parents=("occurrence/missing",))
    with pytest.raises((KeyError, ValueError)):
        store.record_event("occurrence/unknown-request", kind="correlation", manifest=second, request_name="request/missing")
    assert store.get_event("occurrence/one").cid == event.cid


def test_savepoints_allow_trace_request_and_event_to_rollback_in_one_outer_transaction(context):
    trace, store = context
    manifest = store.manifest({"instructions/root": ingredient(store, "instruction")})
    count_before = object_count(trace)
    trace.db.execute("BEGIN")
    evidence(trace, store)
    store.pin_request("request/rollback", manifest)
    store.record_event("occurrence/rollback", kind="activation_requested", manifest=manifest)
    trace.db.execute("ROLLBACK")
    assert trace.records() == []
    assert object_count(trace) == count_before
    with pytest.raises(KeyError):
        store.get_request("request/rollback")
    with pytest.raises(KeyError):
        store.get_event("occurrence/rollback")
    assert store.pin_request("request/rollback", manifest).ref("manifest") == manifest.cid


def test_failed_repin_inside_outer_transaction_preserves_other_pending_writes(context):
    trace, store = context
    before = store.manifest({"instructions/root": ingredient(store, "old")})
    after = store.replace(before, "instructions/root", ingredient(store, "new"))
    store.pin_request("request/one", before)
    trace.db.execute("BEGIN")
    evidence(trace, store)
    with pytest.raises(ValueError):
        store.pin_request("request/one", after)
    store.record_event("occurrence/after-rejection", kind="activation_requested", manifest=after)
    trace.db.execute("COMMIT")
    assert len(trace.records()) == 1
    assert store.get_request("request/one").ref("manifest") == before.cid
    assert store.get_event("occurrence/after-rejection").ref("manifest") == after.cid


def test_concurrent_request_replay_has_one_persisted_snapshot(context):
    _, store = context
    manifest = store.manifest({"instructions/root": ingredient(store, "instruction")})
    gate = Barrier(4)

    def pin(_):
        gate.wait()
        return store.pin_request("request/concurrent", manifest).cid

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(pin, range(4)))
    assert len(set(results)) == 1
    assert len(store.requests_for(manifest)) == 1


def test_two_sqlite_connections_cannot_repin_the_same_request_to_different_manifests(tmp_path: Path):
    path = tmp_path / "synthetic-race.db"
    first_trace = TraceStore(path)
    second_trace = TraceStore(path)
    first = ContextManifestStore(first_trace)
    second = ContextManifestStore(second_trace)
    before = first.manifest({"instructions/root": ingredient(first, "old")})
    after = first.replace(before, "instructions/root", ingredient(first, "new"))
    gate = Barrier(2)

    def pin(store, manifest):
        gate.wait()
        try:
            return store.pin_request("request/race", manifest).ref("manifest")
        except ValueError:
            return "rejected"

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(pin, first, before), pool.submit(pin, second, after)]
            results = [future.result() for future in futures]
        assert results.count("rejected") == 1
        winner = next(result for result in results if result != "rejected")
        assert first.get_request("request/race").ref("manifest") == winner
        assert second.get_request("request/race").ref("manifest") == winner
        assert len(first.requests_for(before)) + len(first.requests_for(after)) == 1
    finally:
        first_trace.close()
        second_trace.close()
