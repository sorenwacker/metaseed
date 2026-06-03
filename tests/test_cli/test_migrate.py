"""Tests for metaseed.cli.migrate."""

import json
from unittest.mock import patch

from metaseed.cli.migrate import (
    is_node_id,
    migrate_all_datasets,
    migrate_dataset,
    print_migration_report,
)


class TestIsNodeId:
    """Test is_node_id function."""

    def test_valid_8_char_hex(self):
        """8 lowercase hex characters is a valid node ID."""
        assert is_node_id("a1b2c3d4") is True
        assert is_node_id("00000000") is True
        assert is_node_id("ffffffff") is True

    def test_invalid_length(self):
        """Wrong length is not a valid node ID."""
        assert is_node_id("a1b2c3") is False  # too short
        assert is_node_id("a1b2c3d4e5") is False  # too long

    def test_invalid_characters(self):
        """Non-hex characters are not valid."""
        assert is_node_id("ghijklmn") is False
        assert is_node_id("A1B2C3D4") is False  # uppercase

    def test_non_string_input(self):
        """Non-string input returns False."""
        assert is_node_id(12345678) is False
        assert is_node_id(None) is False
        assert is_node_id(["a1b2c3d4"]) is False


class TestMigrateDataset:
    """Test migrate_dataset function."""

    def test_migrate_parent_id_to_unique_id(self, tmp_path):
        """Migrates _parent_id to _parent_unique_id."""
        data = {
            "name": "test-dataset",
            "entities": [
                {"_node_id": "aabbccdd", "_type": "Study", "unique_id": "STU001"},
                {
                    "_node_id": "11223344",
                    "_type": "Sample",
                    "unique_id": "SAM001",
                    "_parent_id": "aabbccdd",
                },
            ],
        }
        path = tmp_path / "test.json"
        path.write_text(json.dumps(data))

        report = migrate_dataset(path, dry_run=True)

        assert report["migrated"] is True
        assert report["saved"] is False
        assert len(report["changes"]) >= 1

        # Check the parent ID was identified for migration
        parent_change = next(
            (c for c in report["changes"] if c["field"] == "_parent_id"), None
        )
        assert parent_change is not None
        assert "STU001" in parent_change["new"]

    def test_dry_run_does_not_write(self, tmp_path):
        """Dry run does not modify the file."""
        data = {
            "entities": [
                {"_node_id": "aabbccdd", "_type": "Study", "unique_id": "STU001"},
                {
                    "_node_id": "11223344",
                    "_type": "Sample",
                    "unique_id": "SAM001",
                    "_parent_id": "aabbccdd",
                },
            ]
        }
        path = tmp_path / "test.json"
        path.write_text(json.dumps(data))
        original_content = path.read_text()

        migrate_dataset(path, dry_run=True)

        assert path.read_text() == original_content

    def test_apply_writes_changes(self, tmp_path):
        """With dry_run=False, changes are written to file."""
        data = {
            "entities": [
                {"_node_id": "aabbccdd", "_type": "Study", "unique_id": "STU001"},
                {
                    "_node_id": "11223344",
                    "_type": "Sample",
                    "unique_id": "SAM001",
                    "_parent_id": "aabbccdd",
                },
            ]
        }
        path = tmp_path / "test.json"
        path.write_text(json.dumps(data))

        report = migrate_dataset(path, dry_run=False)

        assert report["saved"] is True

        # Verify file was updated
        updated_data = json.loads(path.read_text())
        sample = next(
            e for e in updated_data["entities"] if e.get("unique_id") == "SAM001"
        )
        assert "_parent_id" not in sample
        assert "_parent_unique_id" in sample
        assert sample["_parent_unique_id"] == "STU001"

    def test_migrates_reference_fields(self, tmp_path):
        """Migrates entity reference fields that look like node IDs."""
        data = {
            "entities": [
                {"_node_id": "aabbccdd", "_type": "Study", "unique_id": "STU001"},
                {
                    "_node_id": "11223344",
                    "_type": "Sample",
                    "unique_id": "SAM001",
                    "material_source": "aabbccdd",
                },
            ]
        }
        path = tmp_path / "test.json"
        path.write_text(json.dumps(data))

        report = migrate_dataset(path, dry_run=True)

        ref_change = next(
            (c for c in report["changes"] if c["field"] == "material_source"), None
        )
        assert ref_change is not None
        assert ref_change["old"] == "aabbccdd"
        assert ref_change["new"] == "STU001"

    def test_no_changes_when_already_migrated(self, tmp_path):
        """No changes when dataset is already migrated."""
        data = {
            "entities": [
                {"_type": "Study", "unique_id": "STU001"},
                {
                    "_type": "Sample",
                    "unique_id": "SAM001",
                    "_parent_unique_id": "STU001",
                },
            ]
        }
        path = tmp_path / "test.json"
        path.write_text(json.dumps(data))

        report = migrate_dataset(path, dry_run=True)

        assert report["migrated"] is False
        assert len(report["changes"]) == 0


