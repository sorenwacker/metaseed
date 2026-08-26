"""`metaseed entity` — the entities inside one saved dataset.

Every command loads the named dataset, changes it through
:class:`~metaseed.api.client.MetaseedClient` — the object the web interface and
the MCP tools also work through — and writes it back.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Any

import typer

from metaseed.cli.output import ExitCode, echo_error, echo_success
from metaseed.cli.workspace import emit, open_dataset, parse_assignments, save_dataset

app = typer.Typer(
    name="entity", no_args_is_help=True, help="Entities inside a dataset."
)

SET_HELP = "Field as name=value; repeatable. A JSON value is read as JSON."


def _walk(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Every entity of a tree serialization, flat, each keeping its id.

    The flat serialization carries no ids -- it is what a dataset file holds --
    so a command that has to name an entity reads the tree instead.
    """
    found: list[dict[str, Any]] = []
    for node in nodes:
        found.append(
            {
                "id": node["id"],
                "type": node["entity_type"],
                "label": node["label"],
                "data": node["data"],
            }
        )
        found.extend(_walk(node.get("children") or []))
    return found


@app.command("list")
def list_entities(
    dataset: Annotated[str, typer.Argument(help="Dataset name")],
    entity_type: Annotated[str | None, typer.Option("--type", "-t")] = None,
) -> None:
    """List a dataset's entities, optionally of one type."""
    client, _data = open_dataset(dataset)
    entities = _walk(client.serialize(format="tree")["tree"])
    if entity_type:
        entities = [e for e in entities if e["type"] == entity_type]
    emit(entities)


@app.command("show")
def show_entity(
    dataset: Annotated[str, typer.Argument(help="Dataset name")],
    entity_id: Annotated[str, typer.Argument(help="Entity id")],
) -> None:
    """Print one entity's stored values."""
    client, _data = open_dataset(dataset)
    try:
        entity = client.get_entity(entity_id)
    except Exception as exc:
        echo_error(f"No entity '{entity_id}' in '{dataset}': {exc}")
        raise typer.Exit(ExitCode.INPUT_ERROR) from exc
    emit({"id": entity.id, "type": entity.entity_type, "data": entity.data})


@app.command("tree")
def entity_tree(dataset: Annotated[str, typer.Argument(help="Dataset name")]) -> None:
    """Print the dataset's entities as a nested tree."""
    client, _data = open_dataset(dataset)
    emit(client.serialize(format="tree"))


@app.command("create")
def create_entity(
    dataset: Annotated[str, typer.Argument(help="Dataset name")],
    entity_type: Annotated[str, typer.Argument(help="Entity type")],
    set_: Annotated[
        list[str] | None, typer.Option("--set", "-s", help=SET_HELP)
    ] = None,
    parent: Annotated[
        str | None, typer.Option("--parent", help="Parent entity id")
    ] = None,
) -> None:
    """Add one entity, optionally under a parent."""
    fields = parse_assignments(set_)
    client, data = open_dataset(dataset)
    try:
        entity = client.create_entity(entity_type, fields, parent_id=parent)
    except Exception as exc:
        echo_error(str(exc))
        raise typer.Exit(ExitCode.VALIDATION_ERROR) from exc
    save_dataset(dataset, client, data)
    echo_success(f"Created {entity_type} {entity.id} in '{dataset}'.")


@app.command("update")
def update_entity(
    dataset: Annotated[str, typer.Argument(help="Dataset name")],
    entity_id: Annotated[str, typer.Argument(help="Entity id")],
    set_: Annotated[
        list[str] | None, typer.Option("--set", "-s", help=SET_HELP)
    ] = None,
) -> None:
    """Change named fields of one entity; unnamed fields keep their values."""
    fields = parse_assignments(set_)
    client, data = open_dataset(dataset)
    try:
        # Merge, as the tool and the form do: a command that named one field
        # must not blank the others.
        current = dict(client.get_entity(entity_id).data)
        current.update(fields)
        client.update_entity(entity_id, current)
    except Exception as exc:
        echo_error(str(exc))
        raise typer.Exit(ExitCode.VALIDATION_ERROR) from exc
    save_dataset(dataset, client, data)
    echo_success(f"Updated {entity_id} in '{dataset}'.")


@app.command("delete")
def delete_entity(
    dataset: Annotated[str, typer.Argument(help="Dataset name")],
    entity_id: Annotated[str, typer.Argument(help="Entity id")],
) -> None:
    """Remove one entity."""
    client, data = open_dataset(dataset)
    try:
        client.delete_entity(entity_id)
    except Exception as exc:
        echo_error(f"No entity '{entity_id}' in '{dataset}': {exc}")
        raise typer.Exit(ExitCode.INPUT_ERROR) from exc
    save_dataset(dataset, client, data)
    echo_success(f"Deleted {entity_id} from '{dataset}'.")


@app.command("bulk-update")
def bulk_update(
    dataset: Annotated[str, typer.Argument(help="Dataset name")],
    entity_type: Annotated[
        str, typer.Option("--type", "-t", help="Entity type to change")
    ],
    set_: Annotated[
        list[str] | None, typer.Option("--set", "-s", help=SET_HELP)
    ] = None,
) -> None:
    """Set the same fields on every entity of one type."""
    fields = parse_assignments(set_)
    client, data = open_dataset(dataset)
    changed = []
    for entity in _walk(client.serialize(format="tree")["tree"]):
        if entity["type"] != entity_type:
            continue
        try:
            client.update_entity(entity["id"], {**entity["data"], **fields})
        except Exception as exc:
            echo_error(f"{entity['id']}: {exc}")
            raise typer.Exit(ExitCode.VALIDATION_ERROR) from exc
        changed.append(entity["id"])
    save_dataset(dataset, client, data)
    echo_success(f"Updated {len(changed)} {entity_type} entities in '{dataset}'.")


@app.command("batch-create")
def batch_create(
    dataset: Annotated[str, typer.Argument(help="Dataset name")],
    source: Annotated[Path, typer.Argument(help="JSON or YAML list of entities")],
) -> None:
    """Add several entities from a file, root-first.

    Each item names its ``_type`` and its fields; ``_parent`` names an earlier
    item's index or an existing entity id, so a parent and its children can
    land together.
    """
    import yaml

    if not source.exists():
        echo_error(f"No such file: {source}")
        raise typer.Exit(ExitCode.INPUT_ERROR)
    payload: Any = yaml.safe_load(source.read_text())
    items = payload.get("entities") if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        echo_error(f"{source} holds no list of entities.")
        raise typer.Exit(ExitCode.INPUT_ERROR)
    client, data = open_dataset(dataset)
    created: list[str] = []
    for position, item in enumerate(items):
        if not isinstance(item, dict) or "_type" not in item:
            echo_error(f"Item {position} names no _type.")
            raise typer.Exit(ExitCode.INPUT_ERROR)
        fields = {k: v for k, v in item.items() if not k.startswith("_")}
        raw_parent = item.get("_parent")
        parent_id: str | None = None
        if isinstance(raw_parent, int):
            parent_id = created[raw_parent]
        elif isinstance(raw_parent, str):
            parent_id = created[int(raw_parent)] if raw_parent.isdigit() else raw_parent
        try:
            entity = client.create_entity(
                str(item["_type"]), fields, parent_id=parent_id
            )
        except Exception as exc:
            echo_error(f"Item {position} ({item['_type']}): {exc}")
            raise typer.Exit(ExitCode.VALIDATION_ERROR) from exc
        created.append(entity.id)
    save_dataset(dataset, client, data)
    typer.echo(json.dumps({"created": created}, indent=2))
