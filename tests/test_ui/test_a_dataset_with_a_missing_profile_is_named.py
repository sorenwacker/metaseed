"""Opening a dataset whose profile version is not installed says so.

The load cleared the open dataset and then failed on the specification, which
answered with a server error and left the graph poll failing as well. See
docs/architecture/dataset-repository.md.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from metaseed.ui.app import create_app
from metaseed.ui.state import AppState


def test_the_datasets_page_names_the_missing_profile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("METASEED_DATASETS_DIR", str(tmp_path))
    (tmp_path / "test-from-elsewhere.json").write_text(
        json.dumps(
            {
                "name": "test-from-elsewhere",
                "profile": "miappe",
                "version": "9.9",
                "entities": [{"_type": "Investigation", "unique_id": "INV-1"}],
            }
        )
    )
    client = TestClient(create_app(AppState()), follow_redirects=True)
    assert client.get("/load-example/isa/1.0").status_code == 200

    response = client.get("/dataset/test-from-elsewhere/edit")

    assert response.status_code == 200
    assert 'data-testid="dataset-profile-missing"' in response.text
    assert "miappe 9.9" in response.text
    assert "1.1, 1.2" in response.text
    graph = client.get("/api/graph")
    assert graph.status_code == 200
    assert graph.json()["nodes"], "the dataset open before is still open"
