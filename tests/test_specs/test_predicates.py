"""Predicates on validation rules: the model, its bounds, its rendering.

A predicate says which records a rule applies to (#211, ADR 003). It is a
structured mapping rather than an expression string, so it is canonical under
`canonical_json` — reformatting cannot change a content hash or force a MAJOR
bump — and a malformed one is rejected field by field at construction instead of
at parse time.

What is rejected at load is the point of the last class here: a predicate naming
a field the entity does not declare would otherwise be a rule that never fires,
discovered only by the record that slipped through.

Evaluating one is `tests/test_validators/test_predicate_evaluation.py`.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError as PydanticValidationError

from metaseed.specs.predicates import (
    MAX_DEPTH,
    MAX_LITERAL_ITEMS,
    MAX_NODES,
    parse_predicate,
    predicate_issues,
    render_predicate,
)


class TestTheModel:
    def test_a_leaf_is_field_operator_value(self) -> None:
        predicate = parse_predicate({"field": "data_type", "op": "==", "value": "CV"})

        assert predicate.field == "data_type"

    @pytest.mark.parametrize("key", ["all", "any"])
    def test_a_group_holds_predicates(self, key: str) -> None:
        predicate = parse_predicate(
            {key: [{"field": "a", "op": "is_set"}, {"field": "b", "op": "is_set"}]}
        )

        assert len(getattr(predicate, key)) == 2

    def test_not_keeps_its_yaml_spelling(self) -> None:
        """The key is `not`; the attribute cannot be, so the alias has to survive
        a round trip or the spec written back to disk would not load again."""
        predicate = parse_predicate({"not": {"field": "a", "op": "is_set"}})

        assert predicate.model_dump(exclude_none=True) == {
            "not": {"field": "a", "op": "is_set"}
        }

    def test_an_unknown_operator_is_rejected(self) -> None:
        with pytest.raises(PydanticValidationError):
            parse_predicate({"field": "a", "op": "matches", "value": "x.*"})

    def test_an_unknown_key_is_rejected(self) -> None:
        with pytest.raises(PydanticValidationError):
            parse_predicate({"field": "a", "op": "==", "value": 1, "scope": "parent"})


class TestRendering:
    """The one-line spelling is kept for reading, not for storing."""

    @pytest.mark.parametrize(
        ("mapping", "rendered"),
        [
            (
                {"field": "is_display_column", "op": "==", "value": True},
                "is_display_column == true",
            ),
            ({"field": "n", "op": ">=", "value": 3}, "n >= 3"),
            ({"field": "name", "op": "!=", "value": "Input"}, "name != 'Input'"),
            ({"field": "name", "op": "is_set"}, "name is set"),
            ({"field": "name", "op": "is_not_set"}, "name is not set"),
            (
                {"field": "isa_tag", "op": "in", "value": ["source", "protocol"]},
                "isa_tag in ['source', 'protocol']",
            ),
            ({"not": {"field": "a", "op": "is_set"}}, "not (a is set)"),
            (
                {
                    "all": [
                        {"field": "a", "op": "is_set"},
                        {"field": "b", "op": "==", "value": 1},
                    ]
                },
                "a is set and b == 1",
            ),
            (
                {
                    "any": [
                        {"field": "a", "op": "is_set"},
                        {"field": "b", "op": "==", "value": 1},
                    ]
                },
                "a is set or b == 1",
            ),
        ],
    )
    def test_it_reads_as_the_sentence_the_constraint_is(
        self, mapping: dict, rendered: str
    ) -> None:
        assert render_predicate(parse_predicate(mapping)) == rendered

    def test_a_group_inside_a_group_is_parenthesised(self) -> None:
        predicate = parse_predicate(
            {
                "all": [
                    {"field": "a", "op": "is_set"},
                    {
                        "any": [
                            {"field": "b", "op": "is_set"},
                            {"field": "c", "op": "is_set"},
                        ]
                    },
                ]
            }
        )

        assert render_predicate(predicate) == "a is set and (b is set or c is set)"


class TestWhatIsRejectedAtLoad:
    """Checked once, loudly, rather than discovered when a record slips through."""

    def test_a_field_the_entity_does_not_declare(self) -> None:
        predicate = parse_predicate({"field": "dsiplay", "op": "is_set"})

        issues = predicate_issues(predicate, {"display", "name"})

        assert issues and "dsiplay" in issues[0]

    def test_a_declared_field_is_accepted(self) -> None:
        predicate = parse_predicate({"field": "display", "op": "is_set"})

        assert predicate_issues(predicate, {"display", "name"}) == []

    def test_unknown_fields_are_not_checked_when_the_entity_is_unknown(self) -> None:
        """A rule may name an item entity this profile does not define; that is
        reported by the caller, and inventing field errors on top adds noise."""
        predicate = parse_predicate({"field": "anything", "op": "is_set"})

        assert predicate_issues(predicate, None) == []

    def test_too_deep(self) -> None:
        predicate: dict = {"field": "a", "op": "is_set"}
        for _ in range(MAX_DEPTH + 1):
            predicate = {"not": predicate}

        issues = predicate_issues(parse_predicate(predicate), {"a"})

        assert issues and "depth" in issues[0]

    def test_too_many_nodes(self) -> None:
        predicate = parse_predicate(
            {"all": [{"field": "a", "op": "is_set"}] * (MAX_NODES + 1)}
        )

        issues = predicate_issues(predicate, {"a"})

        assert issues and "node" in issues[0]

    def test_too_long_a_literal_list(self) -> None:
        predicate = parse_predicate(
            {
                "field": "a",
                "op": "in",
                "value": [str(i) for i in range(MAX_LITERAL_ITEMS + 1)],
            }
        )

        issues = predicate_issues(predicate, {"a"})

        assert issues and "256" in issues[0]

    def test_a_membership_operator_needs_a_list(self) -> None:
        issues = predicate_issues(
            parse_predicate({"field": "a", "op": "in", "value": "source"}), {"a"}
        )

        assert issues and "list" in issues[0]

    def test_a_comparison_operator_needs_a_value(self) -> None:
        issues = predicate_issues(parse_predicate({"field": "a", "op": "=="}), {"a"})

        assert issues and "value" in issues[0]

    def test_a_set_operator_takes_no_value(self) -> None:
        issues = predicate_issues(
            parse_predicate({"field": "a", "op": "is_set", "value": 1}), {"a"}
        )

        assert issues and "value" in issues[0]

    def test_an_empty_group_is_rejected(self) -> None:
        issues = predicate_issues(parse_predicate({"all": []}), {"a"})

        assert issues and "empty" in issues[0]


class TestAppliesToMatchesLikeTheEngine:
    """Load-time predicate checks matched `applies_to` exact-case and read any
    single-entity string as 'all', while the runtime engine normalises case and
    separators — the same defect class as the 54 silently-disabled rules, one
    layer up (#review-260813)."""

    def _profile(self, applies_to):
        from metaseed.specs.schema import (
            EntityDefSpec,
            FieldSpec,
            FieldType,
            ProfileSpec,
            ValidationRuleSpec,
        )

        return ProfileSpec(
            name="p",
            version="1.0",
            root_entity="SampleType",
            entities={
                "SampleType": EntityDefSpec(
                    fields=[
                        FieldSpec(name="title", type=FieldType.STRING),
                        FieldSpec(
                            name="attributes",
                            type=FieldType.LIST,
                            items="SampleAttribute",
                        ),
                    ]
                ),
                "SampleAttribute": EntityDefSpec(
                    fields=[FieldSpec(name="flag", type=FieldType.BOOLEAN)]
                ),
                "Other": EntityDefSpec(
                    fields=[
                        FieldSpec(
                            name="attributes",
                            type=FieldType.LIST,
                            items="SampleAttribute",
                        )
                    ]
                ),
            },
            validation_rules=[
                ValidationRuleSpec(
                    name="one",
                    type="cardinality",
                    applies_to=applies_to,
                    field="attributes",
                    max_items=1,
                    where=parse_predicate({"field": "flag", "op": "is_set"}),
                )
            ],
        )

    def test_a_snake_case_spelling_still_finds_the_entity(self) -> None:
        from metaseed.specs.predicates import profile_predicate_issues

        issues = profile_predicate_issues(self._profile(["sample_type"]))

        assert issues == [], "the engine would run this rule; load-time must agree"

    def test_a_single_entity_string_scopes_to_that_entity_not_all(self) -> None:
        """`applies_to: SampleType` as a bare string was read as every entity,
        so a predicate valid only for SampleType's items raised phantom issues
        against the others."""
        from metaseed.specs.predicates import profile_predicate_issues

        profile = self._profile("SampleType")
        # Make Other's items differ so scoping to all WOULD complain.
        profile.entities["Other"].fields[0].items = "SampleType"

        assert profile_predicate_issues(profile) == []
