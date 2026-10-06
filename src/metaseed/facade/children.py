"""Putting a parent's children back into the fields that hold them.

The entity tree stores a child as its own node, so a parent's nested list is
empty on its own instance even when it has children. Anything that judges a
parent -- a rule that a Run has at least one file -- has to see the children
in their field first. This is the one place that says which field that is, so
every validation entry point counts the same records.
"""

from __future__ import annotations

from typing import Any


def field_holding(child: Any, parent_helper: Any) -> str | None:
    """The parent field a child node belongs in, or None when that is unknown.

    Args:
        child: The child node.
        parent_helper: The entity helper of the parent's type.

    Returns:
        The field the child was recorded in (ADR 006). A child that records
        none -- one an importer linked to its parent by a reference field
        alone -- belongs in the one nested field of the parent that takes its
        entity type. With several such fields the answer is None: a guess would
        put records into a list they are not in.
    """
    recorded: str | None = getattr(child, "parent_field", None)
    if recorded is not None:
        return recorded
    if parent_helper is None:
        return None
    taking = [
        name
        for name, entity_type in parent_helper.nested_fields.items()
        if entity_type == child.entity_type
    ]
    return taking[0] if len(taking) == 1 else None


def instance_data(instance: Any) -> dict[str, Any]:
    """An instance's values as JSON data, without the fields left unset."""
    if instance is not None and hasattr(instance, "model_dump"):
        data: dict[str, Any] = instance.model_dump(mode="json", exclude_none=True)
        return data
    return {}


def data_with_children(node: Any, facade: Any) -> dict[str, Any]:
    """A node's data with its child nodes in the fields that hold them.

    One level deep: each child's own content is validated when the traversal
    reaches it, so only the parent's lists need filling here.

    Args:
        node: The entity node.
        facade: The profile facade the node belongs to.

    Returns:
        The node's JSON data, each child added to the field
        :func:`field_holding` names. A child whose field is unknown is left
        out.
    """
    data = instance_data(node.instance)
    if not node.children:
        return data
    helper = facade.get_helper(node.entity_type)
    if helper is None:
        return data
    for child in node.children:
        target = field_holding(child, helper)
        if target is None:
            continue
        child_data = instance_data(child.instance)
        existing = data.get(target)
        if isinstance(existing, list):
            existing.append(child_data)
        elif helper.field_info(target).get("type") == "list":
            # A list the parent left unset is dropped from its own data.
            data[target] = [child_data]
        else:
            # A single nested entity field, empty on the parent.
            data[target] = child_data
    return data
