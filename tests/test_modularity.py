"""Public API and modularity guarantees (issue #71, ADR 004).

Two promises consumers rely on:

- ``metaseed.list_profiles()`` is a public entry point.
- The reusable tools import WITHOUT the web app. A downstream consumer embeds
  the specs, models, facade and validators headlessly; it should not pay for
  FastAPI, and a core module should not be able to reach into the UI's session.

The gate is in two parts because neither half sees what the other does. The AST
scan finds an import wherever it is written -- inside a function body or a
``TYPE_CHECKING`` block, where an import-graph linter never looks -- which is
how ``cli/migrate.py`` and ``repositories/memory.py`` acquired their edges. The
fresh-interpreter checks find transitive leaks, which no AST scan can see: the
cost of ``cli/migrate.py``'s one import was the whole FastAPI app, three
packages away.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest

SRC_ROOT = Path(__file__).resolve().parent.parent / "src" / "metaseed"

#: Modules outside ``metaseed.ui`` that may import ``metaseed.ui``, with the
#: reason each is a deliberate seam rather than a leak. Any other module fails
#: the gate. Keep this list short: every entry is a place the dependency
#: direction is inverted on purpose.
ALLOWED_UI_IMPORTERS = {
    # The MCP host edits the same local editing session as the web UI -- a tool
    # call and a browser click must land in the same dataset. The dependency is
    # real, so it is declared here in one module instead of hidden inside ~25
    # function bodies across agent/mcp/.
    "agent/mcp/ui_session.py": "the MCP host's declared seam onto the UI session",
    # `metaseed ui` launches the web app; that is what the command is for. The
    # import stays inside the command body so the other CLI commands (and
    # `metaseed --help`) do not load FastAPI.
    "cli/app.py": "the CLI command that starts the web app",
}

#: Packages a consumer imports for the tools alone. Each is loaded in a fresh
#: interpreter and must leave the web stack out of ``sys.modules``.
HEADLESS_MODULES = [
    "metaseed",
    "metaseed.specs",
    "metaseed.facade",
    "metaseed.validators",
    "metaseed.models",
    "metaseed.dcat",
    "metaseed.api.client",
    "metaseed.repositories",
    "metaseed.forms",
    "metaseed.cli.migrate",
]

_WEB_MODULES = ("fastapi", "starlette", "metaseed.ui", "metaseed.ui.app")


def _ui_imports_in(source: str, label: str) -> list[str]:
    """Collect ``metaseed.ui`` imports anywhere in ``source``.

    Walks the full AST, so imports nested inside functions or ``TYPE_CHECKING``
    blocks are found as well.

    Args:
        source: Python source to scan.
        label: Name to prefix each hit with (the module's path).

    Returns:
        ``"<label>:<line>: <statement>"`` for each hit.
    """
    hits: list[str] = []
    tree = ast.parse(source)
    relative = label
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "metaseed.ui" or alias.name.startswith("metaseed.ui."):
                    hits.append(f"{relative}:{node.lineno}: import {alias.name}")
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            module = node.module or ""
            if module == "metaseed.ui" or module.startswith("metaseed.ui."):
                names = ", ".join(alias.name for alias in node.names)
                hits.append(f"{relative}:{node.lineno}: from {module} import {names}")
    return hits


def _ui_imports(path: Path) -> list[str]:
    """``_ui_imports_in`` for a file, labelled by its path under src/metaseed."""
    return _ui_imports_in(
        path.read_text(encoding="utf-8"), path.relative_to(SRC_ROOT).as_posix()
    )


def _core_modules() -> list[Path]:
    """Every module under ``src/metaseed`` that is not part of the web app."""
    return sorted(
        path
        for path in SRC_ROOT.rglob("*.py")
        if path.relative_to(SRC_ROOT).parts[0] != "ui"
    )


def _loaded_web_modules(import_stmt: str) -> list[str]:
    """Run ``import_stmt`` in a fresh interpreter; return any web modules loaded."""
    code = (
        f"{import_stmt}\n"
        "import sys\n"
        f"web = {_WEB_MODULES!r}\n"
        "print(','.join(m for m in web if m in sys.modules))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    )
    loaded = result.stdout.strip()
    return loaded.split(",") if loaded else []


def test_no_core_module_imports_the_web_app() -> None:
    """Nothing outside ``metaseed.ui`` imports ``metaseed.ui``, bar the seams."""
    offenders: list[str] = []
    for path in _core_modules():
        relative = path.relative_to(SRC_ROOT).as_posix()
        if relative in ALLOWED_UI_IMPORTERS:
            continue
        offenders.extend(_ui_imports(path))

    allowed = "\n".join(
        f"  {name} -- {why}" for name, why in ALLOWED_UI_IMPORTERS.items()
    )
    assert not offenders, (
        "the core must not import the web app (ADR 004); move the shared part "
        "down into the core or route it through a declared seam:\n"
        + "\n".join(offenders)
        + f"\nDeclared seams:\n{allowed}"
    )


def test_each_declared_seam_still_exists_and_uses_its_exemption() -> None:
    """An exemption nobody needs is an exemption that should be deleted."""
    for relative, why in ALLOWED_UI_IMPORTERS.items():
        path = SRC_ROOT / relative
        assert path.is_file(), f"{relative} is exempt but does not exist ({why})"
        assert _ui_imports(path), (
            f"{relative} is exempt from the metaseed.ui ban but imports nothing "
            "from it; remove the exemption"
        )


def test_the_gate_sees_an_import_hidden_in_a_function_body() -> None:
    """The dodge the gate exists for: an import a linter cannot see."""
    source = """
def migrate_all_datasets():
    from metaseed.ui.datasets import get_datasets_dir

    return get_datasets_dir()
"""

    assert _ui_imports_in(source, "probe.py") == [
        "probe.py:3: from metaseed.ui.datasets import get_datasets_dir"
    ]


def test_the_gate_sees_a_type_checking_import() -> None:
    """A type-only import still names the UI from the core."""
    source = """
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from metaseed.ui.state import AppState
"""

    assert _ui_imports_in(source, "probe.py") == [
        "probe.py:5: from metaseed.ui.state import AppState"
    ]


@pytest.mark.parametrize("module", HEADLESS_MODULES)
def test_module_imports_without_the_web_stack(module: str) -> None:
    """Importing the tools must not load FastAPI, Starlette or the UI."""
    loaded = _loaded_web_modules(f"import {module}")
    assert loaded == [], f"importing {module} loaded {', '.join(loaded)}"


def test_the_mcp_host_does_not_construct_the_web_app() -> None:
    """The MCP server holds a UI session without starting a web server.

    ``starlette`` is not checked here: ``mcp.server.fastmcp`` imports it, so it
    arrives with the MCP SDK rather than through a metaseed edge.
    """
    loaded = _loaded_web_modules("import metaseed.agent.mcp.server")
    assert "fastapi" not in loaded, "the MCP server pulled in FastAPI"
    assert "metaseed.ui.app" not in loaded, "the MCP server built the web app"


def test_list_profiles_is_public_and_lists_builtins() -> None:
    import metaseed

    profiles = metaseed.list_profiles()
    assert isinstance(profiles, list)
    assert "miappe" in profiles
    assert "list_profiles" in metaseed.__all__


def test_the_save_callback_resolves_when_it_is_called() -> None:
    """Patching ``auto_save`` must take effect on a session already built.

    ``_build_default_context`` used to pass the function object itself, so the
    repository captured whichever ``auto_save`` existed at build time. A test
    that patched it afterwards still ran the real one, writing to the user's
    datasets directory instead of a stub.
    """
    from unittest.mock import patch

    from metaseed.agent.mcp import context as context_module

    context_module.clear_context()
    try:
        context = context_module.resolve_default_context()
        repository = context.get_entity_service().repository
        with patch("metaseed.ui.datasets.auto_save") as stub:
            repository._on_change(context.state)  # type: ignore[misc]
        assert stub.called, (
            "the save callback ran the real auto_save; a session built before "
            "the patch still writes to the user's datasets directory"
        )
    finally:
        context_module.clear_context()
