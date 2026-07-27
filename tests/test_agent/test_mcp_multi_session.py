"""Two MCP sessions in one process must not see each other's dataset.

metaseed's MCP server resolves a session's state through `get_mcp_state()`, which
reads a ContextVar and falls back to a module-level singleton (`_MCPStateHolder`).
Both are process-wide and last-writer-wins, and — the point — **the accessor takes
no argument identifying the caller**. Whichever session was bound most recently
answers for everyone. No implementation of a zero-argument accessor can do better;
the fix is a resolver the host passes in, so a tool resolves its caller's context
per invocation (issue #168).

That is correct as it stands for the stdio server: one process, one user, one
session, where a process-wide default is honest. It stops being correct the moment
a host serves two callers from one process, which is what metaseed-hub's planned
HTTP MCP endpoint does — and the hub already runs two uvicorn workers.

The test below states the property such a host needs. It is expected to fail
today: it is the target, not a claim about current behaviour, and it will be
rewritten against the resolver seam when that lands.
"""

from __future__ import annotations

import asyncio

import pytest

from metaseed.agent.mcp.context import MCPContext
from metaseed.agent.mcp.server import get_mcp_state, reset_mcp_state, set_context
from metaseed.repositories.memory import MemoryEntityRepository
from metaseed.ui.dataset_manager import DatasetManagerFactory
from metaseed.ui.services.entities import EntityService
from metaseed.ui.state import AppState


def _session(profile: str, version: str) -> tuple[AppState, MCPContext]:
    """A session's state and the context a host would build for it."""
    state = AppState()
    state.profile = profile
    state.version = version
    context = MCPContext(
        state=state,
        get_entity_service=lambda: EntityService(MemoryEntityRepository(state)),
        dataset_factory=DatasetManagerFactory(),
    )
    return state, context


@pytest.mark.xfail(
    reason=(
        "get_mcp_state() takes no argument identifying the caller, so the "
        "most recently bound session answers for every caller in the process. "
        "Passing the host a resolver is the fix (#168); until then a host must "
        "not serve two callers from one process."
    ),
    strict=True,
)
def test_a_second_session_does_not_take_over_the_first() -> None:
    """Alice on `pride` and Bob on `miappe` must each keep their own profile."""
    reset_mcp_state()
    try:
        alice_state, alice_context = _session("pride", "1.0")
        _bob_state, bob_context = _session("miappe", "1.1")

        # Alice's request binds her session...
        set_context(alice_context)
        # ...then Bob's request arrives and binds his, before Alice's tool body
        # runs. Two callers on one process interleave exactly like this.
        set_context(bob_context)

        # Alice's tool now resolves its state. Note the ContextVar *is* visible
        # here — asyncio.to_thread copies the context — so this is not the #32
        # fallback path: both channels simply hold whatever was bound last.
        async def resolve_in_a_fresh_task() -> str:
            return await asyncio.to_thread(lambda: get_mcp_state().profile)

        resolved = asyncio.run(resolve_in_a_fresh_task())

        assert resolved == alice_state.profile
        assert resolved != "miappe", "Bob's session answered for Alice"
    finally:
        reset_mcp_state()


def test_one_session_per_process_still_resolves_consistently() -> None:
    """The stdio server's guarantee, which the fix must not regress.

    One caller, one process: whatever the host injected is what every tool sees,
    ContextVar visible or not.
    """
    reset_mcp_state()
    try:
        state, context = _session("darwin-core", "1.0")
        set_context(context)

        async def resolve_in_a_fresh_task() -> str:
            return await asyncio.to_thread(lambda: get_mcp_state().profile)

        assert get_mcp_state().profile == "darwin-core"
        assert asyncio.run(resolve_in_a_fresh_task()) == state.profile
    finally:
        reset_mcp_state()
