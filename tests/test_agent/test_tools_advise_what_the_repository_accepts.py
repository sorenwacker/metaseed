"""What the MCP tools advise must be what create_entity accepts (260816 review).

Four tools built their answers from `helper.nested_fields`, but the repository
validates a parent-child pair against `helper.child_fields`, which honours the
spec's `owns:` markers and is a strict subset wherever a profile uses them. ISA
1.0 uses `owns: true` in 33 places, so the two disagree for 13 entity types.

The consequences all landed on an agent following the server's own
instructions: `create_entity` suggested creating a `Comment` under an
Investigation (rejected), `get_profile_relationships` — which the instructions
name as the authority on the hierarchy — listed child types that cannot be
created, and `validate_relationships` warned "no Comment linked" about links
that cannot exist.

`create_dataset` had a different defect with the same effect: it read
`facade._spec.root_entity`, and `_spec` is set only when a caller passes a
pre-loaded spec, so the documented `root_entity` was null on every real call
while the facade knew the answer.
"""

from __future__ import annotations

import json

from metaseed.agent.mcp.server import create_server
from metaseed.facade import ProfileFacade
from tests.test_agent.helpers import get_tool

#: A pair ISA 1.0 declares as nested but not owned: the repository rejects it.
NOT_OWNED = "Comment"


def _isa_investigation():
    return ProfileFacade("isa", "1.0").Investigation


def test_the_profiles_disagree_only_where_ownership_says_so() -> None:
    """The premise, stated so the tests below cannot quietly stop meaning anything."""
    helper = _isa_investigation()

    assert NOT_OWNED in set(helper.nested_fields.values())
    assert NOT_OWNED not in set(helper.child_fields.values())


def test_relationships_reports_only_creatable_children() -> None:
    tool = get_tool(create_server(), "get_profile_relationships")

    answer = json.loads(tool(profile="isa", version="1.0"))
    investigation = answer["hierarchy"]["Investigation"]

    assert NOT_OWNED not in investigation["children"], investigation["children"]
    assert "Study" in investigation["children"]


def test_creation_hints_suggest_a_child_that_can_be_created() -> None:
    from metaseed.agent.mcp.tools.entities import _creation_hints
    from metaseed.ui.state import AppState

    hints = _creation_hints(AppState(profile="isa", version="1.0"), "Investigation")

    assert NOT_OWNED not in str(hints.get("typical_next", "")), hints


def test_relationship_validation_does_not_warn_about_impossible_links() -> None:
    from metaseed.agent.mcp.server import get_entity_service, set_mcp_state
    from metaseed.ui.state import AppState

    set_mcp_state(AppState(profile="isa", version="1.0"))
    server = create_server()
    get_entity_service().create_entity(
        "Investigation", {"identifier": "INV1", "title": "I"}
    )

    answer = json.loads(get_tool(server, "validate_relationships")())
    issues = " ".join(
        warning.get("issue", "") for warning in answer.get("warnings", [])
    )

    assert NOT_OWNED not in issues, answer.get("warnings")


def test_create_dataset_reports_the_root_entity() -> None:
    tool = get_tool(create_server(), "create_dataset")

    answer = json.loads(tool(name="test-root-probe", profile="isa", version="1.0"))

    assert answer.get("root_entity") == "Investigation", answer
