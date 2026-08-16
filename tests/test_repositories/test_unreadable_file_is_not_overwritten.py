"""A dataset file that could not be read must never be written over.

`_load` caught `(JSONDecodeError, OSError)` and only logged: the repository was
then indistinguishable from one opened on a file that does not exist, and the
first create/update/delete serialized that emptiness over the user's records. A
transient read failure — a permission error, a concurrent writer, a half-written
save — therefore destroyed the dataset.

The failure was self-amplifying, because `_save` truncated the target in place:
an interrupted save produced exactly the corrupt file that makes the next load
fail. Both halves are covered here — refuse to write after a failed read, and
write atomically so the corrupt file does not arise in the first place.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from metaseed.repositories.file import DatasetLoadFailedError, FileEntityRepository


def _dataset_file(tmp_path: Path) -> Path:
    """A dataset file holding one Investigation, as a real one would."""
    path = tmp_path / "dataset.json"
    path.write_text(
        json.dumps(
            {
                "profile": "miappe",
                "version": "1.2",
                "entities": [
                    {
                        "id": "inv-1",
                        "entity_type": "Investigation",
                        "label": "Kept",
                        "parent_id": None,
                        "unique_id": "INV-1",
                        "title": "Kept",
                    }
                ],
            }
        )
    )
    return path


def _corrupt(path: Path) -> str:
    """Truncate the file the way an interrupted save would."""
    text = path.read_text()[: len(path.read_text()) // 2]
    path.write_text(text)
    return text


def test_a_mutation_after_a_failed_read_refuses_instead_of_overwriting(
    tmp_path: Path,
) -> None:
    """The finding itself: one create replaced the whole dataset with itself."""
    path = _dataset_file(tmp_path)
    truncated = _corrupt(path)

    repo = FileEntityRepository(dataset_path=path, profile="miappe", version="1.2")

    with pytest.raises(DatasetLoadFailedError):
        repo.create_entity("Investigation", {"unique_id": "INV-2", "title": "New"})

    assert path.read_text() == truncated, "the unreadable file was written over"


def test_the_refusal_names_the_file_and_the_reason(tmp_path: Path) -> None:
    path = _dataset_file(tmp_path)
    _corrupt(path)
    repo = FileEntityRepository(dataset_path=path, profile="miappe", version="1.2")

    with pytest.raises(DatasetLoadFailedError) as raised:
        repo.create_entity("Investigation", {"unique_id": "INV-2", "title": "New"})

    assert str(path) in str(raised.value)


def test_a_successful_reload_clears_the_refusal(tmp_path: Path) -> None:
    """A transient failure must be recoverable without a new repository."""
    path = _dataset_file(tmp_path)
    good = path.read_text()
    _corrupt(path)
    repo = FileEntityRepository(dataset_path=path, profile="miappe", version="1.2")

    path.write_text(good)
    repo.reload()

    repo.create_entity("Investigation", {"unique_id": "INV-2", "title": "New"})

    written = json.loads(path.read_text())
    ids = {e.get("unique_id") for e in written["entities"]}
    assert {"INV-1", "INV-2"} <= ids, "the recovered dataset lost records"


def test_a_readable_empty_file_still_saves(tmp_path: Path) -> None:
    """Only an unreadable file is refused; a genuinely empty one is not."""
    path = tmp_path / "empty.json"
    path.write_text(json.dumps({"profile": "miappe", "version": "1.2", "entities": []}))
    repo = FileEntityRepository(dataset_path=path, profile="miappe", version="1.2")

    repo.create_entity("Investigation", {"unique_id": "INV-1", "title": "First"})

    assert json.loads(path.read_text())["entities"], (
        "an empty dataset must accept writes"
    )


def test_a_save_does_not_truncate_the_file_in_place(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The amplifier: an interrupted in-place write is what corrupts the file.

    The write is interrupted part-way through, as a crash or a full disk would.
    Writing straight to the target leaves it half-written — the very state that
    makes the next load fail; writing beside it and renaming leaves it whole.
    """
    path = _dataset_file(tmp_path)
    repo = FileEntityRepository(dataset_path=path, profile="miappe", version="1.2")
    before = path.read_text()

    def _die_mid_write(data, handle, **kwargs):
        handle.write('{"entities": [half')
        raise RuntimeError("interrupted")

    monkeypatch.setattr("metaseed.repositories.file.json.dump", _die_mid_write)

    with pytest.raises(RuntimeError):
        repo._save()

    assert path.read_text() == before, "an interrupted save damaged the target file"
