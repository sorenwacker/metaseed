"""Tests for nested route helpers."""

from metaseed.ui.routes.nested import _coerce_form_value


class TestCoerceFormValue:
    """Tests for _coerce_form_value."""

    def test_blank_value_is_dropped(self) -> None:
        """A blank string is dropped (returns None)."""
        assert _coerce_form_value("", "string") is None

    def test_integer_zero_is_preserved(self) -> None:
        """Numeric zero must survive coercion, not be treated as blank."""
        assert _coerce_form_value("0", "integer") == 0

    def test_float_zero_is_preserved(self) -> None:
        """Float zero must survive coercion."""
        assert _coerce_form_value("0.0", "float") == 0.0

    def test_integer_value_is_typed(self) -> None:
        """An integer field value is coerced to int."""
        assert _coerce_form_value("42", "integer") == 42

    def test_float_value_is_typed(self) -> None:
        """A float field value is coerced to float."""
        assert _coerce_form_value("1.5", "float") == 1.5

    def test_non_numeric_integer_left_as_string(self) -> None:
        """An unparseable integer is left untouched rather than dropped."""
        assert _coerce_form_value("abc", "integer") == "abc"

    def test_string_value_passthrough(self) -> None:
        """A string field value passes through unchanged."""
        assert _coerce_form_value("hello", "string") == "hello"

    def test_unknown_type_passthrough(self) -> None:
        """An unknown field type passes the raw value through."""
        assert _coerce_form_value("text", None) == "text"
