"""Serialization utilities for Pydantic models.

This module provides a convenience helper for JSON-compatible output from
Pydantic models. It wraps the standard ``model_dump(mode="json")`` call and
returns an empty dict for a ``None`` instance.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


def to_json_dict(
    instance: BaseModel | None, exclude_none: bool = True
) -> dict[str, Any]:
    """Serialize a Pydantic model instance to a JSON-compatible dictionary.

    Convenience wrapper around ``instance.model_dump(mode="json", ...)`` that
    additionally returns an empty dict for a ``None`` instance. The
    ``mode="json"`` conversion turns dates, URLs, and other complex types into
    JSON-serializable values.

    Args:
        instance: Pydantic model instance to serialize, or None.
        exclude_none: Whether to exclude None values from output. Default True.

    Returns:
        JSON-serializable dictionary, or empty dict if instance is None.

    Example:
        >>> from metaseed.core.serialization import to_json_dict
        >>> data = to_json_dict(entity.instance)
        >>> json.dumps(data)  # Always works
    """
    if instance is None:
        return {}
    if not hasattr(instance, "model_dump"):
        return {}
    return instance.model_dump(mode="json", exclude_none=exclude_none)
