"""Independent direct-use acceptance over authored public evidence only."""
from contextlib import closing
from copy import deepcopy
import hashlib
import io
import json

import pytest

from eidos.api import EidosAPI
from eidos.codex import AppServerClient
from eidos.trace import TraceStore


SCOPE = "direct-frozen-artifact-inputs/v1"


def call(api, path, **query):
    class Handler:
        headers = {}
        rfile = io.BytesIO()
    return api.dispatch(Handler(), "GET", path, {key: [str(value)] for key, value in query.items()})


def uses_path(pair):
    return f"/api/investigations/{pair['investigationId']}/artifacts/{pair['artifactId']}/uses"


def detail(api, pair, row, **changes):
    return call(api, uses_path(pair) + f"/{row['investigationId']}/contexts/{row['contextId']}",
                expectedVersion=changes.pop("expectedVersion", row["ownerVersion"]), **changes)


def raw_record(trace, thread, text):
    return trace.append(source="authored-use-acceptance", direction="internal", message={
        "method": "$history/item", "params": {"threadId": thread, "turnId": "turn",
            "item": {"id": "answer", "type": "agentMessage", "text": text,
                     "future": {"mustSurvive": "KEEP_原文", "data": [0, None, False]}}}})


def selected(*records):
    return [{"threadId": r.thread_id, "startSeq": r.seq, "endSeq": r.seq} for r in records]


def create(api, name, **inputs):
    return api.investigations.create({"requestId": name, "title": name,
        "question": f"Exact saved question for {name}?", **inputs})


def finding(api, work, text, request):
    return api.investigations.create_finding(work["id"], {"requestId": request,
        "contextId": work["currentContextId"], "text": text})[0]


def fixture(api):
    trace = api.store
    r0 = raw_record(trace, "source-public", "An uncertain response is not permission to repeat an effect.")
    r1 = raw_record(trace, "other-public", "Copied records describe history, not current execution authority.")
    a = create(api, "A source", selections=selected(r0))
    f0 = finding(api, a, f"Keep uncertain attempts distinct [evidence:{r0.seq}].", "F0")
    f1 = finding(api, a, "A later hypothesis is a separate finding.", "F1")
    pair = {"investigationId": a["id"], "artifactId": f0["id"]}
    inclusion = {**pair, "rationale": "Retain the exact earlier conclusion and its limits."}
    b = create(api, "B direct", selections=selected(r1), artifactInputs=[inclusion])
    b0 = deepcopy(b["contexts"][0])
    bf = finding(api, b, f"Compare this supplied proposal [artifact:{f0['id']}].", "BF")
    b = api.investigations.revise(b["id"], {"requestId": "B later", "parentContextId": b0["id"],
        "question": "The current question no longer includes F0.", "selections": selected(r0)})
    c = create(api, "C transitive", artifactInputs=[{"investigationId": b["id"],
        "artifactId": bf["id"], "rationale": "Directly supplied BF, not its inputs."}])
    d = create(api, "D copied", inputSource={"investigationId": b["id"], "contextId": b0["id"]})
    e = create(api, "E same records", selections=selected(r0, r1))
    f = create(api, "F textual mention", selections=selected(r0))
    finding(api, f, f"Unsupported mention [artifact:{f0['id']}] is not supplied membership.", "FF")
    return {"a": a, "b": b, "b0": b0, "c": c, "d": d, "e": e, "f": f,
            "f0": f0, "f1": f1, "pair": pair, "r0": r0, "r1": r1}


def owner_rows(trace):
    return [tuple(row) for row in trace.db.execute("SELECT id,state_json FROM investigations ORDER BY id")]


def delete_owner(trace, identifier):
    """Deliberate trusted-store source unavailability, not a product delete route."""
    with trace._lock:
        trace.db.execute("BEGIN IMMEDIATE")
        trace.db.execute("DELETE FROM investigation_requests WHERE investigation_id=?", (identifier,))
        trace.db.execute("DELETE FROM investigation_finding_requests WHERE investigation_id=?", (identifier,))
        trace.db.execute("DELETE FROM investigations WHERE id=?", (identifier,))
        trace.db.execute("COMMIT")


