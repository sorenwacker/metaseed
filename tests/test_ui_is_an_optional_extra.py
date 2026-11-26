"""The web interface is the `ui` extra; the core install does not carry it (261126).

`pip install metaseed` installs the library, the command line and the MCP
server. The web stack (FastAPI, Jinja2, python-multipart) arrives only with
`metaseed[ui]`, and `metaseed ui` without it names that install command.
"""

from __future__ import annotations

import ast
import importlib.util
import re
import tomllib
from pathlib import Path

import pytest
from typer.testing import CliRunner

from metaseed.cli import app
from metaseed.cli.output import ExitCode

ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = ROOT / "src" / "metaseed"

#: Packages only the web interface imports; they belong to the `ui` extra.
WEB_STACK = frozenset({"fastapi", "jinja2", "python-multipart"})

#: Import names of the web stack, as code spells them.
_WEB_IMPORTS = frozenset({"fastapi", "starlette", "jinja2", "multipart"})


def _project() -> dict:
    return tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]


def _names(requirements: list[str]) -> set[str]:
    return {re.split(r"[<>=!~\[;\s]", r, maxsplit=1)[0] for r in requirements}


def test_the_core_install_does_not_carry_the_web_stack() -> None:
    leaked = WEB_STACK & _names(_project()["dependencies"])
    assert not leaked, f"core dependencies include web-only packages {sorted(leaked)}"


def test_the_ui_extra_carries_the_web_stack() -> None:
    ui = _names(_project()["optional-dependencies"].get("ui", []))
    assert ui >= WEB_STACK, f"the ui extra lacks {sorted(WEB_STACK - ui)}"


def test_all_includes_the_ui_extra() -> None:
    all_extra = " ".join(_project()["optional-dependencies"]["all"])
    assert re.search(r"metaseed\[[^\]]*\bui\b", all_extra), (
        "`all` does not install `ui`"
    )


def _web_imports(path: Path) -> list[str]:
    hits = []
    for node in ast.walk(ast.parse(path.read_text(), filename=str(path))):
        if isinstance(node, ast.Import):
            modules = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            modules = [node.module]
        else:
            continue
        for module in modules:
            if module.split(".")[0] in _WEB_IMPORTS:
                relative = path.relative_to(SRC_ROOT).as_posix()
                hits.append(f"{relative}:{node.lineno}: {module}")
    return hits


def test_only_the_web_interface_imports_the_web_stack() -> None:
    offenders = [
        hit
        for path in sorted(SRC_ROOT.rglob("*.py"))
        if path.relative_to(SRC_ROOT).parts[0] != "ui"
        for hit in _web_imports(path)
    ]
    assert not offenders, (
        "code outside metaseed.ui imports a package of the `ui` extra, so a "
        "core install would fail there:\n" + "\n".join(offenders)
    )


def test_metaseed_ui_without_the_extra_names_the_install_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_find_spec = importlib.util.find_spec

    def without_fastapi(name: str, *args: object, **kwargs: object) -> object:
        if name.split(".", maxsplit=1)[0] == "fastapi":
            return None
        return real_find_spec(name, *args, **kwargs)

    monkeypatch.setattr(importlib.util, "find_spec", without_fastapi)
    # Should the guard be missing, fail fast instead of starting a server.
    monkeypatch.setattr(
        "metaseed.ui.app.run_ui", lambda **_: pytest.fail("the web app started")
    )

    result = CliRunner().invoke(app, ["ui"])

    assert result.exit_code == ExitCode.CONFIG_ERROR, result.output
    assert "uv tool install 'metaseed[ui]'" in result.output
    assert "pip install 'metaseed[ui]'" in result.output
