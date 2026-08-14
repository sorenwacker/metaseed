"""The parent-child invariant of the entity tree, decided once (ADR 005).

Three components maintain the tree — the facade's :class:`EntityStore` and
the file and memory repositories — over two data representations (a plain
``data`` dict versus an immutable-by-convention pydantic instance). The
*decisions* of the invariant are representation-free and live here; each
component applies them to its own representation:

- which parent field references a child of a given type,
- what that field's new value is when a child is linked or unlinked,
  including the LIST-vs-ENTITY shape rule (an exactly-one-child field holds
  a scalar, is claimed by the first child, and is cleared only when it names
  the child being removed),
- the structural half: membership in ``parent.children`` plus the child's
  ``parent_id``.

A gate test (``tests/test_tree_linking_is_owned_once.py``) fails when the
shape rule grows a second home.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from metaseed.facade.helper import EntityHelper

__all__ = [
    "NO_CHANGE",
    "link_child",
    "linked_reference_value",
    "target_reference_field",
    "unlink_child",
    "unlinked_reference_value",
]


class _NoChange:
    """Sentinel: the field keeps its current value."""

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return "NO_CHANGE"


NO_CHANGE: Any = _NoChange()


def target_reference_field(parent_helper: EntityHelper, child_type: str) -> str | None:
    """The parent field that references a child of ``child_type``.

    The first-match rule over ``nested_fields``, stated once: the first
    declared nested field whose target names the child's type carries the
    reference.
    """
    for field_name, ref_type in parent_helper.nested_fields.items():
        if ref_type == child_type:
            return str(field_name)
    return None


def linked_reference_value(
    parent_helper: EntityHelper,
    field: str,
    current: Any,
    child_ref: str,
) -> Any:
    """The field's value after linking a child, or :data:`NO_CHANGE`.

    An exactly-one-child (``type: entity``) field holds ONE scalar: the
    first child claims it, later children leave it alone — appending to it
    silently corrupted its shape, which no model caught because entity
    fields are typed ``Any``. A list field gains the reference unless it
    already carries it.
    """
    if field in parent_helper.single_entity_fields:
        if not current:
            return child_ref
        return NO_CHANGE

    refs = (
        list(current) if isinstance(current, list) else ([current] if current else [])
    )
    if child_ref in refs:
        return NO_CHANGE
    return [*refs, child_ref]


def unlinked_reference_value(
    parent_helper: EntityHelper,
    field: str,
    current: Any,
    child_refs: set[str],
) -> Any:
    """The field's value after unlinking a child, or :data:`NO_CHANGE`.

    Linking wrote the reference; an unlink that leaves it hands every save
    and export an identifier naming a record that no longer exists. A scalar
    is cleared only when it names the removed child; a list loses exactly
    the members that do.
    """
    if field in parent_helper.single_entity_fields:
        if current is not None and str(current) in child_refs:
            return None
        return NO_CHANGE

    if isinstance(current, list):
        cleaned = [v for v in current if str(v) not in child_refs]
        if len(cleaned) != len(current):
            return cleaned
    return NO_CHANGE


def link_child(parent: Any, child: Any) -> None:
    """Attach ``child`` under ``parent`` structurally.

    Generic over any node carrying ``id``, ``children`` and ``parent_id`` —
    both ``EntityData`` and ``EntityNode`` do.
    """
    child.parent_id = parent.id
    if all(existing.id != child.id for existing in parent.children):
        parent.children.append(child)


def unlink_child(parent: Any, child: Any) -> None:
    """Detach ``child`` from ``parent`` structurally."""
    parent.children = [c for c in parent.children if c.id != child.id]
    if child.parent_id == parent.id:
        child.parent_id = None
