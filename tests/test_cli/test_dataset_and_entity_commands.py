"""`metaseed dataset` and `metaseed entity` act on saved datasets.

These commands are the terminal's half of what the web interface and the MCP
server already do, so they are tested on what they store and print, not on
exit codes alone.
"""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from metaseed.cli import app
from metaseed.repositories.dataset_repository import DatasetData
from metaseed.repositories.filesystem_dataset import FilesystemDatasetRepository

runner = CliRunner()


def _repo() -> FilesystemDatasetRepository:
    return FilesystemDatasetRepository()


def _make(name: str = "test-cli-dataset") -> str:
    result = runner.invoke(
        app, ["dataset", "create", name, "--profile", "isa", "--version", "1.0"]
    )
    assert result.exit_code == 0, result.output
    return name


class TestDatasetCommands:
    def test_create_stores_a_dataset_bound_to_the_profile(self) -> None:
        _make()
        stored = _repo().load("test-cli-dataset")
        assert (stored.profile, stored.version) == ("isa", "1.0")
        assert stored.entities == []

    def test_create_refuses_a_name_that_is_taken(self) -> None:
        _make()
        result = runner.invoke(
            app,
            [
                "dataset",
                "create",
                "test-cli-dataset",
                "--profile",
                "isa",
                "--version",
                "1.0",
            ],
        )
        assert result.exit_code == 2
        assert "already exists" in result.output

    def test_list_reports_what_is_stored(self) -> None:
        _make()
        result = runner.invoke(app, ["dataset", "list"])
        assert result.exit_code == 0
        listed = json.loads(result.stdout)
        assert [d["name"] for d in listed] == ["test-cli-dataset"]
        assert listed[0]["profile"] == "isa"

    def test_show_prints_the_entities(self) -> None:
        _repo().save(
            "test-cli-shown",
            DatasetData(
                name="test-cli-shown",
                profile="isa",
                version="1.0",
                entities=[
                    {"_type": "Investigation", "identifier": "I1", "title": "An inv"}
                ],
            ),
        )
        result = runner.invoke(app, ["dataset", "show", "test-cli-shown"])
        assert result.exit_code == 0
        shown = json.loads(result.stdout)
        assert shown["profile"] == "isa"
        assert shown["entities"][0]["title"] == "An inv"

    def test_a_missing_dataset_is_named_not_traced(self) -> None:
        result = runner.invoke(app, ["dataset", "show", "test-cli-absent"])
        assert result.exit_code == 2
        assert "test-cli-absent" in result.output
        assert "Traceback" not in result.output

    def test_info_counts_by_type(self) -> None:
        _repo().save(
            "test-cli-counted",
            DatasetData(
                name="test-cli-counted",
                profile="isa",
                version="1.0",
                entities=[
                    {"_type": "Investigation", "identifier": "I1", "title": "t"},
                    {"_type": "Study", "identifier": "S1", "title": "s"},
                    {"_type": "Study", "identifier": "S2", "title": "s2"},
                ],
            ),
        )
        result = runner.invoke(app, ["dataset", "info", "test-cli-counted"])
        assert json.loads(result.stdout)["by_type"] == {"Investigation": 1, "Study": 2}

    def test_delete_removes_it(self) -> None:
        _make("test-cli-doomed")
        assert (
            runner.invoke(app, ["dataset", "delete", "test-cli-doomed"]).exit_code == 0
        )
        assert not _repo().exists("test-cli-doomed")

    def test_import_writes_entities_from_a_file(self, tmp_path: Path) -> None:
        source = tmp_path / "entities.json"
        source.write_text(
            json.dumps(
                {
                    "profile": "isa",
                    "version": "1.0",
                    "entities": [
                        {"_type": "Investigation", "identifier": "I1", "title": "t"}
                    ],
                }
            )
        )
        result = runner.invoke(
            app, ["dataset", "import", "test-cli-imported", str(source)]
        )
        assert result.exit_code == 0
        assert len(_repo().load("test-cli-imported").entities) == 1

    def test_import_says_when_the_profile_is_not_named(self, tmp_path: Path) -> None:
        source = tmp_path / "bare.json"
        source.write_text(json.dumps([{"_type": "Investigation", "identifier": "I1"}]))
        result = runner.invoke(app, ["dataset", "import", "test-cli-bare", str(source)])
        assert result.exit_code == 2
        assert "--profile" in result.output

    def test_export_writes_json_or_yaml(self, tmp_path: Path) -> None:
        _repo().save(
            "test-cli-exported",
            DatasetData(
                name="test-cli-exported",
                profile="isa",
                version="1.0",
                entities=[{"_type": "Investigation", "identifier": "I1", "title": "t"}],
            ),
        )
        out = tmp_path / "out.yaml"
        result = runner.invoke(
            app,
            [
                "dataset",
                "export",
                "test-cli-exported",
                "--format",
                "yaml",
                "--output",
                str(out),
            ],
        )
        assert result.exit_code == 0, result.output
        assert "identifier: I1" in out.read_text()

    def test_export_names_the_formats_it_offers(self) -> None:
        _make("test-cli-formats")
        result = runner.invoke(
            app, ["dataset", "export", "test-cli-formats", "--format", "nonsense"]
        )
        assert result.exit_code == 2
        assert "json" in result.output and "yaml" in result.output

    def test_validate_reports_the_issues_and_exits_one(self) -> None:
        _repo().save(
            "test-cli-invalid",
            DatasetData(
                name="test-cli-invalid",
                profile="isa",
                version="1.0",
                entities=[{"_type": "Investigation", "identifier": "I1", "title": "t"}],
            ),
        )
        result = runner.invoke(app, ["dataset", "validate", "test-cli-invalid"])
        assert result.exit_code == 1
        report = json.loads(result.stdout)
        assert report["valid"] is False
        assert report["issues"], (
            "an investigation with no studies has something to report"
        )


