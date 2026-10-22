"""Every form label, required or optional, opens the field's note on hover.

The form printed a field's description under its input and said nothing about
its type, example, pattern, allowed values or rules, which the exported Excel
heading and the hub's table headings did. The label now carries the same note.
"""

from __future__ import annotations

import html
import re

from fastapi.testclient import TestClient

from metaseed.ui.app import TEMPLATES_DIR, create_app
from metaseed.ui.state import AppState


def _form() -> tuple[str, AppState]:
    state = AppState()
    client = TestClient(create_app(state), follow_redirects=True)
    client.get("/load-example/miappe/1.2")
    root = next(n for n in state.nodes_by_id.values() if not n.parent_id)
    return client.get(f"/form/{root.entity_type}/{root.id}").text, state


def _label_note(page: str, field: str) -> str | None:
    match = re.search(
        rf'<label class="form-label" for="field-{re.escape(field)}"[^>]*?data-note="([^"]*)"',
        page,
    )
    return html.unescape(match.group(1)) if match else None


def test_required_and_optional_labels_carry_their_note() -> None:
    page, state = _form()
    helper = state.get_or_create_facade().Investigation
    required = next(f for f in helper.required_fields if f != "unique_id")
    optional = next(
        f
        for f in helper.all_fields
        if f not in helper.required_fields and f not in helper.child_fields
    )

    for field in (required, optional):
        note = _label_note(page, field)
        assert note, f"no note on {field}"
        assert (helper.field_info(field).get("description") or "").strip()[:20] in note
    assert "Required" in _label_note(page, required)
    assert "Optional" in _label_note(page, optional)


def test_the_page_loads_the_note_box() -> None:
    base = (TEMPLATES_DIR / "base.html").read_text()
    assert "/static/js/field-notes.js" in base
