"""Decorators for spec builder routes.

Provides common decorators to reduce boilerplate in route handlers.
"""

from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from typing import TYPE_CHECKING

from fastapi import HTTPException

if TYPE_CHECKING:
    from .state import SpecBuilderState


def require_spec(get_builder_state: Callable[[], SpecBuilderState]):
    """Decorator factory that ensures a spec is in progress.

    Args:
        get_builder_state: Callable to get the builder state.

    Returns:
        Decorator that validates spec exists before calling handler.

    Raises:
        HTTPException: 400 error if no spec is in progress.
    """

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            builder = get_builder_state()
            if builder.spec is None:
                raise HTTPException(status_code=400, detail="No spec in progress")
            return await func(builder, *args, **kwargs)

        return wrapper

    return decorator
