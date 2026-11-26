"""The ERD redraws an entity when its fields change, without a reload (261126).

The diagram reads an entity map the page inlines once at load. Adding a field
posted the form and swapped the editor panel, but the map and the drawn box
kept the old fields until the page was reloaded.
See docs/guides/spec-builder.md, *Adding Fields via the UI*.
"""

from __future__ import annotations

import os
import socket
import subprocess
import time

import pytest
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

pytestmark = pytest.mark.selenium

PORT = 8087
BASE_URL = f"http://127.0.0.1:{PORT}"

_CREATE = """
const cb = arguments[arguments.length - 1];
fetch('/spec-builder/entity', {
    method: 'POST',
    headers: {'Content-Type': 'application/x-www-form-urlencoded'},
    body: 'name=' + arguments[0]
}).then(r => cb(r.ok ? 'ok' : 'err:' + r.status)).catch(e => cb('err:' + e));
"""

_LABEL = "const n = getNetwork(); return n ? n.body.data.nodes.get(arguments[0]).label : null;"
_POSITION = "return getNetwork().getPositions([arguments[0]])[arguments[0]];"


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    """The metaseed UI on its own port, with throwaway storage."""
    cwd = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    env = {**os.environ, "METASEED_DATASETS_DIR": str(tmp_path_factory.mktemp("erd"))}
    proc = subprocess.Popen(
        ["uv", "run", "uvicorn", "metaseed.ui.app:app", "--port", str(PORT)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        cwd=cwd,
        env=env,
    )
    for _ in range(30):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(1)
            if sock.connect_ex(("127.0.0.1", PORT)) == 0:
                break
        time.sleep(0.5)
    else:
        proc.terminate()
        raise RuntimeError("server failed to start")
    yield proc
    proc.terminate()
    proc.wait()


@pytest.fixture
def builder(server):
    """The spec builder with two entities drawn and Sampling's editor open."""
    _ = server
    options = Options()
    for arg in ("--headless=new", "--window-size=1920,1200", "--no-sandbox"):
        options.add_argument(arg)
    driver = webdriver.Chrome(options=options)
    driver.get(f"{BASE_URL}/spec-builder/reset")
    driver.get(f"{BASE_URL}/spec-builder/new")
    for name in ("Sampling", "Site"):
        assert driver.execute_async_script(_CREATE, name) == "ok"
    # A reload draws both, as a person arriving at the page would see them.
    driver.get(f"{BASE_URL}/spec-builder")
    WebDriverWait(driver, 10).until(lambda d: d.execute_script(_LABEL, "Sampling"))
    driver.execute_script("selectEntity('Sampling')")
    # Sampling's own editor, not whatever the panel held before the swap: a
    # form typed into while htmx replaces it loses the submission.
    WebDriverWait(driver, 10).until(
        lambda d: d.find_elements(
            By.CSS_SELECTOR, '#editor-content script[data-entity-fields="Sampling"]'
        )
    )
    WebDriverWait(driver, 10).until(
        EC.visibility_of_element_located(
            (By.CSS_SELECTOR, "form.add-field-inline input[name='name']")
        )
    )
    yield driver
    driver.quit()


def _add_field(driver, name: str, field_type: str = "string") -> None:
    form = driver.find_element(By.CSS_SELECTOR, "form.add-field-inline")
    form.find_element(By.NAME, "name").send_keys(name)
    form.find_element(By.NAME, "field_type").send_keys(field_type)
    form.find_element(By.CSS_SELECTOR, "button[type='submit']").click()


def test_an_added_field_appears_in_the_entity_box(builder) -> None:
    _add_field(builder, "collection_date")

    WebDriverWait(builder, 5).until(
        lambda d: "collection_date" in (d.execute_script(_LABEL, "Sampling") or "")
    )
    assert "collection_date: string" in builder.execute_script(_LABEL, "Sampling")


def test_the_other_entities_keep_their_place(builder) -> None:
    before = builder.execute_script(_POSITION, "Site")
    _add_field(builder, "depth", "integer")
    WebDriverWait(builder, 5).until(
        lambda d: "depth" in d.execute_script(_LABEL, "Sampling")
    )

    after = builder.execute_script(_POSITION, "Site")
    assert abs(after["x"] - before["x"]) < 1 and abs(after["y"] - before["y"]) < 1


def test_a_removed_field_leaves_the_entity_box(builder) -> None:
    _add_field(builder, "temporary")
    WebDriverWait(builder, 5).until(
        lambda d: "temporary" in d.execute_script(_LABEL, "Sampling")
    )
    # htmx activates swapped-in buttons after the swap event the diagram
    # follows; a click before that is a plain click that sends nothing.
    WebDriverWait(builder, 5).until(
        lambda d: d.execute_script(
            "const b = document.querySelector('#editor-content [hx-delete*=\"/field/\"]');"
            "return !!(b && b['htmx-internal-data'] && b['htmx-internal-data'].initHash);"
        )
    )
    builder.execute_script(
        "window.confirm = () => true;"
        "document.querySelector('#editor-content [hx-delete*=\"/field/\"]').click();"
    )

    WebDriverWait(builder, 5).until(
        lambda d: "temporary" not in d.execute_script(_LABEL, "Sampling")
    )
    assert "(no fields)" in builder.execute_script(_LABEL, "Sampling")
