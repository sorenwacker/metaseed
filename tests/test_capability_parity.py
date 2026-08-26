"""The CLI reaches everything the MCP server and the web interface reach.

A capability that exists only as an MCP tool is unusable from a script; one
that exists only as a route is unusable without a browser. ``docs/specification/
capability-parity.md`` records which command, tool and route serve each
capability, and this gate holds the document and the three surfaces to each
other in both directions: a tool or a state-changing route with no row fails,
and so does a row naming a command that does not exist.

Read-only ``GET`` routes are not enumerated: a rendered page, a form fragment
or a progress poll is a view of a capability, not one of its own. The rule and
its exemptions are stated on the page itself.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import typer

PARITY_DOC = (
    Path(__file__).resolve().parent.parent / "docs/specification/capability-parity.md"
)
TABLE_HEADING = "## The table"
EXEMPTIONS_HEADING = "## Exemptions"


def _cells(line: str) -> list[set[str]]:
    """The back-ticked names in each column of one markdown table row."""
    return [set(re.findall(r"`([^`]+)`", column)) for column in line.split("|")[1:-1]]


def _table_rows() -> list[list[set[str]]]:
    """Every capability row: ``[capabilities, cli, mcp, ui]`` as name sets."""
    text = PARITY_DOC.read_text()
    section = text[text.index(TABLE_HEADING) : text.index(EXEMPTIONS_HEADING)]
    rows = [_cells(line) for line in section.splitlines() if line.startswith("| ")]
    return [row for row in rows if len(row) == 4 and (row[1] or row[2] or row[3])]


def _column(index: int) -> set[str]:
    return {name for row in _table_rows() for name in row[index]}


def _exempt_routes() -> set[str]:
    """Routes the page excuses, with a written reason."""
    text = PARITY_DOC.read_text()
    section = text[text.index(EXEMPTIONS_HEADING) :]
    exempt: set[str] = set()
    for line in section.splitlines():
        if not line.startswith("| `"):
            continue
        route_column, reason_column = line.split("|")[1], line.split("|")[2]
        if reason_column.strip():
            exempt |= set(re.findall(r"`([^`]+)`", route_column))
    return exempt


def _mcp_tools() -> set[str]:
    from metaseed.agent.mcp.server import create_server

    return set(create_server()._tool_manager._tools)


def _cli_commands(app: typer.Typer | None = None, prefix: str = "") -> set[str]:
    """Every command the Typer application registers, groups included."""
    if app is None:
        from metaseed.cli import app as root

        app = root
    names = {
        f"{prefix}{command.name or command.callback.__name__.replace('_', '-')}".strip()
        for command in app.registered_commands
    }
    for group in app.registered_groups:
        group_app = group.typer_instance
        if group_app is None:
            continue
        names |= _cli_commands(group_app, prefix=f"{prefix}{group.name} ")
    return names


def _routes() -> set[str]:
    """Every route the application serves, as ``METHOD /path``."""
    from metaseed.ui.app import create_app
    from metaseed.ui.state import AppState

    found: set[str] = set()

    def walk(routes: list[Any]) -> None:
        for route in routes:
            # A router included into the app is wrapped; its own routes hang
            # off ``original_router``, so a plain walk misses the spec builder.
            inner = getattr(route, "original_router", None)
            if inner is not None:
                walk(inner.routes)
                continue
            if hasattr(route, "routes") and not hasattr(route, "path"):
                walk(route.routes)
                continue
            for method in sorted(
                (getattr(route, "methods", None) or set()) - {"HEAD", "OPTIONS"}
            ):
                found.add(f"{method} {route.path}")

    walk(create_app(AppState()).routes)
    return found


def test_every_mcp_tool_has_a_cli_command() -> None:
    """An agent can do nothing a person at a terminal cannot."""
    documented = _column(2)
    missing = sorted(_mcp_tools() - documented)
    assert not missing, f"MCP tools with no row in {PARITY_DOC.name}: {missing}"
    rows_without_cli = [
        sorted(row[2]) for row in _table_rows() if row[2] and not row[1]
    ]
    assert not rows_without_cli, (
        f"MCP tools whose row names no CLI command: {rows_without_cli}"
    )


def test_the_table_names_no_tool_that_does_not_exist() -> None:
    invented = sorted(_column(2) - _mcp_tools())
    assert not invented, f"rows naming MCP tools that do not exist: {invented}"


def test_every_documented_cli_command_exists() -> None:
    """A renamed or unwritten command is caught here, not by a user."""
    missing = sorted(_column(1) - _cli_commands())
    assert not missing, (
        f"commands named in {PARITY_DOC.name} that the CLI does not have: {missing}"
    )


def test_every_cli_command_is_documented() -> None:
    """The reverse direction, so the table cannot rot into fiction."""
    undocumented = sorted(_cli_commands() - _column(1))
    assert not undocumented, (
        f"CLI commands with no row in {PARITY_DOC.name}: {undocumented}"
    )


def test_every_state_changing_route_is_accounted_for() -> None:
    """A POST, PUT or DELETE is a capability; it needs a command or a reason."""
    mutating = {route for route in _routes() if not route.startswith("GET ")}
    missing = sorted(mutating - _column(3) - _exempt_routes())
    assert not missing, f"state-changing routes with no row and no exemption: {missing}"


def test_the_table_names_no_route_that_does_not_exist() -> None:
    invented = sorted(_column(3) - _routes())
    assert not invented, f"rows naming routes that do not exist: {invented}"


class TestTheGateCatchesWhatItClaims:
    """The gate must fail on a planted violation, or it guards nothing."""

    def test_it_sees_an_undocumented_tool(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        planted = _mcp_tools() | {"an_undocumented_tool"}
        monkeypatch.setattr("tests.test_capability_parity._mcp_tools", lambda: planted)
        with pytest.raises(AssertionError, match="an_undocumented_tool"):
            test_every_mcp_tool_has_a_cli_command()

    def test_it_sees_a_command_that_does_not_exist(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        planted = _cli_commands() - {"version"}
        monkeypatch.setattr(
            "tests.test_capability_parity._cli_commands", lambda: planted
        )
        with pytest.raises(AssertionError, match="version"):
            test_every_documented_cli_command_exists()

    def test_it_sees_an_unaccounted_route(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        planted = _routes() | {"POST /an-unaccounted-route"}
        monkeypatch.setattr("tests.test_capability_parity._routes", lambda: planted)
        with pytest.raises(AssertionError, match="an-unaccounted-route"):
            test_every_state_changing_route_is_accounted_for()

    def test_the_table_is_not_empty(self) -> None:
        # An empty parse would make every check above vacuously green.
        assert len(_table_rows()) > 50
        assert len(_column(1)) > 50
