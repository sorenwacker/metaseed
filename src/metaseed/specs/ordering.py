"""Ordering entity types by the containment tree.

A profile lists its entities in authoring order, which need not be hierarchical.
Containment -- which entity nests which -- is defined by the entities' nesting
fields, not by the order they are written in. This module derives the
hierarchical order (root first, every parent before the types it contains) from
that containment, so specs are saved in it and every consumer that iterates
``facade.entities`` inherits it. See ``docs/api/schema-specs.md``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from metaseed.specs.schema import ProfileSpec

__all__ = [
    "child_entity_types",
    "containment_order",
    "entity_order",
    "is_in_containment_order",
]


def containment_order(names: list[str], children_of: dict[str, list[str]]) -> list[str]:
    """Entity type names in a stable topological order, roots first.

    A *stable* topological sort: every parent precedes the types it contains,
    but the given order is otherwise preserved. A profile whose declared order
    already places each parent before its children is returned unchanged -- so a
    curated order (ISA's ``Investigation > Study > Assay > Person > ...``) is not
    disturbed. Only a genuine violation is corrected, and minimally: an entity
    declared before the parent that contains it (a profile that lists its root
    last) moves down to just past its parents, nothing else shifts.

    Implemented as Kahn's algorithm with the declared index as the tiebreak
    among ready entities. A containment cycle (which a valid profile cannot
    have) leaves its members for the end, in declared order, rather than looping.

    Args:
        names: All entity type names, in declared order.
        children_of: For each name, the entity types it directly contains.

    Returns:
        ``names`` in stable topological order (parent before contained type).
    """
    index = {name: position for position, name in enumerate(names)}
    edges = {
        (parent, child)
        for parent, kids in children_of.items()
        for child in kids
        if child in index and child != parent
    }
    parents_left = dict.fromkeys(names, 0)
    children: dict[str, list[str]] = {name: [] for name in names}
    for parent, child in edges:
        parents_left[child] += 1
        children[parent].append(child)

    def declared_index(name: str) -> int:
        return index[name]

    ready = sorted(
        (name for name in names if parents_left[name] == 0), key=declared_index
    )
    ordered: list[str] = []
    placed: set[str] = set()
    while ready:
        name = ready.pop(0)
        ordered.append(name)
        placed.add(name)
        freed = False
        for child in children[name]:
            parents_left[child] -= 1
            if parents_left[child] == 0:
                ready.append(child)
                freed = True
        if freed:
            ready.sort(key=declared_index)

    # Any entity left in a containment cycle keeps its declared position.
    ordered.extend(name for name in names if name not in placed)
    return ordered


def child_entity_types(spec: ProfileSpec) -> dict[str, list[str]]:
    """For each entity in ``spec``, the entity types it directly contains.

    A field contains another entity when it is nested (``type: list`` or
    ``type: entity``) and its ``items`` names an entity the profile defines.
    """
    result: dict[str, list[str]] = {}
    for name, entity in spec.entities.items():
        result[name] = [
            field.items
            for field in entity.fields
            if field.is_nested() and field.items in spec.entities
        ]
    return result


def entity_order(spec: ProfileSpec) -> list[str]:
    """The entity names of ``spec`` in containment order (root first)."""
    return containment_order(list(spec.entities), child_entity_types(spec))


def is_in_containment_order(spec: ProfileSpec) -> bool:
    """Whether the spec already declares its entities in containment order."""
    return list(spec.entities) == entity_order(spec)
