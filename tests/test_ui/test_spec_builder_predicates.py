"""Authoring a rule predicate from the rule editor (#211, ADR 003).

A predicate decides which items a cardinality rule counts. It is edited as rows
rather than as text, and the field is offered from the fields the counted entity
declares — which is what keeps the load-time "unknown field" error out of reach
of the editor.

The last class here is the seam the design admits to: a predicate that nests
deeper than rows can show is displayed as its one-line spelling and must survive
a save untouched. Dropping it silently would be worse than not offering it.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from metaseed.ui.app import create_app
from metaseed.ui.state import AppState


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(AppState()))


def _profile_with_a_list(client: TestClient) -> None:
    """A SampleType owning SampleAttributes, and one rule to edit."""
    client.get("/spec-builder/new")
    client.post("/spec-builder/entity", data={"name": "SampleType"})
    client.post("/spec-builder/entity", data={"name": "SampleAttribute"})
    client.post(
        "/spec-builder/entity/SampleAttribute/field",
        data={"name": "is_display_column", "field_type": "boolean"},
    )
    client.post(
        "/spec-builder/entity/SampleType/field",
        data={"name": "attributes", "field_type": "list", "items": "SampleAttribute"},
    )
    client.post(
        "/spec-builder/validation-rule", data={"name": "exactly_one_display_column"}
    )


def _save(client: TestClient, **extra: object):
    data: dict = {
        "name": "exactly_one_display_column",
        "rule_type": "cardinality",
        "applies_to": "SampleType",
        "field": "attributes",
        "min_items": "1",
        "max_items": "1",
    }
    data.update(extra)
    return client.put("/spec-builder/validation-rule/0", data=data)


class TestBuildingOne:
    def test_the_editor_offers_the_counted_entitys_fields(self, client) -> None:
        """`is_display_column` is a SampleAttribute field, and it is the item
        entity's fields a predicate reads — not the SampleType's."""
        _profile_with_a_list(client)

        form = client.get("/spec-builder/validation-rule/0").text

        assert 'data-testid="rule-predicate"' in form
        assert "is_display_column" in form

    def test_a_row_becomes_a_predicate(self, client) -> None:
        _profile_with_a_list(client)

        _save(
            client,
            where_field=["is_display_column"],
            where_op=["=="],
            where_value=["true"],
        )

        preview = client.get("/spec-builder/preview").text
        assert "where:" in preview
        assert "field: is_display_column" in preview
        assert "value: true" in preview

    def test_two_rows_become_a_group(self, client) -> None:
        _profile_with_a_list(client)

        _save(
            client,
            where_join="any",
            where_field=["is_display_column", "is_display_column"],
            where_op=["==", "is_not_set"],
            where_value=["true", ""],
        )

        preview = client.get("/spec-builder/preview").text
        assert "any:" in preview

    def test_a_value_is_typed_the_way_yaml_types_it(self, client) -> None:
        """Everything arrives from a form as a string; `true` has to become a
        boolean or a predicate over a boolean column could never match."""
        _profile_with_a_list(client)

        _save(
            client,
            where_field=["is_display_column"],
            where_op=["=="],
            where_value=["true"],
        )

        form = client.get("/spec-builder/validation-rule/0").text
        assert 'value="true"' in form

    def test_the_rules_list_says_what_a_rule_selects(self, client) -> None:
        _profile_with_a_list(client)

        response = _save(
            client,
            where_field=["is_display_column"],
            where_op=["=="],
            where_value=["true"],
        )

        assert 'data-testid="rule-predicate-summary"' in response.text
        assert "where is_display_column == true" in response.text

    def test_no_rows_means_no_predicate(self, client) -> None:
        _profile_with_a_list(client)

        _save(client, where_field=[""], where_op=["=="], where_value=[""])

        assert "where:" not in client.get("/spec-builder/preview").text

    def test_an_edit_is_reversible(self, client) -> None:
        _profile_with_a_list(client)
        _save(
            client,
            where_field=["is_display_column"],
            where_op=["=="],
            where_value=["true"],
        )

        _save(client, where_field=[""], where_op=["=="], where_value=[""])

        assert "where:" not in client.get("/spec-builder/preview").text


class TestWhatItRefuses:
    def test_a_value_left_empty_is_reported_not_stored(self, client) -> None:
        _profile_with_a_list(client)

        response = _save(
            client,
            where_field=["is_display_column"],
            where_op=["=="],
            where_value=[""],
        )

        assert 'data-testid="rule-error"' in response.text
        assert "needs a value" in response.text
        assert "where:" not in client.get("/spec-builder/preview").text

    def test_the_edit_is_not_discarded_when_a_row_is_wrong(self, client) -> None:
        """The form comes back with what was typed still in it."""
        _profile_with_a_list(client)

        response = _save(
            client,
            where_field=["is_display_column"],
            where_op=["=="],
            where_value=[""],
        )

        assert 'data-testid="predicate-row"' in response.text


class TestAPredicateTheRowsCannotShow:
    def _nested(self, client) -> None:
        _profile_with_a_list(client)
        _save(
            client,
            where_field=["is_display_column"],
            where_op=["=="],
            where_value=["true"],
        )
        # Nest it beyond what rows can express, as a hand-written profile may.
        from metaseed.specs.predicates import parse_predicate

        state = client.app.state.ui_state.spec_builder  # type: ignore[attr-defined]
        state.spec.validation_rules[0].where = parse_predicate(
            {"not": {"field": "is_display_column", "op": "is_set"}}
        )

    def test_it_is_shown_as_the_sentence_it_states(self, client) -> None:
        self._nested(client)

        form = client.get("/spec-builder/validation-rule/0").text

        assert 'data-testid="predicate-readonly"' in form
        assert "not (is_display_column is set)" in form

    def test_it_survives_a_save_of_the_rest_of_the_rule(self, client) -> None:
        """Neither flattened nor dropped: the editor cannot show it, which is
        not a reason to destroy it."""
        self._nested(client)

        _save(client, where_keep="1", max_items="2")

        preview = client.get("/spec-builder/preview").text
        assert "not:" in preview
        assert "max_items: 2" in preview


class TestARequirementThatDependsOnAValue:
    """`when`/`require` from the same editor, on a conditional rule."""

    def _conditional(self, client) -> None:
        client.get("/spec-builder/new")
        client.post("/spec-builder/entity", data={"name": "SampleAttribute"})
        client.post(
            "/spec-builder/entity/SampleAttribute/field",
            data={"name": "data_type", "field_type": "string"},
        )
        client.post(
            "/spec-builder/entity/SampleAttribute/field",
            data={"name": "cv_terms", "field_type": "list", "items": "string"},
        )
        client.post("/spec-builder/validation-rule", data={"name": "cv_terms_needed"})

    def _save(self, client, **extra):
        data: dict = {
            "name": "cv_terms_needed",
            "rule_type": "conditional",
            "applies_to": "SampleAttribute",
        }
        data.update(extra)
        return client.put("/spec-builder/validation-rule/0", data=data)

    def test_the_form_offers_it(self, client) -> None:
        self._conditional(client)

        form = client.get("/spec-builder/validation-rule/0").text

        assert 'data-testid="rule-requirement"' in form
        assert 'data-testid="rule-require"' in form

    def test_a_requirement_is_saved(self, client) -> None:
        self._conditional(client)

        self._save(
            client,
            require="cv_terms",
            when_field=["data_type"],
            when_op=["=="],
            when_value=["Controlled Vocabulary"],
        )

        preview = client.get("/spec-builder/preview").text
        assert "when:" in preview
        assert "- cv_terms" in preview
        assert "value: Controlled Vocabulary" in preview

    def test_it_comes_back_into_the_form(self, client) -> None:
        self._conditional(client)
        self._save(
            client,
            require="cv_terms",
            when_field=["data_type"],
            when_op=["=="],
            when_value=["Controlled Vocabulary"],
        )

        form = client.get("/spec-builder/validation-rule/0").text

        assert 'value="cv_terms"' in form
        assert 'value="Controlled Vocabulary"' in form

    def test_removing_it_leaves_the_rule_without_one(self, client) -> None:
        self._conditional(client)
        self._save(
            client,
            require="cv_terms",
            when_field=["data_type"],
            when_op=["=="],
            when_value=["Controlled Vocabulary"],
        )

        self._save(client, require="", when_field=[""], when_op=["=="], when_value=[""])

        preview = client.get("/spec-builder/preview").text
        assert "when:" not in preview
        assert "require:" not in preview


class TestAFailedEditChangesNothing:
    """`apply_to_rule` mutated the stored rule field by field, so a failure
    halfway — an unreadable predicate value — left it half-edited. The route
    now builds the updated rule fresh and swaps it in only on success; the
    error response keeps the typed `when` rows as well as the `where` rows."""

    def test_a_failing_edit_leaves_the_stored_rule_untouched(self, client) -> None:
        client.get("/spec-builder/new")
        client.post("/spec-builder/entity", data={"name": "SampleType"})
        client.post("/spec-builder/validation-rule", data={"name": "steady"})
        client.put(
            "/spec-builder/validation-rule/0",
            data={
                "name": "steady",
                "rule_type": "cardinality",
                "applies_to": "SampleType",
                "field": "attributes",
                "max_items": "3",
            },
        )

        # A new name plus an unreadable predicate value: the edit must fail
        # whole, not rename the rule and then stop.
        client.put(
            "/spec-builder/validation-rule/0",
            data={
                "name": "renamed",
                "rule_type": "cardinality",
                "applies_to": "SampleType",
                "field": "attributes",
                "max_items": "3",
                "where_field": ["flag"],
                "where_op": ["=="],
                "where_value": [""],
            },
        )

        preview = client.get("/spec-builder/preview").text
        assert "steady" in preview, "the failed edit must not have renamed the rule"
        assert "renamed" not in preview

    def test_the_error_response_keeps_the_typed_when_rows(self, client) -> None:
        client.get("/spec-builder/new")
        client.post("/spec-builder/entity", data={"name": "SampleAttribute"})
        client.post("/spec-builder/validation-rule", data={"name": "cv"})

        response = client.put(
            "/spec-builder/validation-rule/0",
            data={
                "name": "cv",
                "rule_type": "conditional",
                "applies_to": "SampleAttribute",
                "require": "cv_terms",
                "when_field": ["data_type"],
                "when_op": ["=="],
                "when_value": [""],
            },
        )

        assert 'data-testid="rule-error"' in response.text
        assert 'value="data_type"' in response.text, "the typed when row survives"
