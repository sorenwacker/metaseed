"""A list of values is edited as values, whatever the value type.

The field template kept its own copy of which list item types are values
(``string``, ``int``, ``float``, ``bool``), narrower than the library's
``PRIMITIVE_TYPES``. A ``list`` of ``uri`` was therefore rendered as a nested
entity list — a "Create first" note on the new form and a "links (2)" button to
a child table on the edit form — so its values could not be seen or edited.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from metaseed.ui.app import create_app
from metaseed.ui.state import AppState

_PROFILE = """\
version: '1.0'
name: test-list-items
root_entity: Thing
entities:
  Thing:
    fields:
    - name: identifier
      type: string
      required: true
    - name: links
      type: list
      items: uri
    - name: dates
      type: list
      items: date
    - name: children
      type: list
      items: Child
  Child:
    fields:
    - name: name
      type: string
"""


@pytest.fixture
def form_html(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    """The new-entity form of a user profile with value lists and an entity list."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    spec_dir = tmp_path / "metaseed" / "specs" / "test-list-items" / "1.0"
    spec_dir.mkdir(parents=True)
    (spec_dir / "profile.yaml").write_text(_PROFILE)
    client = TestClient(create_app(AppState()))
    response = client.get("/form/Thing?profile=test-list-items&version=1.0")
    assert response.status_code == 200, response.text
    return response.text


@pytest.mark.parametrize("field", ["links", "dates"])
def test_a_list_of_values_renders_as_a_one_per_line_text_box(
    form_html: str, field: str
) -> None:
    assert f'data-testid="input-{field}"' in form_html
    assert f"Create first, then add {field}" not in form_html


def test_a_list_of_entities_is_still_a_nested_list(form_html: str) -> None:
    assert "Create first, then add children" in form_html
    assert 'data-testid="input-children"' not in form_html
