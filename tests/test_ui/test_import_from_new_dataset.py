"""A repository record becomes a dataset from the New Dataset screen.

The import field sat on the dataset page, so a dataset had to be created,
given a profile and named before the record that supplies all three was
known. The New Dataset screen now carries one button per registered importer:
each identifier becomes a saved dataset named by the title its record carries.
See docs/architecture/integration-adapters.md, *The hosts*.
"""

from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest
from fastapi.testclient import TestClient

from metaseed import adapters
from metaseed.api.client import MetaseedClient
from metaseed.ui.app import create_app
from metaseed.ui.datasets import imported_dataset_name, list_datasets
from metaseed.ui.state import AppState

IMPORTER = "metaseed.pride.import_accession"


@pytest.fixture
def temp_datasets_dir(tmp_path):
    """Use a temporary directory for datasets so tests never touch real storage."""
    from metaseed.ui.datasets import _factory_var

    datasets_dir = tmp_path / "datasets"
    datasets_dir.mkdir()
    token = _factory_var.set(None)
    try:
        with patch(
            "metaseed.repositories.filesystem_dataset.DEFAULT_DATASETS_DIR",
            datasets_dir,
        ):
            yield datasets_dir
    finally:
        _factory_var.reset(token)


def _project(accession: str, **_kwargs: object) -> MetaseedClient:
    client = MetaseedClient("pride", "1.0")
    client.create_entity(
        "Dataset",
        {"accession": accession, "title": "test-hela: a time course"},
        skip_validation=True,
    )
    return client


def _nothing(_accession: str, **_kwargs: object) -> MetaseedClient:
    return MetaseedClient("pride", "1.0")


def _saved() -> list[str]:
    return sorted(dataset["name"] for dataset in list_datasets())


def _post(client: TestClient, values: str, key: str = "pride-import"):
    return client.post("/import/new", data={"key": key, "values": values})


class TestTheName:
    def test_a_title_becomes_a_name_the_store_accepts(self) -> None:
        name = imported_dataset_name("HeLa phosphoproteome: a time course", "PXD1", [])

        assert name == "HeLa_phosphoproteome_a_time_course"

    def test_a_record_without_a_title_is_named_by_its_identifier(self) -> None:
        assert imported_dataset_name("", "PXD000001", []) == "PXD000001"

    def test_a_taken_name_gets_the_identifier_appended(self) -> None:
        assert (
            imported_dataset_name("Trial", "PXD000001", ["Trial"]) == "Trial_PXD000001"
        )

    def test_a_record_held_under_both_names_has_none_left(self) -> None:
        assert imported_dataset_name("Trial", "PXD1", ["Trial", "Trial_PXD1"]) is None

    def test_a_long_title_still_fits_with_its_identifier(self) -> None:
        name = imported_dataset_name(
            "t" * 200, "https://server.example.org/brapi/v2", ["t" * 40]
        )

        assert name is not None and len(name) <= 64


class TestTheScreen:
    def test_every_importer_adds_its_button(self) -> None:
        html = TestClient(create_app(AppState())).get("/new-dataset").text

        for profile in adapters.importable_profiles():
            action = adapters.import_action_for_profile(profile)
            assert f'name="key" value="{action.key}"' in html, action.key
            assert action.label in html


class TestTheImport:
    def test_each_identifier_becomes_a_saved_dataset(self, temp_datasets_dir) -> None:
        client = TestClient(create_app(AppState()))

        with patch(IMPORTER, _project):
            response = _post(client, "PXD000001\n\nPXD000002\nPXD000001\n")

        assert response.status_code == 200
        assert _saved() == [
            "test-hela_a_time_course",
            "test-hela_a_time_course_PXD000002",
        ]
        assert response.text.count('data-status="imported"') == 2
        assert "/dataset/test-hela_a_time_course/edit" in response.text

    def test_a_record_holding_nothing_saves_nothing(self, temp_datasets_dir) -> None:
        client = TestClient(create_app(AppState()))

        with patch(IMPORTER, _nothing):
            response = _post(client, "PXD999999")

        assert 'data-status="empty"' in response.text
        assert _saved() == []

    def test_a_repository_that_does_not_answer_is_not_checked(
        self, temp_datasets_dir
    ) -> None:
        def _down(_accession: str, **_kwargs: object) -> MetaseedClient:
            raise httpx.ConnectTimeout("no answer")

        client = TestClient(create_app(AppState()))
        with patch(IMPORTER, _down):
            response = _post(client, "PXD000001")

        assert 'data-status="not_checked"' in response.text
        assert _saved() == []

    def test_one_failure_does_not_stop_the_rest(self, temp_datasets_dir) -> None:
        def _second_fails(accession: str, **_kwargs: object) -> MetaseedClient:
            if accession == "bad":
                raise ValueError("not a ProteomeXchange accession")
            return _project(accession)

        client = TestClient(create_app(AppState()))
        with patch(IMPORTER, _second_fails):
            response = _post(client, "bad\nPXD000001")

        assert 'data-status="failed"' in response.text
        assert "not a ProteomeXchange accession" in response.text
        assert _saved() == ["test-hela_a_time_course"]

    def test_more_than_one_submission_takes_imports_nothing(
        self, temp_datasets_dir
    ) -> None:
        client = TestClient(create_app(AppState()))

        with patch(IMPORTER, _project):
            response = _post(client, "\n".join(f"PXD{n:06d}" for n in range(21)))

        assert 'data-testid="import-problem"' in response.text
        assert _saved() == []

    def test_an_unknown_importer_is_refused(self, temp_datasets_dir) -> None:
        response = _post(TestClient(create_app(AppState())), "x", key="nope")

        assert response.status_code == 404
