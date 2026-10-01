"""An adapter can come from outside metaseed, like a profile can (#285).

A package declares a ``metaseed.adapters.Plugin`` under the entry point group
``metaseed.plugins``; its adapters appear beside the built-in ones, its specs
load and its examples are offered. A plugin that cannot be loaded is reported
with its reason, never silently absent, and the others still load.

The plugin here is written into a temporary package and announced through a
seam over ``importlib.metadata.entry_points``, so nothing is installed.
"""

from __future__ import annotations

import importlib.metadata
import shutil
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from metaseed import adapters
from metaseed.specs.loader import SpecLoader

ROOT = Path(__file__).resolve().parents[1] / "src" / "metaseed"
GROUP = "metaseed.plugins"

REGISTRY = """
from pathlib import Path

from metaseed.adapters import Action, AdapterInfo, Plugin

HERE = Path(__file__).parent
PLUGIN = Plugin(
    name="demo",
    adapters=(
        AdapterInfo(
            key="demo",
            name="Demo archive",
            description="A repository metaseed does not ship an adapter for.",
            direction="export",
            extra="demo-plugin",
            requires=(),
            actions=(
                Action(
                    "export",
                    "demo",
                    "Demo file",
                    "demo_plugin.heavy:export",
                    profiles=("demo-profile",),
                ),
            ),
        ),
    ),
    specs_dir=HERE / "specs",
    examples_dir=HERE / "examples",
)
"""

HEAVY = """
def export(client):
    return {"demo.txt": "exported"}
"""


@pytest.fixture
def plugin_package(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A ``demo_plugin`` package carrying an adapter, a profile and an example."""
    package = tmp_path / "demo_plugin"
    package.mkdir()
    (package / "__init__.py").write_text("")
    (package / "registry.py").write_text(REGISTRY)
    (package / "heavy.py").write_text(HEAVY)
    source = ROOT / "specs" / "seek-ready-template" / "1.0" / "profile.yaml"
    spec_dir = package / "specs" / "demo-profile" / "1.0"
    spec_dir.mkdir(parents=True)
    (spec_dir / "profile.yaml").write_text(
        source.read_text().replace("name: seek-ready-template", "name: demo-profile", 1)
    )
    example_dir = package / "examples" / "demo-profile" / "1.0"
    example_dir.mkdir(parents=True)
    shutil.copy(
        next((ROOT / "examples" / "seek-ready-template" / "1.0").glob("*.yaml")),
        example_dir / "demo.yaml",
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    return package


@pytest.fixture
def announce(monkeypatch: pytest.MonkeyPatch):
    """Announce entry points to the registry, and forget them afterwards."""

    def _announce(*points: tuple[str, str]) -> None:
        entry_points = [
            importlib.metadata.EntryPoint(name, value, GROUP) for name, value in points
        ]
        monkeypatch.setattr(adapters, "_entry_points", lambda: entry_points)
        adapters.reload()

    yield _announce
    monkeypatch.undo()
    adapters.reload()
    for name in [m for m in sys.modules if m.startswith("demo_plugin")]:
        del sys.modules[name]


def test_a_plugin_adapter_is_listed_beside_the_built_ins(plugin_package, announce):
    announce(("demo", "demo_plugin.registry:PLUGIN"))

    keys = [a.key for a in adapters.all_adapters()]
    assert "ena" in keys and "demo" in keys
    assert adapters.is_known("demo")
    assert adapters.get_adapter("demo").name == "Demo archive"
    assert {
        a.key for a in adapters.actions_for_profile("demo-profile", kind="export")
    } == {"demo", "dcat"}
    assert adapters.find_action("demo") is not None
    assert adapters.broken_plugins() == ()


def test_enumerating_loads_the_registry_not_the_implementation(
    plugin_package, announce
):
    announce(("demo", "demo_plugin.registry:PLUGIN"))

    adapters.actions_for_profile("demo-profile")
    assert "demo_plugin.registry" in sys.modules
    assert "demo_plugin.heavy" not in sys.modules

    assert adapters.find_action("demo").resolve()(None) == {"demo.txt": "exported"}


def test_a_plugin_profile_loads_and_its_example_is_found(plugin_package, announce):
    announce(("demo", "demo_plugin.registry:PLUGIN"))
    from metaseed.ui.routes.examples import example_exists

    loader = SpecLoader(profile="demo-profile")
    assert "demo-profile" in loader.list_profiles()
    assert loader.list_versions("demo-profile") == ["1.0"]
    assert loader.load_profile("1.0", "demo-profile").root_entity == "Investigation"
    assert example_exists("demo-profile", "1.0")
    assert not example_exists("demo-profile", "9.9")


def test_the_built_ins_go_through_the_same_path(announce):
    announce()

    first = adapters.plugins()[0]
    assert first.name == "metaseed"
    assert first.adapters == adapters.ADAPTERS
    assert first.specs_dir == ROOT / "specs"
    assert first.examples_dir == ROOT / "examples"
    assert adapters.all_adapters() == adapters.ADAPTERS


def test_a_broken_plugin_is_reported_and_the_rest_still_load(plugin_package, announce):
    announce(
        ("bad", "demo_plugin.does_not_exist:PLUGIN"),
        ("demo", "demo_plugin.registry:PLUGIN"),
    )

    assert adapters.is_known("demo")
    (broken,) = adapters.broken_plugins()
    assert broken.name == "bad"
    assert "demo_plugin.does_not_exist" in broken.reason


def test_an_entry_point_that_is_not_a_plugin_is_reported(plugin_package, announce):
    announce(("odd", "demo_plugin.registry:REGISTRY_IS_NOT_HERE"))

    (broken,) = adapters.broken_plugins()
    assert broken.name == "odd"
    assert "REGISTRY_IS_NOT_HERE" in broken.reason

    (plugin_package / "notaplugin.py").write_text("PLUGIN = 'a string'\n")
    announce(("odd", "demo_plugin.notaplugin:PLUGIN"))
    (broken,) = adapters.broken_plugins()
    assert "not a Plugin" in broken.reason


def test_a_plugin_reusing_a_registered_key_is_refused_not_merged(
    plugin_package, announce
):
    (plugin_package / "clash.py").write_text(
        REGISTRY.replace('key="demo"', 'key="ena"').replace(
            'name="demo"', 'name="clash"'
        )
    )
    announce(("clash", "demo_plugin.clash:PLUGIN"))

    (broken,) = adapters.broken_plugins()
    assert "ena" in broken.reason and "already" in broken.reason
    assert adapters.get_adapter("ena").name == "ENA"


def test_the_plugins_page_shows_a_broken_plugin(plugin_package, announce):
    announce(
        ("bad", "demo_plugin.does_not_exist:PLUGIN"),
        ("demo", "demo_plugin.registry:PLUGIN"),
    )
    from metaseed.ui.app import create_app
    from metaseed.ui.state import AppState

    html = TestClient(create_app(AppState())).get("/settings").text

    assert 'data-testid="adapter-demo"' in html
    assert 'data-testid="broken-plugin-bad"' in html
    assert "demo_plugin.does_not_exist" in html


def test_the_cli_lists_plugin_adapters_and_names_broken_plugins(
    plugin_package, announce
):
    announce(
        ("bad", "demo_plugin.does_not_exist:PLUGIN"),
        ("demo", "demo_plugin.registry:PLUGIN"),
    )
    from metaseed.cli import app

    result = CliRunner().invoke(app, ["plugin", "list"])

    assert result.exit_code == 0, result.output
    assert "demo" in result.output
    assert "bad" in result.output and "demo_plugin.does_not_exist" in result.output
