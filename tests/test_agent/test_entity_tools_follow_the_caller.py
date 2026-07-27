"""Entity tools operate on the session of the caller they are serving.

``entities.py`` had ten helpers reaching for a process-wide accessor, several of
them transitively. Threading the session through them is only meaningful if a
tool actually follows the caller, and the existing suite cannot show that: every
test binds one session, where a decoupled tool and a global-reading one behave
identically.

So these register the tools against a resolver that switches callers, and assert
on the entities each caller ends up with. A missed call site shows up here as one
caller seeing the other's data.
"""

from __future__ import annotations

import json
from contextvars import ContextVar

import pytest
from mcp.server.fastmcp import FastMCP

from metaseed.agent.mcp.context import MCPContext
from metaseed.agent.mcp.tools.entities import register_entity_tools
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
def tools() -> dict[str, object]:
    """Entity tools bound to a resolver that follows ``_caller``."""
    contexts = {
        "alice": _context("miappe", "1.1"),
        "bob": _context("miappe", "1.1"),
    }
    mcp = FastMCP(name="test")
    register_entity_tools(mcp, lambda: contexts[_caller.get()])
    return {
        "fns": {name: tool.fn for name, tool in mcp._tool_manager._tools.items()},
        "contexts": contexts,
    }


def _create(fns: dict, entity_type: str, data: dict) -> dict:
    return json.loads(
        fns["create_entity"](entity_type=entity_type, data=json.dumps(data))
    )


def _titles(fns: dict) -> list[str]:
    """Titles of everything the calling session holds, from the tool's own output.

    ``list_entities`` groups by entity type, so this flattens the groups.
    """
    listed = json.loads(fns["list_entities"]())
    return sorted(
        str(entity["data"].get("title", ""))
        for group in listed.get("entities", {}).values()
        for entity in group
    )


def test_each_caller_only_sees_what_they_created(tools: dict) -> None:
    fns = tools["fns"]

    _caller.set("alice")
    _create(fns, "Investigation", {"unique_id": "A1", "title": "ALICE"})
    _caller.set("bob")
    _create(fns, "Investigation", {"unique_id": "B1", "title": "BOB"})

    _caller.set("alice")
    alice_titles = _titles(fns)
    _caller.set("bob")
    bob_titles = _titles(fns)

    assert alice_titles == ["ALICE"], f"alice saw {alice_titles}"
    assert bob_titles == ["BOB"], f"bob saw {bob_titles}"


def test_a_write_lands_in_the_calling_session_s_state(tools: dict) -> None:
    """The entity must reach the caller's own AppState, not merely be reported.

    ``_auto_save_dataset`` is the path that used to resolve a factory ambiently,
    so a write could be reported against one session and persisted through
    another.
    """
    fns, contexts = tools["fns"], tools["contexts"]

    _caller.set("alice")
    _create(fns, "Investigation", {"unique_id": "A1", "title": "ALICE"})

    alice_nodes = list(contexts["alice"].state.nodes_by_id.values())
    assert [getattr(n.instance, "title", None) for n in alice_nodes] == ["ALICE"]
    assert contexts["bob"].state.nodes_by_id == {}


def test_the_reported_dataset_is_the_caller_s(tools: dict) -> None:
    """The decoupled helpers feed hints and safety checks, not the CRUD itself.

    That distinction matters: a tool can create entities in the right session
    while every *helper* still answers from a process-wide default, and a test
    that only checks the created entities would not notice. This asserts on a
    value that comes from ``_get_current_dataset_info`` — i.e. from the state
    the helpers were given — so a helper reaching for a global shows up here.
    """
    from metaseed.ui.datasets import set_current_dataset_name

    fns, contexts = tools["fns"], tools["contexts"]
    set_current_dataset_name(contexts["alice"].state, "alice-dataset")
    set_current_dataset_name(contexts["bob"].state, "bob-dataset")

    _caller.set("alice")
    alice = _create(fns, "Investigation", {"unique_id": "A1", "title": "ALICE"})
    _caller.set("bob")
    bob = _create(fns, "Investigation", {"unique_id": "B1", "title": "BOB"})

    assert alice["_dataset"]["dataset"] == "alice-dataset"
    assert bob["_dataset"]["dataset"] == "bob-dataset"


def test_the_dataset_safety_check_reads_the_caller_s_dataset(tools: dict) -> None:
    """``expected_dataset`` guards against editing the wrong dataset, so it must
    compare against the caller's, not whichever session was bound last."""
    fns = tools["fns"]

    _caller.set("alice")
    result = _create(fns, "Investigation", {"unique_id": "A1", "title": "ALICE"})
    assert "error" not in result

    _caller.set("bob")
    mismatched = json.loads(
        fns["create_entity"](
            entity_type="Investigation",
            data=json.dumps({"unique_id": "B1", "title": "BOB"}),
            expected_dataset="a-dataset-bob-is-not-in",
        )
    )

    assert "error" in mismatched
    assert "Dataset mismatch" in mismatched["error"]
