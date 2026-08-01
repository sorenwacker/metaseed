"""Tests for importing a dataset from a source database in the web UI.

Covers the registry lookup, the state-installing helper, and the ``/import/source``
route that the dataset page's import control posts to. No test reaches the
network: the registered importer is patched, which is exactly the seam a host
uses, so the patch does not bypass the code under test.
"""

from __future__ import annotations

from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient

from metaseed.api.client import MetaseedClient
from metaseed.ui.app import create_app
from metaseed.ui.datasets import (
    EmptyImportError,
    NoImporterError,
    import_from_source,
)
from metaseed.ui.routes.import_export import import_options_for_profile
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


def _pride_client(accession: str = "PXD000000", **_kwargs: object) -> MetaseedClient:
    """Stand in for ``metaseed.pride.import_accession`` without the network."""
    client = MetaseedClient("pride", "1.0")
    client.create_entity(
        "Dataset",
        {"accession": accession, "title": "Imported dataset"},
        skip_validation=True,
    )
    return client


def _empty_client(_accession: str, **_kwargs: object) -> MetaseedClient:
    """An importer that reaches the archive but finds nothing there."""
    return MetaseedClient("pride", "1.0")


def _root_accessions(state: AppState) -> list[str]:
    """The ``accession`` of every root entity currently in ``state``."""
    accessions = []
    for node in state.get_or_create_facade().get_roots():
        instance = node.instance
        data = (
            instance.model_dump()
            if hasattr(instance, "model_dump")
            else dict(instance or {})
        )
        accessions.append(data.get("accession"))
    return accessions


class TestImportOptions:
    """What the dataset page is told to render."""

    def test_options_are_profile_specific(self) -> None:
        """A profile is offered its own importer and never another's."""
        assert [o["key"] for o in import_options_for_profile("pride")] == [
            "pride-import"
        ]
        assert [o["key"] for o in import_options_for_profile("ena")] == ["ena-import"]
        assert import_options_for_profile("darwin-core") == []

    def test_options_carry_the_prompt_wording(self) -> None:
        """The label must say what to type: an accession and a server URL are
        not interchangeable, and the template must not hard-code either."""
        (option,) = import_options_for_profile("miappe")
        assert option["key"] == "brapi-import"
        assert "URL" in option["input_label"]
        assert option["input_placeholder"]

        (pride,) = import_options_for_profile("pride")
        assert "accession" in pride["input_label"].lower()
        assert pride["input_placeholder"] == "PXD000001"


class TestImportFromSourceHelper:
    """The one place an import is actually run and installed."""

    def test_installs_the_imported_dataset(self) -> None:
        """The imported entities become the dataset being edited.

        Asserts on the entity that arrived, not on a count: a facade that was
        swapped in but never re-indexed still reports the old tree.
        """
        state = AppState(profile="miappe", version="1.2")

        with patch("metaseed.pride.import_accession", _pride_client):
            info = import_from_source(state, "pride", "PXD000001")

        assert info["profile"] == "pride"
        assert info["version"] == "1.0"
        assert info["entity_count"] == 1
        assert state.profile == "pride"
        labels = [node.entity_type for node in state.nodes_by_id.values()]
        assert labels == ["Dataset"]
        assert _root_accessions(state) == ["PXD000001"]

    def test_profile_without_an_importer_is_refused_by_name(self) -> None:
        """The error must name the profiles that can be imported, otherwise the
        caller has to read the registry to find out what to type instead."""
        state = AppState(profile="darwin-core", version="1.0")

        with pytest.raises(NoImporterError) as excinfo:
            import_from_source(state, "darwin-core", "anything")

        assert "pride" in str(excinfo.value)

    def test_an_empty_result_leaves_the_dataset_untouched(self) -> None:
        """A wrong accession must not silently blank the dataset being edited.

        Distinguished from "no importer" because the fix differs: retype the
        accession rather than pick another profile.
        """
        state = AppState(profile="miappe", version="1.2")
        state.add_node(
            "Investigation",
            {"unique_id": "INV-1", "title": "Keep me"},
            skip_validation=True,
        )

        with (
            patch("metaseed.pride.import_accession", _empty_client),
            pytest.raises(EmptyImportError),
        ):
            import_from_source(state, "pride", "PXD999999")

        assert state.profile == "miappe"
        assert [n.entity_type for n in state.nodes_by_id.values()] == ["Investigation"]


