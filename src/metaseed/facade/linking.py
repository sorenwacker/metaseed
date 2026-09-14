"""The parent-child invariant of the entity tree, decided once (ADR 005).

Three components maintain the tree — the facade's :class:`EntityStore` and
the file and memory repositories — over two data representations (a plain
``data`` dict versus an immutable-by-convention pydantic instance). The
*decisions* of the invariant are representation-free and live here; each
component applies them to its own representation:

- which parent field a child goes into: the field named for it, or the
  parent's single field for its type; never a guess among several (ADR 006),
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
    "choose_parent_field",
    "field_naming_child",
    "holds_exactly_one",
    "link_child",
    "linked_reference_value",
    "unlink_child",
    "unlinked_reference_value",
]


class _NoChange:
    """Sentinel: the field keeps its current value."""

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return "NO_CHANGE"


NO_CHANGE: Any = _NoChange()


def holds_exactly_one(parent_helper: EntityHelper, field: str) -> bool:
    """Whether ``field`` holds exactly one child (``type: entity``).

    The shape rule's question, asked by the UI too: a form must not offer, and
    a route must not add, a second entity to such a field (ADR 006).
    """
    return field in parent_helper.single_entity_fields


def choose_parent_field(
    parent_helper: EntityHelper, child_type: str, requested: str | None = None
) -> str | None:
    """The parent field a new child of ``child_type`` goes into (ADR 006).

    ``requested`` is used when it is a containment field for the child's type.
    Without one, the parent's single field for that type is used. A parent
    holding the type in several fields -- a DCAT catalogue's ``creator`` and
    ``publisher`` are both Agents -- has no single answer, and the first-match
    guess that used to stand in for one filed every publisher as a creator.

    Raises:
        ValueError: If ``requested`` does not hold the child's type, or no
            field is requested and several do.
    """
    parent_type = getattr(parent_helper, "name", "the parent")
    candidates = [
        name
        for name, target in parent_helper.child_fields.items()
        if target == child_type
    ]
    if requested is not None:
        if requested not in candidates:
            raise ValueError(
                f"{parent_type}.{requested} does not hold {child_type}; "
                f"fields that do: {', '.join(candidates) or 'none'}"
            )
        return requested
    if len(candidates) > 1:
        raise ValueError(
            f"{parent_type} holds {child_type} in several fields "
            f"({', '.join(candidates)}); name one as parent_field"
        )
    return candidates[0] if candidates else None


def field_naming_child(
    parent_helper: EntityHelper,
    parent_data: dict[str, Any],
    child_type: str,
    child_refs: set[str],
) -> str | None:
    """The parent field of a child whose field was never recorded.

    Datasets written before ``_parent_field`` existed still carry the child's
    identifier in the parent's field. That field is the answer; when no
    field names the child, the parent's single field for its type is.
    """
    candidates = [
        name
        for name, target in parent_helper.child_fields.items()
        if target == child_type
    ]
    for name in candidates:
        value = parent_data.get(name)
        values = value if isinstance(value, list) else [value]
        if any(v is not None and str(v) in child_refs for v in values):
            return name
    return candidates[0] if len(candidates) == 1 else None


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


def link_child(parent: Any, child: Any, field: str | None = None) -> None:
    """Attach ``child`` under ``parent`` structurally, in ``field`` when known.

    Generic over any node carrying ``id``, ``children``, ``parent_id`` and
    ``parent_field`` — both ``EntityData`` and ``EntityNode`` do.
    """
    child.parent_id = parent.id
    if field is not None:
        child.parent_field = field
    if all(existing.id != child.id for existing in parent.children):
        parent.children.append(child)


def unlink_child(parent: Any, child: Any) -> None:
    """Detach ``child`` from ``parent`` structurally."""
    parent.children = [c for c in parent.children if c.id != child.id]
    if child.parent_id == parent.id:
        child.parent_id = None
