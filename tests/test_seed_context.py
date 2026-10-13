"""Keep the repository's continuation context navigable, not its prose frozen.

These tests validate packaging/discoverability only. They are not evidence that
architectural claims are true, V1 is delivered, or a host loaded the skills.
"""

from __future__ import annotations

import json
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "seed_manifest.json"


def seed() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def context_paths(manifest: dict) -> list[str]:
    return [
        *manifest["root_documents"],
        *manifest["canonical_documents"],
        *manifest["operating_documents"],
        *manifest["scoped_guides"],
        *(item["path"] for item in manifest["skills"]),
    ]


def test_seed_manifest_and_required_context_exist():
    manifest = seed()
    assert manifest["schema_version"] == 1
    assert re.fullmatch(r"[a-f0-9]{40}", manifest["implementation_base"])
    paths = context_paths(manifest)
    assert len(paths) == len(set(paths)), "duplicate canonical context paths"
    assert manifest["entrypoint"] in paths
    assert set(manifest["reading_order"]) <= set(paths)
    for relative in [*paths, manifest["implementation_snapshot"]]:
        path = (ROOT / relative).resolve()
        assert path.is_relative_to(ROOT), relative
        assert path.is_file(), relative
        assert path.read_text(encoding="utf-8").strip(), relative


def test_seed_markdown_links_resolve_locally():
    problems: list[str] = []
    for relative in context_paths(seed()):
        source = ROOT / relative
        text = source.read_text(encoding="utf-8")
        # Examples inside fenced code are not navigation links.
        text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
        for target in re.findall(r"\[[^\]]*\]\(([^)]+)\)", text):
            target = target.strip()
            if urlsplit(target).scheme or target.startswith("#"):
                continue
            local = unquote(target.split("#", 1)[0].split("?", 1)[0])
            if not local:
                continue
            destination = (source.parent / local).resolve()
            if not destination.is_relative_to(ROOT) or not destination.exists():
                problems.append(f"{relative}: {target}")
    assert not problems, "broken seed navigation:\n" + "\n".join(problems)


def test_repository_skills_have_discoverable_metadata():
    names: set[str] = set()
    for item in seed()["skills"]:
        path = ROOT / item["path"]
        text = path.read_text(encoding="utf-8")
        assert text.startswith("---\n"), item["path"]
        parts = text.split("---", 2)
        assert len(parts) == 3, item["path"]
        metadata = parts[1]
        match = re.search(r"(?m)^name:\s*([a-z0-9-]+)\s*$", metadata)
        assert match is not None, item["path"]
        name = match.group(1)
        assert name == item["name"] == path.parent.name
        assert name not in names
        names.add(name)
        assert re.search(r"(?m)^description:\s*\S.+$", metadata)
        assert parts[2].strip(), item["path"]


def test_entry_instructions_remain_small_and_routed():
    # Project choice: leave substantial room below host instruction budgets.
    assert (ROOT / "AGENTS.md").stat().st_size <= 8192
    assert (ROOT / "START_HERE.md").stat().st_size <= 8192
    start = (ROOT / "START_HERE.md").read_text(encoding="utf-8")
    for document in seed()["canonical_documents"]:
        assert document in start, f"canonical spec is not routed: {document}"


def test_release_and_decision_ids_remain_addressable():
    manifest = seed()
    v1 = (ROOT / "docs/roadmap/V1.md").read_text(encoding="utf-8")
    work = (ROOT / "docs/roadmap/WORKSTREAMS.md").read_text(encoding="utf-8")
    decisions = (ROOT / "docs/roadmap/DECISIONS.md").read_text(encoding="utf-8")
    for identifier in manifest["acceptance_ids"]:
        assert re.search(rf"\|\s*{re.escape(identifier)}\s*\|", v1), identifier
    for identifier in manifest["workstream_ids"]:
        assert re.search(rf"(?m)^## {re.escape(identifier)}\b", work), identifier
    for identifier in manifest["decision_ids"]:
        assert re.search(rf"(?m)^### {re.escape(identifier)}\b", decisions), identifier
