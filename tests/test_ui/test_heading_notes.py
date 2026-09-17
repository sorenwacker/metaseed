"""The note on an exported heading carries what decides a valid value.

Before, the note held the description, required or optional, the unit and an
example. The pattern a value must match, its length and range, its allowed
values and the rules naming it lived only in the specification, so a person
filling in the sheet learned them from the validation report after import.
See docs/architecture/excel-round-trip.md.
"""

from __future__ import annotations

from metaseed.specs.schema import Constraints, FieldSpec, FieldType, ValidationRuleSpec
from metaseed.ui.services.export import build_workbook
from metaseed.ui.services.heading_note import MAX_LISTED_VALUES, heading_note
from metaseed.ui.state import AppState


def _lines(note: str) -> list[str]:
    return note.splitlines()


class TestTheSummaryLine:
    def test_it_names_the_type_in_words(self) -> None:
        field = FieldSpec(
            name="sown", type=FieldType.DATE, required=True, example="2024-03-01"
        )

        assert "Required · Date (YYYY-MM-DD) · Example: 2024-03-01" in _lines(
            heading_note("sown", field, [])
        )

    def test_a_scalar_list_says_how_values_are_separated(self) -> None:
        field = FieldSpec(name="keywords", type=FieldType.LIST, items="string")

        assert "Optional · List of values separated by commas" in heading_note(
            "keywords", field, []
        )

    def test_a_field_holding_entities_has_no_type(self) -> None:
        field = FieldSpec(name="studies", type=FieldType.LIST, items="Study")

        assert _lines(heading_note("studies", field, [])) == ["Optional"]


class TestConstraintsOnTheField:
    def test_each_constraint_gets_its_line(self) -> None:
        field = FieldSpec(
            name="plot",
            type=FieldType.STRING,
            constraints=Constraints(pattern="^P[0-9]+$", min_length=2, max_length=8),
        )
        lines = _lines(heading_note("plot", field, []))

        assert "Pattern: ^P[0-9]+$" in lines
        assert "Length: 2 to 8 characters" in lines

    def test_a_one_sided_bound_says_which_side(self) -> None:
        field = FieldSpec(
            name="depth",
            type=FieldType.FLOAT,
            constraints=Constraints(minimum=0, min_items=None),
        )

        assert "Range: at least 0" in _lines(heading_note("depth", field, []))

    def test_list_cardinality(self) -> None:
        field = FieldSpec(
            name="descriptors",
            type=FieldType.LIST,
            items="string",
            constraints=Constraints(min_items=1, max_items=3),
        )

        assert "Number of values: 1 to 3" in _lines(
            heading_note("descriptors", field, [])
        )

    def test_allowed_values_stop_at_the_limit(self) -> None:
        values = [f"v{i}" for i in range(MAX_LISTED_VALUES + 4)]
        field = FieldSpec(
            name="kind", type=FieldType.STRING, constraints=Constraints(enum=values)
        )
        line = next(
            line
            for line in _lines(heading_note("kind", field, []))
            if line.startswith("Allowed")
        )

        assert f"v{MAX_LISTED_VALUES - 1}" in line
        assert f"v{MAX_LISTED_VALUES}," not in line
        assert line.endswith("and 4 more, see the dropdown")

    def test_ontologies_references_and_uniqueness(self) -> None:
        field = FieldSpec(
            name="study_ref",
            type=FieldType.ONTOLOGY_TERM,
            ontologies=["to", "co_321"],
            reference="Study.unique_id",
            unique_within="parent",
        )
        lines = _lines(heading_note("study_ref", field, []))

        assert "Ontologies: to, co_321" in lines
        assert "Must match: Study.unique_id" in lines
        assert "Unique: within the parent" in lines

    def test_a_term_scope(self) -> None:
        field = FieldSpec(
            name="tech", type=FieldType.ONTOLOGY_TERM, within="JERM:00025"
        )

        assert "Terms under: JERM:00025" in _lines(heading_note("tech", field, []))


class TestRulesFromTheProfile:
    def test_a_rule_constraint_is_shown_once_with_the_field_constraint(self) -> None:
        field = FieldSpec(
            name="unique_id",
            type=FieldType.STRING,
            constraints=Constraints(pattern="^[a-z]+$"),
        )
        rule = ValidationRuleSpec(
            name="id_pattern",
            description="Lowercase only",
            field="unique_id",
            pattern="^[a-z]+$",
        )
        lines = _lines(heading_note("unique_id", field, [rule]))

        assert lines.count("Pattern: ^[a-z]+$") == 1
        assert "Rules: Lowercase only" in lines

    def test_a_rule_naming_the_field_in_its_condition_is_listed(self) -> None:
        field = FieldSpec(name="start_date", type=FieldType.DATE)
        rules = [
            ValidationRuleSpec(
                name="range",
                description="End after start",
                condition="end_date >= start_date",
            ),
            ValidationRuleSpec(
                name="other", description="Not this one", condition="end_date >= date"
            ),
        ]

        assert "Rules: End after start" in _lines(
            heading_note("start_date", field, rules)
        )

    def test_a_rule_naming_the_field_in_when_or_require_is_listed(self) -> None:
        field = FieldSpec(name="doi", type=FieldType.STRING)
        rule = ValidationRuleSpec.model_validate(
            {
                "name": "identity",
                "description": "A publication carries a resolvable identifier",
                "type": "conditional",
                "when": {"field": "pubmed_id", "op": "is_not_set"},
                "require": ["doi"],
            }
        )

        assert "Rules: A publication carries a resolvable identifier" in _lines(
            heading_note("doi", field, [rule])
        )

    def test_rule_values_fill_in_what_the_field_does_not_declare(self) -> None:
        field = FieldSpec(name="decimalLatitude", type=FieldType.FLOAT)
        rule = ValidationRuleSpec(
            name="lat",
            description="Latitude range",
            field="decimalLatitude",
            minimum=-90,
            maximum=90,
        )

        assert "Range: -90 to 90" in _lines(
            heading_note("decimalLatitude", field, [rule])
        )


def test_the_exported_miappe_study_sheet_carries_constraints_and_rules() -> None:
    """End to end: the note is what the workbook carries, with the profile's
    rules for that entity."""
    state = AppState(profile="miappe", version="1.2")
    facade = state.get_or_create_facade()
    study = facade.Study.create(unique_id="STU1", title="Site A", skip_validation=True)
    state.add_node("Study", study)
    sheet = build_workbook(state)["Study"]
    heading = next(cell for cell in sheet[1] if cell.value == "start_date")

    assert heading.comment is not None
    lines = heading.comment.text.splitlines()
    assert "Pattern: ^[0-9]{4}-[0-9]{2}-[0-9]{2}$" in lines
    rules_line = next(line for line in lines if line.startswith("Rules: "))
    assert "End date must not be before start date" in rules_line
    assert "Event end date" not in rules_line
