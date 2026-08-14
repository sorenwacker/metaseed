"""A child that fails for ANY reason stays in the form with an error.

The generic `except Exception` branches in `_update_existing_child` and
`_create_new_child` only logged a warning — unlike the ValidationError
branch they neither recorded an error nor kept the failed item, so the
rebuilt form silently dropped what the user typed and the caller showed
"Saved" over truncated data.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from metaseed.ui.helpers.validation import (
    ValidationResult,
    _create_new_child,
    _update_existing_child,
)


def _helper_that_raises(exc: Exception) -> MagicMock:
    helper = MagicMock()
    helper.create.side_effect = exc
    return helper


def test_a_non_validation_failure_is_reported_on_create() -> None:
    result = ValidationResult()
    item = {"name": "typed by the user"}

    _create_new_child(
        state=MagicMock(),
        child_type="Sample",
        child_helper=_helper_that_raises(TypeError("boom")),
        cleaned={"name": "typed by the user"},
        node_id="n1",
        field_name="samples",
        item=item,
        result=result,
    )

    assert result.has_errors()
    assert result.failed_items.get("samples") == [item]


def test_a_non_validation_failure_is_reported_on_update() -> None:
    result = ValidationResult()
    item = {"name": "edited by the user"}
    state = MagicMock()
    state.update_node.side_effect = AttributeError("store broke")
    helper = MagicMock()

    _update_existing_child(
        state=state,
        existing_node=MagicMock(id="n2"),
        child_type="Sample",
        child_helper=helper,
        cleaned={"name": "edited by the user"},
        field_name="samples",
        item=item,
        result=result,
    )

    assert result.has_errors()
    assert result.failed_items.get("samples") == [item]
