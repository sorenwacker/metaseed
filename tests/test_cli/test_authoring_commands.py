"""`metaseed spec`, `metaseed profile`, `metaseed extract` and `metaseed dcat`.

A draft on the command line is a file rather than a session, so the tests
follow one through the same steps an author would: start it, shape it, check
it, save it.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml
from typer.testing import CliRunner

from metaseed.cli import app
from metaseed.repositories.dataset_repository import DatasetData
from metaseed.repositories.filesystem_dataset import FilesystemDatasetRepository

runner = CliRunner()


class TestSpecCommands:
    def _draft(self, tmp_path: Path) -> Path:
        draft = tmp_path / "draft.yaml"
        result = runner.invoke(
            app,
            [
                "spec",
                "create",
                str(draft),
                "--name",
                "test-authored",
                "--version",
                "1.0",
            ],
        )
        assert result.exit_code == 0, result.output
        return draft

    def test_a_draft_is_a_file_that_carries_what_was_declared(
        self, tmp_path: Path
    ) -> None:
        draft = self._draft(tmp_path)
        written = yaml.safe_load(draft.read_text())
        assert written["name"] == "test-authored"
        assert written["version"] == "1.0"

    def test_entities_and_fields_accumulate(self, tmp_path: Path) -> None:
        draft = self._draft(tmp_path)
        assert (
            runner.invoke(app, ["spec", "add-entity", str(draft), "Study"]).exit_code
            == 0
        )
        added = runner.invoke(
            app,
            [
                "spec",
                "add-field",
                str(draft),
                "Study",
                "identifier",
                "--type",
                "string",
                "--set",
                "required=true",
                "--set",
                "is_identifier=true",
            ],
        )
        assert added.exit_code == 0, added.output
        assert (
            runner.invoke(app, ["spec", "set-root", str(draft), "Study"]).exit_code == 0
        )
        status = json.loads(runner.invoke(app, ["spec", "status", str(draft)]).stdout)
        assert status["root_entity"] == "Study"
        assert status["entities"] == {"Study": 1}

    def test_a_field_on_an_entity_that_is_not_there_is_refused(
        self, tmp_path: Path
    ) -> None:
        draft = self._draft(tmp_path)
        result = runner.invoke(app, ["spec", "add-field", str(draft), "Nowhere", "x"])
        assert result.exit_code == 2
        assert "Nowhere" in result.output

    def test_a_draft_that_is_not_there_says_how_to_start_one(
        self, tmp_path: Path
    ) -> None:
        result = runner.invoke(app, ["spec", "status", str(tmp_path / "absent.yaml")])
        assert result.exit_code == 2
        assert "spec create" in result.output

    def test_preview_prints_the_profile_it_would_become(self, tmp_path: Path) -> None:
        draft = self._draft(tmp_path)
        runner.invoke(app, ["spec", "add-entity", str(draft), "Study"])
        printed = runner.invoke(app, ["spec", "preview", str(draft)]).stdout
        assert "name: test-authored" in printed
        assert "Study" in printed

    def test_validate_reports_a_clean_draft_as_valid(self, tmp_path: Path) -> None:
        draft = self._draft(tmp_path)
        runner.invoke(app, ["spec", "add-entity", str(draft), "Study"])
        runner.invoke(
            app,
            [
                "spec",
                "add-field",
                str(draft),
                "Study",
                "identifier",
                "--type",
                "string",
            ],
        )
        runner.invoke(app, ["spec", "set-root", str(draft), "Study"])
        result = runner.invoke(app, ["spec", "validate", str(draft)])
        assert result.exit_code == 0, result.output
        assert json.loads(result.stdout)["valid"] is True

    def test_renaming_an_entity_follows_through(self, tmp_path: Path) -> None:
        draft = self._draft(tmp_path)
        runner.invoke(app, ["spec", "add-entity", str(draft), "Study"])
        runner.invoke(app, ["spec", "set-root", str(draft), "Study"])
        assert (
            runner.invoke(
                app, ["spec", "rename-entity", str(draft), "Study", "Trial"]
            ).exit_code
            == 0
        )
        status = json.loads(runner.invoke(app, ["spec", "status", str(draft)]).stdout)
        assert list(status["entities"]) == ["Trial"]
        assert status["root_entity"] == "Trial"

    def test_notes_are_kept_beside_the_draft(self, tmp_path: Path) -> None:
        draft = self._draft(tmp_path)
        assert (
            runner.invoke(
                app, ["spec", "notes", str(draft), "Ask about units"]
            ).exit_code
            == 0
        )
        assert (
            "Ask about units"
            in runner.invoke(app, ["spec", "notes", str(draft)]).stdout
        )


class TestProfileCommands:
    def test_schema_names_the_root_and_the_entities(self) -> None:
        result = runner.invoke(
            app, ["profile", "schema", "--profile", "isa", "--version", "1.0"]
        )
        assert result.exit_code == 0
        schema = json.loads(result.stdout)
        assert schema["root_entity"] == "Investigation"
        assert "Study" in schema["entities"]

    def test_required_lists_only_required_fields(self) -> None:
        result = runner.invoke(
            app,
            [
                "profile",
                "required",
                "Investigation",
                "--profile",
                "isa",
                "--version",
                "1.0",
            ],
        )
        assert result.exit_code == 0
        assert all(field["required"] for field in json.loads(result.stdout))

    def test_relationships_name_the_children(self) -> None:
        result = runner.invoke(
            app, ["profile", "relationships", "--profile", "isa", "--version", "1.0"]
        )
        assert (
            "Study"
            in json.loads(result.stdout)["entities"]["Investigation"][
                "children"
            ].values()
        )

    def test_an_entity_that_is_not_in_the_profile_is_named(self) -> None:
        result = runner.invoke(
            app,
            ["profile", "fields", "Nowhere", "--profile", "isa", "--version", "1.0"],
        )
        assert result.exit_code == 2
        assert "Nowhere" in result.output


class TestExtractCommands:
    def _csv(self, tmp_path: Path) -> Path:
        source = tmp_path / "rows.csv"
        source.write_text(
            "identifier,title,description\nI1,First,Some text\nI2,Second,More\n"
        )
        return source

    def test_parse_reports_the_columns_and_rows(self, tmp_path: Path) -> None:
        result = runner.invoke(app, ["extract", "parse", str(self._csv(tmp_path))])
        assert result.exit_code == 0, result.output
        table = json.loads(result.stdout)["tables"][0]
        assert table["columns"] == ["identifier", "title", "description"]
        assert table["rows"] == 2

    def test_analyze_maps_columns_onto_fields(self, tmp_path: Path) -> None:
        result = runner.invoke(
            app,
            [
                "extract",
                "analyze",
                str(self._csv(tmp_path)),
                "--entity",
                "Investigation",
                "--profile",
                "isa",
                "--version",
                "1.0",
            ],
        )
        assert result.exit_code == 0, result.output
        mapped = {
            m["field"]: m["column"] for m in json.loads(result.stdout)["mappings"]
        }
        assert mapped["title"] == "title"

    def test_run_extracts_the_rows(self, tmp_path: Path) -> None:
        out = tmp_path / "records.json"
        result = runner.invoke(
            app,
            [
                "extract",
                "run",
                str(self._csv(tmp_path)),
                "--entity",
                "Investigation",
                "--profile",
                "isa",
                "--version",
                "1.0",
                "--output",
                str(out),
            ],
        )
        assert result.exit_code == 0, result.output
        records = json.loads(out.read_text())["extracted"]
        assert [r["identifier"] for r in records] == ["I1", "I2"]

    def test_a_file_with_no_parser_is_reported_not_traced(self, tmp_path: Path) -> None:
        source = tmp_path / "notes.md"
        source.write_text("# not a table")
        result = runner.invoke(app, ["extract", "parse", str(source)])
        assert result.exit_code == 2
        assert "Traceback" not in result.output


class TestDcatCommands:
    def _dataset(self) -> str:
        FilesystemDatasetRepository().save(
            "test-cli-catalogued",
            DatasetData(
                name="test-cli-catalogued",
                profile="isa",
                version="1.0",
                entities=[
                    {"_type": "Investigation", "identifier": "I1", "title": "An inv"}
                ],
            ),
        )
        return "test-cli-catalogued"

    def test_set_then_show_returns_the_fields(self) -> None:
        name = self._dataset()
        result = runner.invoke(
            app,
            [
                "dcat",
                "set",
                name,
                "--title",
                "A catalogue title",
                "--keyword",
                "drought",
            ],
        )
        assert result.exit_code == 0, result.output
        fields = json.loads(
            runner.invoke(app, ["dcat", "show", name, "--format", "fields"]).stdout
        )
        assert fields["title"] == "A catalogue title"
        assert fields["keywords"] == ["drought"]

    def test_show_emits_a_card(self) -> None:
        name = self._dataset()
        result = runner.invoke(app, ["dcat", "show", name])
        assert result.exit_code == 0, result.output
        assert "@context" in result.stdout
