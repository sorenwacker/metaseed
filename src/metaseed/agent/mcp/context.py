"""MCP context for dependency injection.

Provides explicit dependencies for MCP tools without globals.
The context is created during app initialization and passed to all tools.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

from metaseed.agent.mcp.ui_session import (
    AppState,
    DatasetManagerFactory,
    EntityService,
    ui_datasets,
)
from metaseed.repositories.memory import MemoryEntityRepository


@dataclass
class MCPContext:
    """Explicit dependencies for MCP tools.

    This dataclass holds all dependencies needed by MCP tools,
    eliminating the need for module-level globals. It ensures
    that all tools operate on the same state instance.

    Attributes:
        state: The shared AppState instance.
        get_entity_service: Factory function that returns a fresh EntityService.
            Called on each tool invocation to ensure the service uses current state.
        dataset_factory: Factory for creating DatasetManager instances tied to state.
    """

    state: AppState
    get_entity_service: Callable[[], EntityService]
    dataset_factory: DatasetManagerFactory


class ContextUnavailableError(RuntimeError):
    """Raised when the caller a tool is serving cannot be identified.

    A host that serves several callers raises this rather than falling back to a
    process-wide default, because the default would be another caller's session.
    Failing closed turns a cross-tenant data leak into an error message.
    """


ResolveContext = Callable[[], "MCPContext"]
"""How a tool obtains the context for the call it is serving.

Resolved per invocation, inside the tool body, because that is the only scope in
which the caller is identifiable: an MCP server dispatches handlers from its own
task group, so a host cannot bind a ContextVar around the call from outside.
"""


@dataclass
class _DefaultSession:
    """Holds the single session a process serves when nothing richer is bound.

    A holder rather than a module global, so binding it is an ordinary attribute
    write: the ``global`` statement is what this codebase avoids.
    """

    context: MCPContext | None = None


# Honest for the stdio server (one process, one user) and for the web UI; a host
# serving more than one caller passes its own resolver instead of relying on it.
_default = _DefaultSession()
_override: ContextVar[MCPContext | None] = ContextVar("mcp_context", default=None)


def set_default_context(context: MCPContext | None) -> None:
    """Bind the process-wide default session."""
    _default.context = context


def default_context() -> MCPContext | None:
    """The process-wide default session, if one has been bound."""
    return _default.context


def bound_context() -> MCPContext | None:
    """The context bound to the current scope, ignoring the default."""
    return _override.get()


def set_scope(context: MCPContext | None) -> None:
    """Bind (or clear) the context for the current scope."""
    _override.set(context)


@contextmanager
def use_context(context: MCPContext) -> Iterator[None]:
    """Bind ``context`` for the duration of the block, then restore.

    Scoped to the current execution context, so it never disturbs the process
    default and cannot leak into a sibling task.
    """
    token = _override.set(context)
    try:
        yield
    finally:
        _override.reset(token)


def resolve_default_context() -> MCPContext:
    """The context for a process serving a single session.

    Prefers whatever is bound to the current scope, then the process default,
    and otherwise creates the single session this process will use. Never
    raises: a standalone ``metaseed mcp`` has no host to bind anything, and
    every tool still has to work.
    """
    bound = _override.get()
    if bound is not None:
        return bound
    if _default.context is None:
        _default.context = _build_default_context()
    return _default.context


def _build_default_context() -> MCPContext:
    """Create the single session a standalone process serves.

    The save callback resolves ``auto_save`` when it is called rather than when
    the context is built. Binding the function object here captured whichever
    one existed at build time, so a test that replaced it afterwards still ran
    the real one and wrote to the user's datasets directory.
    """
    state = AppState()
    return MCPContext(
        state=state,
        get_entity_service=lambda: EntityService(
            # The wrapper is deliberate: inlining it passes the function object
            # bound now, which is the defect this exists to avoid.
            MemoryEntityRepository(
                state,
                on_change=lambda s: ui_datasets.auto_save(s),  # noqa: PLW0108
            )
        ),
        dataset_factory=DatasetManagerFactory(),
    )


def clear_context() -> None:
    """Forget both the scope binding and the process default (for tests)."""
    _default.context = None
    _override.set(None)
