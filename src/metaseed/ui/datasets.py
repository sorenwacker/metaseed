"""Dataset persistence for the UI.

This module provides helper functions for dataset operations.
All operations use DatasetManagerFactory for proper dependency injection.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING, Any

from metaseed.repositories.dataset_repository import DatasetData, DatasetRepository
from metaseed.repositories.filesystem_dataset import (
    DEFAULT_DATASETS_DIR,
)

if TYPE_CHECKING:
    from .dataset_manager import DatasetManagerFactory
    from .state import AppState

from contextvars import ContextVar

DATASETS_DIR = DEFAULT_DATASETS_DIR

# Context variable for request-scoped factory
_factory_var: ContextVar[DatasetManagerFactory | None] = ContextVar(
    "dataset_factory", default=None
)


def _get_factory() -> DatasetManagerFactory:
    """Get or create the factory for current context."""
    factory = _factory_var.get()
    if factory is None:
        from .dataset_manager import DatasetManagerFactory

        factory = DatasetManagerFactory()
        _factory_var.set(factory)
    return factory


def _resolve_factory() -> DatasetManagerFactory:
    """Resolve the active dataset factory.

    Prefers the factory from the MCP context when one is set (which keeps
    save, load, and auto-save pointed at the same repository during MCP
    sessions and test isolation), and otherwise falls back to the
    context-variable factory from :func:`_get_factory`.

    Returns:
        The dataset factory to use for repository-backed operations.
    """
    try:
        from metaseed.agent.mcp.server import get_context

        ctx = get_context()
    except ImportError:
        ctx = None

    if ctx is not None:
        return ctx.dataset_factory
    return _get_factory()


def get_datasets_dir() -> Path:
    """Get the datasets directory, creating it if needed."""
    DATASETS_DIR.mkdir(parents=True, exist_ok=True)
    return DATASETS_DIR


def validate_dataset_name(name: str) -> str | None:
    """Validate a dataset name.

    Args:
        name: Dataset name to validate.

    Returns:
        Error message if invalid, None if valid.
    """
    return DatasetRepository.validate_name(name)


def list_datasets() -> list[dict[str, Any]]:
    """List all saved datasets.

    Returns:
        List of dataset info dicts with name, profile, version, entity_count, modified.
    """
    repo = _resolve_factory().sync_repo
    return [asdict(d) for d in repo.list()]


def save_dataset(state: AppState, name: str) -> dict[str, Any]:
    """Save current state as a named dataset.

    Args:
        state: AppState to save.
        name: Dataset name.

    Returns:
        Dict with saved dataset info.

    Raises:
        ValueError: If name is invalid.
    """
    factory = _resolve_factory()
    manager = factory.get_manager(state)
    result = manager.save_dataset(name)
    return asdict(result)


def load_dataset(state: AppState, name: str) -> dict[str, Any]:
    """Load a dataset into the state.

    Args:
        state: AppState to load into.
        name: Dataset name to load.

    Returns:
        Dict with loaded dataset info.

    Raises:
        FileNotFoundError: If dataset doesn't exist.
        ValueError: If dataset is invalid.
    """
    factory = _resolve_factory()
    manager = factory.get_manager(state)
    result = manager.load_dataset(name)
    return asdict(result)


def import_dataset(state: AppState, raw: bytes | str) -> dict[str, Any]:
    """Import a dataset from raw JSON content into the state.

    The expected JSON shape matches a saved dataset file: an object with
    ``profile`` and ``entities`` (a list), and optionally ``name``, ``version``
    and ``modified``. The imported dataset replaces the current state but is
    not persisted to storage.

    Args:
        state: AppState to load the imported dataset into.
        raw: Raw JSON content (bytes or str) from an uploaded file.

    Returns:
        Dict with imported dataset info (name, profile, version, entity_count).

    Raises:
        ValueError: If the content is not a valid dataset JSON document.
    """
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError(f"Invalid JSON: {exc}") from exc

    if not isinstance(payload, dict):
        raise ValueError("Dataset JSON must be an object")  # noqa: TRY004

    profile = payload.get("profile")
    entities = payload.get("entities")
    if not profile or entities is None:
        raise ValueError("Dataset JSON must contain 'profile' and 'entities'")
    if not isinstance(entities, list):
        raise ValueError("Dataset 'entities' must be a list")  # noqa: TRY004

    data = DatasetData(
        name=payload.get("name", ""),
        profile=profile,
        version=payload.get("version") or "",
        entities=entities,
        modified=payload.get("modified", ""),
    )

    factory = _resolve_factory()
    manager = factory.get_manager(state)
    return asdict(manager.import_data(data))


def delete_dataset(name: str) -> bool:
    """Delete a dataset.

    Args:
        name: Dataset name to delete.

    Returns:
        True if deleted, False if not found.
    """
    repo = _resolve_factory().sync_repo
    return repo.delete(name)


def get_current_dataset_name(state: AppState) -> str | None:
    """Get the name of the currently loaded dataset, if any.

    This is stored in the state after a load operation.
    """
    return getattr(state, "_current_dataset", None)


def set_current_dataset_name(state: AppState, name: str | None) -> None:
    """Set the current dataset name in state."""
    state._current_dataset = name


def auto_save(state: AppState) -> None:
    """Auto-save the current state.

    Saves to the current dataset if one is loaded, otherwise derives a name
    from the first entity's label (title, name, etc.).
    Notifies connected WebSocket clients of the change.

    Args:
        state: AppState to save.
    """
    factory = _resolve_factory()
    manager = factory.get_manager(state)
    manager.current_dataset = get_current_dataset_name(state)
    manager.auto_save()
    set_current_dataset_name(state, manager.current_dataset)
