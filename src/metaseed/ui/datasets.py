"""Dataset persistence for the UI.

This module provides helper functions for dataset operations.
All operations use DatasetManagerFactory for proper dependency injection.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict
from typing import TYPE_CHECKING, Any

from metaseed.repositories.dataset_repository import DatasetData, DatasetRepository

if TYPE_CHECKING:
    from collections.abc import Iterable

    from .dataset_manager import DatasetManagerFactory
    from .state import AppState

from contextvars import ContextVar, Token

# Context variable for request-scoped factory
_factory_var: ContextVar[DatasetManagerFactory | None] = ContextVar(
    "dataset_factory", default=None
)


def factory_token(
    factory: DatasetManagerFactory | None,
) -> Token[DatasetManagerFactory | None]:
    """Bind ``factory`` and return the token that restores what it replaced.

    For a caller that binds a factory for the duration of a block and must put
    the previous one back afterwards, rather than clearing it.

    Args:
        factory: The factory to bind, or None to unbind.

    Returns:
        The token to pass to :func:`reset_factory`.
    """
    return _factory_var.set(factory)


def reset_factory(token: Token[DatasetManagerFactory | None]) -> None:
    """Restore the factory that was bound before ``token`` was issued.

    Args:
        token: The token returned by :func:`factory_token`.
    """
    _factory_var.reset(token)


def set_factory(factory: DatasetManagerFactory | None) -> None:
    """Bind the factory this session's saves and loads go through.

    Called by whoever composes the application -- the web app, the MCP host, a
    test -- so that every path in the session writes to one repository. Passing
    None clears the binding, and the next resolution creates a private default.

    Args:
        factory: The factory to use, or None to unbind.
    """
    _factory_var.set(factory)


def _resolve_factory() -> DatasetManagerFactory:
    """The factory this session saves and loads through.

    Returns whatever was bound by :func:`set_factory`, and otherwise creates a
    private one and binds it. It does not look around for an owner: this module
    used to import the MCP server to ask whether an agent session was running,
    which made the interface depend on the agent layer, hid the dependency from
    every signature, and left a test no way to supply its own factory except by
    patching internals. The owner now pushes its factory in.

    Returns:
        The dataset factory to use for repository-backed operations.
    """
    factory = _factory_var.get()
    if factory is None:
        from .dataset_manager import DatasetManagerFactory

        factory = DatasetManagerFactory()
        _factory_var.set(factory)
    return factory


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

    return import_payload(state, payload)


def import_payload(state: AppState, payload: dict[str, Any]) -> dict[str, Any]:
    """Install an already-parsed dataset payload into ``state``.

    The dict-level half of :func:`import_dataset`, shared with the Excel
    importer so both formats load through one code path.
    """
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


class ImportSourceError(ValueError):
    """A source-database import could not be completed."""


class NoImporterError(ImportSourceError):
    """The profile declares no importer, so nothing could be fetched."""


class EmptyImportError(ImportSourceError):
    """The importer ran but the record held no metadata.

    Separate from :class:`NoImporterError` because the remedy differs: retype
    the accession rather than choose another profile.
    """


def import_from_source(state: AppState, profile: str, value: str) -> dict[str, Any]:
    """Import a public record into ``state`` through the adapter registry.

    Resolves the profile's registered importer (:func:`metaseed.adapters.
    import_action_for_profile`), runs it, and installs the result as the dataset
    being edited. Every host — the web UI route, the MCP tool — goes through
    here, so an import cannot behave differently depending on where it started.

    The state is replaced only once the import has produced entities: a wrong
    accession leaves the current dataset intact.

    Args:
        state: AppState the imported dataset replaces.
        profile: Profile to import into (e.g. ``"pride"``, ``"miappe"``).
        value: The single string the importer takes — an accession for the
            archives, a server URL for BrAPI.

    Returns:
        Dict with the imported ``profile``, ``version``, ``root_count`` and
        ``entity_count``.

    Raises:
        NoImporterError: If no installed adapter imports into ``profile``.
        EmptyImportError: If the importer returned no entities.
        ModuleNotFoundError: If the adapter's extra is not installed. Left to
            propagate: no host can install a package on the user's behalf.
    """
    from metaseed import adapters

    action = adapters.import_action_for_profile(profile)
    if action is None:
        importable = ", ".join(adapters.importable_profiles()) or "none"
        raise NoImporterError(
            f"No importer for profile '{profile}'. Importable profiles: {importable}."
        )

    client = action.resolve()(value)
    if not client.get_roots():
        raise EmptyImportError(
            f"'{value}' returned no {profile} metadata; nothing was imported."
        )

    state.profile = client.profile
    state.version = client.version
    # Adopt the importer's facade wholesale rather than replaying entities into
    # the old one: it already holds the validated nested structure, and
    # state.reset() would clear the entities that were just fetched.
    state.facade = client.facade
    state.editing_node_id = None
    state.invalidate_cache()

    return {
        "profile": client.profile,
        "version": client.version,
        "root_count": len(client.get_roots()),
        "entity_count": len(state.nodes_by_id),
    }


#: Identifiers one New Dataset submission takes; they are fetched in turn.
MAX_IMPORTED_AT_ONCE = 20

_NOT_NAME_CHARACTERS = re.compile(r"[^a-zA-Z0-9_-]+")


def _name_part(text: str, length: int) -> str:
    """``text`` reduced to the characters a dataset name may hold."""
    return _NOT_NAME_CHARACTERS.sub("_", text).strip("_-")[:length].strip("_-")


def imported_dataset_name(
    title: str, identifier: str, taken: Iterable[str]
) -> str | None:
    """The name an imported record is saved under, or ``None`` if none is free.

    The record's title names the dataset, else its identifier. Where that name
    is taken the identifier is appended; where that is taken too the record is
    already imported.

    Args:
        title: The title the root record carries at the repository.
        identifier: The accession or server URL the record was fetched by.
        taken: Names of the datasets that exist.

    Returns:
        A name :func:`validate_dataset_name` accepts, or ``None``.
    """
    taken = set(taken)
    tail = _name_part(identifier, 23)
    head = _name_part(title, 40) or tail
    for name in dict.fromkeys((head, f"{head}_{tail}")):
        if name and name not in taken and validate_dataset_name(name) is None:
            return name
    return None


def source_did_not_answer(exc: Exception) -> bool:
    """Whether an import failed on the repository's availability, not the identifier."""
    try:
        import httpx
    except ModuleNotFoundError:  # an importer that does not use httpx raised it
        transport_error: tuple[type[Exception], ...] = ()
    else:
        transport_error = (httpx.TransportError,)
    if isinstance(exc, transport_error):
        return True
    status = getattr(getattr(exc, "response", None), "status_code", None)
    return isinstance(status, int) and status >= 500


def import_as_new_dataset(state: AppState, profile: str, value: str) -> dict[str, Any]:
    """Import one record and save it as a dataset named by the record.

    Never raises for a failed import: the outcome says what happened, so a
    list of identifiers can be worked through whatever any one of them does.

    Args:
        state: AppState the imported dataset is installed in before saving.
        profile: Profile whose registered importer fetches the record.
        value: The accession or server URL.

    Returns:
        Dict with ``identifier``, ``status`` (``imported``, ``empty``,
        ``duplicate``, ``failed`` or ``not_checked``), and ``name`` or
        ``detail`` where the status has one.

    Raises:
        NoImporterError: If no installed adapter imports into ``profile``.
    """
    try:
        import_from_source(state, profile, value)
    except NoImporterError:
        raise
    except EmptyImportError:
        return {"identifier": value, "status": "empty"}
    except Exception as exc:
        status = "not_checked" if source_did_not_answer(exc) else "failed"
        return {"identifier": value, "status": status, "detail": str(exc)[:200]}

    roots = state.get_or_create_facade().get_roots()
    instance = roots[0].instance if roots else None
    data = instance.model_dump() if instance is not None else {}
    title = str(data.get("title") or "")
    name = imported_dataset_name(title, value, (d["name"] for d in list_datasets()))
    if name is None:
        return {"identifier": value, "status": "duplicate", "detail": title}
    save_dataset(state, name)
    set_current_dataset_name(state, name)
    return {"identifier": value, "status": "imported", "name": name}


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


def auto_save(state: AppState, factory: DatasetManagerFactory | None = None) -> None:
    """Auto-save the current state.

    Saves to the current dataset if one is loaded, otherwise derives a name
    from the first entity's label (title, name, etc.).
    Notifies connected WebSocket clients of the change.

    Args:
        state: AppState to save.
        factory: The factory to save through. A caller serving a specific
            session passes its own, so the write lands in that session's
            repository; resolving ambiently here would send reads and writes to
            different places once a host serves more than one caller.
    """
    factory = factory or _resolve_factory()
    manager = factory.get_manager(state)
    manager.current_dataset = get_current_dataset_name(state)
    manager.auto_save()
    set_current_dataset_name(state, manager.current_dataset)
