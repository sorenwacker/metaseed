"""A reference whose target may live outside the dataset.

`reference` has meant one thing: the target is a record in this file, and a
value with no match is broken. Many identifiers are not like that. Darwin Core's
`acceptedNameUsageID` names a taxon in GBIF's backbone, `occurrenceID` can name
a museum catalogue record, and DiSSCo and ENA both carry accessions minted
elsewhere. Declaring those fields as references would have reported correct data
as broken — so they were left undeclared, and therefore checked by nothing at
all, which is the worse of the two.

`reference_scope: external` says the target may be elsewhere. Three outcomes,
for the same reason the term check has three: resolved here, not resolvable from
here (reported as *not checked*), or broken. An identifier nobody can resolve
from here is not thereby wrong.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from metaseed.validators.dataset import DatasetValidator


class _NoService:
    """A term source carrying nothing, so no test here reaches the network."""

    def get_term_sync(self, term_id: str) -> object | None:
        return None

    def has_ontology_sync(self, ontology_id: str) -> bool | None:
        return False


def _profile(scope: str | None) -> dict[str, Any]:
    """A checklist whose taxa may be named from outside it."""
    accepted: dict[str, Any] = {
        "name": "acceptedNameUsageID",
        "type": "string",
        "reference": "Taxon.taxonID",
    }
    if scope is not None:
        accepted["reference_scope"] = scope
    return {
        "spec_version": "0.8",
        "name": "checklist",
        "version": "1.0",
        "display_name": "Checklist",
        "root_entity": "Dataset",
        "entities": {
            "Dataset": {
                "fields": [
                    {"name": "title", "type": "string", "required": True},
                    {"name": "taxa", "type": "list", "items": "Taxon"},
                ]
            },
            "Taxon": {
                "fields": [
                    {"name": "taxonID", "type": "string", "required": True},
                    accepted,
                ]
            },
        },
    }


@pytest.fixture
def specs_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    directory = tmp_path / "metaseed" / "specs" / "checklist" / "1.0"
    directory.mkdir(parents=True)
    return directory


def _write(specs_dir: Path, profile: dict[str, Any]) -> None:
    (specs_dir / "profile.yaml").write_text(yaml.safe_dump(profile, sort_keys=False))


def _dataset(tmp_path: Path, *taxa: tuple[str, str | None]) -> Path:
    path = tmp_path / "dataset.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "title": "A checklist",
                "taxa": [
                    {
                        "taxonID": own,
                        **({"acceptedNameUsageID": accepted} if accepted else {}),
                    }
                    for own, accepted in taxa
                ],
            }
        )
    )
    return path


def _validate(specs_dir: Path, path: Path):
    return DatasetValidator("checklist", "1.0", _NoService()).validate_file(path)


class TestTheDefaultIsUnchanged:
    """The five profiles that already declare references must not move."""

    def test_a_target_that_is_not_here_is_still_broken(
        self, specs_dir: Path, tmp_path: Path
    ) -> None:
        _write(specs_dir, _profile(None))

        result = _validate(specs_dir, _dataset(tmp_path, ("T-1", "GBIF:12345")))

        assert [e.rule for e in result.errors] == ["reference_integrity"]
        assert "GBIF:12345" in result.errors[0].message

    def test_saying_dataset_says_what_the_default_already_said(
        self, specs_dir: Path, tmp_path: Path
    ) -> None:
        _write(specs_dir, _profile("dataset"))

        result = _validate(specs_dir, _dataset(tmp_path, ("T-1", "GBIF:12345")))

        assert [e.rule for e in result.errors] == ["reference_integrity"]


class TestAnExternalTarget:
    def test_an_unresolvable_value_is_not_an_error(
        self, specs_dir: Path, tmp_path: Path
    ) -> None:
        _write(specs_dir, _profile("external"))

        result = _validate(specs_dir, _dataset(tmp_path, ("T-1", "GBIF:12345")))

        assert result.errors == []
        assert result.is_valid

    def test_it_is_reported_as_not_checked(
        self, specs_dir: Path, tmp_path: Path
    ) -> None:
        """Silence would hide the unverifiable surface; an error would invent a
        fault. The third outcome is the honest one."""
        _write(specs_dir, _profile("external"))

        result = _validate(specs_dir, _dataset(tmp_path, ("T-1", "GBIF:12345")))

        assert len(result.warnings) == 1
        assert result.warnings[0].rule == "reference_not_checked"
        assert "acceptedNameUsageID" in result.warnings[0].field
        assert "Taxon.taxonID" in result.warnings[0].message

    def test_one_report_per_field_however_many_rows(
        self, specs_dir: Path, tmp_path: Path
    ) -> None:
        """A dataset of 10,000 occurrences must not say the same thing 10,000
        times: a surface that noisy is one nobody reads."""
        _write(specs_dir, _profile("external"))

        result = _validate(
            specs_dir,
            _dataset(
                tmp_path,
                ("T-1", "GBIF:1"),
                ("T-2", "GBIF:2"),
                ("T-3", "GBIF:3"),
            ),
        )

        assert len(result.warnings) == 1
        assert "3" in result.warnings[0].message

    def test_a_target_that_is_here_is_still_checked(
        self, specs_dir: Path, tmp_path: Path
    ) -> None:
        """External is not an excuse to stop looking: a value naming a record in
        this dataset resolves against it, and nothing is reported."""
        _write(specs_dir, _profile("external"))

        result = _validate(specs_dir, _dataset(tmp_path, ("T-1", None), ("T-2", "T-1")))

        assert result.errors == []
        assert result.warnings == []

    def test_a_field_with_no_values_reports_nothing(
        self, specs_dir: Path, tmp_path: Path
    ) -> None:
        _write(specs_dir, _profile("external"))

        result = _validate(specs_dir, _dataset(tmp_path, ("T-1", None)))

        assert result.warnings == []

    def test_a_directory_reports_it_once_for_the_whole_dataset(
        self, specs_dir: Path, tmp_path: Path
    ) -> None:
        """The fact is about the field, not about the file it was seen in."""
        _write(specs_dir, _profile("external"))
        directory = tmp_path / "dataset"
        directory.mkdir()
        for index in range(3):
            (directory / f"part{index}.yaml").write_text(
                yaml.safe_dump(
                    {
                        "title": "A checklist",
                        "taxa": [
                            {"taxonID": f"T-{index}", "acceptedNameUsageID": "GBIF:1"}
                        ],
                    }
                )
            )

        result = DatasetValidator("checklist", "1.0", _NoService()).validate_directory(
            directory
        )

        assert len(result.warnings) == 1
        assert "3 value(s)" in result.warnings[0].message


class TestWhatTheSpecEditorRefuses:
    def test_a_scope_on_a_field_that_references_nothing(self) -> None:
        """Otherwise the marker says how something resolves that does not
        exist, and reads as a check that is running when none is."""
        from metaseed.specs.builder import SpecBuilder

        profile = _profile("external")
        del profile["entities"]["Taxon"]["fields"][1]["reference"]

        issues = SpecBuilder.from_yaml(yaml.safe_dump(profile)).validate()

        assert any("needs a 'reference'" in issue for issue in issues)

    def test_a_scope_beside_a_reference_is_accepted(self) -> None:
        from metaseed.specs.builder import SpecBuilder

        assert (
            SpecBuilder.from_yaml(yaml.safe_dump(_profile("external"))).validate() == []
        )


class TestTheShippedDeclarations:
    """Darwin Core's three self-referencing identifiers, which waited on this.

    They name a taxon in GBIF's backbone or the campaign a survey belonged to,
    so declaring them as plain references would have reported correct data as
    broken. Left undeclared they were checked by nothing at all.
    """

    def test_darwin_core_declares_them_external(self) -> None:
        from metaseed.specs.loader import SpecLoader

        profile = SpecLoader().load_profile("1.0", "darwin-core")
        assert profile is not None
        declared = {
            f"{entity}.{field.name}": field.reference_scope
            for entity, definition in profile.entities.items()
            for field in definition.fields
            if field.reference
        }

        assert declared["Event.parentEventID"] == "external"
        assert declared["Taxon.acceptedNameUsageID"] == "external"
        assert declared["Taxon.parentNameUsageID"] == "external"

    def test_the_within_dataset_ones_are_untouched(self) -> None:
        """The four that do resolve here keep the default meaning."""
        from metaseed.specs.loader import SpecLoader

        profile = SpecLoader().load_profile("1.0", "darwin-core")
        assert profile is not None
        local = {
            f"{entity}.{field.name}"
            for entity, definition in profile.entities.items()
            for field in definition.fields
            if field.reference and field.reference_scope is None
        }

        assert local == {
            "Event.occurrenceID",
            "Location.eventID",
            "Identification.occurrenceID",
            "Organism.occurrenceID",
        }