class TestImportSourceRoute:
    """End to end through the route the UI control posts to."""

    def test_route_imports_and_shows_the_result(self) -> None:
        state = AppState(profile="pride", version="1.0")
        client = TestClient(create_app(state))

        with patch("metaseed.pride.import_accession", _pride_client):
            response = client.post(
                "/import/source", data={"key": "pride-import", "value": "PXD000001"}
            )

        assert response.status_code == 200
        assert "Imported 1 entities" in response.text
        # The imported entities are only visible after the page reloads, so the
        # response has to ask for it; the notification alone would leave the
        # user looking at the empty dataset they just filled.
        assert "refreshPage" in response.headers.get("HX-Trigger", "")
        assert _root_accessions(state) == ["PXD000001"]

    def test_route_reports_an_empty_import_without_replacing_the_dataset(self) -> None:
        state = AppState(profile="pride", version="1.0")
        state.add_node(
            "Dataset",
            {"accession": "PXD000002", "title": "Existing"},
            skip_validation=True,
        )
        client = TestClient(create_app(state))

        with patch("metaseed.pride.import_accession", _empty_client):
            response = client.post(
                "/import/source", data={"key": "pride-import", "value": "PXD999999"}
            )

        assert response.status_code == 200
        assert "notification-error" in response.text
        assert "refreshPage" not in response.headers.get("HX-Trigger", "")
        assert _root_accessions(state) == ["PXD000002"]

    def test_route_refuses_an_importer_not_offered_for_the_profile(self) -> None:
        """The route gates on the same predicate that renders the control.

        Ungated, a hand-posted key would import a PRIDE project into a
        darwin-core dataset and replace it with a foreign profile.
        """
        state = AppState(profile="darwin-core", version="1.0")
        client = TestClient(create_app(state))

        importer = Mock(side_effect=_pride_client)
        with patch("metaseed.pride.import_accession", importer):
            response = client.post(
                "/import/source", data={"key": "pride-import", "value": "PXD000001"}
            )

        assert response.status_code == 404
        importer.assert_not_called()
        assert state.profile == "darwin-core"

    def test_route_rejects_an_unknown_key(self) -> None:
        client = TestClient(create_app(AppState(profile="pride", version="1.0")))
        response = client.post("/import/source", data={"key": "nope", "value": "x"})
        assert response.status_code == 404


class TestImportControlIsRendered:
    """The capability has to be reachable, not merely routable."""

    def test_dataset_page_offers_the_profiles_importer(self) -> None:
        state = AppState()
        client = TestClient(create_app(state), follow_redirects=True)

        response = client.get("/load-example/pride/1.0")

        assert response.status_code == 200
        assert 'data-testid="btn-import-pride-import"' in response.text
        assert "ProteomeXchange accession" in response.text
        assert 'data-testid="btn-import-ena-import"' not in response.text

    def test_empty_dataset_offers_the_importer_too(self, temp_datasets_dir) -> None:
        """An empty dataset is exactly when a user wants to fill it from an
        archive, so the control must not be hidden behind having entities.

        The empty dataset renders a different template branch from the populated
        one, so offering the control in only one of them hides it precisely when
        it is most useful.
        """
        from metaseed.ui.datasets import save_dataset

        state = AppState(profile="pride", version="1.0")
        save_dataset(state, "blank")
        client = TestClient(create_app(state), follow_redirects=True)

        response = client.get("/dataset/blank/edit")

        assert response.status_code == 200
        assert "This dataset has no entities yet" in response.text
        assert 'data-testid="btn-import-pride-import"' in response.text

    def test_dataset_page_offers_no_importer_for_a_profile_without_one(self) -> None:
        state = AppState()
        client = TestClient(create_app(state), follow_redirects=True)

        response = client.get("/load-example/darwin-core/1.0")

        assert response.status_code == 200
        assert "btn-import-" not in response.text
