"""Tests for the ``import_from_database`` MCP tool.

The tool must reuse the adapter registry rather than reimplement an importer, so
the registered ``import_accession`` is patched: a test that bypassed the registry
would still pass if the tool hard-coded a per-database branch.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from metaseed.agent.mcp import server as srv
from metaseed.api.client import MetaseedClient
from metaseed.repositories.filesystem_dataset import FilesystemDatasetRepository
from metaseed.ui.dataset_manager import DatasetManagerFactory
from metaseed.ui.state import AppState

from .helpers import get_tool


def _pride_client(accession: str = "PXD000000", **_kwargs: object) -> MetaseedClient:
    """Stand in for ``metaseed.pride.import_accession`` without the network."""
    client = MetaseedClient("pride", "1.0")
    client.create_entity(
        "Dataset",
        {"accession": accession, "title": "Imported dataset"},
        skip_validation=True,
    )
    return client


@pytest.fixture
def import_tool(tmp_path):
    """The tool bound to an isolated session and dataset repository."""
    srv.set_mcp_state(AppState(profile="miappe", version="1.2"))
    context = srv.get_context()
    assert context is not None
    context.dataset_factory = DatasetManagerFactory(
        sync_repo=FilesystemDatasetRepository(datasets_dir=tmp_path)
    )
    server = srv.create_server()
    tool = get_tool(server, "import_from_database")
    assert tool is not None, "import_from_database is not registered"
    return tool, tmp_path


def test_import_loads_the_record_and_saves_it(import_tool):
    """The imported record becomes the current dataset and is persisted.

    Asserts on the entity that arrived rather than a count: an importer whose
    result was saved but never installed on the state reports success while
    leaving the agent editing the previous dataset.
    """
    tool, datasets_dir = import_tool

    with patch("metaseed.pride.import_accession", _pride_client):
        data = json.loads(
            tool(profile="pride", accession="PXD000001", name="test-imported")
        )

    assert data.get("status") == "imported", data
    assert data["profile"] == "pride"
    assert data["accession"] == "PXD000001"
    assert data["entity_count"] == 1

    state = srv.get_mcp_state()
    assert state.profile == "pride"
    (imported,) = state.get_or_create_facade().get_roots()
    assert imported.instance.model_dump()["accession"] == "PXD000001"

    saved = json.loads((datasets_dir / "test-imported.json").read_text())
    assert saved["profile"] == "pride"
    assert saved["entities"][0]["accession"] == "PXD000001"


def test_import_reports_the_profiles_that_can_be_imported(import_tool):
    """A profile with no importer must be refused with the usable alternatives,
    otherwise the agent's only recovery is to guess another profile name."""
    tool, _ = import_tool

    data = json.loads(tool(profile="darwin-core", accession="X", name="n"))

    assert "error" in data
    assert "pride" in data["available"]
    assert "darwin-core" not in data["available"]


def test_import_of_an_empty_result_does_not_replace_the_dataset(import_tool):
    """A wrong accession must not blank the dataset the agent is working on."""
    tool, _ = import_tool
    state = srv.get_mcp_state()
    state.add_node(
        "Investigation",
        {"unique_id": "INV-1", "title": "Keep me"},
        skip_validation=True,
    )

    def _empty(_accession: str, **_kwargs: object) -> MetaseedClient:
        return MetaseedClient("pride", "1.0")

    with patch("metaseed.pride.import_accession", _empty):
        data = json.loads(tool(profile="pride", accession="PXD999999", name="n"))

    assert "error" in data
    assert state.profile == "miappe"
    assert [n.entity_type for n in state.nodes_by_id.values()] == ["Investigation"]
