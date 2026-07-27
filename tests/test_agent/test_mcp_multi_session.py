"""One MCP server, two callers, no leakage between them.

This is the property the whole refactor exists for, and the successor to the
``xfail`` pin that documented its absence (#195). That pin could not simply be
un-marked: it called ``get_mcp_state()``, which takes no argument identifying
the caller, so *no* implementation of it could have passed. The fix is not a
better accessor but a resolver the host supplies, and this is what that buys.

The companion test at the bottom documents the process default that remains —
correct for ``metaseed mcp`` and the web UI, and the reason a multi-caller host
must pass a resolver rather than rely on it.
"""

from __future__ import annotations

import json
from contextvars import ContextVar

import pytest

from metaseed.agent.mcp.context import ContextUnavailableError, MCPContext
from metaseed.agent.mcp.server import create_server, reset_mcp_state, set_context
from metaseed.repositories.memory import MemoryEntityRepository
from metaseed.ui.dataset_manager import DatasetManagerFactory
from metaseed.ui.services.entities import EntityService
from metaseed.ui.state import AppState

_caller: ContextVar[str] = ContextVar("caller")


def _context(profile: str, version: str) -> MCPContext:
    state = AppState()
    state.profile = profile
    state.version = version
    return MCPContext(
        state=state,
        get_entity_service=lambda: EntityService(MemoryEntityRepository(state)),
        dataset_factory=DatasetManagerFactory(),
    )


@pytest.fixture
def two_callers() -> dict:
    """A server whose tools follow whichever caller is currently set."""
    # Both on miappe so either can create an entity with a couple of fields;
    # the profile-isolation test below builds its own pair.
    contexts = {"alice": _context("miappe", "1.1"), "bob": _context("miappe", "1.1")}
    server = create_server(resolve_context=lambda: contexts[_caller.get()])
    return {
        "fns": {name: tool.fn for name, tool in server._tool_manager._tools.items()},
        "contexts": contexts,
    }


def _unique_ids(listed: str) -> list[str]:
    """Identifiers in a ``list_entities`` payload, whatever types they are."""
    payload = json.loads(listed)
    return sorted(
        str(entity["data"].get("unique_id") or entity["data"].get("accession") or "")
        for group in payload.get("entities", {}).values()
        for entity in group
    )


def test_two_callers_keep_their_own_entities(two_callers: dict) -> None:
    """Asserts on identifiers rather than counts: a shared-state bug satisfies
    ``total == 1`` for both callers by accident, but cannot produce the right
    identifier for each."""
    fns = two_callers["fns"]

    _caller.set("alice")
    fns["create_entity"](
        entity_type="Investigation",
        data=json.dumps({"unique_id": "ALICE-1", "title": "Alice's trial"}),
    )
    _caller.set("bob")
    fns["create_entity"](
        entity_type="Investigation",
        data=json.dumps({"unique_id": "BOB-1", "title": "Bob's trial"}),
    )

    _caller.set("alice")
    alice = _unique_ids(fns["list_entities"]())
    _caller.set("bob")
    bob = _unique_ids(fns["list_entities"]())

    assert alice == ["ALICE-1"]
    assert bob == ["BOB-1"]


def test_each_caller_sees_their_own_profile() -> None:
    """The profile decides which entity types exist, so answering with the wrong
    one is not a cosmetic error — it is a different schema."""
    contexts = {"alice": _context("miappe", "1.1"), "bob": _context("pride", "1.0")}
    server = create_server(resolve_context=lambda: contexts[_caller.get()])
    fns = {name: tool.fn for name, tool in server._tool_manager._tools.items()}

    _caller.set("alice")
    alice = json.loads(fns["get_dataset_info"]())
    _caller.set("bob")
    bob = json.loads(fns["get_dataset_info"]())

    assert alice["profile"] == "miappe"
    assert bob["profile"] == "pride"


def test_a_caller_that_cannot_be_identified_gets_an_error_not_someone_else_s_data() -> (
    None
):
    """Failing closed is the point: the only thing left to fall back to is
    another caller's session, so a host that cannot identify its caller must
    error even when a perfectly good default exists."""

    def _resolve() -> MCPContext:
        raise ContextUnavailableError("no MCP request in scope")

    reset_mcp_state()
    try:
        someone_else = _context("miappe", "1.1")
        set_context(someone_else)  # a default exists, and must not be used
        server = create_server(resolve_context=_resolve)
        fns = {name: tool.fn for name, tool in server._tool_manager._tools.items()}

        # Reported as a tool error rather than raised: an MCP client sees a
        # message it can act on instead of an opaque protocol failure.
        result = json.loads(fns["list_entities"]())

        assert "error" in result
        assert someone_else.state.nodes_by_id == {}, (
            "the process default was used as a fallback"
        )
    finally:
        reset_mcp_state()


def test_a_server_with_no_resolver_serves_the_one_process_session() -> None:
    """What ``metaseed mcp`` and the web UI rely on, stated as an assertion
    rather than left implicit — and the reason a multi-caller host must pass a
    resolver instead of depending on this.
    """
    reset_mcp_state()
    try:
        alice = _context("miappe", "1.1")
        bob = _context("pride", "1.0")
        server = create_server()
        fns = {name: tool.fn for name, tool in server._tool_manager._tools.items()}

        set_context(alice)
        set_context(bob)

        assert json.loads(fns["get_dataset_info"]())["profile"] == "pride"
    finally:
        reset_mcp_state()