@pytest.fixture(autouse=True)
def forbid_native(monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail("result-use inspection attempted native startup")
    monkeypatch.setattr(AppServerClient, "start", forbidden)


def test_exact_direct_uses_survive_source_and_raw_deletion_and_reopen(tmp_path):
    path = tmp_path / "uses.db"
    with closing(TraceStore(path)) as trace, closing(EidosAPI(trace)) as api:
        f = fixture(api)
        before = owner_rows(trace)
        status, page = call(api, uses_path(f["pair"]))
        assert status == 200, page
        assert page["scope"] == SCOPE and page["source"] == f["pair"] and page["unchanged"] is False
        assert {(r["investigationId"], r["contextId"], r["isCurrent"]) for r in page["uses"]} == {
            (f["b"]["id"], f["b0"]["id"], False), (f["d"]["id"], f["d"]["currentContextId"], True)}
        assert all(r["matchingInputCount"] == 1 for r in page["uses"])
        assert page["nextCursor"] is None
        assert not any(key in json.dumps(page) for key in ("rawText", "projectedPrompt", "mustSurvive", "authorship"))
        for row in page["uses"]:
            status, exact = detail(api, f["pair"], row)
            assert status == 200, exact
            context = f["b0"] if row["investigationId"] == f["b"]["id"] else f["d"]["contexts"][0]
            assert exact["context"] == context and exact["matchingInputIndexes"] == [0]
            assert exact["ownerVersion"] == row["ownerVersion"] and exact["isCurrent"] == row["isCurrent"]
            assert exact["context"]["artifactInputs"][0]["artifact"] == f["f0"]
        assert owner_rows(trace) == before
        # Source deletion must not turn D's retained F0 into F1, or erase B0.
        delete_owner(trace, f["a"]["id"])
        trace.db.execute("DELETE FROM trace_records")
        status, same = call(api, uses_path(f["pair"]), knownVersion=page["version"])
        assert status == 200 and same["unchanged"] is True
        assert "uses" not in same and "nextCursor" not in same
        for row in page["uses"]:
            status, packet = detail(api, f["pair"], row)
            assert status == 200, packet
            assert packet["context"]["artifactInputs"][0]["artifact"] == f["f0"]
            assert packet["context"]["records"][0]["rawText"] == f["r1"].raw_text
        canonical = owner_rows(trace)
        api.investigation_reads.rebuild()
        assert owner_rows(trace) == canonical
        assert call(api, uses_path(f["pair"])) == (200, page)
    with closing(TraceStore(path)) as trace, closing(EidosAPI(trace)) as api:
        assert owner_rows(trace) == canonical and trace.records() == []
        assert call(api, uses_path(f["pair"])) == (200, page)
        delete_owner(trace, f["d"]["id"])
        status, after = call(api, uses_path(f["pair"]))
        assert status == 200 and [r["contextId"] for r in after["uses"]] == [f["b0"]["id"]]
        removed = next(r for r in page["uses"] if r["investigationId"] == f["d"]["id"])
        assert detail(api, f["pair"], removed)[0] == 404


def test_independent_writer_invalidates_page_and_detail_without_current_substitution(tmp_path):
    path = tmp_path / "writer.db"
    with closing(TraceStore(path)) as trace, closing(EidosAPI(trace)) as api, \
            closing(TraceStore(path)) as other_trace, closing(EidosAPI(other_trace)) as other:
        f = fixture(api)
        status, first = call(api, uses_path(f["pair"]), limit=1)
        assert status == 200 and len(first["uses"]) == 1 and first["nextCursor"]
        status, second = call(api, uses_path(f["pair"]), limit=1, cursor=first["nextCursor"])
        assert status == 200 and len(second["uses"]) == 1
        old_rows = first["uses"] + second["uses"]
        assert len({(r["investigationId"], r["contextId"]) for r in old_rows}) == 2
        # An unrelated owner update is deliberately not a global invalidation.
        other.investigations.create_finding(f["e"]["id"], {"requestId": "unrelated-finding",
            "contextId": f["e"]["currentContextId"], "text": "Unrelated owner change."})
        assert call(api, uses_path(f["pair"]), limit=1, cursor=first["nextCursor"]) == (200, second)
        old_d = next(row for row in old_rows if row["investigationId"] == f["d"]["id"])
        d1 = other.investigations.revise(f["d"]["id"], {"requestId": "D revised",
            "parentContextId": f["d"]["currentContextId"], "question": "Now retain only the raw evidence.",
            "selections": selected(f["r0"])})
        assert call(api, uses_path(f["pair"]), limit=1, cursor=first["nextCursor"])[0] == 409
        assert detail(api, f["pair"], old_d)[0] == 409
        status, refreshed = call(api, uses_path(f["pair"]), limit=1, knownVersion=first["version"])
        assert status == 200 and refreshed["unchanged"] is False
        status, all_uses = call(api, uses_path(f["pair"]))
        assert status == 200
        new_d = next(row for row in all_uses["uses"] if row["investigationId"] == f["d"]["id"])
        assert new_d["isCurrent"] is False and new_d["contextId"] != d1["currentContextId"]
        status, historical = detail(api, f["pair"], new_d)
        assert status == 200 and historical["context"] == f["d"]["contexts"][0]
        wrong_context = {**new_d, "contextId": d1["currentContextId"]}
        assert detail(api, f["pair"], wrong_context)[0] == 409
        wrong_source = {**f["pair"], "artifactId": f["f1"]["id"]}
        assert detail(api, wrong_source, new_d)[0] == 409
        assert call(api, uses_path(wrong_source), limit=1, cursor=refreshed["nextCursor"])[0] == 400
        assert call(api, uses_path(f["pair"]), limit=2, cursor=refreshed["nextCursor"])[0] == 400


@pytest.mark.parametrize("damage", ["ambiguous-context", "malformed-snapshot", "authored-prose", "authored-citations"])
def test_trusted_store_damage_refuses_matching_detail_instead_of_selecting_first(tmp_path, damage):
    with closing(TraceStore(tmp_path / "damage.db")) as trace, closing(EidosAPI(trace)) as api:
        f = fixture(api)
        status, page = call(api, uses_path(f["pair"]))
        assert status == 200, page
        row = next(r for r in page["uses"] if r["investigationId"] == f["d"]["id"])
        poisoned = api.investigations.get(f["d"]["id"])
        if damage == "ambiguous-context":
            duplicate = deepcopy(poisoned["contexts"][0])
            duplicate["question"] = "Same identifier, conflicting frozen meaning."
            poisoned["contexts"].append(duplicate)
        elif damage == "malformed-snapshot":
            poisoned["contexts"][0]["artifactInputs"][0]["artifact"] = {"id": "different-artifact", "text": "Do not substitute."}
        elif damage == "authored-prose":
            poisoned["contexts"][0]["artifactInputs"][0]["artifact"]["text"] = "Changed prose under unchanged F0 identity."
        else:
            poisoned["contexts"][0]["artifactInputs"][0]["artifact"]["citations"] = [f["r1"].seq]
        # Explicit corruption by trusted host, outside all supported write APIs.
        api.investigations._save(poisoned)
        raw = trace.db.execute("SELECT state_json FROM investigations WHERE id=?", (poisoned["id"],)).fetchone()[0]
        version = "iv1_" + hashlib.sha256(raw.encode()).hexdigest()
        assert detail(api, f["pair"], row, expectedVersion=version)[0] == 409
        status, result = call(api, uses_path(f["pair"]))
        assert status == 409, result
        assert trace.db.execute("SELECT state_json FROM investigations WHERE id=?", (poisoned["id"],)).fetchone()[0] == raw


@pytest.mark.parametrize("preview_character", ["🗺", "\x00"])
def test_utf8_envelope_reduces_page_without_skipping_saved_uses(tmp_path, preview_character):
    with closing(TraceStore(tmp_path / "utf8.db")) as trace, closing(EidosAPI(trace)) as api:
        f = fixture(api)
        expected = {(f["b"]["id"], f["b0"]["id"]), (f["d"]["id"], f["d"]["currentContextId"])}
        for index in range(40):
            # Deliberate trusted import of long Unicode coordinates/metadata.
            # This tests a read envelope, not admission of a new native identity.
            work = deepcopy(f["d"])
            work["id"] = "🧭" * 180 + f"{index:03}"
            work["title"] = preview_character * 300
            context = work["contexts"][0]
            context["id"] = "📚" * 180 + f"{index:03}"
            context["question"] = preview_character * 300
            context["artifactInputs"][0]["rationale"] = preview_character * 300
            work["currentContextId"] = context["id"]
            work["createdAtMs"] += 100 + index
            trace.db.execute("INSERT INTO investigations VALUES(?,?,?)",
                (work["id"], work["createdAtMs"], json.dumps(work, ensure_ascii=False, sort_keys=True, separators=(",", ":"))))
            expected.add((work["id"], context["id"]))
        canonical = owner_rows(trace)
        cursor, seen, pages = None, [], 0
        while True:
            query = {"limit": 40, **({"cursor": cursor} if cursor else {})}
            status, page = call(api, uses_path(f["pair"]), **query)
            assert status == 200, page
            encoded = json.dumps(page, ensure_ascii=False, separators=(",", ":")).encode()
            assert len(encoded) <= 128 * 1024
            assert 0 < len(page["uses"]) <= 40
            if pages == 0:
                assert len(page["uses"]) < 40 and page["nextCursor"]
            for row in page["uses"]:
                assert all(len(row[key]) <= 240 for key in ("investigationTitle", "questionExcerpt", "rationaleExcerpt"))
                seen.append((row["investigationId"], row["contextId"]))
            pages += 1
            assert pages <= 42  # A zero-progress cursor may never loop.
            cursor = page["nextCursor"]
            if cursor is None:
                break
        assert set(seen) == expected and len(seen) == len(expected)
        assert owner_rows(trace) == canonical


def test_hot_use_reads_do_not_parse_canonical_owners(tmp_path, monkeypatch):
    import eidos.investigation_reads as read_module
    with closing(TraceStore(tmp_path / "hot.db")) as trace, closing(EidosAPI(trace)) as api:
        f = fixture(api)
        status, page = call(api, uses_path(f["pair"]))
        assert status == 200, page
        canonical = {row[1] for row in owner_rows(trace)}
        actual_loads = read_module.json.loads
        def forbid_owner_load(value, *args, **kwargs):
            if isinstance(value, str) and value in canonical:
                pytest.fail("warm direct-use read parsed a canonical owner")
            return actual_loads(value, *args, **kwargs)
        monkeypatch.setattr(read_module.json, "loads", forbid_owner_load)
        assert call(api, uses_path(f["pair"])) == (200, page)
        status, unchanged = call(api, uses_path(f["pair"]), knownVersion=page["version"])
        assert status == 200 and unchanged["unchanged"] is True
