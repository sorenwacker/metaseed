"""Dataset persistence for the UI.

Provides save/load functionality for editor state, allowing users to
save their work and switch between different datasets.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .state import AppState

# Default storage location
DATASETS_DIR = Path.home() / ".local" / "share" / "metaseed" / "datasets"


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
    if not name:
        return "Dataset name is required"
    if not re.match(r"^[a-zA-Z0-9][a-zA-Z0-9_-]*$", name):
        return "Name must start with alphanumeric and contain only letters, numbers, hyphens, underscores"
    if len(name) > 64:
        return "Name must be 64 characters or less"
    return None


def list_datasets() -> list[dict[str, Any]]:
    """List all saved datasets.

    Returns:
        List of dataset info dicts with name, profile, version, entity_count, modified.
    """
    datasets_dir = get_datasets_dir()
    datasets = []

    for path in sorted(datasets_dir.glob("*.json")):
        try:
            with open(path) as f:
                data = json.load(f)

            # Count entities
            entity_count = len(data.get("entities", []))

            datasets.append(
                {
                    "name": path.stem,
                    "profile": data.get("profile", "unknown"),
                    "version": data.get("version", "unknown"),
                    "entity_count": entity_count,
                    "modified": data.get("modified", path.stat().st_mtime),
                }
            )
        except (json.JSONDecodeError, OSError):
            # Skip invalid files
            continue

    # Sort by modified time, most recent first
    datasets.sort(key=lambda d: d.get("modified", 0), reverse=True)
    return datasets


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
    error = validate_dataset_name(name)
    if error:
        raise ValueError(error)

    datasets_dir = get_datasets_dir()
    path = datasets_dir / f"{name}.json"

    # Serialize entity tree with hierarchy using unique_id for relationships
    entities = []

    def get_entity_unique_id(node: Any) -> str | None:
        """Get the unique_id from an entity node."""
        if node.instance and hasattr(node.instance, "model_dump"):
            data = node.instance.model_dump(exclude_none=True)
            return data.get("unique_id")
        return None

    def serialize_with_children(node: Any, parent_unique_id: str | None = None) -> None:
        """Recursively serialize node and all children.

        Uses unique_id for parent references instead of internal node IDs.
        """
        entity_data = _serialize_node(node)
        if entity_data:
            # Store parent relationship using unique_id (stable across reloads)
            if parent_unique_id:
                entity_data["_parent_unique_id"] = parent_unique_id
            entities.append(entity_data)

            # Get this node's unique_id for children to reference
            node_unique_id = get_entity_unique_id(node)

            # Serialize children
            for child in node.children:
                serialize_with_children(child, node_unique_id)

    for node in state.entity_tree:
        serialize_with_children(node)

    data = {
        "name": name,
        "profile": state.profile,
        "version": state.version or state.get_or_create_facade().version,
        "entities": entities,
        "modified": datetime.now().isoformat(),
    }

    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)

    return {
        "name": name,
        "profile": data["profile"],
        "version": data["version"],
        "entity_count": len(entities),
    }


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
    datasets_dir = get_datasets_dir()
    path = datasets_dir / f"{name}.json"

    if not path.exists():
        raise FileNotFoundError(f"Dataset not found: {name}")

    with open(path) as f:
        data = json.load(f)

    # Update state profile/version
    state.profile = data.get("profile", state.profile)
    state.version = data.get("version")
    state.facade = None  # Force reload with new profile
    state.reset()  # Clear existing entities

    # Load entities with hierarchy support using unique_id for relationships
    facade = state.get_or_create_facade()
    loaded_count = 0

    # First pass: create all entities and track by unique_id
    unique_id_to_node: dict[str, Any] = {}
    old_id_to_node: dict[str, Any] = {}  # For backwards compatibility
    nodes_with_parent: list[tuple[Any, str, bool]] = []  # (node, parent_ref, is_unique_id)

    for entity_data in data.get("entities", []):
        entity_type = entity_data.get("_type")
        if not entity_type:
            continue

        try:
            helper = getattr(facade, entity_type, None)
            if helper:
                # Extract parent reference - prefer new format, fall back to old
                parent_unique_id = entity_data.get("_parent_unique_id")
                old_parent_id = entity_data.get("_parent_id")  # Backwards compat
                old_node_id = entity_data.get("_node_id")  # Backwards compat

                # Remove internal fields before creating
                fields = {k: v for k, v in entity_data.items() if not k.startswith("_")}
                instance = helper.create(**fields)

                # Create node without parent initially
                node = state.add_node(entity_type, instance)
                loaded_count += 1

                # Track by unique_id for relationship restoration
                entity_unique_id = fields.get("unique_id")
                if entity_unique_id:
                    unique_id_to_node[entity_unique_id] = node

                # Track by old node_id for backwards compatibility
                if old_node_id:
                    old_id_to_node[old_node_id] = node

                # Track nodes that need parent relationship
                if parent_unique_id:
                    nodes_with_parent.append((node, parent_unique_id, True))
                elif old_parent_id:
                    nodes_with_parent.append((node, old_parent_id, False))
        except Exception:
            # Skip invalid entities
            continue

    # Second pass: restore parent-child relationships
    for node, parent_ref, is_unique_id in nodes_with_parent:
        if is_unique_id:
            parent_node = unique_id_to_node.get(parent_ref)
        else:
            # Backwards compatibility: look up by old node_id
            parent_node = old_id_to_node.get(parent_ref)

        if parent_node:
            # Remove from root level
            state.entity_tree = [n for n in state.entity_tree if n.id != node.id]

            # Add as child of parent
            node.parent_id = parent_node.id
            parent_node.children.append(node)

    return {
        "name": name,
        "profile": state.profile,
        "version": state.version,
        "entity_count": loaded_count,
    }


def delete_dataset(name: str) -> bool:
    """Delete a dataset.

    Args:
        name: Dataset name to delete.

    Returns:
        True if deleted, False if not found.
    """
    datasets_dir = get_datasets_dir()
    path = datasets_dir / f"{name}.json"

    if path.exists():
        path.unlink()
        return True
    return False


def get_current_dataset_name(state: AppState) -> str | None:
    """Get the name of the currently loaded dataset, if any.

    This is stored in the state after a load operation.
    """
    return getattr(state, "_current_dataset", None)


def set_current_dataset_name(state: AppState, name: str | None) -> None:
    """Set the current dataset name in state."""
    state._current_dataset = name  # type: ignore[attr-defined]


def _serialize_node(node: Any) -> dict[str, Any] | None:
    """Serialize a TreeNode to a dict."""
    if not node.instance:
        return None

    if hasattr(node.instance, "model_dump"):
        data = node.instance.model_dump(exclude_none=True)
    else:
        return None

    # Add entity type for reconstruction
    data["_type"] = node.entity_type
    return data


def _get_default_dataset_name(state: AppState) -> str:
    """Get a default dataset name from the first entity's label.

    Args:
        state: AppState to get name from.

    Returns:
        A sanitized name suitable for a dataset filename.
    """
    if state.entity_tree:
        label = state.entity_tree[0].label
        if label and label != f"New {state.entity_tree[0].entity_type}":
            # Sanitize: replace spaces/special chars with hyphens, lowercase
            name = re.sub(r"[^a-zA-Z0-9]+", "-", label).strip("-").lower()
            if name and len(name) <= 64:
                return name
    return "autosave"


def auto_save(state: AppState) -> None:
    """Auto-save the current state.

    Saves to the current dataset if one is loaded, otherwise derives a name
    from the first entity's label (title, name, etc.).
    Notifies connected WebSocket clients of the change.

    Args:
        state: AppState to save.
    """
    current = get_current_dataset_name(state)
    name = current or _get_default_dataset_name(state)

    try:
        result = save_dataset(state, name)
        if not current:
            set_current_dataset_name(state, name)

        # Notify WebSocket clients
        from metaseed.ui.websocket import notify_state_changed

        notify_state_changed(
            event="state_changed",
            dataset=name,
            entity_count=result.get("entity_count", 0),
        )
    except (ValueError, OSError):
        # Silently fail on auto-save errors
        pass
