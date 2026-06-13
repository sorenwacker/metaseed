"""Tests for dataset JSON import (helper and /import route)."""

import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from metaseed.ui.app import create_app
from metaseed.ui.datasets import import_dataset
from metaseed.ui.state import AppState


@pytest.fixture
def temp_datasets_dir(tmp_path):
    """Use a temporary directory for datasets so tests never touch real storage."""
    from metaseed.ui.datasets import _factory_var

    datasets_dir = tmp_path / "datasets"
    datasets_dir.mkdir()

    token = _factory_var.set(None)
    try:
        with (
            patch(
                "metaseed.repositories.filesystem_dataset.DEFAULT_DATASETS_DIR",
                datasets_dir,
            ),
            patch("metaseed.ui.datasets.DATASETS_DIR", datasets_dir),
        ):
            yield datasets_dir
    finally:
        _factory_var.reset(token)


def _dataset_json(profile: str = "miappe", version: str = "1.2") -> str:
    """Build a minimal valid dataset JSON document."""
    return json.dumps(
        {
            "name": "imported",
            "profile": profile,
            "version": version,
            "entities": [
                {
                    "_type": "Investigation",
                    "unique_id": "INV-001",
                    "title": "Imported Investigation",
                }
            ],
        }
    )


class TestImportDatasetHelper:
    """Tests for the import_dataset helper."""

    def test_imports_entities_and_switches_profile(self, temp_datasets_dir):
        """A valid dataset JSON loads its entities and adopts its profile."""
        state = AppState(profile="isa")  # different starting profile

        result = import_dataset(state, _dataset_json())

        assert result["profile"] == "miappe"
        assert result["entity_count"] == 1
        assert state.profile == "miappe"
        assert len(state.entity_tree) == 1
        assert state.entity_tree[0].entity_type == "Investigation"

    def test_accepts_bytes(self, temp_datasets_dir):
        """Raw bytes (as delivered by an upload) are accepted."""
        state = AppState(profile="miappe")

        result = import_dataset(state, _dataset_json().encode("utf-8"))

        assert result["entity_count"] == 1

    def test_roundtrip_with_saved_format(self, temp_datasets_dir):
        """Importing the exact output of facade.to_dict() restores the entities."""
        source = AppState(profile="miappe")
        facade = source.get_or_create_facade()
        facade.add_entity("Investigation", {"unique_id": "INV-9", "title": "Roundtrip"})
        payload = json.dumps(
            {"profile": "miappe", "version": "1.2", "entities": facade.to_dict()}
        )

        target = AppState(profile="isa")
        result = import_dataset(target, payload)

        assert result["entity_count"] == 1
        assert target.entity_tree[0].instance.unique_id == "INV-9"

    def test_invalid_json_raises(self, temp_datasets_dir):
        """Non-JSON content raises ValueError, not a JSON decode error."""
        state = AppState(profile="miappe")

        with pytest.raises(ValueError, match="Invalid JSON"):
            import_dataset(state, "{not valid json")

    def test_missing_required_keys_raises(self, temp_datasets_dir):
        """A document without profile/entities is rejected."""
        state = AppState(profile="miappe")

        with pytest.raises(ValueError, match=r"profile.*entities"):
            import_dataset(state, json.dumps({"name": "x"}))

    def test_entities_must_be_list(self, temp_datasets_dir):
        """entities given as a non-list is rejected."""
        state = AppState(profile="miappe")

        with pytest.raises(ValueError, match="must be a list"):
            import_dataset(state, json.dumps({"profile": "miappe", "entities": {}}))

    def test_non_object_payload_raises(self, temp_datasets_dir):
        """A top-level JSON array is rejected."""
        state = AppState(profile="miappe")

        with pytest.raises(ValueError, match="must be an object"):
            import_dataset(state, json.dumps([1, 2, 3]))


class TestImportRoute:
    """Tests for the POST /import route."""

    def test_import_route_loads_dataset(self, temp_datasets_dir):
        """Uploading a valid file imports the dataset and reports the count."""
        state = AppState()
        client = TestClient(create_app(state))

        response = client.post(
            "/import",
            files={"file": ("data.json", _dataset_json(), "application/json")},
        )

        assert response.status_code == 200
        assert "Imported 1 entities" in response.text
        assert "miappe" in response.text
        assert "notification-success" in response.text
        assert len(state.entity_tree) == 1

    def test_import_route_reports_invalid_file(self, temp_datasets_dir):
        """An invalid upload yields an error notification, not a 500."""
        state = AppState()
        client = TestClient(create_app(state))

        response = client.post(
            "/import",
            files={"file": ("bad.json", "{nope", "application/json")},
        )

        assert response.status_code == 200
        assert "Import failed" in response.text
        assert "notification-error" in response.text
