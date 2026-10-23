"""A load that could not build every entity says so (#348).

A FAIDARE import was saved, and loading it answered ``"status": "loaded"`` with
``"entity_count": 0``: the entities the load dropped appeared only as log
warnings, so an empty dataset was reported as a success.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi.testclient import TestClient

from metaseed.ui.app import create_app
from metaseed.ui.state import AppState

_GOOD = {"_type": "Investigation", "unique_id": "INV-1", "title": "Kept"}
_UNKNOWN = {"_type": "NoSuchEntity", "unique_id": "X-1"}


def _write(name: str, entities: list[dict]) -> None:
    path = Path(os.environ["METASEED_DATASETS_DIR"]) / f"{name}.json"
    path.write_text(
        json.dumps(
            {"name": name, "profile": "miappe", "version": "1.2", "entities": entities}
        )
    )


def _client() -> TestClient:
    return TestClient(create_app(AppState()), follow_redirects=True)


def test_a_partial_load_reports_what_it_dropped() -> None:
    _write("test-partial-load", [_GOOD, _UNKNOWN])

    body = (
        _client().post("/api/datasets/load", json={"name": "test-partial-load"}).json()
    )

    assert body["status"] == "partially_loaded"
    assert body["entity_count"] == 1
    assert body["skipped_count"] == 1


def test_a_load_that_built_nothing_is_not_reported_as_loaded() -> None:
    _write("test-empty-load", [_UNKNOWN, {**_UNKNOWN, "unique_id": "X-2"}])

    body = _client().post("/api/datasets/load", json={"name": "test-empty-load"}).json()

    assert body["status"] == "not_loaded"
    assert body["skipped_count"] == 2


def test_a_whole_load_is_loaded() -> None:
    _write("test-whole-load", [_GOOD])

    body = _client().post("/api/datasets/load", json={"name": "test-whole-load"}).json()

    assert body["status"] == "loaded"
    assert body["skipped_count"] == 0


def test_the_dataset_page_warns_about_dropped_entities() -> None:
    _write("test-partial-page", [_GOOD, _UNKNOWN])

    page = _client().get("/dataset/test-partial-page/edit").text

    assert 'data-testid="dataset-load-warning"' in page
    assert "1 of 2 entities could not be loaded" in page
