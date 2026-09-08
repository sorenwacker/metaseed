"""The suite never reads or writes the user's real data directories.

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


def test_the_specs_dir_is_private_to_the_test():
    """The same for specifications, which had no override at all.

    A test that saved or published a specification wrote into the user's real
    ``~/.local/share/metaseed/specs``. The fixtures did not merely sit there:
    ``metaseed profiles`` lists user specifications alongside the built-in ones,
    so a `selenium-test` profile appeared in the user's own list, beside the
    profiles their work depends on.
    """
    from metaseed.paths import get_user_specs_dir

    real = Path.home() / ".local" / "share" / "metaseed" / "specs"
    resolved = get_user_specs_dir()

    assert resolved != real, "a test would touch the user's specifications"
    assert real not in resolved.parents
