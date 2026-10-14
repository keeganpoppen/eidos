"""Direct saved input membership, using authored public data and no native calls."""
import base64
from copy import deepcopy
import json

import pytest

from eidos.api import EidosAPI
from eidos.investigation import InvestigationStore, _json
from eidos.investigation_reads import InvestigationReads, MAX_USES_BYTES, USES_SCOPE
from eidos.trace import TraceStore


def reference(owner, finding):
    return {"investigationId": owner["id"], "artifactId": finding["id"], "rationale": "Exact supplied claim"}


def route(owner, finding):
    return f"/api/investigations/{owner['id']}/artifacts/{finding['id']}/uses"


def get(api, path, **query):
    return api.dispatch(None, "GET", path, {key: [str(value)] for key, value in query.items()})


def detail(api, path, row):
    return get(api, f"{path}/{row['investigationId']}/contexts/{row['contextId']}", expectedVersion=row["ownerVersion"])


@pytest.fixture
def setup(tmp_path):
    trace = TraceStore(tmp_path / "uses.db")
    api = EidosAPI(trace)
    store = api.investigations
    trace.append(source="authored-public-fixture", direction="internal", message={"method": "$history/item", "params": {
        "threadId": "source", "turnId": "turn", "item": {"id": "source", "type": "agentMessage", "text": "Public original", "unknown": True}}})
    selections = [{"threadId": "source", "startSeq": 1, "endSeq": 1, "rationale": "Original source"}]
    a = store.create({"requestId": "A", "title": "A", "question": "Original question", "selections": selections})
    f0, _ = store.create_finding(a["id"], {"requestId": "F0", "contextId": a["currentContextId"], "text": "First conclusion [evidence:1]"})
    b = store.create({"requestId": "B", "title": "B", "question": "Historical consumer question", "artifactInputs": [reference(a, f0)]})
    b0 = b["contexts"][0]
    bf, _ = store.create_finding(b["id"], {"requestId": "BF", "contextId": b0["id"], "text": f"Derived conclusion [artifact:{f0['id']}]"})
    c = store.create({"requestId": "C", "title": "C", "question": "Transitive consumer", "artifactInputs": [reference(b, bf)]})
    d = store.create({"requestId": "D", "title": "D", "question": "Copied inputs", "inputSource": {"investigationId": b["id"], "contextId": b0["id"]}})
    store.create({"requestId": "E", "title": "E", "question": "Raw support only", "inputSource": {"investigationId": a["id"], "contextId": a["currentContextId"]}})
    store.create({"requestId": "F", "title": "F", "question": "Merely mentions " + f0["id"], "selections": selections})
    b = store.revise(b["id"], {"requestId": "B1", "parentContextId": b0["id"], "question": "Current without old result", "selections": selections})
    try:
        yield trace, api, a, f0, b, b0, c, d
    finally:
        api.close()
        trace.close()


def test_direct_frozen_uses_include_old_context_and_copied_inputs_only(setup):
    trace, api, a, f0, b, b0, c, d = setup
    before = [tuple(r) for r in trace.db.execute("SELECT * FROM investigations ORDER BY id")]
    status, page = get(api, route(a, f0))
    assert status == 200 and page["scope"] == USES_SCOPE and page["source"] == {"investigationId": a["id"], "artifactId": f0["id"]}
    assert {row["investigationId"] for row in page["uses"]} == {b["id"], d["id"]}
    rows = {row["investigationId"]: row for row in page["uses"]}
    assert rows[b["id"]]["contextId"] == b0["id"] and not rows[b["id"]]["isCurrent"]
    assert rows[d["id"]]["isCurrent"] and rows[d["id"]]["matchingInputCount"] == 1
    status, saved = detail(api, route(a, f0), rows[b["id"]])
    assert status == 200 and saved["context"] == b0 and saved["matchingInputIndexes"] == [0]
    assert not saved["isCurrent"] and saved["context"]["id"] != b["currentContextId"]
    assert "projectedPrompt" not in _json(page) and "rawText" not in _json(page) and f0["text"] not in _json(page)
    assert [tuple(r) for r in trace.db.execute("SELECT * FROM investigations ORDER BY id")] == before
    assert get(api, route(a, f0), knownVersion=page["version"])[1] == {
        "scope": USES_SCOPE, "source": page["source"], "version": page["version"], "unchanged": True}


