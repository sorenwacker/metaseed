"""End-to-end Selenium tests for the SEEK export journey.

Drives a real browser + live server through the full flow the SEEK integration
adds:

1. configure the SEEK plugin on the Plugins page — the API key is stored but the
   secret is never rendered back into the form (masked, "leave blank to keep");
2. load a real ISA dataset and confirm the ``/seek`` page renders role-aware
   context with an enabled download and the configured instance link, and that
   the download endpoint serves valid FAIR Data Station Turtle RDF;
3. set an entity's SEEK ``role`` in the Spec Builder and confirm it serializes
   to the profile YAML.

The server runs with ``XDG_DATA_HOME`` pointed at a throwaway dir so writing SEEK
config does not touch the developer's real ``settings.json``.
"""

import os
import socket
import subprocess
import tempfile
import time

import pytest
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait

# Drives a real browser + server; excluded from the pre-push hook for speed.
pytestmark = pytest.mark.selenium

PORT = 8766
BASE_URL = f"http://127.0.0.1:{PORT}"


@pytest.fixture(scope="module")
def server():
    """Start a hermetic metaseed server (isolated settings dir) for the module."""
    cwd = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    data_dir = tempfile.mkdtemp(prefix="metaseed-seek-e2e-")
    env = {**os.environ, "XDG_DATA_HOME": data_dir}  # redirect settings.json

    proc = subprocess.Popen(
        ["uv", "run", "uvicorn", "metaseed.ui.app:app", "--port", str(PORT)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        cwd=cwd,
        env=env,
    )

    for _ in range(30):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        connected = sock.connect_ex(("127.0.0.1", PORT)) == 0
        sock.close()
        if connected:
            break
        time.sleep(0.5)
    else:
        output = proc.stdout.read().decode() if proc.stdout else ""
        proc.terminate()
        raise RuntimeError(f"Server failed to start: {output}")

    time.sleep(0.5)
    yield proc
    proc.terminate()
    proc.wait()


@pytest.fixture
def driver(server):
    """Headless Chrome driver."""
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")

    driver = webdriver.Chrome(options=options)
    driver.implicitly_wait(5)
    yield driver
    driver.quit()


def _wait(driver, selector, timeout=10):
    """Wait for a CSS selector to be present and return the element."""
    return WebDriverWait(driver, timeout).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
    )


def _configure_seek(driver, url="http://localhost:3001", api_key="SECRET-KEY-XYZ"):
    """Fill and submit the SEEK plugin config form; return once the row swaps."""
    driver.get(f"{BASE_URL}/settings")
    _wait(driver, '[data-testid="config-seek"]')
    url_input = driver.find_element(By.CSS_SELECTOR, '[data-testid="config-seek-url"]')
    url_input.clear()
    url_input.send_keys(url)
    if api_key is not None:
        key_input = driver.find_element(
            By.CSS_SELECTOR, '[data-testid="config-seek-api_key"]'
        )
        key_input.clear()
        key_input.send_keys(api_key)
    driver.find_element(
        By.CSS_SELECTOR, '[data-testid="config-seek"] button[type="submit"]'
    ).click()
    # HTMX swaps #adapter-seek; the URL prefills back once persisted.
    WebDriverWait(driver, 10).until(
        lambda d: d.find_element(
            By.CSS_SELECTOR, '[data-testid="config-seek-url"]'
        ).get_attribute("value")
        == url
    )


