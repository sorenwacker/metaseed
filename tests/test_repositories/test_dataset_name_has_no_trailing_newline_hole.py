"""A dataset name is the whole string, newline included (260816 review).

`validate_dataset_name` is the choke point that keeps a dataset name from
becoming a path, and it matched with `$`, which in Python matches before a
trailing newline. So `"ok\\n"` passed a check whose whole job is to be exact,
and the name reached the filesystem with a character the pattern was written
to exclude.
"""

from __future__ import annotations

import pytest

from metaseed.repositories.dataset_repository import validate_dataset_name


@pytest.mark.parametrize("name", ["ok\n", "ok\r\n", "ok\n\n"])
def test_a_trailing_newline_is_refused(name: str) -> None:
    assert validate_dataset_name(name) is not None, repr(name)


def test_an_ordinary_name_is_still_accepted() -> None:
    assert validate_dataset_name("wheat-drought_2024") is None
