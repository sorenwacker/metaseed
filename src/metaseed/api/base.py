"""Shared base for MetaseedClient mixins.

Holds helpers that more than one mixin depends on, so the dependency is
explicit rather than relying on sibling mixins being composed in a particular
order on the concrete client.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Self

if TYPE_CHECKING:
    from metaseed.facade import ProfileFacade


class InstanceDataMixin:
    """Provides instance-data extraction shared by the client mixins."""

    _facade: ProfileFacade

    def _get_instance_data(self: Self, instance: Any) -> dict[str, Any]:
        """Extract a JSON-compatible data dictionary from a model instance.

        Args:
            instance: Pydantic model instance or None.

        Returns:
            Data dictionary, or empty dict if instance is None/invalid.
        """
        if instance and hasattr(instance, "model_dump"):
            result: dict[str, Any] = instance.model_dump(mode="json", exclude_none=True)
            return result
        return {}
