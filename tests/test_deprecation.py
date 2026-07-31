"""Tests for the ``@deprecated`` decorator (issue #69).

The deprecation policy in ``docs/specification/api-contract.md`` is only
enforceable if a deprecated symbol says so at runtime. These tests pin the
warning's category, its content, where it is reported, and that decorating a
callable leaves its signature and docstring usable.
"""

from __future__ import annotations

import inspect
import warnings
from pathlib import Path
from typing import Any

import pytest

from metaseed.deprecation import deprecated


@deprecated(since="0.22", removed_in="1.0", use_instead="new_loader")
def old_loader(path: str, *, strict: bool = True) -> str:
    """Load a thing.

    Args:
        path: Where the thing is.
        strict: Whether to be strict.

    Returns:
        The path it was given.
    """
    return path


@deprecated(since="0.22", removed_in="0.30")
def gone_without_replacement() -> int:
    """Return a number."""
    return 7


class Loader:
    """Holder for a deprecated method."""

    @deprecated(since="0.22", removed_in="1.0", use_instead="Loader.load")
    def legacy_load(self, path: str) -> str:
        """Load from ``path``."""
        return path


def _warn_once(call: Any) -> warnings.WarningMessage:
    """Call ``call`` capturing exactly one warning, and return it."""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        call()
    assert len(caught) == 1
    return caught[0]


class TestWarning:
    """A deprecated callable warns, with the documented content."""

    def test_call_emits_deprecation_warning(self) -> None:
        record = _warn_once(lambda: old_loader("p"))

        assert record.category is DeprecationWarning

    def test_message_names_symbol_versions_and_replacement(self) -> None:
        record = _warn_once(lambda: old_loader("p"))
        message = str(record.message)

        assert "old_loader" in message
        assert "0.22" in message
        assert "1.0" in message
        assert "new_loader" in message

    def test_message_without_replacement_still_names_removal(self) -> None:
        record = _warn_once(gone_without_replacement)
        message = str(record.message)

        assert "gone_without_replacement" in message
        assert "0.30" in message
        assert "instead" not in message

    def test_warning_points_at_the_caller(self) -> None:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            call_line = inspect.currentframe().f_lineno + 1  # type: ignore[union-attr]
            old_loader("p")

        assert Path(caught[0].filename) == Path(__file__)
        assert caught[0].lineno == call_line

    def test_method_warns_and_points_at_the_caller(self) -> None:
        loader = Loader()

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            call_line = inspect.currentframe().f_lineno + 1  # type: ignore[union-attr]
            loader.legacy_load("p")

        assert caught[0].category is DeprecationWarning
        assert "legacy_load" in str(caught[0].message)
        assert Path(caught[0].filename) == Path(__file__)
        assert caught[0].lineno == call_line

    def test_error_filter_turns_the_warning_into_a_failure(self) -> None:
        with pytest.warns(DeprecationWarning, match="old_loader"):
            old_loader("p")


class TestWrappedCallableIsUnchanged:
    """Decorating must not alter what the callable does or how it reads."""

    def test_arguments_and_return_value_pass_through(self) -> None:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            assert old_loader("some/path", strict=False) == "some/path"
            assert Loader().legacy_load("p") == "p"

    def test_signature_is_preserved(self) -> None:
        assert list(inspect.signature(old_loader).parameters) == ["path", "strict"]

    def test_identity_metadata_is_preserved(self) -> None:
        assert old_loader.__name__ == "old_loader"
        assert old_loader.__qualname__ == "old_loader"

    def test_original_docstring_is_kept(self) -> None:
        assert old_loader.__doc__ is not None
        assert "Load a thing." in old_loader.__doc__
        assert "path: Where the thing is." in old_loader.__doc__

    def test_docstring_gains_the_deprecation_note(self) -> None:
        assert old_loader.__doc__ is not None
        assert "0.22" in old_loader.__doc__
        assert "1.0" in old_loader.__doc__
        assert "new_loader" in old_loader.__doc__

    def test_undocumented_callable_gets_a_docstring(self) -> None:
        @deprecated(since="0.22", removed_in="1.0")
        def bare() -> None: ...

        assert bare.__doc__ is not None
        assert "0.22" in bare.__doc__