class TestEntityCommands:
    def test_create_then_list_shows_it_with_an_id(self) -> None:
        _make("test-cli-entities")
        created = runner.invoke(
            app,
            [
                "entity",
                "create",
                "test-cli-entities",
                "Investigation",
                "--set",
                "identifier=I1",
                "--set",
                "title=An investigation",
            ],
        )
        assert created.exit_code == 0, created.output
        listed = json.loads(
            runner.invoke(app, ["entity", "list", "test-cli-entities"]).stdout
        )
        assert listed[0]["type"] == "Investigation"
        assert listed[0]["data"]["title"] == "An investigation"
        assert listed[0]["id"]

    def test_a_child_lands_under_its_parent(self) -> None:
        _make("test-cli-nested")
        runner.invoke(
            app,
            [
                "entity",
                "create",
                "test-cli-nested",
                "Investigation",
                "--set",
                "identifier=I1",
                "--set",
                "title=t",
            ],
        )
        parent = json.loads(
            runner.invoke(app, ["entity", "list", "test-cli-nested"]).stdout
        )[0]["id"]
        child = runner.invoke(
            app,
            [
                "entity",
                "create",
                "test-cli-nested",
                "Study",
                "--set",
                "identifier=S1",
                "--set",
                "title=A study",
                "--parent",
                parent,
            ],
        )
        assert child.exit_code == 0, child.output
        tree = json.loads(
            runner.invoke(app, ["entity", "tree", "test-cli-nested"]).stdout
        )
        assert tree["tree"][0]["children"][0]["entity_type"] == "Study"

    def test_update_changes_only_what_it_names(self) -> None:
        _make("test-cli-updated")
        runner.invoke(
            app,
            [
                "entity",
                "create",
                "test-cli-updated",
                "Investigation",
                "--set",
                "identifier=I1",
                "--set",
                "title=Before",
            ],
        )
        entity_id = json.loads(
            runner.invoke(app, ["entity", "list", "test-cli-updated"]).stdout
        )[0]["id"]
        result = runner.invoke(
            app,
            ["entity", "update", "test-cli-updated", entity_id, "--set", "title=After"],
        )
        assert result.exit_code == 0, result.output
        shown = json.loads(
            runner.invoke(app, ["entity", "show", "test-cli-updated", entity_id]).stdout
        )
        assert shown["data"]["title"] == "After"
        assert shown["data"]["identifier"] == "I1", "an unnamed field keeps its value"

    def test_delete_removes_it_from_the_saved_dataset(self) -> None:
        _make("test-cli-deleted")
        runner.invoke(
            app,
            [
                "entity",
                "create",
                "test-cli-deleted",
                "Investigation",
                "--set",
                "identifier=I1",
                "--set",
                "title=t",
            ],
        )
        entity_id = json.loads(
            runner.invoke(app, ["entity", "list", "test-cli-deleted"]).stdout
        )[0]["id"]
        assert (
            runner.invoke(
                app, ["entity", "delete", "test-cli-deleted", entity_id]
            ).exit_code
            == 0
        )
        assert _repo().load("test-cli-deleted").entities == []

    def test_a_field_value_that_is_json_stays_json(self) -> None:
        _make("test-cli-json-values")
        runner.invoke(
            app,
            [
                "entity",
                "create",
                "test-cli-json-values",
                "Investigation",
                "--set",
                "identifier=I1",
                "--set",
                "title=t",
                "--set",
                'comments=[{"name": "a", "value": "b"}]',
            ],
        )
        listed = json.loads(
            runner.invoke(app, ["entity", "list", "test-cli-json-values"]).stdout
        )
        assert listed[0]["data"]["comments"][0]["name"] == "a"

    def test_a_malformed_assignment_is_refused_by_name(self) -> None:
        _make("test-cli-bad-set")
        result = runner.invoke(
            app,
            [
                "entity",
                "create",
                "test-cli-bad-set",
                "Investigation",
                "--set",
                "identifier",
            ],
        )
        assert result.exit_code == 2
        assert "name=value" in result.output

    def test_batch_create_nests_by_position(self, tmp_path: Path) -> None:
        _make("test-cli-batch")
        batch = tmp_path / "batch.json"
        batch.write_text(
            json.dumps(
                [
                    {"_type": "Investigation", "identifier": "I1", "title": "An inv"},
                    {
                        "_type": "Study",
                        "identifier": "S1",
                        "title": "A study",
                        "_parent": 0,
                    },
                ]
            )
        )
        result = runner.invoke(
            app, ["entity", "batch-create", "test-cli-batch", str(batch)]
        )
        assert result.exit_code == 0, result.output
        assert len(json.loads(result.stdout)["created"]) == 2
        tree = json.loads(
            runner.invoke(app, ["entity", "tree", "test-cli-batch"]).stdout
        )
        assert tree["tree"][0]["children"][0]["entity_type"] == "Study"

    def test_bulk_update_touches_only_the_named_type(self) -> None:
        _make("test-cli-bulk")
        for identifier in ("I1", "I2"):
            runner.invoke(
                app,
                [
                    "entity",
                    "create",
                    "test-cli-bulk",
                    "Investigation",
                    "--set",
                    f"identifier={identifier}",
                    "--set",
                    "title=Before",
                ],
            )
        result = runner.invoke(
            app,
            [
                "entity",
                "bulk-update",
                "test-cli-bulk",
                "--type",
                "Investigation",
                "--set",
                "title=After",
            ],
        )
        assert result.exit_code == 0, result.output
        listed = json.loads(
            runner.invoke(app, ["entity", "list", "test-cli-bulk"]).stdout
        )
        assert [e["data"]["title"] for e in listed] == ["After", "After"]
