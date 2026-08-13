"""A predicated rule, from the profile on disk to the message a person reads.

The unit tests either side of this one cover the predicate and the rule. This
one is the join: the profile is written to disk, loaded through `SpecLoader`,
and a dataset validated through `DatasetValidator` — which is what proves the
predicate survives loading, that the item label is resolved from the item
entity's own markers, and that a predicate naming a field nobody declares is
refused at load rather than becoming a rule that never fires (#211).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from metaseed.specs.builder import SpecBuilder
from metaseed.specs.loader import SpecLoader, SpecLoadError
from metaseed.validators.dataset import DatasetValidator


class _NoService:
    """A term source carrying nothing, so no test here reaches the network."""

    def get_term_sync(self, term_id: str) -> object | None:
        return None

    def has_ontology_sync(self, ontology_id: str) -> bool | None:
        return False


def _profile(predicate: dict[str, Any] | None = None, **rule: Any) -> dict[str, Any]:
    """A two-entity profile whose sample type declares its display column."""
    where = (
        {"field": "is_display_column", "op": "==", "value": True}
        if predicate is None
        else predicate
    )
    return {
        "spec_version": "0.7",
        "name": "seekish",
        "version": "1.0",
        "display_name": "Seekish",
        "root_entity": "SampleType",
        "entities": {
            "SampleType": {
                "fields": [
                    {"name": "title", "type": "string", "required": True},
                    {"name": "attributes", "type": "list", "items": "SampleAttribute"},
                ]
            },
            "SampleAttribute": {
                "fields": [
                    {"name": "name", "type": "string", "is_label": True},
                    {"name": "is_display_column", "type": "boolean"},
                    {"name": "data_type", "type": "string"},
                ]
            },
        },
        "validation_rules": [
            {
                "name": "exactly_one_display_column",
                "type": "cardinality",
                "applies_to": ["SampleType"],
                "field": "attributes",
                "where": where,
                "min_items": 1,
                "max_items": 1,
                **rule,
            }
        ],
    }


@pytest.fixture
def specs_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A user specs directory this test owns, so nothing touches the real one."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    directory = tmp_path / "metaseed" / "specs" / "seekish" / "1.0"
    directory.mkdir(parents=True)
    return directory


def _write(specs_dir: Path, profile: dict[str, Any]) -> None:
    (specs_dir / "profile.yaml").write_text(yaml.safe_dump(profile, sort_keys=False))


def _dataset(tmp_path: Path, *display_flags: bool) -> Path:
    path = tmp_path / "dataset.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "title": "CropXR extended metadata controlled vocabulary upload",
                "attributes": [
                    {"name": f"Attribute {i}", "is_display_column": flag}
                    for i, flag in enumerate(display_flags)
                ],
            }
        )
    )
    return path


class TestValidatingADataset:
    def test_the_template_with_no_display_column_is_reported(
        self, specs_dir: Path, tmp_path: Path
    ) -> None:
        _write(specs_dir, _profile())

        result = DatasetValidator("seekish", "1.0", _NoService()).validate_file(
            _dataset(tmp_path, False, False, False)
        )

        reported = [e for e in result.errors if e.rule == "exactly_one_display_column"]
        assert len(reported) == 1
        assert (
            "expected exactly 1 of 3 'attributes' to match "
            "is_display_column == true, found 0" in reported[0].message
        )

    def test_two_display_columns_are_named_by_their_own_label_field(
        self, specs_dir: Path, tmp_path: Path
    ) -> None:
        """`name` is marked `is_label` on SampleAttribute, and that is where the
        message gets it from — not from the field being called 'name'."""
        _write(specs_dir, _profile())

        result = DatasetValidator("seekish", "1.0", _NoService()).validate_file(
            _dataset(tmp_path, True, False, True)
        )

        reported = [e for e in result.errors if e.rule == "exactly_one_display_column"]
        assert "attributes[0] 'Attribute 0', attributes[2] 'Attribute 2'" in (
            reported[0].message
        )

    def test_exactly_one_passes(self, specs_dir: Path, tmp_path: Path) -> None:
        _write(specs_dir, _profile())

        result = DatasetValidator("seekish", "1.0", _NoService()).validate_file(
            _dataset(tmp_path, False, True, False)
        )

        assert [
            e for e in result.errors if e.rule == "exactly_one_display_column"
        ] == []


class TestWhatTheLoaderRefuses:
    def test_a_predicate_field_the_item_entity_does_not_declare(
        self, specs_dir: Path
    ) -> None:
        _write(
            specs_dir,
            _profile({"field": "is_dispaly_column", "op": "==", "value": True}),
        )

        with pytest.raises(SpecLoadError) as caught:
            SpecLoader().load_profile("1.0", "seekish")

        assert "is_dispaly_column" in str(caught.value)
        assert "never fire" in str(caught.value)

    def test_a_where_on_a_rule_that_selects_nothing(self, specs_dir: Path) -> None:
        """`cardinality` counts a subset and `uniqueness` compares one; a
        reference rule does neither, so a predicate on it means nothing."""
        profile = _profile()
        profile["validation_rules"][0].update(
            {
                "type": "reference",
                "field": "attributes",
                "reference": "SampleAttribute.name",
                "min_items": None,
                "max_items": None,
            }
        )
        _write(specs_dir, profile)

        with pytest.raises(SpecLoadError) as caught:
            SpecLoader().load_profile("1.0", "seekish")

        assert "only supported on a cardinality or uniqueness rule" in str(caught.value)

    def test_a_where_over_a_list_of_scalars(self, specs_dir: Path) -> None:
        profile = _profile()
        profile["entities"]["SampleType"]["fields"][1] = {
            "name": "attributes",
            "type": "list",
            "items": "string",
        }
        _write(specs_dir, profile)

        with pytest.raises(SpecLoadError) as caught:
            SpecLoader().load_profile("1.0", "seekish")

        assert "not a list of entities" in str(caught.value)

    def test_a_newer_format_version_says_so(self, specs_dir: Path) -> None:
        """The rejected key names itself; only the declared version says why."""
        profile = _profile()
        profile["spec_version"] = "0.9"
        profile["validation_rules"][0]["unless"] = {"field": "a", "op": "is_set"}
        _write(specs_dir, profile)

        with pytest.raises(SpecLoadError) as caught:
            SpecLoader().load_profile("1.0", "seekish")

        assert "declares spec_version 0.9" in str(caught.value)
        assert "supports up to" in str(caught.value)

    def test_a_good_profile_loads(self, specs_dir: Path) -> None:
        _write(specs_dir, _profile())

        profile = SpecLoader().load_profile("1.0", "seekish")

        assert profile is not None
        assert profile.validation_rules[0].where is not None


class TestWhatTheDraftEditorReports:
    def test_spec_validate_lists_the_same_problem(self) -> None:
        """Told while the draft is being edited, not when someone loads it."""
        builder = SpecBuilder.from_yaml(
            yaml.safe_dump(
                _profile({"field": "is_dispaly_column", "op": "==", "value": True})
            )
        )

        issues = builder.validate()

        assert any("is_dispaly_column" in issue for issue in issues)

    def test_a_good_draft_has_nothing_to_report(self) -> None:
        builder = SpecBuilder.from_yaml(yaml.safe_dump(_profile()))

        assert builder.validate() == []


def _uniqueness_profile() -> dict[str, Any]:
    """The fourth SEEK constraint: singleton ISA tags, with `Input` exempt."""
    profile = _profile()
    profile["entities"]["SampleAttribute"]["fields"].append(
        {"name": "isa_tag", "type": "string"}
    )
    profile["validation_rules"] = [
        {
            "name": "singleton_isa_tags",
            "type": "uniqueness",
            "applies_to": ["SampleAttribute"],
            "field": "isa_tag",
            "unique_within": "parent",
            "where": {
                "all": [
                    {
                        "field": "isa_tag",
                        "op": "in",
                        "value": ["source", "protocol", "sample", "data_file"],
                    },
                    {"field": "name", "op": "!=", "value": "Input"},
                ]
            },
        }
    ]
    return profile


def _tagged(tmp_path: Path, *attributes: tuple[str, str]) -> Path:
    path = tmp_path / "dataset.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "title": "Assay sample",
                "attributes": [
                    {"name": name, "isa_tag": tag} for name, tag in attributes
                ],
            }
        )
    )
    return path


class TestUniquenessOverASubset:
    """A `where` on uniqueness counts only the records it selects (#211).

    Enforced by `DatasetValidator`, not by an engine rule: uniqueness is a
    question about the records around this one, and an engine sees one record.
    """

    def _errors(self, specs_dir: Path, tmp_path: Path, *attributes: tuple[str, str]):
        _write(specs_dir, _uniqueness_profile())
        result = DatasetValidator("seekish", "1.0", _NoService()).validate_file(
            _tagged(tmp_path, *attributes)
        )
        return [e for e in result.errors if e.rule == "uniqueness"]

    def test_a_repeated_tag_is_reported(self, specs_dir: Path, tmp_path: Path) -> None:
        errors = self._errors(
            specs_dir, tmp_path, ("Growth Protocol", "protocol"), ("Prep", "protocol")
        )

        assert len(errors) == 1
        assert "protocol" in errors[0].message

    def test_a_tag_outside_the_selected_set_is_not_counted(
        self, specs_dir: Path, tmp_path: Path
    ) -> None:
        """`parameter_value` is not one of the singleton tags, so repeating it is
        not a defect — and the rule must not report it as one."""
        errors = self._errors(
            specs_dir, tmp_path, ("A", "parameter_value"), ("B", "parameter_value")
        )

        assert errors == []

    def test_the_exempt_records_are_not_counted(
        self, specs_dir: Path, tmp_path: Path
    ) -> None:
        """Attributes named `Input` are exempt from the count, which is a
        constraint no unpredicated uniqueness rule can express."""
        errors = self._errors(
            specs_dir, tmp_path, ("Input", "sample"), ("Input", "sample")
        )

        assert errors == []

    def test_the_message_says_what_was_counted(
        self, specs_dir: Path, tmp_path: Path
    ) -> None:
        errors = self._errors(
            specs_dir, tmp_path, ("Growth Protocol", "protocol"), ("Prep", "protocol")
        )

        assert "isa_tag in [" in errors[0].message
        assert "name != 'Input'" in errors[0].message


def _requirement_profile(**rule: Any) -> dict[str, Any]:
    """The first SEEK constraint: a Controlled Vocabulary attribute needs terms."""
    profile = _profile()
    profile["entities"]["SampleAttribute"]["fields"].append(
        {"name": "cv_terms", "type": "list", "items": "string"}
    )
    profile["validation_rules"] = [
        {
            "name": "cv_terms_required_for_controlled_vocabulary",
            "type": "conditional",
            "applies_to": ["SampleAttribute"],
            "when": {
                "field": "data_type",
                "op": "==",
                "value": "Controlled Vocabulary",
            },
            "require": ["cv_terms"],
            **rule,
        }
    ]
    return profile


class TestScopingARuleToANestedEntity:
    """Found while wiring #211: a rule naming a nested entity never fired here.

    The three spellings of one entity — a profile's `SampleAttribute`, the
    dataset validator's `sample_attribute` for a child and `sampletype` for its
    own root — were compared on case alone. The root matched and every nested
    entity missed, which silently disabled 54 rules across the shipped profiles
    on the path the application validates through. Re-measured against every
    shipped example: no error count changed.
    """

    @pytest.mark.parametrize(
        "spelling", ["SampleAttribute", "sample_attribute", "sampleattribute"]
    )
    def test_every_spelling_of_one_entity_is_the_same_entity(
        self, spelling: str
    ) -> None:
        from metaseed.specs.schema import ValidationRuleSpec
        from metaseed.validators.engine import _applies_to_entity

        rule = ValidationRuleSpec(name="r", applies_to=["SampleAttribute"])

        assert _applies_to_entity(rule, spelling)

    def test_a_rule_on_a_child_reaches_the_child(
        self, specs_dir: Path, tmp_path: Path
    ) -> None:
        _write(specs_dir, _requirement_profile())
        path = tmp_path / "dataset.yaml"
        path.write_text(
            yaml.safe_dump(
                {
                    "title": "Assay sample",
                    "attributes": [
                        {"name": "Origin", "data_type": "Controlled Vocabulary"}
                    ],
                }
            )
        )

        result = DatasetValidator("seekish", "1.0", _NoService()).validate_file(path)

        assert any(e.field.startswith("attributes[0]") for e in result.errors)


class TestARequirementThatDependsOnAValue:
    def _errors(self, specs_dir: Path, tmp_path: Path, data_type: str):
        _write(specs_dir, _requirement_profile())
        path = tmp_path / "dataset.yaml"
        path.write_text(
            yaml.safe_dump(
                {
                    "title": "Assay sample",
                    "attributes": [{"name": "Sample Origin", "data_type": data_type}],
                }
            )
        )
        result = DatasetValidator("seekish", "1.0", _NoService()).validate_file(path)
        return [
            e
            for e in result.errors
            if e.rule == "cv_terms_required_for_controlled_vocabulary"
        ]

    def test_the_value_that_demands_the_field(
        self, specs_dir: Path, tmp_path: Path
    ) -> None:
        errors = self._errors(specs_dir, tmp_path, "Controlled Vocabulary")

        assert len(errors) == 1
        assert "cv_terms" in errors[0].message
        assert "data_type == 'Controlled Vocabulary'" in errors[0].message

    def test_another_value_demands_nothing(
        self, specs_dir: Path, tmp_path: Path
    ) -> None:
        assert self._errors(specs_dir, tmp_path, "String") == []


class TestWhatTheLoaderRefusesOfARequirement:
    def test_half_of_it(self, specs_dir: Path) -> None:
        profile = _requirement_profile()
        del profile["validation_rules"][0]["require"]
        _write(specs_dir, profile)

        with pytest.raises(SpecLoadError) as caught:
            SpecLoader().load_profile("1.0", "seekish")

        assert "go together" in str(caught.value)

    def test_it_together_with_the_legacy_condition(self, specs_dir: Path) -> None:
        _write(specs_dir, _requirement_profile(condition="cv_terms"))

        with pytest.raises(SpecLoadError) as caught:
            SpecLoader().load_profile("1.0", "seekish")

        assert "cannot both be set" in str(caught.value)

    def test_a_required_field_the_entity_does_not_declare(
        self, specs_dir: Path
    ) -> None:
        _write(specs_dir, _requirement_profile(require=["cv_termz"]))

        with pytest.raises(SpecLoadError) as caught:
            SpecLoader().load_profile("1.0", "seekish")

        assert "cv_termz" in str(caught.value)
