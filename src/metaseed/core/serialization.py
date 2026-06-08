"""Serialization utilities for Pydantic models.

This module provides safe serialization helpers that ensure JSON-compatible
output from Pydantic models. Use these instead of calling model_dump() directly.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


def to_json_dict(
    instance: BaseModel | None, exclude_none: bool = True
) -> dict[str, Any]:
    """Serialize a Pydantic model instance to a JSON-compatible dictionary.

    This is the ONLY safe way to serialize entity instances for JSON/YAML output.
    It ensures dates, URLs, and other complex types are converted to strings.

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
