"""The datasets overview is searched on the server and shown a page at a time.

The box above the list hid cards on the page; a dataset beyond the page could
not be found, and a long list was one long page.
See docs/getting-started/quickstart.md, *Web UI*.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from metaseed.ui.app import create_app
from metaseed.ui.datasets import save_dataset
from metaseed.ui.routes.core import DATASETS_PER_PAGE
from metaseed.ui.state import AppState


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


@pytest.fixture
def many_datasets(temp_datasets_dir) -> TestClient:
    """A page and a bit of datasets: all but three are MIAPPE, three are ISA."""
    for n in range(DATASETS_PER_PAGE + 6):
        profile = "isa" if n % 10 == 0 else "miappe"
        version = "1.0" if profile == "isa" else "1.2"
        save_dataset(AppState(profile=profile, version=version), f"test-ds-{n:02d}")
    return TestClient(create_app(AppState()))


def _listed(html: str) -> list[str]:
    import re

    return re.findall(r'class="dataset-card-name">([^<]+)<', html)


def test_the_first_page_holds_one_page_of_datasets_and_a_pager(many_datasets) -> None:
    html = many_datasets.get("/").text

    assert len(_listed(html)) == DATASETS_PER_PAGE
    assert 'data-testid="pager-next"' in html
    assert 'data-testid="pager-previous"' not in html
    assert f"Page 1 of 2 &middot; {DATASETS_PER_PAGE + 6} datasets" in html


def test_the_second_page_holds_the_rest(many_datasets) -> None:
    html = many_datasets.get("/", params={"page": 2}).text

    assert len(_listed(html)) == 6
    assert 'data-testid="pager-previous"' in html
    assert 'data-testid="pager-next"' not in html


def test_a_search_narrows_by_name_or_standard_whatever_the_case(many_datasets) -> None:
    by_standard = many_datasets.get("/", params={"q": "ISA"}).text
    by_name = many_datasets.get("/", params={"q": "ds-1"}).text

    assert len(_listed(by_standard)) == 3
    assert 'value="ISA"' in by_standard, "the box keeps what was searched"
    assert 'data-testid="dataset-pager"' not in by_standard
    assert all(name.startswith("test-ds-1") for name in _listed(by_name))
    assert len(_listed(by_name)) == 10


def test_a_search_that_matches_nothing_says_so_and_offers_everything(
    many_datasets,
) -> None:
    html = many_datasets.get("/", params={"q": "zzz"}).text

    assert _listed(html) == []
    assert 'data-testid="dataset-search-empty"' in html
    assert "No datasets match &ldquo;zzz&rdquo;" in html


def test_a_page_beyond_the_last_shows_the_last(many_datasets) -> None:
    html = many_datasets.get("/", params={"page": 99}).text

    assert len(_listed(html)) == 6
    assert "Page 2 of 2" in html


def test_the_search_asks_the_server_and_records_the_address(many_datasets) -> None:
    html = many_datasets.get("/").text

    assert 'hx-get="/"' in html
    assert 'hx-trigger="input changed delay:300ms, search"' in html
    assert 'hx-push-url="true"' in html
