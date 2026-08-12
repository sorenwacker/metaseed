"""Reading a dataset as a person writes it.

A dataset arrives in one of two shapes. The store's own serialization is a flat
list where every entity carries a ``_type`` and a reference to its parent; a
document is a root object with its children embedded in its own fields, which is
how the shipped examples, the exporter's YAML and anything hand-written are
written.

Only the first was ever read. A document was handed to the same loader, which
skipped every entity for want of a ``_type`` and returned zero — silently, which
is why nobody noticed the shipped examples could not be loaded by a consumer
(#246).

This lives apart from :class:`~metaseed.facade.core.ProfileFacade` because it is
one job with one dependency — somewhere to put entities — and the facade had
grown to thirty-odd methods that change for unrelated reasons.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from pathlib import Path

    from metaseed.facade.helper import EntityHelper
    from metaseed.facade.node import EntityNode


class EntitySink(Protocol):
    """Somewhere to put an entity, and enough to know what may nest in it.

    A protocol rather than the facade itself: this loader needs three things,
    and stating them is cheaper than depending on a class with thirty-eight
    methods. It also means a test can hand it a list.
    """

    def add_entity(
        self,
        entity_type: str,
        data: dict[str, Any],
        node_id: str | None = ...,
        parent_id: str | None = ...,
        skip_validation: bool = ...,
    ) -> EntityNode:
        """Store one entity, optionally under a parent."""
        ...

    def get_helper(self, entity_type: str) -> EntityHelper | None:
        """The helper for a type, or ``None`` when the profile has no such type."""
        ...

    def uses_ownership(self) -> bool:
        """Whether the profile declares containment with ``owns`` markers."""
        ...


def is_serialized(entities: list[Any]) -> bool:
    """Whether this is the store's own serialization rather than a document.

    The serialized form carries a ``_type`` on every entity; a document written
    by a person carries none. Deciding by what is present beats deciding by
    shape: a single entity is a mapping either way.
    """
    return any(isinstance(e, dict) and "_type" in e for e in entities)


class DocumentLoader:
    """Loads a nested document into an :class:`EntitySink`.

    Attributes:
        sink: Where loaded entities are put.
        default_root: The entity type a document is assumed to be when the
            caller does not say.
    """

    def __init__(self, sink: EntitySink, default_root: str | None = None) -> None:
        """Initialize the loader.

        Args:
            sink: Where to put the entities.
            default_root: The profile's root entity, used when a document does
                not say what it is.
        """
        self.sink = sink
        self.default_root = default_root

    def load(self, document: dict[str, Any], entity_type: str | None = None) -> int:
        """Load one entity and the entities nested inside it.

        Where the profile declares containment with ``owns`` markers, only the
        owned fields are walked, so an embedded value-object — an
        ``OntologyAnnotation`` in ``Assay.measurement_type``, a ``Comment`` —
        stays inline instead of becoming a separate node that nothing links to.
        Profiles without markers treat every nested field as containment.

        Args:
            document: The root entity's data, with children embedded.
            entity_type: What the root is. Defaults to the profile's root.

        Returns:
            Number of entities loaded, the root included.
        """
        root_type = entity_type or self.default_root
        if root_type is None:
            return 0
        node = self.sink.add_entity(root_type, document, skip_validation=True)
        return 1 + self._load_children(document, root_type, node.id)

    def _load_children(
        self, parent_data: dict[str, Any], parent_type: str, parent_id: str
    ) -> int:
        """Add every entity embedded in ``parent_data``, recursively."""
        helper = self.sink.get_helper(parent_type)
        if helper is None:
            return 0

        child_fields = (
            helper.owned_child_fields
            if self.sink.uses_ownership()
            else helper.nested_fields
        )

        loaded = 0
        for field_name, child_type in child_fields.items():
            items = parent_data.get(field_name)
            if isinstance(items, dict):
                items = [items]
            if not isinstance(items, list):
                continue
            if self.sink.get_helper(child_type) is None:
                continue
            for item in items:
                if not isinstance(item, dict):
                    continue  # a plain string names a child, it does not embed one
                child = self.sink.add_entity(
                    child_type, item, parent_id=parent_id, skip_validation=True
                )
                loaded += 1 + self._load_children(item, child_type, child.id)
        return loaded


def read_yaml(path: str | Path) -> Any:
    """The parsed contents of a YAML file.

    Separated from the loading so the format decision below can be tested
    without a file, and so a caller holding parsed data need not write it to
    disk first.
    """
    from pathlib import Path as _Path

    import yaml

    with _Path(path).open() as f:
        return yaml.safe_load(f)
