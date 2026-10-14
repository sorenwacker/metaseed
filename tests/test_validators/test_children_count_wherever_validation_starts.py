"""A parent is validated with its children, wherever validation is started.

Reported as #343: importing an ENA study gave 36 runs with four files each, and
``validate_dataset`` called every run invalid: "'files' must have at least 1
item(s), but has 0". Children are separate nodes, so a parent's own list is
empty. ``client.validate()`` put them back before judging the parent; the MCP
tool and the web application each walked the tree on their own and did not, and
none of the three placed a child that an importer had linked by reference only.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from metaseed import MetaseedClient
from metaseed.facade.children import data_with_children, field_holding

EXAMPLE = "src/metaseed/examples/ena/1.0/arabidopsis-drought-rnaseq.yaml"
SRC = Path("src/metaseed")


def _walk(node):
    yield node
    for child in node.children:
        yield from _walk(child)


@pytest.fixture
def ena() -> MetaseedClient:
    client = MetaseedClient("ena", "1.0")
    client.load_yaml(EXAMPLE)
    return client


def _runs(client: MetaseedClient) -> list:
    return [
        n
        for root in client.facade.get_roots()
        for n in _walk(root)
        if n.entity_type == "Run"
    ]


def test_a_run_is_given_its_files(ena: MetaseedClient) -> None:
    run = _runs(ena)[0]
    files = [child for child in run.children if child.entity_type == "File"]
    assert files, "the example run has files"
    assert len(data_with_children(run, ena.facade)["files"]) == len(files)


def test_the_mcp_tool_counts_children(ena: MetaseedClient) -> None:
    from metaseed.agent.mcp.tools.validation import _validate_node_recursive

    results: list[dict] = []
    for root in ena.facade.get_roots():
        _validate_node_recursive(root, ena.facade, results)

    invalid = [(r["entity_type"], r["errors"]) for r in results if not r["valid"]]
    assert not invalid, invalid


def test_a_child_linked_by_reference_alone_is_counted(ena: MetaseedClient) -> None:
    """The importer's shape: a File naming its Run by ``run_ref``, recorded in no field."""
    for root in ena.facade.get_roots():
        for node in _walk(root):
            if node.entity_type == "File":
                node.parent_field = None

    issues = [(i.rule, i.message) for i in ena.validate().issues]
    assert not issues, issues


def test_the_field_is_the_one_that_takes_the_childs_type(ena: MetaseedClient) -> None:
    run = _runs(ena)[0]
    file = next(child for child in run.children if child.entity_type == "File")
    file.parent_field = None
    assert field_holding(file, ena.facade.get_helper("Run")) == "files"


def test_a_field_is_not_guessed_between_several_of_one_type() -> None:
    from types import SimpleNamespace

    parent = SimpleNamespace(
        nested_fields={"sources": "Material", "samples": "Material"}
    )
    child = SimpleNamespace(parent_field=None, entity_type="Material")
    assert field_holding(child, parent) is None

    recorded = SimpleNamespace(parent_field="samples", entity_type="Material")
    assert field_holding(recorded, parent) == "samples"


@pytest.mark.parametrize(
    "module",
    ["agent/mcp/tools/validation.py", "ui/routes/api.py", "api/validation.py"],
)
def test_no_validation_entry_point_dumps_a_node_on_its_own(module: str) -> None:
    """The defect was a second and a third tree walk, then a single-entity tool.
    Every function that hands a node to a validator must take the node's data
    from the shared function, not from the instance directly. Selected by what
    it calls rather than by name, so a renamed or new entry point is covered."""
    validators = {"validate_entity", "validate_fn", "validate_entity_with_report"}
    tree = ast.parse((SRC / module).read_text())
    callers = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef)
        and any(
            isinstance(c, ast.Call)
            and isinstance(c.func, ast.Name)
            and c.func.id in validators
            for c in ast.walk(n)
        )
    ]
    assert callers, f"{module} no longer calls a validator this gate reads"
    for caller in callers:
        source = ast.unparse(caller)
        assert "data_with_children" in source or "_data_with_children" in source, (
            f"{module}:{caller.name} validates a node without its children"
        )
        assert "instance.model_dump" not in source, (
            f"{module}:{caller.name} reads the instance directly"
        )


def test_the_mcp_single_entity_tool_counts_children(ena: MetaseedClient) -> None:
    """validate_entity dumped the node alone, so a Run with files failed min-items."""
    import json

    from metaseed.agent.mcp.server import create_server, reset_mcp_state, set_mcp_state
    from metaseed.ui.state import AppState

    state = AppState(profile="ena", version="1.0")
    state.facade = ena.facade
    reset_mcp_state()
    try:
        set_mcp_state(state)
        tool = create_server()._tool_manager._tools["validate_entity"]
        run = _runs(ena)[0]

        result = json.loads(tool.fn(node_id=run.id))

        assert result.get("valid") is True, result
    finally:
        reset_mcp_state()
