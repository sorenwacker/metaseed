""" "Saved" must mean written (260816 review).

`POST /api/dcat/metadata` assigned `state.catalog_metadata` and answered
`{"status": "saved"}` without calling `auto_save`, which every other mutating
route does. `DatasetManager` round-trips the field and the repository stores
it, so nothing was broken except that no write was ever triggered: the title,
publisher and licence a user typed — for exactly the profiles (Darwin Core and
kin) that cannot derive them — were gone after a reload, having been reported
as saved.
"""

from __future__ import annotations

from typing import Any

import pytest

pytest.importorskip("rdflib")

from fastapi.testclient import TestClient

from metaseed.ui.app import create_app


class _RecordingFactory:
    """Stands in for the app's dataset factory, recording what gets saved."""

    def __init__(self) -> None:
        self.saved: list[Any] = []

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return self

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.saved.append((args, kwargs))


def test_setting_catalog_metadata_triggers_a_save() -> None:
    app = create_app()
    client = TestClient(app)
    client.get("/load-example/miappe/1.2", follow_redirects=True)

    from metaseed.ui import datasets as datasets_module

    calls: list[Any] = []
    original = datasets_module.auto_save

    def _spy(state: Any, factory: Any = None) -> Any:
        calls.append(state)
        return original(state, factory)

    datasets_module.auto_save = _spy
    try:
        response = client.post(
            "/api/dcat/metadata",
            data={
                "title": "A title only the user knows",
                "description": "d",
                "publisher": "p",
                "license": "l",
                "keywords": "one, two",
            },
        )
    finally:
        datasets_module.auto_save = original

    assert response.status_code == 200
    assert response.json()["status"] == "saved"
    assert calls, "answered 'saved' without asking anything to save"


def test_the_metadata_survives_into_the_card() -> None:
    """What was set is what the card shows, so the write is not merely attempted."""
    client = TestClient(create_app())
    client.get("/load-example/miappe/1.2", follow_redirects=True)

    client.post(
        "/api/dcat/metadata",
        data={
            "title": "A title only the user knows",
            "description": "d",
            "publisher": "p",
            "license": "",
            "keywords": "",
        },
    )
    card = client.get("/api/dcat").json()

    assert card["metadata"]["title"] == "A title only the user knows"
