"""Entity storage and management.

This module provides the EntityStore class for CRUD operations on entity
instances, relationship resolution, and serialization.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Self
from uuid import uuid4

from pydantic import BaseModel, ValidationError

from metaseed.facade.node import IDENTIFIER_FIELDS, EntityNode
from metaseed.logging import get_logger

logger = get_logger(__name__)


def _generate_node_id() -> str:
    """Generate a unique node ID.

    Returns:
        8-character hex string ID.
    """
    return uuid4().hex[:8]


if TYPE_CHECKING:
    from metaseed.facade.helper import EntityHelper

__all__ = ["EntityStore"]


class EntityStore:
    """Storage and management for entity instances.

    Handles CRUD operations, relationship resolution, and serialization
    of entity instances. Uses an index for fast lookups by identifier fields.

    Attributes:
        _instances: Dictionary mapping node IDs to EntityNodes.
        _index: Dictionary mapping identifier values to node IDs.
    """

    def __init__(
        self: Self,
        helper_getter: Callable[[str], EntityHelper],
        instance_creator: Callable[[str, dict[str, Any]], BaseModel],
    ) -> None:
        """Initialize the entity store.

        Args:
            helper_getter: Function to get EntityHelper by entity type name.
            instance_creator: Function to create validated model instances.
        """
        self._instances: dict[str, EntityNode] = {}
        self._index: dict[str, str] = {}  # identifier value -> node_id
        self._get_helper = helper_getter
        self._create_instance_callback = instance_creator

    def _create_instance(
        self: Self,
        entity_type: str,
        data: dict[str, Any],
        skip_validation: bool = False,
    ) -> BaseModel:
        """Create a model instance.

        Args:
            entity_type: Type of entity.
            data: Field values for the entity.
            skip_validation: If True, skip Pydantic validation.

        Returns:
            Model instance.
        """
        if skip_validation:
            helper = self._get_helper(entity_type)
            return helper.create(skip_validation=True, **data)
        return self._create_instance_callback(entity_type, data)

    def add_entity(
        self: Self,
        entity_type: str,
        data: dict[str, Any],
        node_id: str | None = None,
        parent_id: str | None = None,
        skip_validation: bool = False,
    ) -> EntityNode:
        """Add an entity instance and auto-link to parent via reference fields.

        This method creates an EntityNode, validates the data against the schema,
        and automatically establishes parent-child relationships by examining
        reference fields in the entity data.

        Args:
            entity_type: Type of entity (e.g., "Study", "Sample").
            data: Field values for the entity.
            node_id: Optional node ID. If not provided, generates an 8-character
                hex id.
            parent_id: Optional explicit parent node ID. If not provided,
                      attempts to resolve parent via reference fields.
            skip_validation: If True, skip Pydantic validation. Use for
                progressive editing where entities are saved with incomplete data.

        Returns:
            The created EntityNode.

        Raises:
            AttributeError: If entity_type is not found in this profile.

        Example:
            >>> store.add_entity("Study", {"alias": "s1", "title": "My Study"})
            >>> store.add_entity("Sample", {"alias": "sam1", "study_ref": "s1", ...})
            >>> # Sample is auto-linked to Study via study_ref
        """
        # When created under an explicit parent, fill the child's parent-reference
        # field (e.g. investigation_id) from the parent so the caller need not
        # repeat it -- otherwise a required reference fails validation below.
        if parent_id is not None:
            data = self._fill_parent_reference(entity_type, data, parent_id)

        instance = self._create_instance(entity_type, data, skip_validation)

        # Resolve parent: explicit parent_id takes precedence, then reference fields
        resolved_parent_id = parent_id
        if resolved_parent_id is None:
            resolved_parent_id = self._resolve_parent(entity_type, data)

        node = EntityNode(
            id=node_id or _generate_node_id(),
            entity_type=entity_type,
            instance=instance,
            parent_id=resolved_parent_id,
        )

        self._instances[node.id] = node

        # Link to parent's children list if parent exists
        if resolved_parent_id and resolved_parent_id in self._instances:
            parent_node = self._instances[resolved_parent_id]
            parent_node.children.append(node)

        # Index by every identifier field (common + entity-specific) for lookups
        for id_field in self._get_identifier_fields(entity_type):
            id_value = data.get(id_field)
            if id_value:
                self._index[str(id_value)] = node.id

        return node

    def _resolve_parent(
        self: Self,
        entity_type: str,
        data: dict[str, Any],
    ) -> str | None:
        """Find parent node via reference fields.

        Examines the entity's reference fields (e.g., study_ref, sample_ref)
        and looks up the referenced entity in the index.

        Args:
            entity_type: Type of entity being created.
            data: Entity data containing potential reference field values.

        Returns:
            Parent node ID if found, None otherwise.
        """
        try:
            helper = self._get_helper(entity_type)
        except (KeyError, AttributeError):
            return None

        for field_name in helper.reference_fields:
            ref_value = data.get(field_name)
            if ref_value and str(ref_value) in self._index:
                return self._index[str(ref_value)]

        return None

    def _fill_parent_reference(
        self: Self,
        entity_type: str,
        data: dict[str, Any],
        parent_id: str,
    ) -> dict[str, Any]:
        """Populate a child's parent-reference field from its explicit parent.

        The inverse of :meth:`_resolve_parent`: when a child is created under an
        explicit ``parent_id``, set its reference to the parent (e.g. a Study's
        ``investigation_id``, or an ENA Sample's ``study_ref``) so callers need
        not repeat it. The field name and the parent value to copy both come from
        the helper's parsed ``reference_fields`` map
        (``{field_name: (target_entity_type, target_field)}``) -- matching the
        parent's entity type -- rather than a name convention, so it works for any
        reference field regardless of naming (``_id``, ``_ref``, etc.).
        Conservative: fills only a reference field the caller left unset, and only
        when the parent actually carries the referenced value; never overrides
        provided data.

        Args:
            entity_type: Type of the child being created.
            data: The child's field values.
            parent_id: The explicit parent node id.

        Returns:
            ``data`` (a copy with the reference filled, or unchanged).
        """
        parent_node = self._instances.get(parent_id)
        if parent_node is None:
            return data
        try:
            helper = self._get_helper(entity_type)
        except (KeyError, AttributeError):
            return data

        for ref_field, (
            target_entity_type,
            target_field,
        ) in helper.reference_fields.items():
            if target_entity_type != parent_node.entity_type or data.get(ref_field):
                continue
            parent_value = getattr(parent_node.instance, target_field, None)
            if parent_value is not None:
                return {**data, ref_field: parent_value}

        return data

    def _get_identifier_fields(self: Self, entity_type: str) -> list[str]:
        """Get all identifier fields for an entity type.

        Combines common identifier fields with entity-specific identifier field.

        Args:
            entity_type: Type of entity.

        Returns:
            List of identifier field names.
        """
        fields = list(IDENTIFIER_FIELDS)
        try:
            helper = self._get_helper(entity_type)
            if helper.identifier_field and helper.identifier_field not in fields:
                fields.append(helper.identifier_field)
        except (KeyError, AttributeError):
            pass
        return fields

    def get_entity(self: Self, node_id: str) -> EntityNode | None:
        """Get an entity node by its ID.

        Args:
            node_id: The node ID to look up.

        Returns:
            EntityNode if found, None otherwise.
        """
        return self._instances.get(node_id)

    def get_entity_by_ref(self: Self, ref_value: str) -> EntityNode | None:
        """Get an entity node by its reference value (alias/unique_id).

        Args:
            ref_value: The alias or unique_id to look up.

        Returns:
            EntityNode if found, None otherwise.
        """
        node_id = self._index.get(ref_value)
        if node_id:
            return self._instances.get(node_id)
        return None

    def update_entity(
        self: Self,
        node_id: str,
        data: dict[str, Any],
        skip_validation: bool = False,
    ) -> EntityNode | None:
        """Update an existing entity's data.

        Args:
            node_id: ID of the node to update.
            data: New field values.
            skip_validation: If True, skip Pydantic validation.

        Returns:
            Updated EntityNode if found, None otherwise.
        """
        node = self._instances.get(node_id)
        if not node:
            return None

        id_fields_to_check = self._get_identifier_fields(node.entity_type)

        # Remove old index entries
        old_data = (
            node.instance.model_dump() if hasattr(node.instance, "model_dump") else {}
        )
        for id_field in id_fields_to_check:
            old_value = old_data.get(id_field)
            if old_value and str(old_value) in self._index:
                if self._index[str(old_value)] == node_id:
                    del self._index[str(old_value)]

        # Create new instance
        node.instance = self._create_instance(node.entity_type, data, skip_validation)

        # Add new index entries
        for id_field in id_fields_to_check:
            new_value = data.get(id_field)
            if new_value:
                self._index[str(new_value)] = node_id

        return node

    def delete_entity(self: Self, node_id: str) -> bool:
        """Delete an entity and all its children recursively.

        Args:
            node_id: ID of the node to delete.

        Returns:
            True if deleted, False if not found.
        """
        node = self._instances.get(node_id)
        if not node:
            return False

        def remove_recursively(n: EntityNode) -> None:
            for child in n.children:
                remove_recursively(child)
            # Remove from index
            if n.instance and hasattr(n.instance, "model_dump"):
                data = n.instance.model_dump()
                for id_field in self._get_identifier_fields(n.entity_type):
                    id_value = data.get(id_field)
                    if (
                        id_value
                        and str(id_value) in self._index
                        and self._index[str(id_value)] == n.id
                    ):
                        del self._index[str(id_value)]
            self._instances.pop(n.id, None)

        # Remove from parent's children list
        if node.parent_id and node.parent_id in self._instances:
            parent = self._instances[node.parent_id]
            parent.children = [c for c in parent.children if c.id != node_id]

        remove_recursively(node)
        return True

    def get_children(self: Self, node_id: str) -> list[EntityNode]:
        """Get all direct children of a node.

        Args:
            node_id: ID of the parent node.

        Returns:
            List of child EntityNodes.
        """
        node = self._instances.get(node_id)
        if node:
            return node.children
        return []

    def get_roots(self: Self) -> list[EntityNode]:
        """Get all root nodes (nodes without parents).

        Returns:
            List of root EntityNodes.
        """
        return [n for n in self._instances.values() if n.parent_id is None]

    def to_dict(self: Self) -> list[dict[str, Any]]:
        """Export all entities for serialization.

        Returns a flat list of entity data with metadata for reconstruction.
        Uses _parent_unique_id for parent references (stable across reloads).

        Returns:
            List of entity dictionaries with _type and optional _parent_unique_id.
        """
        entities: list[dict[str, Any]] = []

        def serialize_node(
            node: EntityNode, parent_unique_id: str | None = None
        ) -> None:
            if node.instance and hasattr(node.instance, "model_dump"):
                data = node.instance.model_dump(mode="json", exclude_none=True)
            else:
                data = {}

            data["_type"] = node.entity_type
            # Persist the node id so it survives a reload verbatim. The graph
            # endpoint reloads the dataset from disk on every poll; without a
            # stored id, entities without an identifier value would be assigned
            # a fresh id each reload and re-appear in the graph on every tick.
            data["_node_id"] = node.id
            if parent_unique_id:
                data["_parent_unique_id"] = parent_unique_id
            entities.append(data)

            # The identifier value children reference. Consult the entity's own
            # declared identifier field: hardcoding unique_id and alias produced
            # no parent link at all for the seven profiles keyed on anything
            # else, so their hierarchy flattened on every reload.
            node_unique_id = data.get("unique_id") or data.get("alias")
            if not node_unique_id:
                try:
                    id_field = self._get_helper(node.entity_type).identifier_field
                except (KeyError, AttributeError):
                    id_field = None
                if id_field:
                    candidate = data.get(id_field)
                    # Only a scalar can serve as a reference value: an
                    # identifier field may itself be entity-typed (e.g. isa
                    # ProtocolParameter.parameter_name), and a dict is neither
                    # hashable nor meaningful as a parent reference.
                    if isinstance(candidate, (str, int, float, bool)):
                        node_unique_id = str(candidate)

            for child in node.children:
                serialize_node(child, node_unique_id)

        for root in self.get_roots():
            serialize_node(root)

        return entities

    def load_from_dict(self: Self, entities: list[dict[str, Any]]) -> int:
        """Load entities from serialized data.

        Reconstructs the entity graph from a flat list of entity dictionaries.
        Handles parent relationships via _parent_id, _parent_unique_id, and
        reference fields.

        Args:
            entities: List of entity dictionaries with _type metadata.

        Returns:
            Number of entities loaded.
        """
        self.clear()

        id_to_node: dict[str, EntityNode] = {}
        old_id_to_node: dict[str, EntityNode] = {}
        nodes_with_parent: list[tuple[EntityNode, str, bool]] = []

        # Phase 1: Create all nodes
        for entity_data in entities:
            result = self._create_node_from_dict(entity_data)
            if result:
                node, id_to_node_entry, old_id_entry, parent_entry = result
                if id_to_node_entry:
                    id_to_node[id_to_node_entry] = node
                if old_id_entry:
                    old_id_to_node[old_id_entry] = node
                if parent_entry:
                    nodes_with_parent.append(parent_entry)

        # Phase 2: Link nodes to parents
        self._link_by_stored_refs(nodes_with_parent, id_to_node, old_id_to_node)
        self._link_by_nested_arrays(id_to_node)
        self._link_by_reference_fields(id_to_node)

        if entities and not self._instances:
            # Every entity was skipped. Returning 0 quietly is how a whole
            # dataset went missing unnoticed: this format needs a ``_type`` on
            # each entity, and a document written by hand has none (#246).
            logger.warning(
                "Loaded 0 of %d entities: none carried a '_type'. A dataset "
                "written as a nested document loads with load_yaml or "
                "load_nested, not with load_from_dict.",
                len(entities),
            )

        return len(self._instances)

    def _create_node_from_dict(
        self: Self, entity_data: dict[str, Any]
    ) -> (
        tuple[EntityNode, str | None, str | None, tuple[EntityNode, str, bool] | None]
        | None
    ):
        """Create a single node from serialized data.

        Malformed entities (those raising ValidationError, ValueError, or
        TypeError during instance creation) are skipped and logged at warning
        level rather than aborting the load. This keeps ``load_from_dict``
        resilient while making dropped entities visible.

        Args:
            entity_data: Serialized entity dictionary with ``_type`` metadata.

        Returns:
            Tuple of (node, id_for_index, old_node_id, parent_tuple), or None
            if the entity has no type, an unknown type, or is malformed.
        """
        entity_type = entity_data.get("_type")
        if not entity_type:
            return None

        try:
            helper = self._get_helper(entity_type)
        except (KeyError, AttributeError):
            return None

        try:
            parent_unique_id = entity_data.get("_parent_unique_id")
            old_parent_id = entity_data.get("_parent_id")
            old_node_id = entity_data.get("_node_id")

            # Filter to valid fields only (lenient loading)
            valid_fields = set(helper.all_fields)
            fields = {
                k: v
                for k, v in entity_data.items()
                if not k.startswith("_") and k in valid_fields
            }

            try:
                instance = self._create_instance(entity_type, fields)
            except ValidationError as exc:
                # Distinguish an incomplete *draft* from corrupt data. The UI
                # persists drafts on purpose (a root can be saved before its
                # required children exist); dropping those on read lost user
                # data, because several routes reload from disk on ordinary
                # navigation. Only absent required fields qualify -- anything
                # else (wrong types, unusable values) is still treated as
                # malformed and skipped by the caller. ``validate()`` continues
                # to report the draft's gaps.
                errors = exc.errors()
                if not errors or not all(err["type"] == "missing" for err in errors):
                    raise
                instance = self._create_instance(
                    entity_type, fields, skip_validation=True
                )

            # Restore the persisted node id so a node keeps the same identity
            # across reloads (the graph endpoint reloads from disk on every
            # poll). Fall back to the identifier value for datasets written
            # before ids were persisted, and only generate one as a last resort
            # for entities that have neither. Never reuse an id already in use:
            # entities that collide on the same value must stay distinct nodes
            # rather than overwriting each other and silently disappearing.
            id_field = helper.identifier_field
            entity_id = fields.get(id_field) if id_field else None
            node_id = old_node_id or (
                str(entity_id) if entity_id else _generate_node_id()
            )
            while node_id in self._instances:
                node_id = _generate_node_id()

            node = EntityNode(
                id=node_id,
                entity_type=entity_type,
                instance=instance,
                parent_id=None,
            )
            self._instances[node.id] = node

            # Build return values
            id_for_index = str(entity_id) if entity_id else None
            # Index by every identifier field, matching add_entity, so that
            # references resolve after a reload regardless of which id field
            # they target.
            for id_field in self._get_identifier_fields(entity_type):
                id_value = fields.get(id_field)
                if id_value:
                    self._index[str(id_value)] = node.id

            parent_entry = None
            if parent_unique_id:
                parent_entry = (node, parent_unique_id, True)
            elif old_parent_id:
                parent_entry = (node, old_parent_id, False)

            return (node, id_for_index, old_node_id, parent_entry)

        except (ValidationError, ValueError, TypeError) as exc:
            identifier = entity_data.get("_node_id")
            if identifier is None:
                for id_field in IDENTIFIER_FIELDS:
                    if entity_data.get(id_field) is not None:
                        identifier = entity_data[id_field]
                        break
                else:
                    identifier = "<unknown>"
            logger.warning(
                "Skipping malformed entity of type %r (identifier=%r): %s",
                entity_type,
                identifier,
                exc,
            )
            return None

    def _link_by_stored_refs(
        self: Self,
        nodes_with_parent: list[tuple[EntityNode, str, bool]],
        id_to_node: dict[str, EntityNode],
        old_id_to_node: dict[str, EntityNode],
    ) -> None:
        """Link nodes to parents by stored _parent_unique_id or _parent_id."""
        for node, parent_ref, is_unique_id in nodes_with_parent:
            parent_node = (
                id_to_node.get(parent_ref)
                if is_unique_id
                else old_id_to_node.get(parent_ref)
            )
            if parent_node:
                node.parent_id = parent_node.id
                parent_node.children.append(node)

    def _link_by_nested_arrays(self: Self, id_to_node: dict[str, EntityNode]) -> None:
        """Link children via parent's nested array fields."""
        for node in list(self._instances.values()):
            if node.parent_id:
                continue

            try:
                helper = self._get_helper(node.entity_type)
            except (KeyError, AttributeError):
                continue

            node_data = node.instance.model_dump() if node.instance else {}

            for field_name in helper.nested_fields:
                child_ids = node_data.get(field_name, [])
                if not isinstance(child_ids, list):
                    continue

                for child_id in child_ids:
                    child_node = id_to_node.get(str(child_id))
                    if child_node and child_node.parent_id is None:
                        child_node.parent_id = node.id
                        node.children.append(child_node)

    def _link_by_reference_fields(
        self: Self, id_to_node: dict[str, EntityNode]
    ) -> None:
        """Link orphan nodes to parents via reference fields.

        A reference field does not merely record a link here: it decides the
        parent. That is what makes a self-referencing type — Darwin Core's
        ``parentEventID`` naming another Event, ``acceptedNameUsageID`` naming
        another Taxon — able to build a hierarchy at all, and also what makes a
        cycle dangerous. Two records naming each other would each become the
        other's parent, leaving a dataset with no roots (every node has a
        parent) and a ``children`` graph that recurses without end.

        A node is therefore never parented under one of its own descendants.
        """
        for node in list(self._instances.values()):
            if node.parent_id:
                continue

            try:
                helper = self._get_helper(node.entity_type)
            except (KeyError, AttributeError):
                continue

            node_data = node.instance.model_dump() if node.instance else {}

            for field_name in helper.reference_fields:
                ref_value = node_data.get(field_name)
                if not ref_value:
                    continue

                parent_node = id_to_node.get(str(ref_value))
                if parent_node is None or parent_node.id == node.id:
                    continue
                if self._would_cycle(node, parent_node):
                    logger.warning(
                        "%s '%s' references '%s', which is already beneath it; "
                        "leaving it unparented rather than closing a cycle.",
                        node.entity_type,
                        node.id,
                        ref_value,
                    )
                    continue
                node.parent_id = parent_node.id
                parent_node.children.append(node)
                break

    def _would_cycle(self: Self, node: EntityNode, parent: EntityNode) -> bool:
        """Whether parenting ``node`` under ``parent`` closes a loop.

        True when ``parent`` is ``node`` itself or sits beneath it already.
        Walked upwards from the proposed parent, which is bounded by the number
        of nodes even if the graph is already inconsistent.
        """
        seen: set[str] = set()
        current: EntityNode | None = parent
        while current is not None:
            if current.id == node.id:
                return True
            if current.id in seen:
                # The existing graph is already looped; refuse to add to it.
                return True
            seen.add(current.id)
            current = (
                self._instances.get(current.parent_id) if current.parent_id else None
            )
        return False

    def clear(self: Self) -> None:
        """Clear all stored entity instances."""
        self._instances.clear()
        self._index.clear()