def test_original_owner_and_raw_deletion_do_not_remove_consumer_facts(setup):
    trace, api, a, f0, b, b0, _, _ = setup
    page = get(api, route(a, f0))[1]
    trace.db.execute("DELETE FROM investigation_requests WHERE investigation_id=?", (a["id"],))
    trace.db.execute("DELETE FROM investigations WHERE id=?", (a["id"],))
    trace.db.execute("DELETE FROM trace_records")
    after = get(api, route(a, f0))[1]
    assert after == page
    row = next(row for row in page["uses"] if row["investigationId"] == b["id"])
    assert detail(api, route(a, f0), row)[1]["context"] == b0
    trace.db.execute("DELETE FROM investigation_requests WHERE investigation_id=?", (b["id"],))
    trace.db.execute("DELETE FROM investigations WHERE id=?", (b["id"],))
    assert len(get(api, route(a, f0))[1]["uses"]) == 1
    assert detail(api, route(a, f0), row)[0] == 404


def test_independent_writer_stales_cursor_and_detail_but_unrelated_owner_does_not(setup):
    trace, api, a, f0, b, _, _, d = setup
    path = route(a, f0)
    first = get(api, path, limit=1)[1]
    assert first["nextCursor"]
    # An additional value on the upstream owner changes no consumer membership.
    api.investigations.create_finding(a["id"], {"requestId": "F1", "contextId": a["currentContextId"], "text": "Another conclusion"})
    assert get(api, path, limit=1, cursor=first["nextCursor"])[0] == 200
    assert get(api, path, limit=1, knownVersion=first["version"])[1]["unchanged"]
    writer = TraceStore(trace.path)
    try:
        other = InvestigationStore(writer)
        work = other.get(d["id"])
        other.revise(d["id"], {"requestId": "D1", "parentContextId": work["currentContextId"], "question": "Another copied-input question",
            "artifactInputs": [reference(a, f0)]})
    finally:
        writer.close()
    assert get(api, path, limit=1, cursor=first["nextCursor"])[0] == 409
    old = next(row for row in get(api, path)[1]["uses"] if row["investigationId"] == d["id"])
    old["ownerVersion"] = "iv1_" + "0" * 64
    assert detail(api, path, old)[0] == 409
    assert len(get(api, path)[1]["uses"]) == 3


def test_migration_and_rebuild_preserve_canonical_bytes_and_versions(setup):
    trace, api, a, f0, *_ = setup
    page = get(api, route(a, f0))[1]
    before = [tuple(r) for r in trace.db.execute("SELECT * FROM investigations ORDER BY id")]
    # Simulate an old read index before this projection existed.
    trace.db.execute("DROP TRIGGER investigation_read_result_uses_delete")
    trace.db.execute("DROP TABLE investigation_read_result_uses")
    trace.db.execute("DROP TABLE investigation_read_result_use_owners")
    reads = InvestigationReads(api.investigations)
    assert reads.uses(a["id"], f0["id"], {}) == page
    assert trace.db.execute("SELECT count(*) FROM investigation_read_result_use_owners").fetchone()[0] == 6
    reads.rebuild()
    assert reads.uses(a["id"], f0["id"], {}) == page
    assert [tuple(r) for r in trace.db.execute("SELECT * FROM investigations ORDER BY id")] == before


def test_warm_list_and_conditional_reads_parse_no_whole_owner(setup, monkeypatch):
    _, api, a, f0, *_ = setup
    reads = api.investigation_reads
    page = reads.uses(a["id"], f0["id"], {})
    loads = json.loads
    def small(value, *args, **kwargs):
        assert len(value) < 1600, "warm uses parsed canonical history"
        return loads(value, *args, **kwargs)
    monkeypatch.setattr("eidos.investigation_reads.json.loads", small)
    assert reads.uses(a["id"], f0["id"], {"knownVersion": [page["version"]]})["unchanged"]


