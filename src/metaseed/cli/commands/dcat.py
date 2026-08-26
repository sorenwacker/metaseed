"""`metaseed dcat` — the catalogue record of a dataset.

Uses :func:`metaseed.dcat.export.build_card` and the serializers the DCAT page
uses, and stores the card's fields where the page stores them: on the dataset's
:class:`~metaseed.repositories.dataset_repository.CatalogMetadata`.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Annotated

import typer

from metaseed.cli.output import ExitCode, echo_error, echo_success
from metaseed.cli.workspace import emit, open_dataset, repository
from metaseed.repositories.dataset_repository import CatalogMetadata

app = typer.Typer(name="dcat", no_args_is_help=True, help="Catalogue records.")


@app.command("show")
def show(
    dataset: Annotated[str, typer.Argument(help="Dataset name")],
    fmt: Annotated[
        str, typer.Option("--format", "-f", help="jsonld, turtle, or fields")
    ] = "jsonld",
) -> None:
    """Print a dataset's catalogue card."""
    from metaseed.dcat.export import build_card
    from metaseed.dcat.serialize import to_jsonld, to_turtle

    client, data = open_dataset(dataset)
    if fmt == "fields":
        emit(asdict(data.catalog_metadata) if data.catalog_metadata else {})
        return
    card = build_card(client, catalog_metadata=data.catalog_metadata)
    if card is None:
        echo_error(f"'{dataset}' holds no entities, so it has no catalogue card.")
        raise typer.Exit(ExitCode.INPUT_ERROR)
    if fmt not in ("jsonld", "turtle"):
        echo_error("Format is 'jsonld', 'turtle' or 'fields'.")
        raise typer.Exit(ExitCode.INPUT_ERROR)
    typer.echo(to_jsonld(card) if fmt == "jsonld" else to_turtle(card))


@app.command("set")
def set_fields(
    dataset: Annotated[str, typer.Argument(help="Dataset name")],
    title: Annotated[str | None, typer.Option("--title")] = None,
    description: Annotated[str | None, typer.Option("--description")] = None,
    publisher: Annotated[str | None, typer.Option("--publisher")] = None,
    license_: Annotated[str | None, typer.Option("--license")] = None,
    landing_page: Annotated[str | None, typer.Option("--landing-page")] = None,
    keywords: Annotated[
        list[str] | None, typer.Option("--keyword", help="Repeatable")
    ] = None,
    themes: Annotated[
        list[str] | None, typer.Option("--theme", help="Repeatable")
    ] = None,
) -> None:
    """Set the catalogue fields a profile cannot derive from its entities."""
    store = repository()
    data = store.load(dataset) if store.exists(dataset) else None
    if data is None:
        echo_error(f"No dataset named '{dataset}'.")
        raise typer.Exit(ExitCode.INPUT_ERROR)
    current = data.catalog_metadata or CatalogMetadata()
    given = {
        "title": title,
        "description": description,
        "publisher": publisher,
        "license": license_,
        "landing_page": landing_page,
    }
    for name, value in given.items():
        if value is not None:
            setattr(current, name, value)
    if keywords:
        current.keywords = list(keywords)
    if themes:
        current.themes = list(themes)
    data.catalog_metadata = current
    store.save(dataset, data)
    echo_success(f"Updated the catalogue card of '{dataset}'.")