def test_configure_seek_plugin_masks_secret(driver):
    """Saving a SEEK API key persists it but never renders it back to the form."""
    _configure_seek(driver, api_key="SECRET-KEY-XYZ")

    # The secret must not appear anywhere in the returned HTML, and its input is
    # blank with a "leave blank to keep" hint; the URL (non-secret) prefills back.
    assert "SECRET-KEY-XYZ" not in driver.page_source
    assert "leave blank to keep" in driver.page_source
    key_input = driver.find_element(
        By.CSS_SELECTOR, '[data-testid="config-seek-api_key"]'
    )
    assert key_input.get_attribute("value") == ""

    # Persists across a full page reload (stored in settings.json).
    driver.get(f"{BASE_URL}/settings")
    _wait(driver, '[data-testid="config-seek"]')
    assert "SECRET-KEY-XYZ" not in driver.page_source
    assert "leave blank to keep" in driver.page_source
    url_input = driver.find_element(By.CSS_SELECTOR, '[data-testid="config-seek-url"]')
    assert url_input.get_attribute("value") == "http://localhost:3001"
    # The "Open SEEK →" action link is offered once the plugin is enabled.
    assert driver.find_elements(By.CSS_SELECTOR, '[data-testid="link-seek-action"]')


def test_seek_export_end_to_end(driver):
    """Configure SEEK, load a dataset, and export valid ISA RDF from /seek."""
    _configure_seek(driver)

    # One GET seeds a real ISA dataset and pins the active profile to isa.
    driver.get(f"{BASE_URL}/load-example/isa/1.0")

    driver.get(f"{BASE_URL}/seek")
    # Download is enabled (not the disabled placeholder), the sync panel is shown,
    # and the configured instance URL appears.
    export_link = _wait(driver, '[data-testid="seek-export-rdf"]')
    assert export_link is not None
    assert driver.find_elements(By.CSS_SELECTOR, '[data-testid="seek-sync-form"]')
    assert not driver.find_elements(
        By.CSS_SELECTOR, '[data-testid="seek-export-disabled"]'
    )
    assert "isa" in driver.page_source  # active profile shown
    assert "Investigation" in driver.page_source  # exportable type listed
    assert "localhost:3001" in driver.page_source

    # The download endpoint returns valid FAIR Data Station Turtle (fetched in the
    # browser session so it exercises the same route the button hits).
    body = driver.execute_async_script(
        """
        const cb = arguments[arguments.length - 1];
        fetch('/seek/isa-rdf')
            .then(r => r.text())
            .then(cb)
            .catch(e => cb('ERR:' + e));
        """
    )
    assert "@prefix" in body  # Turtle
    assert "jerm:Investigation" in body  # the ISA Investigation was emitted


def test_spec_builder_seek_role_serializes_to_yaml(driver):
    """Setting an entity's SEEK role via the editor writes it to the profile.

    Guards against a regression where the Apply handler (``updateEntity`` in
    spec-builder.js) hand-built the PUT body and dropped ``seek_role``, so the
    dropdown silently did nothing through the real UI.
    """
    driver.get(f"{BASE_URL}/spec-builder/reset")
    driver.get(f"{BASE_URL}/spec-builder/new")
    _wait(driver, "#editor-content")

    # Create an entity, then open its editor the way the entity list does.
    created = driver.execute_async_script(
        """
        const cb = arguments[arguments.length - 1];
        fetch('/spec-builder/entity', {
            method: 'POST',
            headers: {'Content-Type': 'application/x-www-form-urlencoded'},
            body: 'name=Sampling'
        }).then(r => cb(r.ok ? 'ok' : 'err:' + r.status)).catch(e => cb('err:' + e));
        """
    )
    assert created == "ok"
    driver.execute_script("selectEntity('Sampling')")

    # The editor shows the SEEK role dropdown; choose a role and click Apply.
    role_select = _wait(driver, '[data-testid="entity-seek-role"]')
    Select(role_select).select_by_visible_text("Sample")
    driver.find_element(
        By.CSS_SELECTOR, "#entity-details-form button[type='submit']"
    ).click()

    # The chosen role is serialized into the profile YAML preview.
    driver.get(f"{BASE_URL}/spec-builder/preview")
    WebDriverWait(driver, 10).until(lambda d: "role: Sample" in d.page_source)
    assert "role: Sample" in driver.page_source