@pytest.mark.parametrize("query", [
    {"limit": ["0"]}, {"limit": ["41"]}, {"limit": ["no"]}, {"limit": ["1", "2"]},
    {"q": ["unsupported"]}, {"cursor": ["bad"]}, {"knownVersion": [""]},
])
def test_bad_list_parameters_are_controlled(setup, query):
    _, api, a, f0, *_ = setup
    assert api.dispatch(None, "GET", route(a, f0), query)[0] == 400


def test_cursor_binds_pair_limit_and_relation_and_conditionals_bind_page(setup):
    _, api, a, f0, *_ = setup
    path = route(a, f0)
    first = get(api, path, limit=1)[1]
    assert get(api, path, limit=2, cursor=first["nextCursor"])[0] == 400
    assert get(api, path.replace(f0["id"], "another"), limit=1, cursor=first["nextCursor"])[0] == 400
    second = get(api, path, limit=1, cursor=first["nextCursor"], knownVersion=first["version"])[1]
    assert not second["unchanged"] and second["version"] != first["version"]
    cursor = json.loads(base64.urlsafe_b64decode(first["nextCursor"] + "=" * (-len(first["nextCursor"]) % 4)))
    cursor["relationVersion"] = "ur1_" + "z" * 64
    changed = base64.urlsafe_b64encode(_json(cursor).encode()).decode().rstrip("=")
    assert get(api, path, limit=1, cursor=changed)[0] == 400


def test_detail_requires_exact_membership_and_version_without_current_fallback(setup):
    _, api, a, f0, b, b0, *_ = setup
    row = next(row for row in get(api, route(a, f0))[1]["uses"] if row["investigationId"] == b["id"])
    path = f"{route(a, f0)}/{b['id']}/contexts/{b0['id']}"
    assert get(api, path)[0] == 400
    assert api.dispatch(None, "GET", path, {"expectedVersion": [row["ownerVersion"], row["ownerVersion"]]})[0] == 400
    assert get(api, path + "missing", expectedVersion=row["ownerVersion"])[0] == 404
    assert get(api, path.replace(b0["id"], b["currentContextId"]), expectedVersion=row["ownerVersion"])[0] == 409
    assert get(api, path.replace(f0["id"], "another"), expectedVersion=row["ownerVersion"])[0] == 409


@pytest.mark.parametrize("mutate", [
    lambda w: w["contexts"][0]["artifactInputs"][0].update(artifact={"id": "wrong"}),
    lambda w: w["contexts"][0]["artifactInputs"][0].update(sourceContextId="wrong"),
    lambda w: w["contexts"][0]["artifactInputs"][0].update(rationale=[]),
    lambda w: w["contexts"][0]["artifactInputs"][0]["artifact"].update(text="Modified under the old finding ID"),
    lambda w: w["contexts"][0]["artifactInputs"][0]["artifact"].update(citations=[]),
    lambda w: w["contexts"][0]["artifactInputs"][0].update(sourceAdoption={
        "artifactId": w["contexts"][0]["artifactInputs"][0]["artifactId"], "decision": [], "note": ""}),
    lambda w: w["contexts"].append({**w["contexts"][0], "question": "Conflicting same identity"}),
])
def test_trusted_malformed_snapshot_injection_refuses_instead_of_hiding_use(setup, mutate):
    trace, api, a, f0, _, _, _, d = setup
    work = api.investigations.get(d["id"])
    mutate(work)
    trace.db.execute("UPDATE investigations SET state_json=? WHERE id=?", (_json(work), d["id"]))
    assert api.investigation_reads.catalog({"q": ["not-present"]}, artifacts=True)["artifacts"] == []
    assert get(api, route(a, f0))[0] == 409


