"""A dataset save that fails partway must leave the previous file intact.

The save opened the target in write mode and dumped into it, so a write that
failed midway left a truncated file and the previous dataset was lost.
"""

import pytest

from metaseed.repositories.dataset_repository import DatasetData
from metaseed.repositories.filesystem_dataset import FilesystemDatasetRepository


def _data(entities: list) -> DatasetData:
    return DatasetData(
        name="test-atomic", profile="miappe", version="1.2", entities=entities
    )


def test_a_failed_save_keeps_the_previous_version(tmp_path) -> None:
    repo = FilesystemDatasetRepository(tmp_path)
    original = [{"_type": "Investigation", "unique_id": "INV-1", "title": "Kept"}]
    repo.save("test-atomic", _data(original))

    circular: list = []
    circular.append(circular)
    broken = [{"_type": "Investigation", "unique_id": "INV-1", "title": circular}]
    with pytest.raises(ValueError):
        repo.save("test-atomic", _data(broken))

    assert repo.load("test-atomic").entities == original
    assert sorted(p.name for p in tmp_path.iterdir()) == ["test-atomic.json"]
