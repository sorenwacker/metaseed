"""How an MCP context is bound, and how far the binding reaches.

Two channels, deliberately distinct: a **process default** for the single session
a standalone server or the web UI serves, and a **scope binding** for a caller a
host is currently serving. Confusing them is what makes one caller answer for
another, so each test here pins which one a given call touches.
"""

from __future__ import annotations

import asyncio

from metaseed.agent.mcp import context as ctx
from metaseed.agent.mcp.context import (
    MCPContext,
    bound_context,
    clear_context,
    default_context,
    resolve_default_context,
    set_default_context,
    use_context,
)
from metaseed.repositories.memory import MemoryEntityRepository
from metaseed.ui.dataset_manager import DatasetManagerFactory
from metaseed.ui.services.entities import EntityService
from metaseed.ui.state import AppState


def _context(profile: str) -> MCPContext:
    state = AppState()
    state.profile = profile
    return MCPContext(
        state=state,
        get_entity_service=lambda: EntityService(MemoryEntityRepository(state)),
        dataset_factory=DatasetManagerFactory(),
    )


def test_a_standalone_process_gets_one_session_without_being_told() -> None:
    """``metaseed mcp`` has no host to bind anything, and every tool still has
    to work — and has to see the same session on the next call."""
    clear_context()
    try:
        first = resolve_default_context()
        assert resolve_default_context() is first
    finally:
        clear_context()


def test_the_scope_binding_wins_over_the_default() -> None:
    clear_context()
    try:
        set_default_context(_context("miappe"))

        with use_context(_context("pride")):
            assert resolve_default_context().state.profile == "pride"

        assert resolve_default_context().state.profile == "miappe"
    finally:
        clear_context()


def test_the_scope_binding_is_restored_and_nests() -> None:
    clear_context()
    try:
        with use_context(_context("a")):
            with use_context(_context("b")):
                assert resolve_default_context().state.profile == "b"
            assert resolve_default_context().state.profile == "a"
        assert bound_context() is None
    finally:
        clear_context()


def test_binding_a_scope_never_touches_the_process_default() -> None:
    """A host binding a caller must not overwrite what everything else sees —
    that is precisely how one caller ends up answering for another."""
    clear_context()
    try:
        base = _context("miappe")
        set_default_context(base)

        with use_context(_context("pride")):
            assert default_context() is base

        assert default_context() is base
    finally:
        clear_context()


def test_a_task_started_inside_the_scope_inherits_it() -> None:
    clear_context()
    try:

        async def main() -> str:
            with use_context(_context("pride")):
                return await asyncio.to_thread(
                    lambda: resolve_default_context().state.profile
                )

        assert asyncio.run(main()) == "pride"
    finally:
        clear_context()


def test_a_task_started_outside_the_scope_does_not_see_it() -> None:
    """The binding is scoped, not global: a caller bound in one task must not
    leak into a task that was already running."""
    clear_context()
    try:
        set_default_context(_context("miappe"))

        async def main() -> str:
            started_first = asyncio.create_task(_read_after(0.01))
            with use_context(_context("pride")):
                await asyncio.sleep(0)
            return await started_first

        assert asyncio.run(main()) == "miappe"
    finally:
        clear_context()


async def _read_after(delay: float) -> str:
    await asyncio.sleep(delay)
    return resolve_default_context().state.profile


def test_clearing_forgets_both_channels() -> None:
    clear_context()
    set_default_context(_context("pride"))
    ctx.set_scope(_context("ena"))

    clear_context()

    assert default_context() is None
    assert bound_context() is None
