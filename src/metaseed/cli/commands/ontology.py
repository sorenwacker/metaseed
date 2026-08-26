"""`metaseed ontology` — looking terms up and checking the ones a dataset uses.

Every command goes through :func:`metaseed.services.terms.get_term_source`, the
router the web interface and the MCP tools use, so a term found here is the term
they find: local vocabularies first, then the configured lookup service.
"""

from __future__ import annotations

from typing import Annotated

import typer

from metaseed.cli.output import ExitCode, echo_error
from metaseed.cli.workspace import emit, open_dataset

app = typer.Typer(name="ontology", no_args_is_help=True, help="Ontology terms.")


@app.command("search")
def search(
    query: Annotated[str, typer.Argument(help="What to search for")],
    ontology: Annotated[
        str | None, typer.Option("--ontology", "-o", help="Restrict to one")
    ] = None,
    limit: Annotated[int, typer.Option("--limit", "-n")] = 10,
) -> None:
    """Search the ontologies for a term."""
    from metaseed.services.terms import get_term_source

    try:
        results = get_term_source().search_sync(query, ontology=ontology, limit=limit)
    except Exception as exc:
        echo_error(f"Search for '{query}' failed: {exc}")
        raise typer.Exit(ExitCode.INPUT_ERROR) from exc
    emit([term.__dict__ if hasattr(term, "__dict__") else term for term in results])


@app.command("term")
def term(
    term_id: Annotated[str, typer.Argument(help="Term id, e.g. PO:0007113")],
) -> None:
    """Look one term up by its identifier."""
    from metaseed.services.terms import get_term_source

    try:
        found = get_term_source().get_term_sync(term_id)
    except Exception as exc:
        echo_error(f"Lookup of '{term_id}' failed: {exc}")
        raise typer.Exit(ExitCode.INPUT_ERROR) from exc
    if found is None:
        echo_error(f"No term '{term_id}'.")
        raise typer.Exit(ExitCode.INPUT_ERROR)
    emit(found.__dict__ if hasattr(found, "__dict__") else found)


@app.command("suggest")
def suggest(
    text: Annotated[str, typer.Argument(help="The value to find a term for")],
    ontology: Annotated[str | None, typer.Option("--ontology", "-o")] = None,
    limit: Annotated[int, typer.Option("--limit", "-n")] = 5,
) -> None:
    """Suggest terms for a free-text value."""
    from metaseed.services.terms import get_term_source

    try:
        results = get_term_source().search_sync(text, ontology=ontology, limit=limit)
    except Exception as exc:
        echo_error(f"Suggesting a term for '{text}' failed: {exc}")
        raise typer.Exit(ExitCode.INPUT_ERROR) from exc
    emit([term.__dict__ if hasattr(term, "__dict__") else term for term in results])


@app.command("list")
def list_ontologies(
    limit: Annotated[int, typer.Option("--limit", "-n")] = 50,
) -> None:
    """List the ontologies the lookup service offers."""
    from metaseed.services.terms import get_term_source

    try:
        emit(get_term_source().list_ontologies_sync(limit=limit))
    except LookupError as exc:
        echo_error(str(exc))
        raise typer.Exit(ExitCode.CONFIG_ERROR) from exc
    except Exception as exc:
        # A service that does not answer is "not checked", not a failure of
        # anything the user holds.
        emit({"checked": False, "reason": str(exc)})


@app.command("validate")
def validate_terms(
    dataset: Annotated[str, typer.Argument(help="Dataset name")],
) -> None:
    """Check that every ontology term a dataset uses resolves.

    A term source that cannot be reached is reported as *not checked*, never as
    a failure: someone else's downtime must not invalidate the data.
    """
    from metaseed.services.term_check import check_term

    client, _data = open_dataset(dataset)
    checked: list[dict[str, object]] = []
    for entity in client.serialize()["entities"]:
        entity_type = str(entity.get("_type", "?"))
        for field_name, value in entity.items():
            if not isinstance(value, str) or ":" not in value:
                continue
            if "ontology" not in field_name and "_term" not in field_name:
                continue
            verdict = check_term(value, ontologies=None)
            checked.append(
                {
                    "entity": entity_type,
                    "field": field_name,
                    "term": value,
                    "outcome": getattr(verdict.outcome, "value", str(verdict.outcome)),
                    "message": verdict.message,
                }
            )
    emit({"dataset": dataset, "terms": checked})