def test_duplicate_matching_inputs_are_one_context_row_with_exact_indexes(setup):
    trace, api, a, f0, _, _, _, d = setup
    work = api.investigations.get(d["id"])
    work["contexts"][0]["artifactInputs"].append(deepcopy(work["contexts"][0]["artifactInputs"][0]))
    work["contexts"][0]["artifactInputs"][1]["rationale"] = "Second historical inclusion"
    trace.db.execute("UPDATE investigations SET state_json=? WHERE id=?", (_json(work), d["id"]))
    row = next(row for row in get(api, route(a, f0))[1]["uses"] if row["investigationId"] == d["id"])
    assert row["matchingInputCount"] == 2
    assert detail(api, route(a, f0), row)[1]["matchingInputIndexes"] == [0, 1]


def test_malformed_uses_refuse_without_changing_legacy_catalog_and_repair_clears_error(setup):
    trace, api, a, f0, _, _, _, d = setup
    before = api.investigations.get(d["id"])
    malformed = deepcopy(before)
    malformed["contexts"][0]["artifactInputs"] = [{"ignoredFixture": "INPUT_ONLY_CANARY"}]
    trace.db.execute("UPDATE investigations SET state_json=? WHERE id=?", (_json(malformed), d["id"]))
    canonical = [tuple(row) for row in trace.db.execute("SELECT * FROM investigations ORDER BY id")]
    assert api.investigation_reads.catalog({"q": ["INPUT_ONLY_CANARY"]}, artifacts=True)["artifacts"] == []
    assert get(api, route(a, f0))[0] == 409
    api.investigation_reads.rebuild()
    assert get(api, route(a, f0))[0] == 409
    assert [tuple(row) for row in trace.db.execute("SELECT * FROM investigations ORDER BY id")] == canonical
    writer = TraceStore(trace.path)
    try:
        writer.db.execute("UPDATE investigations SET state_json=? WHERE id=?", (_json(before), d["id"]))
    finally:
        writer.close()
    assert get(api, route(a, f0))[0] == 200
    assert trace.db.execute("SELECT error FROM investigation_read_result_use_owners WHERE owner_id=?", (d["id"],)).fetchone()[0] is None


@pytest.mark.parametrize("character", ["🧭", "\x00"])
def test_full_utf8_envelope_reduces_rows_with_correct_cursor(setup, character):
    _, api, a, f0, *_ = setup
    for index in range(45):
        api.investigations.create({"requestId": f"large-{index}", "title": character * 200,
            "question": character * 300, "artifactInputs": [{**reference(a, f0), "rationale": character * 300}]})
    path = route(a, f0)
    seen = set()
    cursor = None
    pages = 0
    first_count = None
    while True:
        status, page = get(api, path, limit=40, **({"cursor": cursor} if cursor else {}))
        assert status == 200 and len(_json(page).encode()) <= MAX_USES_BYTES
        assert 1 <= len(page["uses"]) <= 40
        if first_count is None:
            first_count = len(page["uses"])
        for row in page["uses"]:
            key = (row["investigationId"], row["contextId"])
            assert key not in seen
            seen.add(key)
            for field in ("investigationTitle", "questionExcerpt", "rationaleExcerpt"):
                assert len(row[field]) <= 240
        pages += 1
        if not page["nextCursor"]:
            break
        cursor = page["nextCursor"]
    assert len(seen) == 47 and pages >= 2
    if character == "\x00":
        assert first_count < 40  # Serialized escape expansion actually reduces the page.


def test_overlong_imported_context_identity_refuses_unfollowable_cursor(setup):
    trace, api, a, f0, _, _, _, d = setup
    work = api.investigations.get(d["id"])
    work["contexts"][0]["id"] = "x" * (MAX_USES_BYTES + 1)
    trace.db.execute("UPDATE investigations SET state_json=? WHERE id=?", (_json(work), d["id"]))
    assert get(api, route(a, f0), limit=40)[0] == 409


def test_bounded_source_identity_and_defensive_unfit_envelope(setup, monkeypatch):
    _, api, a, f0, *_ = setup
    assert get(api, route(a, f0).replace(a["id"], "x" * 201))[0] == 400
    # The defensive branch remains terminating even if a later deployment lowers its envelope budget.
    monkeypatch.setattr("eidos.investigation_reads.MAX_USES_BYTES", 300)
    assert get(api, route(a, f0))[0] == 413
