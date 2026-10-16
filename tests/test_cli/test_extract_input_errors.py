"""`metaseed extract` reports bad input with exit code 2, not a traceback.

`run` parsed its source without the existence check `parse` has, `run` and
`analyze` indexed `--table` unchecked, and the `--mapping` file and the records
read by `validate` and `export` were parsed unguarded.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from metaseed.cli import app
from metaseed.cli.output import ExitCode

runner = CliRunner()
PROFILE = ["--profile", "isa", "--version", "1.0"]


def _csv(tmp_path: Path) -> Path:
    source = tmp_path / "rows.csv"
    source.write_text("identifier,title\nI1,First\n")
    return source


def _input_error(args: list[str]) -> str:
    result = runner.invoke(app, ["extract", *args])
    assert isinstance(result.exception, SystemExit), result.exception
    assert result.exit_code == ExitCode.INPUT_ERROR, result.output
    return result.output


def test_run_reports_a_missing_source(tmp_path: Path) -> None:
    output = _input_error(
        ["run", str(tmp_path / "absent.csv"), "-e", "Investigation", *PROFILE]
    )
    assert "No such file" in output


@pytest.mark.parametrize("command", ["run", "analyze"])
@pytest.mark.parametrize("table", ["5", "-1"])
def test_a_table_index_out_of_range_is_reported(
    tmp_path: Path, command: str, table: str
) -> None:
    output = _input_error(
        [
            command,
            str(_csv(tmp_path)),
            "-e",
            "Investigation",
            "--table",
            table,
            *PROFILE,
        ]
    )
    assert "--table" in output


@pytest.mark.parametrize("content", ["{not json", '[{"column": "title"}]'])
def test_run_reports_an_unusable_mapping_file(tmp_path: Path, content: str) -> None:
    mapping = tmp_path / "mapping.json"
    mapping.write_text(content)
    _input_error(
        [
            "run",
            str(_csv(tmp_path)),
            "-e",
            "Investigation",
            "-m",
            str(mapping),
            *PROFILE,
        ]
    )


def test_run_reports_a_missing_mapping_file(tmp_path: Path) -> None:
    _input_error(
        [
            "run",
            str(_csv(tmp_path)),
            "-e",
            "Investigation",
            "-m",
            str(tmp_path / "absent.json"),
            *PROFILE,
        ]
    )


@pytest.mark.parametrize("command", ["validate", "export"])
def test_records_that_are_not_json_are_reported(tmp_path: Path, command: str) -> None:
    records = tmp_path / "records.json"
    records.write_text("{not json")
    args = (
        [command, str(records), "-e", "Investigation", *PROFILE]
        if command == "validate"
        else [command, str(records), str(tmp_path / "out.json")]
    )
    _input_error(args)
