"""Tests for the validators API surface (validate_entity)."""

from __future__ import annotations

from metaseed.validators.api import validate_entity


def test_missing_required_field_reported_once():
    """A missing required field must not be reported twice (Pydantic 'missing'
    plus the engine's RequiredFieldsRule). The engine owns required-field errors.
    """
    # MIAPPE Investigation requires unique_id and title; omit title.
    data = {"unique_id": "INV001"}

    errors = validate_entity(data, "Investigation", profile="miappe", version="1.2")

    title_errors = [e for e in errors if e.field == "title"]
    assert len(title_errors) == 1
    assert title_errors[0].rule == "required_fields"
