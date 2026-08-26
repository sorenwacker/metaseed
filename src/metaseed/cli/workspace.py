"""Opening a saved dataset from the command line, and writing it back.

The MCP server and the web interface both act on one session's in-memory
dataset; a command line has no session, so every command names the dataset it
acts on. :func:`open_dataset` loads it into a :class:`MetaseedClient` — the
same object the routes and the tools work through — and :func:`save_dataset`
writes the result back under the same name, keeping the fields the repository
records (creation time, catalogue card, hub provenance) intact.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import typer

from metaseed.cli.output import ExitCode, echo_error
from metaseed.repositories.dataset_repository import DatasetData
from metaseed.repositories.filesystem_dataset import FilesystemDatasetRepository

if TYPE_CHECKING:
    from metaseed.api.client import MetaseedClient


def repository() -> FilesystemDatasetRepository:
    """The saved-dataset store this machine uses."""
    return FilesystemDatasetRepository()


def load_data(name: str) -> DatasetData:
    """One saved dataset, or exit with a message naming it.

    Args:
        name: The dataset's name.

    Raises:
        typer.Exit: With :data:`ExitCode.INPUT_ERROR` when there is no such
            dataset.
    """
    try:
        return repository().load(name)
    except FileNotFoundError:
        echo_error(
            f"No dataset named '{name}'. `metaseed dataset list` shows what is saved."
        )
        raise typer.Exit(ExitCode.INPUT_ERROR) from None


def open_dataset(name: str) -> tuple[MetaseedClient, DatasetData]:
    """A saved dataset as a loaded client, with the record it came from.

    Args:
        name: The dataset's name.

    Returns:
        The client holding its entities, and the stored record.

    Raises:
        typer.Exit: When the dataset or its profile cannot be loaded.
    """
    from metaseed.api.client import MetaseedClient

    data = load_data(name)
    try:
        client = MetaseedClient(data.profile, data.version)
    except Exception as exc:
        echo_error(
            f"Dataset '{name}' names profile {data.profile} {data.version}, which "
            f"could not be loaded: {exc}"
        )
        raise typer.Exit(ExitCode.CONFIG_ERROR) from exc
    if data.entities:
        # A node the profile cannot place is dropped by the load. Saving
        # serializes what loaded, so going on would write the truncation back
        # over the file -- the command refuses instead, naming what it could
        # not place.
        skipped: list[str] = []
        client.load(
            {"entities": data.entities},
            on_skip=lambda node: skipped.append(f"{node.entity_type} ({node.reason})"),
        )
        if skipped:
            echo_error(
                f"'{name}' holds {len(skipped)} entities profile {data.profile} "
                f"{data.version} cannot place, and changing it would lose them: "
                + "; ".join(sorted(set(skipped))[:5])
            )
            raise typer.Exit(ExitCode.CONFIG_ERROR)
    return client, data


def save_dataset(name: str, client: MetaseedClient, data: DatasetData) -> None:
    """Write a client's entities back under ``name``, keeping the record's fields."""
    data.entities = client.serialize()["entities"]
    repository().save(name, data)


def emit(value: Any) -> None:
    """Print a result as JSON, so a script can read what a person reads."""
    typer.echo(json.dumps(value, indent=2, default=str))


def parse_assignments(values: list[str] | None) -> dict[str, Any]:
    """``--set name=value`` pairs as a dictionary.

    A value that parses as JSON is used as JSON, so lists and numbers survive;
    anything else stays a string.

    Args:
        values: The raw ``name=value`` strings.

    Raises:
        typer.Exit: When an entry has no ``=``.
    """
    fields: dict[str, Any] = {}
    for raw in values or []:
        name, separator, value = raw.partition("=")
        if not separator:
            echo_error(f"'{raw}' is not name=value")
            raise typer.Exit(ExitCode.INPUT_ERROR)
        try:
            fields[name] = json.loads(value)
        except json.JSONDecodeError:
            fields[name] = value
    return fields
