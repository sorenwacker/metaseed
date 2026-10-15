"""The profile picker reached from /form/<root> is the one /new-dataset shows.

Opened without ``?profile=``, the form route rendered the picker with only the
profile list: under a mount such as /hub every link went to the unprefixed
root, and the import controls were missing.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from metaseed.ui.app import create_app
from metaseed.ui.state import AppState


def _page(path: str) -> str:
    client = TestClient(create_app(AppState(), base_url="/hub"))
    response = client.get(path)
    assert response.status_code == 200
    return response.text


def test_the_form_route_s_picker_matches_new_dataset() -> None:
    picker = _page("/form/Investigation")

    assert 'hx-post="/hub/import/new"' in picker, "the import controls are missing"
    assert 'hx-get="/new-dataset/name' not in picker, "a link left the mount"
    assert picker == _page("/new-dataset")
