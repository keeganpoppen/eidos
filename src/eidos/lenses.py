from __future__ import annotations

"""Generic lenses over addressable Eidos Values.

The key operation is schema-agnostic: find permanent Names embedded anywhere
inside an Eidos Value, then walk those named Values to a chosen depth. This is
the smallest executable form of progressively expanding an observer's
addressable semantic context.
"""

from dataclasses import dataclass
from typing import Any, Callable, Iterable

from .core import Name, RecordValue


Resolver = Callable[[str], Any]


def referenced_names(value: Any) -> tuple[Name, ...]:
    """Return every Name structurally embedded in an Eidos Value."""

    found: list[Name] = []
    seen: set[str] = set()

    def visit(item: Any) -> None:
        if isinstance(item, Name):
            if item.value not in seen:
                seen.add(item.value)
                found.append(item)
            return
        if isinstance(item, RecordValue):
            for _, child in item.fields:
                visit(child)
            return
        if isinstance(item, dict):
            for child in item.values():
                visit(child)
            return
        if isinstance(item, (tuple, list)):
            for child in item:
                visit(child)

    visit(value)
    return tuple(found)


@dataclass(frozen=True)
class SemanticNode:
    name: Name
    value: Any
    depth: int
    references: tuple[Name, ...]


@dataclass(frozen=True)
class SemanticNeighborhood:
    roots: tuple[Name, ...]
    nodes: tuple[SemanticNode, ...]

    def by_name(self) -> dict[str, SemanticNode]:
        return {node.name.value: node for node in self.nodes}


def walk_named_values(
    roots: Iterable[Name | str],
    *,
    resolve: Resolver,
    depth: int,
) -> SemanticNeighborhood:
    """Expand an addressable semantic neighborhood to a bounded depth.

    resolve(name) should return the Value bound to that permanent Name.
    Unbound references are retained as edges but are not fatal: authority Names,
    external entities, or as-yet-unmaterialized semantic objects may be visible
    without themselves denoting a locally persisted Value.
    """

    if depth < 0:
        raise ValueError("depth must be non-negative")

    root_names = tuple(
        root if isinstance(root, Name) else Name(root)
        for root in roots
    )
    queue: list[tuple[Name, int]] = [(root, 0) for root in root_names]
    visited: set[str] = set()
    nodes: list[SemanticNode] = []

    while queue:
        name, current_depth = queue.pop(0)
        if name.value in visited:
            continue
        visited.add(name.value)

        try:
            value = resolve(name.value)
        except KeyError:
            continue

        references = referenced_names(value)
        nodes.append(
            SemanticNode(
                name=name,
                value=value,
                depth=current_depth,
                references=references,
            )
        )
        if current_depth >= depth:
            continue
        for reference in references:
            if reference.value not in visited:
                queue.append((reference, current_depth + 1))

    return SemanticNeighborhood(roots=root_names, nodes=tuple(nodes))
