"""State management for the Spec Builder.

Contains dataclasses for managing spec builder state including the working
specification, current editing context, and change tracking.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Self

if TYPE_CHECKING:
    from metaseed.specs.schema import ProfileSpec


@dataclass
class SpecBuilderState:
    """Server-side state for the Spec Builder.

    Attributes:
        spec: The ProfileSpec being edited, or None if not started.
        editing_entity: Name of entity currently being edited, or None.
        editing_field_idx: Index of field being edited within current entity.
        editing_rule_idx: Index of validation rule being edited.
        template_source: Tuple of (profile, version) if cloned from template.
        has_unsaved_changes: Whether there are unsaved modifications.
    """

    spec: ProfileSpec | None = None
    editing_entity: str | None = None
    editing_field_idx: int | None = None
    editing_rule_idx: int | None = None
    template_source: tuple[str, str] | None = None
    has_unsaved_changes: bool = False

    def reset(self: Self) -> None:
        """Reset all state to initial values."""
        self.spec = None
        self.editing_entity = None
        self.editing_field_idx = None
        self.editing_rule_idx = None
        self.template_source = None
        self.has_unsaved_changes = False

    def mark_changed(self: Self) -> None:
        """Mark that unsaved changes exist."""
        self.has_unsaved_changes = True

    def mark_saved(self: Self) -> None:
        """Mark that all changes have been saved."""
        self.has_unsaved_changes = False

    def is_active(self: Self) -> bool:
        """Check if a spec is currently being edited."""
        return self.spec is not None

    def get_entity_names(self: Self) -> list[str]:
        """Get list of entity names in the spec."""
        if self.spec is None:
            return []
        return list(self.spec.entities.keys())

    def get_current_entity_field_count(self: Self) -> int:
        """Get field count for the currently editing entity."""
        if self.spec is None or self.editing_entity is None:
            return 0
        entity = self.spec.entities.get(self.editing_entity)
        if entity is None:
            return 0
        return len(entity.fields)
