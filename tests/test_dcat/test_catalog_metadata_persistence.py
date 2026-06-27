"""CatalogMetadata round-trips through the filesystem dataset repository (#27)."""

from __future__ import annotations

from metaseed.repositories.dataset_repository import CatalogMetadata, DatasetData
from metaseed.repositories.filesystem_dataset import FilesystemDatasetRepository


def test_catalog_metadata_round_trips(tmp_path):
    repo = FilesystemDatasetRepository(datasets_dir=tmp_path)
    data = DatasetData(
        name="ds1",
        profile="darwin-core",
        version="1.0",
        entities=[],
        catalog_metadata=CatalogMetadata(
            title="My dataset",
            description="desc",
            publisher="Org",
            keywords=["a", "b"],
        ),
    )

    repo.save("ds1", data)
    loaded = repo.load("ds1")

    assert loaded.catalog_metadata is not None
    assert loaded.catalog_metadata.title == "My dataset"
    assert loaded.catalog_metadata.publisher == "Org"
    assert loaded.catalog_metadata.keywords == ["a", "b"]


def test_absent_catalog_metadata_loads_as_none(tmp_path):
    repo = FilesystemDatasetRepository(datasets_dir=tmp_path)
    repo.save("ds2", DatasetData(name="ds2", profile="miappe", version="1.2"))

    loaded = repo.load("ds2")
    assert loaded.catalog_metadata is None
