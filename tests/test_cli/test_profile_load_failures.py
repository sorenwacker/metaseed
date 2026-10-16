"""A profile that fails to load is a config error in every CLI command.

`profile` and `extract` each had their own guarded loader, while the `seek`
commands called `SpecLoader().load_profile` unguarded and ended in a traceback.
One helper, `cli.workspace.load_profile_spec`, now does it for all of them, and
the gate below keeps further command modules from loading a profile any other
way.
"""

from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from metaseed.cli import app
from metaseed.cli.output import ExitCode
from metaseed.specs.loader import SpecLoadError

runner = CliRunner()
COMMANDS = Path(__file__).resolve().parents[2] / "src" / "metaseed" / "cli" / "commands"


@pytest.mark.parametrize(
    "args",
    [
        ["seek", "preview"],
        ["seek", "isa-templates"],
        ["seek", "model-ttl"],
        ["profile", "schema"],
    ],
)
def test_a_profile_that_fails_to_load_is_a_config_error(args: list[str]) -> None:
    with patch(
        "metaseed.specs.loader.SpecLoader.load_profile",
        side_effect=SpecLoadError("broken"),
    ):
        result = runner.invoke(app, [*args, "-p", "isa", "-v", "1.0"])
    assert isinstance(result.exception, SystemExit), result.exception
    assert result.exit_code == ExitCode.CONFIG_ERROR
    assert "broken" in result.output


def test_command_modules_load_profiles_only_through_the_shared_helper() -> None:
    offenders = [
        path.name
        for path in sorted(COMMANDS.glob("*.py"))
        if re.search(r"\.load_profile\(", path.read_text())
    ]
    assert offenders == [], (
        "load a profile with metaseed.cli.workspace.load_profile_spec, "
        f"which turns a load failure into a config error: {offenders}"
    )
