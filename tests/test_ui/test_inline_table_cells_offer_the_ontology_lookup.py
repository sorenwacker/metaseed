"""A cell of a table under Related Entities offers the ontology lookup.

The main table's cells and the form's fields had it; an inline table's cells
were plain text boxes, so a term in a child record's row had to be typed by id.
"""

from __future__ import annotations

import re

from fastapi.testclient import TestClient

from metaseed.ui.app import create_app
from metaseed.ui.state import AppState


def test_an_ontology_column_cell_opens_the_lookup() -> None:
    state = AppState()
    client = TestClient(create_app(state), follow_redirects=True)
    client.get("/load-example/miappe/1.2")
    study = next(n for n in state.nodes_by_id.values() if n.entity_type == "Study")
    page = client.get(f"/form/Study/{study.id}").text

    cell = re.search(
        r'<input[^>]*data-lookup-type="ontology"[^>]*'
        r'data-testid="inline-cell-events-0-event_accession_number"',
        page,
        re.DOTALL,
    )
    assert cell, "the events table's accession cell has no ontology lookup"
    assert 'data-input="inline-cell-events-0-event_accession_number"' in page, (
        "no search button points at the cell"
    )
