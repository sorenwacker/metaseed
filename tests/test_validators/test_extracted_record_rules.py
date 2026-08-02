"""Tests for running profile validation rules against a single extracted record.

An extracted record is one row mapped onto an entity: flat, with its children
extracted separately and its siblings invisible to it. The engine built for that
shape must run the rules the record can answer and must not run the ones it
cannot, because a rule that cannot see its data reports every record as bad.
"""

from __future__ import annotations

from metaseed.specs.loader import SpecLoader
from metaseed.specs.schema import (
    EntityDefSpec,
    FieldSpec,
    FieldType,
    ProfileSpec,
    ValidationRuleSpec,
)
from metaseed.validators.engine import create_engine_for_extracted_record
from metaseed.validators.rules import ListCardinalityRule


def _profile() -> ProfileSpec:
    """A profile exercising every rule type against one entity."""
    return ProfileSpec(
        version="1.0",
        name="test-profile",
        root_entity="Sample",
        entities={
            "Sample": EntityDefSpec(
                fields=[
                    FieldSpec(name="unique_id", type=FieldType.STRING, required=True),
                    FieldSpec(name="trait", type=FieldType.STRING),
                    FieldSpec(name="trait_accession", type=FieldType.STRING),
                    FieldSpec(name="start_date", type=FieldType.DATE),
                    FieldSpec(name="end_date", type=FieldType.DATE),
                    FieldSpec(name="keywords", type=FieldType.LIST, items="string"),
                    FieldSpec(name="readings", type=FieldType.LIST, items="Reading"),
                    FieldSpec(name="study_id", type=FieldType.STRING),
                ]
            ),
            "Reading": EntityDefSpec(
                fields=[FieldSpec(name="unique_id", type=FieldType.STRING)]
            ),
        },
        validation_rules=[
            ValidationRuleSpec(
                name="trait_required",
                type="conditional",
                applies_to=["Sample"],
                condition="trait OR trait_accession",
            ),
            ValidationRuleSpec(
                name="date_order",
                type="date_range",
                applies_to=["Sample"],
                start_field="start_date",
                end_field="end_date",
            ),
            ValidationRuleSpec(
                name="keywords_present",
                type="cardinality",
                applies_to=["Sample"],
                field="keywords",
                min_items=1,
            ),
            ValidationRuleSpec(
                name="readings_present",
                type="cardinality",
                applies_to=["Sample"],
                field="readings",
                min_items=1,
            ),
            ValidationRuleSpec(
                name="unique_id_unique",
                type="uniqueness",
                applies_to=["Sample"],
                field="unique_id",
                unique_within="parent",
            ),
            ValidationRuleSpec(
                name="study_exists",
                type="reference",
                applies_to=["Sample"],
                field="study_id",
                reference="Study.unique_id",
            ),
        ],
    )


class TestRuleSelection:
    """Which declared rules reach a single extracted record."""

    def test_conditional_rule_reports_a_record_that_violates_it(self) -> None:
        engine = create_engine_for_extracted_record("Sample", _profile())

        errors = engine.validate({"unique_id": "S1", "keywords": ["a"]})

        assert [e.rule for e in errors] == ["trait_required"]

    def test_a_record_satisfying_every_rule_reports_nothing(self) -> None:
        engine = create_engine_for_extracted_record("Sample", _profile())

        errors = engine.validate(
            {
                "unique_id": "S1",
                "trait": "plant height",
                "start_date": "2024-01-01",
                "end_date": "2024-02-01",
                "keywords": ["height"],
            }
        )

        assert errors == []

    def test_date_range_rule_runs(self) -> None:
        engine = create_engine_for_extracted_record("Sample", _profile())

        errors = engine.validate(
            {
                "unique_id": "S1",
                "trait": "plant height",
                "keywords": ["height"],
                "start_date": "2024-03-15",
                "end_date": "2024-03-01",
            }
        )

        assert [e.rule for e in errors] == ["date_range"]

    def test_cardinality_over_a_list_of_scalars_runs(self) -> None:
        engine = create_engine_for_extracted_record("Sample", _profile())

        errors = engine.validate({"unique_id": "S1", "trait": "t", "keywords": []})

        assert [e.rule for e in errors] == ["keywords_present"]

    def test_cardinality_over_a_child_collection_is_not_run(self) -> None:
        # Children are extracted as their own records, so the parent record
        # never holds them; running the rule would fail every row.
        engine = create_engine_for_extracted_record("Sample", _profile())

        assert not any(
            isinstance(rule, ListCardinalityRule) and rule.field == "readings"
            for rule in engine.rules
        )

    def test_uniqueness_and_reference_rules_are_not_run(self) -> None:
        # Neither can see beyond the single record: uniqueness needs siblings,
        # reference needs the identifiers held elsewhere in the dataset. No
        # engine builds them; DatasetValidator enforces both over the tree.
        engine = create_engine_for_extracted_record("Sample", _profile())

        assert {rule.name for rule in engine.rules}.isdisjoint(
            {"unique_id_unique", "study_exists", "uniqueness", "entity_reference"}
        )

    def test_entity_derived_rules_are_not_added(self) -> None:
        # validate_instance reports missing required fields itself; the engine
        # carries only what the profile declares.
        engine = create_engine_for_extracted_record("Sample", _profile())

        assert {rule.name for rule in engine.rules} == {
            "trait_required",
            "date_range",
            "keywords_present",
        }

    def test_rules_declared_for_another_entity_are_not_run(self) -> None:
        engine = create_engine_for_extracted_record("Reading", _profile())

        assert engine.rules == []


class TestShippedProfiles:
    """The same selection against a real profile."""

    def test_miappe_observed_variable_without_a_trait_is_reported(self) -> None:
        profile = SpecLoader(profile="miappe").load_profile("1.2", "miappe")
        engine = create_engine_for_extracted_record("ObservedVariable", profile)

        errors = engine.validate({"unique_id": "OV1", "variable_name": "height"})

        assert "observed_variable_trait_required" in {e.rule for e in errors}

    def test_miappe_investigation_row_is_not_faulted_for_absent_children(self) -> None:
        # 'investigation_has_studies' is a cardinality rule over a child
        # collection: an extracted Investigation row has no studies in it.
        profile = SpecLoader(profile="miappe").load_profile("1.2", "miappe")
        engine = create_engine_for_extracted_record("Investigation", profile)

        errors = engine.validate({"unique_id": "INV1", "title": "T"})

        assert [e.rule for e in errors] == []