class TestMigrateAllDatasets:
    """Test migrate_all_datasets function."""

    def test_migrates_all_json_files(self, tmp_path):
        """Migrates all .json files in datasets directory."""
        # Create test files
        data1 = {
            "name": "ds1",
            "entities": [
                {"_node_id": "aaaaaaaa", "_type": "Study", "unique_id": "S1"},
                {
                    "_node_id": "bbbbbbbb",
                    "_type": "Sample",
                    "unique_id": "X1",
                    "_parent_id": "aaaaaaaa",
                },
            ],
        }
        data2 = {
            "name": "ds2",
            "entities": [{"_type": "Study", "unique_id": "S2"}],
        }

        (tmp_path / "ds1.json").write_text(json.dumps(data1))
        (tmp_path / "ds2.json").write_text(json.dumps(data2))

        with patch("metaseed.cli.migrate.get_datasets_dir", return_value=tmp_path):
            reports = migrate_all_datasets(dry_run=True)

        assert len(reports) == 2
        ds1_report = next(r for r in reports if "ds1" in r["file"])
        assert ds1_report["migrated"] is True

    def test_handles_invalid_json(self, tmp_path):
        """Reports error for invalid JSON files."""
        (tmp_path / "invalid.json").write_text("not json")

        with patch("metaseed.cli.migrate.get_datasets_dir", return_value=tmp_path):
            reports = migrate_all_datasets(dry_run=True)

        assert len(reports) == 1
        assert "error" in reports[0]


class TestPrintMigrationReport:
    """Test print_migration_report function."""

    def test_prints_changes(self, capsys):
        """Prints migration changes."""
        reports = [
            {
                "file": "/path/to/test.json",
                "dataset": "test",
                "entity_count": 2,
                "changes": [
                    {
                        "entity": "SAM001",
                        "field": "_parent_id",
                        "old": "abc",
                        "new": "STU001",
                    }
                ],
                "saved": False,
            }
        ]

        print_migration_report(reports)

        captured = capsys.readouterr()
        assert "test" in captured.out
        assert "SAM001" in captured.out
        assert "DRY RUN" in captured.out

    def test_prints_saved_status(self, capsys):
        """Prints [SAVED] when changes were applied."""
        reports = [
            {
                "file": "/path/to/test.json",
                "dataset": "test",
                "entity_count": 1,
                "changes": [{"entity": "X", "field": "f", "old": "a", "new": "b"}],
                "saved": True,
            }
        ]

        print_migration_report(reports)

        captured = capsys.readouterr()
        assert "[SAVED]" in captured.out

    def test_prints_errors(self, capsys):
        """Prints errors for failed migrations."""
        reports = [{"file": "/path/to/bad.json", "error": "Invalid JSON"}]

        print_migration_report(reports)

        captured = capsys.readouterr()
        assert "[ERROR]" in captured.out
        assert "Invalid JSON" in captured.out

    def test_prints_summary(self, capsys):
        """Prints summary at the end."""
        reports = [
            {
                "file": "a.json",
                "dataset": "a",
                "entity_count": 1,
                "changes": [{"entity": "X", "field": "f", "old": "1", "new": "2"}],
                "saved": False,
            },
            {
                "file": "b.json",
                "dataset": "b",
                "entity_count": 1,
                "changes": [],
                "saved": False,
                "migrated": False,
            },
        ]

        print_migration_report(reports)

        captured = capsys.readouterr()
        assert "Total:" in captured.out
        assert "2 datasets" in captured.out
