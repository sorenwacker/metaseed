"""Runtime marking of deprecated callables.

The deprecation policy in ``docs/specification/api-contract.md`` requires a
public symbol to be marked deprecated in a release before it is removed in a
later one. :func:`deprecated` is how that mark is made machine-visible: a
consumer learns about the removal when they call the symbol, not when it
disappears.

This is a maintenance tool, not consumer surface. It lives at the package root
alongside the other cross-cutting modules (``logging``, ``settings``, ``paths``)
because any subpackage may need it and it must not pull one subpackage into
another, and it is deliberately absent from the top-level ``__all__`` so
decorating a symbol never enlarges the public API the policy governs.

Example:
    >>> @deprecated(since="0.22", removed_in="1.0", use_instead="new_loader")
    ... def old_loader(path: str) -> str:
    ...     '''Load a thing.'''
    ...     return path
"""

from __future__ import annotations

import functools
import inspect
import warnings
from collections.abc import Callable
from typing import Any, TypeVar, cast

__all__ = ["deprecated"]

F = TypeVar("F", bound=Callable[..., Any])


def _warning_message(
    name: str, since: str, removed_in: str, use_instead: str | None
) -> str:
    """Build the text of the ``DeprecationWarning``."""
    message = (
        f"{name} is deprecated since metaseed {since} "
        f"and is scheduled for removal in {removed_in}."
    )
    if use_instead:
        message += f" Use {use_instead} instead."
    return message


def _docstring_with_note(doc: str | None, note: str) -> str:
    """Append the deprecation note to a docstring so ``help()`` shows it."""
    if not doc or not doc.strip():
        return note
    return f"{inspect.cleandoc(doc)}\n\n{note}"


def deprecated(
    *, since: str, removed_in: str, use_instead: str | None = None
) -> Callable[[F], F]:
    """Mark a function or method as deprecated.

    Calling the decorated callable emits a :class:`DeprecationWarning` naming
    it, the version that deprecated it, the version scheduled for removal, and
    the replacement. The warning is reported against the caller's line
    (``stacklevel=2``), so it points at the code that has to change. The same
    note is appended to the docstring, so ``help()`` and the rendered API docs
    carry it too.

    ``removed_in`` is required: an open-ended deprecation warning gives a
    consumer no deadline and the project no removal date.

    Args:
        since: Version that deprecated the callable, e.g. ``"0.22"``.
        removed_in: Version scheduled to remove it, e.g. ``"1.0"``.
        use_instead: What to use instead. Omit when there is no replacement.

    Returns:
        A decorator that wraps the callable, preserving its signature, name,
        and docstring.

    Example:
        >>> @deprecated(since="0.22", removed_in="1.0", use_instead="load")
        ... def load_dataset(path: str) -> None:
        ...     '''Load a dataset.'''
    """

    def decorate(func: F) -> F:
        message = _warning_message(func.__qualname__, since, removed_in, use_instead)

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            warnings.warn(message, DeprecationWarning, stacklevel=2)
            return func(*args, **kwargs)

        wrapper.__doc__ = _docstring_with_note(func.__doc__, message)
        return cast("F", wrapper)

    return decorate
