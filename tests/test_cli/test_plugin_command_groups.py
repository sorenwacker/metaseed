"""Plugins inject their command groups; the core command line names none.

A plugin's adapter declares its group with ``commands_ref``. The core lists the
group only while the plugin is installed and enabled, and run without it, the
group says what is missing. ``metaseed --help`` once listed ``dcat`` on an
install without rdflib. The tests announce a plugin of their own through the
registry's entry-point seam, so they prove the injection rather than a list.
"""

from __future__ import annotations

import ast
import importlib.metadata
from pathlib import Path

import pytest
import typer
from typer.testing import CliRunner

from metaseed import adapters
from metaseed.cli.output import ExitCode
from metaseed.cli.plugin_commands import register_plugin_groups
from metaseed.settings import Settings

runner = CliRunner()

demo_commands = typer.Typer(no_args_is_help=True)


@demo_commands.command()
def hello() -> None:
    """Prove the group ran."""
    typer.echo("demo says hello")


def _plugin(requires: tuple[str, ...]) -> adapters.Plugin:
    return adapters.Plugin(
        name="demo",
        adapters=(
            adapters.AdapterInfo(
                key="demo",
                name="Demo",
                description="A plugin the tests inject.",
                direction="export",
                extra="demo",
                requires=requires,
                commands_ref=f"{__name__}:demo_commands",
            ),
        ),
    )


INSTALLED = _plugin(requires=("json",))
NOT_INSTALLED = _plugin(requires=("a_module_that_is_not_installed",))


@pytest.fixture
def announce(monkeypatch: pytest.MonkeyPatch):
    def _announce(attribute: str) -> None:
        point = importlib.metadata.EntryPoint(
            "demo", f"{__name__}:{attribute}", "metaseed.plugins"
        )
        monkeypatch.setattr(adapters, "_entry_points", lambda: [point])
        adapters.reload()

    yield _announce
    monkeypatch.undo()
    adapters.reload()


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(tmp_path / "settings.json")


def _app(settings: Settings) -> typer.Typer:
    app = typer.Typer()

    @app.command()
    def version() -> None:
        """A core command, so the app is a group."""

    register_plugin_groups(app, settings)
    return app


def _listed(app: typer.Typer) -> set[str]:
    """The commands ``--help`` lists, read from the command itself.

    Not from the help text: CI renders it with colour codes between the words.
    """
    group = typer.main.get_command(app)
    return {name for name, command in group.commands.items() if not command.hidden}


def test_an_enabled_plugin_group_is_listed_and_runs(
    announce, settings: Settings
) -> None:
    announce("INSTALLED")
    app = _app(settings)
    assert "demo" in _listed(app)
    result = runner.invoke(app, ["demo", "hello"])
    assert result.exit_code == 0
    assert "demo says hello" in result.output


def test_a_disabled_plugin_group_is_hidden_and_names_the_enable_command(
    announce, settings: Settings
) -> None:
    announce("INSTALLED")
    settings.set_adapter_enabled("demo", False)
    app = _app(settings)
    assert "demo" not in _listed(app)
    result = runner.invoke(app, ["demo", "hello"])
    assert result.exit_code == ExitCode.CONFIG_ERROR
    assert "metaseed plugin enable demo" in result.output
    assert "demo says hello" not in result.output


def test_a_plugin_group_that_is_not_installed_is_hidden_and_names_the_install_command(
    announce, settings: Settings
) -> None:
    announce("NOT_INSTALLED")
    app = _app(settings)
    assert "demo" not in _listed(app)
    result = runner.invoke(app, ["demo", "hello"])
    assert result.exit_code == ExitCode.CONFIG_ERROR
    assert "uv tool install 'metaseed[demo]'" in result.output


def test_the_built_in_plugins_declare_their_groups() -> None:
    declared = {info.key for info in adapters.BUILTIN.adapters if info.commands_ref}
    assert declared == {"seek", "hub", "dcat"}


def test_the_core_command_line_imports_no_plugin_command_module() -> None:
    """The core registers what plugins declare; importing a group is a fork of that."""
    import importlib.util

    origin = importlib.util.find_spec("metaseed.cli.app").origin
    plugin_modules = {
        info.commands_ref.partition(":")[0]
        for info in adapters.all_adapters()
        if info.commands_ref
    }
    tree = ast.parse(Path(origin).read_text(encoding="utf-8"))
    imported = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    } | {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    assert not imported & plugin_modules
