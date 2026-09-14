"""An edit form offers a way back before its fields, not only after them.

The table view of a nested field has a Back button above the table, but the
entity edit forms had none at the top: leaving the root entity's form meant the
breadcrumb or scrolling past every field to Cancel, and a nested entity's form
had only Cancel and Save & Back at the bottom.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from metaseed.ui.app import create_app
from metaseed.ui.state import AppState


def _loaded_isa_example() -> tuple[AppState, TestClient]:
    state = AppState()
    client = TestClient(create_app(state), follow_redirects=True)
    response = client.get("/load-example/isa/1.0")
    assert response.status_code == 200, response.text
    return state, client


def _root_form(state: AppState, client: TestClient) -> str:
    root = next(n for n in state.nodes_by_id.values() if n.parent_id is None)
    response = client.get(f"/form/{root.entity_type}/{root.id}")
    assert response.status_code == 200, response.text
    return response.text


def test_the_edit_form_has_a_back_button_above_its_fields() -> None:
    state, client = _loaded_isa_example()
    html = _root_form(state, client)

    before_form = html.split('data-testid="form-entity"')[0]
    assert 'data-testid="btn-back"' in before_form


def test_a_nested_entity_form_has_a_back_button_above_its_fields() -> None:
    state, client = _loaded_isa_example()
    _root_form(state, client)  # opening the parent fills its nested items

    response = client.get("/nested/Investigation/studies/0")
    assert response.status_code == 200, response.text

    before_form = response.text.split('data-testid="form-entity"')[0]
    assert 'data-testid="btn-back"' in before_form
