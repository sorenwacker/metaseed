"""Dataset persistence for the UI.

This module provides backward-compatible functions for dataset operations.
All operations delegate to DatasetManager for actual implementation.

For new code, prefer using DatasetManager directly via:
    from metaseed.ui.dataset_manager import get_manager
"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING, Any

from metaseed.repositories.dataset_repository import DatasetRepository
from metaseed.repositories.filesystem_dataset import DEFAULT_DATASETS_DIR

if TYPE_CHECKING:
    from .state import AppState

DATASETS_DIR = DEFAULT_DATASETS_DIR


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
    from .dataset_manager import list_datasets_compat

    return list_datasets_compat()


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
    from .dataset_manager import DatasetManager, get_repository

    manager = DatasetManager(get_repository(), state)
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
    from .dataset_manager import DatasetManager, get_repository

    manager = DatasetManager(get_repository(), state)
    result = manager.load_dataset(name)
    return asdict(result)


def delete_dataset(name: str) -> bool:
    """Delete a dataset.

    Args:
        name: Dataset name to delete.

    Returns:
        True if deleted, False if not found.
    """
    from .dataset_manager import get_repository

    return get_repository().delete(name)


def get_current_dataset_name(state: AppState) -> str | None:
    """Get the name of the currently loaded dataset, if any.

    This is stored in the state after a load operation.
    """
    return getattr(state, "_current_dataset", None)


def set_current_dataset_name(state: AppState, name: str | None) -> None:
    """Set the current dataset name in state."""
    state._current_dataset = name  # type: ignore[attr-defined]


def auto_save(state: AppState) -> None:
    """Auto-save the current state.

    Saves to the current dataset if one is loaded, otherwise derives a name
    from the first entity's label (title, name, etc.).
    Notifies connected WebSocket clients of the change.

    Args:
        state: AppState to save.
    """
    from .dataset_manager import DatasetManager, get_repository

    manager = DatasetManager(get_repository(), state)
    manager._current = get_current_dataset_name(state)
    manager.auto_save()
    set_current_dataset_name(state, manager._current)
