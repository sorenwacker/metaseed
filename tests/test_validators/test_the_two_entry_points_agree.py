"""An unknown entity answers the same through either door (260816 review).

`validate_entity()` reports an unknown entity type as a returned error;
`validate()` raised `SpecLoadError` for the same input, so what a caller got
depended on which entry point they came through. Both are public API and both
declare they return a list of errors; the raise leaked a loader internal
through the one that cascades.
"""

from __future__ import annotations

from metaseed.validators import validate, validate_entity


def test_validate_returns_the_error_it_used_to_raise() -> None:
    errors = validate({"x": 1}, entity="NoSuchEntity", version="1.2", profile="miappe")

    assert len(errors) == 1
    assert "NoSuchEntity" in errors[0].message


def test_the_two_answers_have_the_same_shape() -> None:
    through_validate = validate(
        {"x": 1}, entity="NoSuchEntity", version="1.2", profile="miappe"
    )
    through_validate_entity = validate_entity(
        {"x": 1}, entity_type="NoSuchEntity", version="1.2", profile="miappe"
    )

    assert [e.rule for e in through_validate] == [
        e.rule for e in through_validate_entity
    ]


def test_a_known_entity_still_validates() -> None:
    errors = validate(
        {"unique_id": "INV-1", "title": "T"},
        entity="Investigation",
        version="1.2",
        profile="miappe",
    )

    assert all("Unknown entity" not in e.message for e in errors)
