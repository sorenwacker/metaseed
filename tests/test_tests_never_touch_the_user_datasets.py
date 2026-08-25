"""The suite never reads or writes the user's real datasets directory.

A test that saved through the app wrote into ``~/.local/share/metaseed/datasets``
and a cleanup there deleted the user's own datasets while the UI was open. The
autouse fixture in ``conftest.py`` gives every test a private directory; this
pins that it is in effect for every test, including one that asks the
repository or the UI helper for the directory.
"""

from __future__ import annotations

from pathlib import Path


def test_the_datasets_dir_is_private_to_the_test():
    from metaseed.paths import get_datasets_dir
    from metaseed.repositories.filesystem_dataset import default_datasets_dir

    real = Path.home() / ".local" / "share" / "metaseed" / "datasets"
    for resolved in (default_datasets_dir(), get_datasets_dir()):
        assert resolved != real, "a test would touch the user's datasets"
        assert real not in resolved.parents
