"""A row added with + Add has the same controls as a row that was stored.

Stored rows and added rows were drawn by two copies of the row markup. The
ontology lookup and the Edit button went into one copy only, so a freshly added
row had neither until the page was reloaded.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from metaseed.ui.app import TEMPLATES_DIR, create_app
from metaseed.ui.state import AppState


def _client_on_a_study() -> TestClient:
    state = AppState()
    client = TestClient(create_app(state), follow_redirects=True)
    client.get("/load-example/miappe/1.2")
    study = next(n for n in state.nodes_by_id.values() if n.entity_type == "Study")
    client.get(f"/form/Study/{study.id}")
    return client


def test_an_added_row_offers_the_ontology_lookup() -> None:
    client = _client_on_a_study()

    row = client.post(
        "/table/Study/events/row", headers={"HX-Target": "inline-table-body-events"}
    ).text

    assert 'data-lookup-type="ontology"' in row, (
        "the added row's term cell is plain text"
    )
    assert "ontology-lookup-btn" in row, "the added row has no search button"


def test_an_added_row_has_an_edit_button() -> None:
    client = _client_on_a_study()

    row = client.post(
        "/table/Study/events/row", headers={"HX-Target": "inline-table-body-events"}
    ).text

    assert (
        ">\n            Edit\n" in row or "Edit</button>" in row or "Edit\n" in row
    ), "the added row has no Edit button"


def test_the_row_markup_lives_in_one_template() -> None:
    partials = TEMPLATES_DIR / "partials"
    holders = [
        p.name
        for p in partials.glob("inline_table*.html")
        if "cell-input-wrapper" in p.read_text()
    ]
    assert holders == ["inline_table_row.html"], holders
