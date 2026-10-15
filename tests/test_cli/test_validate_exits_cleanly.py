"""`metaseed validate` reports a bad document or entity type with an exit code.

A YAML document that is not a mapping, and an entity type the profile lacks on
a profile with structural checks, both ended in a traceback.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from metaseed.cli import app
from metaseed.cli.output import ExitCode

runner = CliRunner()


@pytest.mark.parametrize("profile", ["isa", "pride"])
def test_a_document_that_is_not_a_mapping_is_an_input_error(
    tmp_path: Path, profile: str
) -> None:
    source = tmp_path / "list.yaml"
    source.write_text("- a\n- b\n")
    entity = "Dataset" if profile == "pride" else "Investigation"
    result = runner.invoke(app, ["validate", str(source), "-p", profile, "-e", entity])
    assert result.exception is None or isinstance(result.exception, SystemExit)
    assert result.exit_code == ExitCode.INPUT_ERROR
    assert "mapping" in result.output


def test_an_unknown_entity_type_with_profile_checks_is_an_input_error(
    tmp_path: Path,
) -> None:
    source = tmp_path / "doc.yaml"
    source.write_text("title: x\n")
    result = runner.invoke(app, ["validate", str(source), "-p", "pride", "-e", "Nope"])
    assert result.exception is None or isinstance(result.exception, SystemExit)
    assert result.exit_code == ExitCode.INPUT_ERROR
