"""A nested entity's edit form must show the way back to its parent.

The breadcrumb there was hardcoded to "Entities > <this entity>": it named no
ancestor, and the Back button returns to the entity list. A child opened
directly — from the graph, a link, or a table row — therefore offered no way up,
and reaching its parent meant returning to the root list and descending again.

The containment chain is recorded on every node (`parent_id` and `parent_field`,
ADR 006), so the path can be shown. Checked against the bundled examples: every
child in miappe 1.2 and isa 1.0 records both.
"""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from metaseed.ui.app import create_app
from metaseed.ui.state import AppState


def _example_client() -> tuple[TestClient, AppState]:
    state = AppState()
    client = TestClient(create_app(state), follow_redirects=True)
    client.get("/load-example/miappe/1.2")
    return client, state


def _breadcrumb_of(html: str) -> str:
    """The breadcrumb element alone, so a match elsewhere cannot pass a test."""
    start = html.index('data-testid="breadcrumb"')
    return html[start : html.index("</nav>", start)]


def _a_child(state: AppState) -> Any:
    return next(node for node in state.nodes_by_id.values() if node.parent_id)


def _a_grandchild(state: AppState) -> Any:
    """A node whose parent has a parent — the case that proves ordering."""
    return next(
        node
        for node in state.nodes_by_id.values()
        if node.parent_id and state.nodes_by_id[node.parent_id].parent_id
    )


def test_a_childs_edit_form_links_to_its_parent() -> None:
    client, state = _example_client()
    child = _a_child(state)
    parent = state.nodes_by_id[child.parent_id]

    breadcrumb = _breadcrumb_of(
        client.get(f"/form/{child.entity_type}/{child.id}").text
    )

    assert f"/form/{parent.entity_type}/{parent.id}" in breadcrumb, (
        "the parent must be reachable from the child's edit form"
    )
    assert (parent.label or parent.entity_type) in breadcrumb, (
        "the link must say which entity it leads to"
    )


def test_the_breadcrumb_names_the_field_the_child_sits_in() -> None:
    """ "Investigation > Person" hides which field holds the child, and a parent
    may hold one entity type in more than one field (ADR 006)."""
    client, state = _example_client()
    child = _a_child(state)

    breadcrumb = _breadcrumb_of(
        client.get(f"/form/{child.entity_type}/{child.id}").text
    )

    assert child.parent_field in breadcrumb, (
        f"the field {child.parent_field!r} the child sits in must be named"
    )


def test_ancestors_are_ordered_root_first() -> None:
    client, state = _example_client()
    grandchild = _a_grandchild(state)
    parent = state.nodes_by_id[grandchild.parent_id]
    grandparent = state.nodes_by_id[parent.parent_id]

    breadcrumb = _breadcrumb_of(
        client.get(f"/form/{grandchild.entity_type}/{grandchild.id}").text
    )

    grandparent_link = f"/form/{grandparent.entity_type}/{grandparent.id}"
    parent_link = f"/form/{parent.entity_type}/{parent.id}"
    assert grandparent_link in breadcrumb, "every ancestor must be listed, not just one"
    assert parent_link in breadcrumb

    assert breadcrumb.index(grandparent_link) < breadcrumb.index(parent_link), (
        "the path reads from the root down, like the nested-table breadcrumb"
    )
