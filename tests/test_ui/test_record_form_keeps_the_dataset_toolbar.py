"""A record's form keeps the dataset's toolbar and leads back to the dataset.

Opening a record replaced the dataset page, toolbar and all, so the graph could
only be switched on after going back; and the form's first crumb, Entities,
loaded the list of datasets rather than the dataset.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from metaseed.ui.app import create_app
from metaseed.ui.state import AppState


def _opened() -> tuple[TestClient, AppState]:
    state = AppState()
    client = TestClient(create_app(state), follow_redirects=True)
    client.get("/load-example/miappe/1.2")
    return client, state


def _form() -> tuple[str, str]:
    client, state = _opened()
    study = next(n for n in state.nodes_by_id.values() if n.entity_type == "Study")
    return client.get(f"/form/Study/{study.id}").text, state._current_dataset


def test_the_toolbar_sits_outside_what_a_form_replaces() -> None:
    """Under the header, before #main: opening a record swaps #main only."""
    client, state = _opened()
    page = client.get(f"/dataset/{state._current_dataset}/edit").text

    bar = page.index('data-testid="dataset-bar"')
    assert 'data-testid="btn-view-graph"' in page[bar:]
    assert bar < page.index('id="main"')
    assert page.count('data-testid="btn-view-graph"') == 1


def test_entities_leads_to_the_open_dataset() -> None:
    page, name = _form()

    assert name
    assert f'href="/dataset/{name}/edit"' in page


def test_the_toolbar_links_carry_the_mount_prefix() -> None:
    state = AppState()
    client = TestClient(create_app(state, base_url="/hub"), follow_redirects=True)
    client.get("/load-example/miappe/1.2")
    page = client.get(f"/dataset/{state._current_dataset}/edit").text

    assert 'href="/hub/export"' in page
    assert 'hx-post="/hub/import"' in page


def test_the_bar_does_not_take_the_row_that_fills_the_screen() -> None:
    """The layout's grid had three rows; the bar became the stretching one."""
    from metaseed.ui.app import STATIC_DIR

    css = (STATIC_DIR / "css" / "style.css").read_text()
    assert (
        ".layout:has(> .dataset-bar) {\n    grid-template-rows: auto auto 1fr auto;"
        in css
    )
