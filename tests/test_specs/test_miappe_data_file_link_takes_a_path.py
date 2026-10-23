"""A MIAPPE data file's location may be a path relative to the submission (#403).

MIAPPE DM-38 (PPEO:hasDigitalLocation) allows a file identifier or a path
within the submission. The field was typed ``uri``, which accepts only absolute
URLs, so a dataset listing its files as ``raw/plot1.csv`` could not validate.
"""

from __future__ import annotations

import pytest

from metaseed.facade import ProfileFacade


@pytest.mark.parametrize("version", ["1.1", "1.2"])
@pytest.mark.parametrize(
    "link",
    ["raw/plot1.csv", "plot1.csv", "https://doi.org/10.5281/zenodo.1234567"],
)
def test_a_data_file_link_accepts_a_relative_path_and_a_url(version, link) -> None:
    facade = ProfileFacade("miappe", version)

    data_file = facade.DataFile.create(
        unique_id="DF-1", study_id="STU-1", name="plot1.csv", link=link
    )

    assert str(data_file.link) == link


@pytest.mark.parametrize("version", ["1.1", "1.2"])
@pytest.mark.parametrize("link", ["/home/user/plot1.csv", "C:\\data\\plot1.csv"])
def test_an_absolute_local_path_is_still_rejected(version, link) -> None:
    # A path outside the submission points at someone's own disk, not at a file
    # anyone else can resolve.
    facade = ProfileFacade("miappe", version)

    with pytest.raises(ValueError, match="link"):
        facade.DataFile.create(unique_id="DF-1", study_id="STU-1", name="x", link=link)
