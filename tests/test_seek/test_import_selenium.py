"""Drive a real SEEK through the FAIR Data Station import of a metaseed export.

The rest of the SEEK suite stops at the API: it provisions Sample Types, syncs a
dataset, and confirms SEEK's own reader can parse what we emit. None of that
exercises the path a user actually takes -- uploading the exported ``.ttl`` on a
project's import page -- which is a multipart form behind session auth and CSRF,
reachable by a browser and not by the API token.

Marked ``selenium`` and ``network``; skipped unless pointed at an instance::

    SEEK_URL=http://localhost:3000 \
    SEEK_LOGIN=admin SEEK_PASSWORD=... \
        uv run pytest tests/test_seek/test_import_selenium.py -m "selenium and network"

The import runs as a background job, so SEEK must have its workers running
(``seek-workers`` in the docker compose) or the status never leaves "in progress".
"""

from __future__ import annotations

import os
import time
import uuid

import pytest

pytest.importorskip("selenium")
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

pytestmark = [pytest.mark.selenium, pytest.mark.network]

IMPORT_TIMEOUT = 180


def _settings() -> tuple[str, str, str]:
    """The instance and browser login to drive, or skip."""
    url = os.environ.get("SEEK_URL")
    login = os.environ.get("SEEK_LOGIN")
    password = os.environ.get("SEEK_PASSWORD")
    if not (url and login and password):
        pytest.skip("set SEEK_URL, SEEK_LOGIN and SEEK_PASSWORD to run the import test")
    return url.rstrip("/"), login, password


@pytest.fixture
def driver():
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--window-size=1400,1200")
    d = webdriver.Chrome(options=options)
    d.set_page_load_timeout(60)
    try:
        yield d
    finally:
        d.quit()


def _exported_dataset(tmp_path, external_id: str):
    """Write a small ISA dataset out as FAIR Data Station RDF.

    The external identifier is unique per run: SEEK refuses a second import of
    the same one into a project, which would otherwise make this pass once and
    fail forever after.
    """
    from metaseed import MetaseedClient
    from metaseed.seek.fairds import to_fair_data_station_rdf

    client = MetaseedClient("isa", "1.0")
    investigation = client.create_entity(
        "Investigation",
        {"identifier": external_id, "title": f"metaseed import {external_id}"},
        skip_validation=True,
    )
    study = client.create_entity(
        "Study",
        {"identifier": f"{external_id}-STU", "title": "imported study"},
        parent_id=investigation.id,
        skip_validation=True,
    )
    client.create_entity(
        "Sample", {"name": "imported-sample"}, parent_id=study.id, skip_validation=True
    )

    rdf = to_fair_data_station_rdf(client)
    path = tmp_path / f"{external_id}.ttl"
    path.write_bytes(rdf if isinstance(rdf, bytes) else rdf.encode())
    return path


def _log_in(driver, url: str, login: str, password: str) -> None:
    driver.get(f"{url}/login")
    WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.ID, "login")))
    driver.find_element(By.ID, "login").send_keys(login)
    driver.find_element(By.ID, "password").send_keys(password)
    driver.find_element(By.ID, "login_button").click()
    # SEEK confirms with a flash message and leaves ``login`` in the URL, so the
    # path alone does not tell success from a rejected form.
    WebDriverWait(driver, 30).until(
        lambda d: (
            "successfully logged in" in d.page_source
            or "Invalid username/password" in d.page_source
        )
    )
    assert "Invalid username/password" not in driver.page_source, "login was rejected"


def _first_project_id(driver, url: str) -> str:
    """The id of a real project, not an action link like ``guided_create``.

    The project list mixes both, so a plain first-link match landed on
    ``/projects/guided_create`` and the import page reported no such project.
    """
    driver.get(f"{url}/projects")
    WebDriverWait(driver, 30).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "a[href*='/projects/']"))
    )
    for a in driver.find_elements(By.CSS_SELECTOR, "a[href*='/projects/']"):
        tail = (a.get_attribute("href") or "").rstrip("/").split("/")[-1]
        if tail.isdigit():
            return tail
    raise AssertionError("no numeric project id on the projects page")


def test_an_exported_dataset_imports_through_the_project_page(driver, tmp_path) -> None:
    url, login, password = _settings()
    external_id = f"INV-sel-{uuid.uuid4().hex[:8]}"
    ttl = _exported_dataset(tmp_path, external_id)

    _log_in(driver, url, login, password)
    project_id = _first_project_id(driver, url)

    driver.get(f"{url}/projects/{project_id}/import_from_fairdata_station")
    upload = WebDriverWait(driver, 30).until(
        EC.presence_of_element_located((By.ID, "datastation_data"))
    )
    upload.send_keys(str(ttl))
    driver.find_element(By.NAME, "commit").click()

    # SEEK stays on the import page and shows a status panel rather than
    # redirecting; a refused file is reported here too.
    WebDriverWait(driver, 30).until(
        lambda d: (
            external_id in d.page_source
            or "Unable to find" in d.page_source
            or "No file was submitted" in d.page_source
        )
    )
    assert "Unable to find" not in driver.page_source, driver.page_source[:400]
    assert "No file was submitted" not in driver.page_source

    # The import is a background job: the panel reads "Queued" and the worker
    # moves it to "Completed". Poll the status endpoint, which is what SEEK's own
    # page refreshes against, until it settles.
    deadline = time.time() + IMPORT_TIMEOUT
    status = ""
    while time.time() < deadline:
        # The status panel is rendered on the import page itself; the bare
        # status route needs an upload_id and 404s without one.
        driver.get(f"{url}/projects/{project_id}/import_from_fairdata_station")
        page = driver.page_source
        if external_id in page and "Completed" in page:
            status = "Completed"
            break
        if "Failed" in page or "Error" in page:
            status = page
            break
        time.sleep(5)
    assert status == "Completed", (
        f"import of {external_id} did not complete within {IMPORT_TIMEOUT}s "
        f"(is the seek-workers container running?); last status: {status[:300]}"
    )
