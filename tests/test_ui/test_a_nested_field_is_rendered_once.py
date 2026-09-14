"""A nested field is drawn once, by the one partial that draws such a table.

A required containment field appeared twice on an edit form: as an unlabelled
`(1 item)` button among the Required Fields — `field.html` has its own branches
for nested `list` and `entity` fields — and again, far below, as its real table
under Related Entities. In the Health-RI catalogue `contact_point`, `creator`
and `publisher` were each rendered both ways, the button roughly 24,000
characters above the table.

Two renderings of one field mean two implementations of what a nested field
looks like. ADR 006 decided there is one: the child table, drawn by
`inline_table.html`, in the field's own place.

The form is rendered directly here rather than through a route: no shipped
profile declares a required nested field (checked across all of them), so the
duplicate only appears with a profile like the user's own, which CI cannot see.
"""

from __future__ import annotations

from typing import Any

import pytest
from jinja2 import Environment, FileSystemLoader

import metaseed.ui.app as appmod

FIELD = "contact_point"


@pytest.fixture
def env() -> Environment:
    environment = Environment(
        loader=FileSystemLoader(str(appmod.TEMPLATES_DIR)), autoescape=True
    )
    # `display` is registered on the app's env as a closure inside create_app,
    # so it cannot be imported; this stands in for it while the structure of
    # the form is what is under test.
    environment.filters["display"] = lambda value: "" if value is None else str(value)
    return environment


def _nested_field() -> dict[str, Any]:
    """A containment field that is required — so it is listed among the
    required fields *and* among the nested fields, which is what duplicated."""
    return {
        "name": FIELD,
        "type": "entity",
        "items": "Kind",
        "required": True,
        "nested": True,
        "description": "Who can answer questions about the catalogue.",
    }


def _table_data() -> dict[str, Any]:
    return {
        "columns": ["email"],
        "rows": [{"_idx": 0, "email": "contact@example.org"}],
        "column_types": {"email": "string"},
        "column_constraints": {},
        "required_columns": {"email"},
        "reference_fields": {},
        "parent_id_fields": {},
        "has_nested_children": False,
        "nested_entity_type": "Kind",
    }


def _render(env: Environment) -> str:
    field = _nested_field()
    return env.get_template("partials/form_sections.html").render(
        entity_type="Catalog",
        is_edit=True,
        node_id="n1",
        required_fields=[field],
        optional_fields=[],
        nested_fields=[field],
        inline_tables={FIELD: _table_data()},
        values={FIELD: {"email": "contact@example.org"}},
        auto_fields=set(),
        field_errors={},
        child_entity_fields=[],
    )


def test_the_field_is_drawn_once(env: Environment) -> None:
    html = _render(env)

    assert html.count(f'data-testid="inline-table-{FIELD}"') == 1, (
        "the field's table must appear exactly once"
    )


def test_no_nested_button_stands_in_for_the_table(env: Environment) -> None:
    """The `(1 item)` button named neither the field nor the action, and led to
    a list view of something that holds exactly one."""
    html = _render(env)

    assert f'data-testid="btn-nested-{FIELD.replace("_", "-")}"' not in html
    assert "(1 item)" not in html


def test_the_table_sits_where_the_field_is(env: Environment) -> None:
    """Below every other field, under a separate heading, it was 1500px away
    from the field it belongs to."""
    html = _render(env)

    related = html.find("Related Entities")
    table = html.index(f'data-testid="inline-table-{FIELD}"')

    assert related == -1 or table < related, (
        "a required nested field is drawn in its own place, not in a section below"
    )
