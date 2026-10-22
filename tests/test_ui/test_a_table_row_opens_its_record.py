"""Every row under Related Entities opens the record it stands for.

A row offered only Delete, and Edit only when the row's type held records of
its own, so a Source in a Study's table could not be opened from there.
"""

from __future__ import annotations

import re

from fastapi.testclient import TestClient

from metaseed.ui.app import create_app
from metaseed.ui.state import AppState


def test_each_row_has_an_edit_button_to_its_own_record() -> None:
    state = AppState()
    client = TestClient(create_app(state), follow_redirects=True)
    client.get("/load-example/miappe/1.2")
    inv = next(n for n in state.nodes_by_id.values() if not n.parent_id)
    page = client.get(f"/form/{inv.entity_type}/{inv.id}").text

    held = [c for c in inv.children if c.parent_field == "studies"] or [
        c for c in inv.children if c.entity_type == "Study"
    ]
    links = re.findall(
        r'data-testid="inline-open-studies-\d+"[^>]*hx-get="/form/Study/([^"]+)"|hx-get="/form/Study/([^"]+)"[^>]*data-testid="inline-open-studies-\d+"',
        page,
    )
    opened = [a or b for a, b in links]
    assert held
    assert opened == [c.id for c in held]
