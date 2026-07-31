"""Tests for ``metaseed migrate-specs`` (metaseed.cli.migrate_specs).

Every test builds its own specs tree under ``tmp_path`` and passes it in
explicitly, so no test reads or writes the developer's real user specs
directory.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from metaseed.cli import migrate_specs as migrate_specs_module
from metaseed.cli.app import app
from metaseed.cli.migrate_specs import (
    Outcome,
    SpecVersionMigration,
    has_failures,
    migrate_spec_versions,
    normalize_profile_version,
    print_migration_report,
)
from metaseed.specs.schema import ProfileSpec

SPEC_TEMPLATE = """\
spec_version: '0.5'
version: {version}  # cloned from miappe
name: {name}
display_name: Cinema
description: A profile used by the migration tests.
root_entity: Film
entities:
  Film:
    description: A film.
    fields:
    - name: title
      codename: title
      type: string
      required: true
      description: The title.
"""


def write_spec(
    root: Path, name: str, version_dir: str, declared: str, *, quoted: bool = True
) -> Path:
    """Write a spec at ``root/<name>/<version_dir>/profile.yaml``.

    Args:
        root: The specs tree root.
        name: Profile name.
        version_dir: Directory name holding the spec.
        declared: The value written for the ``version:`` key.
        quoted: Whether the value is written as a quoted YAML string.

    Returns:
        Path to the written profile.yaml.
    """
    path = root / name / version_dir / "profile.yaml"
    path.parent.mkdir(parents=True)
    value = f"'{declared}'" if quoted else declared
    path.write_text(SPEC_TEMPLATE.format(version=value, name=name), encoding="utf-8")
    return path


def only(migrations: list[SpecVersionMigration]) -> SpecVersionMigration:
    """Return the single reported migration, asserting there is exactly one."""
    assert len(migrations) == 1, migrations
    return migrations[0]


class TestNormalizeProfileVersion:
    """Each documented normalization rule."""

    def test_conforming_version_is_unchanged(self):
        """A MAJOR.MINOR version normalizes to itself and is not lossy."""
        result = normalize_profile_version("1.2")
        assert result.value == "1.2"
        assert result.lossy is False

    def test_leading_v_is_stripped(self):
        """'v1.2' -> '1.2'."""
        result = normalize_profile_version("v1.2")
        assert result.value == "1.2"
        assert result.lossy is False

    def test_single_integer_gains_a_minor_component(self):
        """'1' -> '1.0'."""
        result = normalize_profile_version("1")
        assert result.value == "1.0"
        assert result.lossy is False

    def test_prerelease_suffix_is_dropped(self):
        """The from_template population: '1.2-dev-a1b2c3' -> '1.2'."""
        result = normalize_profile_version("1.2-dev-a1b2c3")
        assert result.value == "1.2"
        assert result.lossy is False

    def test_release_candidate_suffix_is_dropped(self):
        """'1.2-rc1' -> '1.2'."""
        assert normalize_profile_version("1.2-rc1").value == "1.2"

    def test_build_suffix_is_dropped(self):
        """'1.2+build.5' -> '1.2'."""
        assert normalize_profile_version("1.2+build.5").value == "1.2"

    def test_three_components_truncate_and_are_lossy(self):
        """'1.2.3' -> '1.2', flagged lossy because the patch is discarded."""
        result = normalize_profile_version("1.2.3")
        assert result.value == "1.2"
        assert result.lossy is True

    def test_four_components_truncate_and_are_lossy(self):
        """'1.2.3.4' -> '1.2', also lossy."""
        result = normalize_profile_version("1.2.3.4")
        assert result.value == "1.2"
        assert result.lossy is True

    def test_rules_combine(self):
        """'v1.2.3-rc1' -> '1.2', lossy: strip, truncate and suffix at once."""
        result = normalize_profile_version("v1.2.3-rc1")
        assert result.value == "1.2"
        assert result.lossy is True

    @pytest.mark.parametrize("value", ["draft", "latest", "", "v", "release-2"])
    def test_underivable_values_are_not_guessed(self, value):
        """A value with no leading integer yields no version."""
        result = normalize_profile_version(value)
        assert result.value is None
        assert result.lossy is False

    def test_a_rule_is_always_named(self):
        """Every result carries the rule text the report prints."""
        for value in ["1.2", "v1.2", "1", "1.2-rc1", "1.2.3", "draft"]:
            assert normalize_profile_version(value).rule


class TestDryRun:
    """Dry run reports without touching the filesystem."""

    def test_dry_run_leaves_the_file_byte_identical(self, tmp_path):
        """The default mode never writes."""
        path = write_spec(tmp_path, "cinema", "1.2-dev-a1b2c3", "1.2-dev-a1b2c3")
        before = path.read_bytes()

        migrations = migrate_spec_versions(dry_run=True, dirs=[tmp_path])

        assert path.read_bytes() == before
        assert only(migrations).applied is False

    def test_dry_run_leaves_the_directory_in_place(self, tmp_path):
        """A planned rename is not performed in dry run."""
        write_spec(tmp_path, "cinema", "1.2-dev-a1b2c3", "1.2-dev-a1b2c3")

        migrate_spec_versions(dry_run=True, dirs=[tmp_path])

        assert (tmp_path / "cinema" / "1.2-dev-a1b2c3").is_dir()
        assert not (tmp_path / "cinema" / "1.2").exists()

    def test_dry_run_reports_the_repair_it_would_make(self, tmp_path):
        """The report names the path, old version and new version."""
        path = write_spec(tmp_path, "cinema", "1.2-dev-a1b2c3", "1.2-dev-a1b2c3")

        migration = only(migrate_spec_versions(dry_run=True, dirs=[tmp_path]))

        assert migration.path == path
        assert migration.old_version == "1.2-dev-a1b2c3"
        assert migration.new_version == "1.2"
        assert migration.outcome is Outcome.REPAIRABLE


class TestApply:
    """--apply writes, and writes only the version."""

    def test_apply_rewrites_only_the_version_line(self, tmp_path):
        """Every other line of the file survives unchanged."""
        path = write_spec(tmp_path, "cinema", "1.2-dev-a1b2c3", "1.2-dev-a1b2c3")
        before = path.read_text(encoding="utf-8").splitlines()

        migrate_spec_versions(dry_run=False, dirs=[tmp_path])

        after = (
            (tmp_path / "cinema" / "1.2" / "profile.yaml")
            .read_text(encoding="utf-8")
            .splitlines()
        )
        assert len(after) == len(before)
        changed = [
            i for i, (a, b) in enumerate(zip(before, after, strict=True)) if a != b
        ]
        assert changed == [1]
        assert after[1] == "version: '1.2'  # cloned from miappe"

    def test_the_repaired_spec_loads_as_a_profilespec(self, tmp_path):
        """The point of the migration: the file is loadable again."""
        write_spec(tmp_path, "cinema", "1.2-dev-a1b2c3", "1.2-dev-a1b2c3")

        migrate_spec_versions(dry_run=False, dirs=[tmp_path])

        data = yaml.safe_load(
            (tmp_path / "cinema" / "1.2" / "profile.yaml").read_text(encoding="utf-8")
        )
        assert ProfileSpec.model_validate(data).version == "1.2"

    def test_apply_renames_the_version_directory(self, tmp_path):
        """The directory name is the version specs are addressed by."""
        write_spec(tmp_path, "cinema", "1.2-dev-a1b2c3", "1.2-dev-a1b2c3")

        migration = only(migrate_spec_versions(dry_run=False, dirs=[tmp_path]))

        assert (tmp_path / "cinema" / "1.2" / "profile.yaml").exists()
        assert not (tmp_path / "cinema" / "1.2-dev-a1b2c3").exists()
        assert migration.renamed_to == tmp_path / "cinema" / "1.2"
        assert migration.applied is True

    def test_a_mismatched_directory_is_left_alone(self, tmp_path):
        """When the directory already disagrees with the version, only the file changes."""
        write_spec(tmp_path, "cinema", "1.0", "1.2-dev-a1b2c3")

        migration = only(migrate_spec_versions(dry_run=False, dirs=[tmp_path]))

        assert (tmp_path / "cinema" / "1.0" / "profile.yaml").exists()
        assert not (tmp_path / "cinema" / "1.2").exists()
        assert migration.renamed_to is None
        assert migration.applied is True
        data = yaml.safe_load(
            (tmp_path / "cinema" / "1.0" / "profile.yaml").read_text(encoding="utf-8")
        )
        assert data["version"] == "1.2"

    def test_an_unquoted_numeric_version_is_quoted(self, tmp_path):
        """'version: 1' is an int in YAML; it becomes the string '1.0'."""
        write_spec(tmp_path, "cinema", "1", "1", quoted=False)

        migrate_spec_versions(dry_run=False, dirs=[tmp_path])

        text = (tmp_path / "cinema" / "1.0" / "profile.yaml").read_text(
            encoding="utf-8"
        )
        assert "version: '1.0'" in text
        assert ProfileSpec.model_validate(yaml.safe_load(text)).version == "1.0"

    def test_a_conforming_but_unquoted_version_is_quoted_in_place(self, tmp_path):
        """'version: 1.0' is a float in YAML, so the spec fails to load as-is."""
        write_spec(tmp_path, "cinema", "1.0", "1.0", quoted=False)

        migration = only(migrate_spec_versions(dry_run=False, dirs=[tmp_path]))

        assert migration.outcome is Outcome.REPAIRABLE
        assert migration.applied is True
        assert migration.renamed_to is None
        text = (tmp_path / "cinema" / "1.0" / "profile.yaml").read_text(
            encoding="utf-8"
        )
        assert "version: '1.0'" in text
        assert ProfileSpec.model_validate(yaml.safe_load(text)).version == "1.0"

    def test_a_trailing_zero_is_replaced_whole_not_by_prefix(self, tmp_path):
        """'version: 1.20' is the float 1.2; the value must not be spliced."""
        write_spec(tmp_path, "cinema", "1.20", "1.20", quoted=False)

        migrate_spec_versions(dry_run=False, dirs=[tmp_path])

        text = (tmp_path / "cinema" / "1.20" / "profile.yaml").read_text(
            encoding="utf-8"
        )
        assert "version: '1.2'  # cloned from miappe" in text
        assert ProfileSpec.model_validate(yaml.safe_load(text)).version == "1.2"

    def test_a_double_quoted_value_keeps_its_comment(self, tmp_path):
        """Quoting style is normalized; everything after the value is kept."""
        path = tmp_path / "cinema" / "1.2-rc1" / "profile.yaml"
        path.parent.mkdir(parents=True)
        path.write_text(
            SPEC_TEMPLATE.format(version='"1.2-rc1"', name="cinema"), encoding="utf-8"
        )

        migrate_spec_versions(dry_run=False, dirs=[tmp_path])

        text = (tmp_path / "cinema" / "1.2" / "profile.yaml").read_text(
            encoding="utf-8"
        )
        assert "version: '1.2'  # cloned from miappe" in text

    def test_an_unlocatable_version_line_is_left_for_a_human(self, tmp_path):
        """A flow-style document has no 'version:' line to rewrite."""
        path = tmp_path / "cinema" / "1.2-rc1" / "profile.yaml"
        path.parent.mkdir(parents=True)
        path.write_text(
            '{"version": "1.2-rc1", "name": "cinema", "root_entity": "Film",'
            ' "entities": {}}\n',
            encoding="utf-8",
        )
        before = path.read_bytes()

        migration = only(migrate_spec_versions(dry_run=False, dirs=[tmp_path]))

        assert path.read_bytes() == before
        assert migration.outcome is Outcome.MANUAL
        assert migration.applied is False

    def test_an_unlocatable_version_line_is_reported_in_dry_run_too(self, tmp_path):
        """A dry run must predict what --apply will do, not disagree with it."""
        path = tmp_path / "cinema" / "1.2-rc1" / "profile.yaml"
        path.parent.mkdir(parents=True)
        path.write_text('{"version": "1.2-rc1", "name": "cinema"}\n', encoding="utf-8")

        migration = only(migrate_spec_versions(dry_run=True, dirs=[tmp_path]))

        assert migration.outcome is Outcome.MANUAL

    def test_a_conforming_spec_is_not_rewritten(self, tmp_path):
        """Nothing to do means nothing written and nothing reported."""
        path = write_spec(tmp_path, "cinema", "1.2", "1.2")
        before = path.read_bytes()

        migrations = migrate_spec_versions(dry_run=False, dirs=[tmp_path])

        assert path.read_bytes() == before
        assert migrations == []
        assert has_failures(migrations) is False


class TestLossy:
    """Truncating a patch component is reported, not hidden."""

    def test_three_component_version_is_flagged_lossy(self, tmp_path):
        """'1.2.3' migrates to '1.2' and the report says information was dropped."""
        write_spec(tmp_path, "cinema", "1.2.3", "1.2.3")

        migration = only(migrate_spec_versions(dry_run=True, dirs=[tmp_path]))

        assert migration.new_version == "1.2"
        assert migration.lossy is True

    def test_lossy_is_not_a_failure(self, tmp_path):
        """A lossy repair still succeeds; --apply exits 0."""
        write_spec(tmp_path, "cinema", "1.2.3", "1.2.3")

        migrations = migrate_spec_versions(dry_run=False, dirs=[tmp_path])

        assert only(migrations).applied is True
        assert has_failures(migrations) is False


class TestManualFix:
    """Underivable versions are reported, never guessed."""

    def test_underivable_version_is_reported_not_changed(self, tmp_path):
        """'draft' is left exactly as written."""
        path = write_spec(tmp_path, "cinema", "draft", "draft")
        before = path.read_bytes()

        migration = only(migrate_spec_versions(dry_run=False, dirs=[tmp_path]))

        assert path.read_bytes() == before
        assert migration.outcome is Outcome.MANUAL
        assert migration.new_version is None
        assert migration.old_version == "draft"
        assert migration.applied is False

    def test_manual_report_names_the_path_and_the_rule(self, tmp_path):
        """The report is actionable without opening the file."""
        path = write_spec(tmp_path, "cinema", "latest", "latest")

        migration = only(migrate_spec_versions(dry_run=True, dirs=[tmp_path]))

        assert migration.path == path
        assert migration.reason

    def test_manual_fixes_are_not_failures(self, tmp_path):
        """--apply exits 0: the command did everything it could do."""
        write_spec(tmp_path, "cinema", "draft", "draft")

        migrations = migrate_spec_versions(dry_run=False, dirs=[tmp_path])

        assert has_failures(migrations) is False


class TestCollisions:
    """Two specs must never be normalized onto one identity."""

    def test_two_specs_normalizing_to_one_version_are_refused(self, tmp_path):
        """Both files are left untouched, including their version value."""
        first = write_spec(tmp_path, "cinema", "1.2-rc1", "1.2-rc1")
        second = write_spec(tmp_path, "cinema", "1.2-dev-a1b2c3", "1.2-dev-a1b2c3")
        before = (first.read_bytes(), second.read_bytes())

        migrations = migrate_spec_versions(dry_run=False, dirs=[tmp_path])

        assert (first.read_bytes(), second.read_bytes()) == before
        assert {m.outcome for m in migrations} == {Outcome.COLLISION}
        assert len(migrations) == 2
        assert all("1.2" in m.reason for m in migrations)

    def test_a_collision_is_a_failure(self, tmp_path):
        """--apply exits non-zero: a requested repair did not happen."""
        write_spec(tmp_path, "cinema", "1.2-rc1", "1.2-rc1")
        write_spec(tmp_path, "cinema", "1.2-dev-a1b2c3", "1.2-dev-a1b2c3")

        migrations = migrate_spec_versions(dry_run=False, dirs=[tmp_path])

        assert has_failures(migrations) is True

    def test_an_existing_target_directory_is_refused(self, tmp_path):
        """A repair that would overwrite a released version is refused."""
        write_spec(tmp_path, "cinema", "1.2", "1.2")
        stale = write_spec(tmp_path, "cinema", "1.2-dev-a1b2c3", "1.2-dev-a1b2c3")
        before = stale.read_bytes()

        migration = only(migrate_spec_versions(dry_run=False, dirs=[tmp_path]))

        assert stale.read_bytes() == before
        assert migration.outcome is Outcome.COLLISION
        assert (tmp_path / "cinema" / "1.2" / "profile.yaml").exists()

    def test_the_same_version_under_different_names_is_not_a_collision(self, tmp_path):
        """Collision is per profile name, not across the whole tree."""
        write_spec(tmp_path, "cinema", "1.2-rc1", "1.2-rc1")
        write_spec(tmp_path, "theatre", "1.2-rc1", "1.2-rc1")

        migrations = migrate_spec_versions(dry_run=False, dirs=[tmp_path])

        assert {m.outcome for m in migrations} == {Outcome.REPAIRABLE}
        assert all(m.applied for m in migrations)
        assert has_failures(migrations) is False

    def test_a_mismatched_directory_cannot_collide(self, tmp_path):
        """No rename is planned, so an existing 1.2 directory is irrelevant."""
        write_spec(tmp_path, "cinema", "1.2", "1.2")
        write_spec(tmp_path, "cinema", "0.9", "1.2-rc1")

        migration = only(migrate_spec_versions(dry_run=False, dirs=[tmp_path]))

        assert migration.outcome is Outcome.REPAIRABLE
        assert migration.applied is True

    def test_a_duplicated_declared_identity_is_reported(self, tmp_path, capsys):
        """The repair is safe -- different paths -- but must not pass silently.

        Nothing is overwritten and both specs stay addressable by their own
        directory, so this is a note rather than a refusal; but two files then
        claim the same name and version, which the report has to say.
        """
        write_spec(tmp_path, "cinema", "1.2", "1.2")
        write_spec(tmp_path, "cinema", "0.9", "1.2-rc1")

        migrations = migrate_spec_versions(dry_run=True, dirs=[tmp_path])
        print_migration_report(migrations, dry_run=True)

        assert "also declares" in capsys.readouterr().out


class TestReportOutput:
    """The printed report carries what the docs promise."""

    def test_report_lists_path_versions_and_flags(self, tmp_path, capsys):
        """One line per non-conforming spec plus a summary."""
        write_spec(tmp_path, "cinema", "1.2.3", "1.2.3")
        write_spec(tmp_path, "theatre", "draft", "draft")

        migrations = migrate_spec_versions(dry_run=True, dirs=[tmp_path])
        print_migration_report(migrations, dry_run=True)

        out = capsys.readouterr().out
        assert "1.2.3" in out
        assert "LOSSY" in out
        assert "NEEDS MANUAL FIX" in out
        assert "draft" in out
        assert "profile.yaml" in out

    def test_report_distinguishes_a_planned_repair_from_a_written_one(
        self, tmp_path, capsys
    ):
        """A dry-run line must not read as though the file was changed."""
        write_spec(tmp_path, "cinema", "1.2-rc1", "1.2-rc1")

        print_migration_report(
            migrate_spec_versions(dry_run=True, dirs=[tmp_path]), dry_run=True
        )
        planned = capsys.readouterr().out

        print_migration_report(
            migrate_spec_versions(dry_run=False, dirs=[tmp_path]), dry_run=False
        )
        written = capsys.readouterr().out

        assert "WOULD REPAIR" in planned
        assert "REPAIRED" in written
        assert "WOULD REPAIR" not in written

    def test_report_does_not_claim_a_matching_directory_differs(self, tmp_path, capsys):
        """The only fault here is the quoting; the directory already agrees."""
        write_spec(tmp_path, "cinema", "1.0", "1.0", quoted=False)

        print_migration_report(
            migrate_spec_versions(dry_run=True, dirs=[tmp_path]), dry_run=True
        )

        assert "differs" not in capsys.readouterr().out

    def test_report_warns_that_renames_strand_dataset_references(
        self, tmp_path, capsys
    ):
        """A saved dataset records the profile version it was created against."""
        write_spec(tmp_path, "cinema", "1.2-rc1", "1.2-rc1")

        print_migration_report(
            migrate_spec_versions(dry_run=True, dirs=[tmp_path]), dry_run=True
        )

        assert "dataset" in capsys.readouterr().out.lower()

    def test_no_rename_means_no_dataset_warning(self, tmp_path, capsys):
        """The warning is tied to renames, not printed on every run."""
        write_spec(tmp_path, "cinema", "1.0", "1.2-rc1")

        print_migration_report(
            migrate_spec_versions(dry_run=True, dirs=[tmp_path]), dry_run=True
        )

        assert "dataset" not in capsys.readouterr().out.lower()

    def test_report_states_when_there_is_nothing_to_do(self, tmp_path, capsys):
        """An empty report is still a report."""
        write_spec(tmp_path, "cinema", "1.2", "1.2")

        print_migration_report(
            migrate_spec_versions(dry_run=True, dirs=[tmp_path]), dry_run=True
        )

        assert "0" in capsys.readouterr().out


class TestCliCommand:
    """The command is reachable as `metaseed migrate-specs`."""

    def test_dry_run_is_the_default(self, tmp_path, monkeypatch):
        """Running the command without --apply writes nothing."""
        path = write_spec(tmp_path, "cinema", "1.2-dev-a1b2c3", "1.2-dev-a1b2c3")
        before = path.read_bytes()
        monkeypatch.setattr(migrate_specs_module, "get_spec_dirs", lambda: [tmp_path])

        result = CliRunner().invoke(app, ["migrate-specs"])

        assert result.exit_code == 0, result.output
        assert path.read_bytes() == before
        assert "1.2-dev-a1b2c3" in result.output

    def test_apply_writes_and_exits_zero(self, tmp_path, monkeypatch):
        """A successful repair is not an error."""
        write_spec(tmp_path, "cinema", "1.2-dev-a1b2c3", "1.2-dev-a1b2c3")
        monkeypatch.setattr(migrate_specs_module, "get_spec_dirs", lambda: [tmp_path])

        result = CliRunner().invoke(app, ["migrate-specs", "--apply"])

        assert result.exit_code == 0, result.output
        assert (tmp_path / "cinema" / "1.2" / "profile.yaml").exists()

    def test_apply_exits_non_zero_on_a_refused_collision(self, tmp_path, monkeypatch):
        """Genuine failure to complete a repair is signalled to the shell."""
        write_spec(tmp_path, "cinema", "1.2-rc1", "1.2-rc1")
        write_spec(tmp_path, "cinema", "1.2-dev-a1b2c3", "1.2-dev-a1b2c3")
        monkeypatch.setattr(migrate_specs_module, "get_spec_dirs", lambda: [tmp_path])

        result = CliRunner().invoke(app, ["migrate-specs", "--apply"])

        assert result.exit_code != 0
        assert "COLLISION" in result.output

    def test_apply_exits_zero_when_nothing_needs_repair(self, tmp_path, monkeypatch):
        """Nothing to do is success."""
        write_spec(tmp_path, "cinema", "1.2", "1.2")
        monkeypatch.setattr(migrate_specs_module, "get_spec_dirs", lambda: [tmp_path])

        result = CliRunner().invoke(app, ["migrate-specs", "--apply"])

        assert result.exit_code == 0, result.output
