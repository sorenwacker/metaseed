"""Profile version format, the shipped-profile gate, and the content hash.

Covers `metaseed.specs.versioning` and the `ProfileSpec` surface built on it.
The comparator that decides *which* bump a change requires is tested in
tests/test_specs/test_compare.py.

See docs/api/schema-specs.md#profile-versioning.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

import metaseed.specs
from metaseed.specs.builder import SpecBuilder
from metaseed.specs.loader import SpecLoader
from metaseed.specs.schema import (
    EntityDefSpec,
    FieldSpec,
    FieldType,
    ProfileSpec,
    ValidationRuleSpec,
)
from metaseed.specs.versioning import (
    PROFILE_VERSION_PATTERN,
    check_profile_version,
    declared_bump,
)

_SPECS_DIR = Path(metaseed.specs.__file__).resolve().parent
_SHIPPED = sorted(_SPECS_DIR.glob("*/*/profile.yaml"))


def _spec(version: str = "1.0", **overrides: object) -> ProfileSpec:
    """A minimal, valid two-entity spec."""
    data: dict[str, object] = {
        "name": "cinema",
        "version": version,
        "root_entity": "Film",
        "entities": {
            "Film": EntityDefSpec(
                description="A motion picture",
                fields=[
                    FieldSpec(name="identifier", type=FieldType.STRING, required=True),
                    FieldSpec(name="title", type=FieldType.STRING),
                ],
            )
        },
    }
    data.update(overrides)
    return ProfileSpec.model_validate(data)


class TestVersionFormat:
    """`version` is MAJOR.MINOR and nothing else."""

    @pytest.mark.parametrize("version", ["1.0", "0.4", "1.1", "12.3", "1.11", "10.0"])
    def test_major_minor_is_accepted(self, version: str) -> None:
        assert _spec(version).version == version

    @pytest.mark.parametrize(
        "version",
        ["1", "1.0.0", "1.1-dev", "1.1-dev-a1b2c3", "v1.1", "latest", "", "1.", ".1"],
    )
    def test_anything_else_is_rejected(self, version: str) -> None:
        with pytest.raises(ValueError):
            _spec(version)

    def test_the_error_names_the_offender_and_the_rule(self) -> None:
        with pytest.raises(ValueError) as excinfo:
            _spec("1.1-dev-a1b2c3")

        message = str(excinfo.value)
        assert "1.1-dev-a1b2c3" in message
        assert "MAJOR.MINOR" in message
        assert r"^\d+\.\d+$" in message

    def test_check_returns_the_message_instead_of_raising(self) -> None:
        assert check_profile_version("1.0") is None
        problem = check_profile_version("v1")
        assert problem is not None
        assert "v1" in problem

    def test_yaml_import_rejects_a_malformed_version(self) -> None:
        with pytest.raises(ValueError, match=r"MAJOR\.MINOR"):
            SpecBuilder.from_yaml("name: p\nversion: '1'\nentities: {}\n")


@pytest.mark.parametrize(
    "path", _SHIPPED, ids=[str(p.parent.relative_to(_SPECS_DIR)) for p in _SHIPPED]
)
def test_every_shipped_profile_declares_a_major_minor_version(path: Path) -> None:
    """CI gate: a shipped profile with a non-conforming version fails here.

    Loading is the assertion — `ProfileSpec` rejects a malformed version — but
    the explicit pattern check keeps the failure legible.
    """
    spec = ProfileSpec.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))

    assert PROFILE_VERSION_PATTERN.match(spec.version), (
        f"{path} declares version {spec.version!r}"
    )


def test_the_shipped_profile_gate_covers_every_profile() -> None:
    """Guard the gate itself: an empty glob would make it vacuously green."""
    assert len(_SHIPPED) >= 10


class TestContentHash:
    """A canonical hash identifying exact spec content."""

    def test_format_is_sha256_and_64_hex(self) -> None:
        assert re.fullmatch(r"sha256:[0-9a-f]{64}", _spec().content_hash)

    def test_short_hash_is_the_first_twelve_hex_of_the_full_hash(self) -> None:
        spec = _spec()

        assert re.fullmatch(r"sha256:[0-9a-f]{12}", spec.short_hash)
        assert spec.content_hash.startswith(spec.short_hash)

    def test_identical_content_hashes_identically(self) -> None:
        assert _spec().content_hash == _spec().content_hash

    def test_yaml_round_trip_is_stable(self) -> None:
        spec = _spec()

        reloaded = SpecBuilder.from_yaml(SpecBuilder.from_spec(spec).to_yaml()).spec

        assert reloaded.content_hash == spec.content_hash

    def test_mapping_key_order_in_the_source_yaml_does_not_change_the_hash(
        self,
    ) -> None:
        ordered = (
            "name: cinema\n"
            "version: '1.0'\n"
            "root_entity: Film\n"
            "entities:\n"
            "  Film:\n"
            "    description: A motion picture\n"
            "    fields:\n"
            "      - name: title\n"
            "        type: string\n"
        )
        shuffled = (
            "root_entity: Film\n"
            "entities:\n"
            "  Film:\n"
            "    fields:\n"
            "      - type: string\n"
            "        name: title\n"
            "    description: A motion picture\n"
            "version: '1.0'\n"
            "name: cinema\n"
        )

        assert (
            SpecBuilder.from_yaml(shuffled).spec.content_hash
            == SpecBuilder.from_yaml(ordered).spec.content_hash
        )

    def test_entity_order_in_the_source_yaml_does_not_change_the_hash(self) -> None:
        first = (
            "name: cinema\nversion: '1.0'\nroot_entity: Film\n"
            "entities:\n  Film:\n    description: f\n  Credit:\n    description: c\n"
        )
        second = (
            "name: cinema\nversion: '1.0'\nroot_entity: Film\n"
            "entities:\n  Credit:\n    description: c\n  Film:\n    description: f\n"
        )

        assert (
            SpecBuilder.from_yaml(second).spec.content_hash
            == SpecBuilder.from_yaml(first).spec.content_hash
        )

    def test_an_explicit_null_hashes_like_an_omitted_key(self) -> None:
        omitted = "name: cinema\nversion: '1.0'\nentities: {}\n"
        explicit = "name: cinema\nversion: '1.0'\nentities: {}\nontology: null\n"

        assert (
            SpecBuilder.from_yaml(explicit).spec.content_hash
            == SpecBuilder.from_yaml(omitted).spec.content_hash
        )

    def test_a_value_written_explicitly_hashes_like_its_default(self) -> None:
        implicit = (
            "name: cinema\nversion: '1.0'\n"
            "entities:\n  Film:\n    fields:\n      - name: title\n        type: string\n"
        )
        explicit = (
            "name: cinema\nversion: '1.0'\n"
            "entities:\n  Film:\n    fields:\n      - name: title\n"
            "        type: string\n        required: false\n"
        )

        assert (
            SpecBuilder.from_yaml(explicit).spec.content_hash
            == SpecBuilder.from_yaml(implicit).spec.content_hash
        )

    @pytest.mark.parametrize(
        ("attribute", "value"),
        [
            ("version", "1.1"),
            ("name", "theatre"),
            ("root_entity", "Credit"),
            ("description", "changed"),
        ],
    )
    def test_a_real_content_change_changes_the_hash(
        self, attribute: str, value: str
    ) -> None:
        changed = _spec()
        setattr(changed, attribute, value)

        assert changed.content_hash != _spec().content_hash

    def test_a_field_edit_changes_the_hash(self) -> None:
        changed = _spec()
        changed.entities["Film"].fields[1].required = True

        assert changed.content_hash != _spec().content_hash

    def test_field_order_is_content_and_changes_the_hash(self) -> None:
        """`fields` is a sequence; its order drives form and template layout."""
        reordered = _spec()
        reordered.entities["Film"].fields.reverse()

        assert reordered.content_hash != _spec().content_hash

    def test_two_specs_claiming_the_same_version_are_distinguishable(self) -> None:
        published = _spec("1.1")
        local = _spec("1.1")
        local.entities["Film"].fields.append(
            FieldSpec(name="runtime_minutes", type=FieldType.INTEGER)
        )

        assert published.version == local.version
        assert published.content_hash != local.content_hash


class TestDeclaredBump:
    """What a pair of version strings claims about compatibility."""

    @pytest.mark.parametrize(
        ("old", "new", "expected"),
        [
            ("1.0", "2.0", "major"),
            ("1.0", "1.1", "minor"),
            ("1.0", "1.0", "none"),
            ("1.1", "1.0", "downgrade"),
            ("2.0", "1.9", "downgrade"),
            ("1.9", "2.0", "major"),
        ],
    )
    def test_classification(self, old: str, new: str, expected: str) -> None:
        assert declared_bump(old, new) == expected

    def test_a_malformed_version_is_an_error(self) -> None:
        with pytest.raises(ValueError, match=r"MAJOR\.MINOR"):
            declared_bump("1.0", "1.1-dev")


class TestBuilderReportsVersionFormat:
    """`SpecBuilder.validate()` surfaces a malformed version like any issue."""

    def _draft(self) -> SpecBuilder:
        builder = SpecBuilder.empty("cinema", "1.0")
        builder.add_entity("Film")
        builder.add_field("Film", "title", FieldType.STRING)
        builder.set_root_entity("Film")
        return builder

    def test_a_well_formed_draft_reports_no_version_issue(self) -> None:
        assert self._draft().validate() == []

    def test_a_malformed_version_is_reported_as_an_issue(self) -> None:
        builder = self._draft()
        builder.set_metadata(version="1.1-dev-a1b2c3")

        issues = builder.validate()

        assert any(
            "1.1-dev-a1b2c3" in issue and "MAJOR.MINOR" in issue for issue in issues
        )

    def test_the_draft_is_still_editable_with_a_malformed_version(self) -> None:
        """Reporting, not raising: authoring continues after a bad version."""
        builder = self._draft()
        builder.set_metadata(version="draft")
        builder.add_field("Film", "year", FieldType.INTEGER)

        assert [f.name for f in builder.spec.entities["Film"].fields] == [
            "title",
            "year",
        ]


class TestFromTemplateKeepsALoadableVersion:
    """A cloned draft must round-trip through YAML."""

    def test_the_clone_keeps_the_source_version(self) -> None:
        builder = SpecBuilder.from_template("miappe", "1.2")

        assert builder.spec.version == "1.2"

    def test_the_clone_survives_a_yaml_round_trip(self) -> None:
        builder = SpecBuilder.from_template("miappe", "1.2")

        reloaded = SpecBuilder.from_yaml(builder.to_yaml()).spec

        assert reloaded.content_hash == builder.spec.content_hash


class TestSaveRefusesAnUnloadableVersion:
    def test_save_spec_rejects_a_malformed_version(self, tmp_path, monkeypatch) -> None:
        from metaseed.specs import persistence

        monkeypatch.setattr(persistence, "get_custom_specs_dir", lambda: tmp_path)
        spec = _spec()
        spec.name = "my-cinema"
        spec.version = "1.1-dev-a1b2c3"

        with pytest.raises(ValueError, match=r"MAJOR\.MINOR"):
            persistence.save_spec(spec)

        assert list(tmp_path.iterdir()) == []


class TestLoaderConstraintInjection:
    """Loading must not invent an empty constraints block.

    ``_merge_rule_constraints_into_fields`` creates ``Constraints()`` before it
    knows whether any value applies, so a rule that writes nothing leaves an
    all-None object where the spec declared none. ``exclude_none`` keeps that
    object as an empty mapping while a genuine ``None`` is dropped, so the same
    content hashes two ways -- breaking the round-trip stability the hash
    promises.
    """

    @staticmethod
    def _load(tmp_path: Path) -> ProfileSpec:
        """Write a spec whose numeric rule targets a string field, and load it.

        The rule passes the type gate (a string field is a valid target) but
        every guarded assignment inside it is skipped, so nothing is written.
        """
        spec = _spec(
            validation_rules=[
                ValidationRuleSpec(
                    name="title_range", applies_to="Film", field="title", minimum=1
                )
            ]
        )
        profile_dir = tmp_path / "cinema" / "1.0"
        profile_dir.mkdir(parents=True)
        (profile_dir / "profile.yaml").write_text(SpecBuilder.from_spec(spec).to_yaml())

        loader = SpecLoader(profile="cinema")
        loader._user_specs_dir = tmp_path
        return loader.load_profile(version="1.0", profile="cinema")

    def test_a_rule_that_sets_nothing_leaves_the_field_without_constraints(
        self, tmp_path: Path
    ) -> None:
        loaded = self._load(tmp_path)

        title = next(f for f in loaded.entities["Film"].fields if f.name == "title")
        assert title.constraints is None

    def test_such_a_spec_still_round_trips_to_the_same_hash(
        self, tmp_path: Path
    ) -> None:
        loaded = self._load(tmp_path)

        on_disk = SpecBuilder.from_yaml(
            (tmp_path / "cinema" / "1.0" / "profile.yaml").read_text()
        ).spec
        assert loaded.content_hash == on_disk.content_hash


class TestVersionOrdering:
    """Versions order numerically, not lexicographically: '1.9' < '1.10'.

    Both 'latest version' answers — the profile catalogue's and the spec
    filesystem's — sorted version strings as text, so releasing 1.10 after 1.9
    made 'latest' step backwards to 1.9 (#review-260813)."""

    def test_the_key_orders_two_digit_minors_after_one_digit(self) -> None:
        from metaseed.specs.versioning import version_sort_key

        assert sorted(["1.10", "1.9", "1.2"], key=version_sort_key) == [
            "1.2",
            "1.9",
            "1.10",
        ]

    def test_a_malformed_version_sorts_first_not_crashes(self) -> None:
        """A stray directory name must not take 'latest' from a real version."""
        from metaseed.specs.versioning import version_sort_key

        assert sorted(["1.1", "not-a-version"], key=version_sort_key)[-1] == "1.1"

    def test_list_versions_uses_it(self, tmp_path, monkeypatch) -> None:
        import yaml

        from metaseed.specs.loader import SpecLoader

        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
        for version in ("1.9", "1.10", "1.2"):
            d = tmp_path / "metaseed" / "specs" / "orderly" / version
            d.mkdir(parents=True)
            (d / "profile.yaml").write_text(
                yaml.safe_dump(
                    {
                        "name": "orderly",
                        "version": version,
                        "root_entity": "Thing",
                        "entities": {
                            "Thing": {"fields": [{"name": "id", "type": "string"}]}
                        },
                    }
                )
            )

        versions = SpecLoader().list_versions("orderly")

        assert versions == ["1.2", "1.9", "1.10"], (
            "versions[-1] is what 'latest' means everywhere"
        )
