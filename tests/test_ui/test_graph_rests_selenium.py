"""The open graph must stop fetching while its tab is in the background.

The source gate for this is tests/test_ui/test_the_graph_rests_while_hidden.py;
this is the behaviour itself, in a real browser: a page that keeps polling is
visible here as requests that keep arriving, which no source scan can show.

Chrome does not let a test background a tab, so visibility is overridden on the
document and the event dispatched — which is exactly what the page listens to.
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
from selenium.webdriver.support.ui import WebDriverWait

pytestmark = pytest.mark.selenium

PORT = 8084
BASE_URL = f"http://127.0.0.1:{PORT}"

#: Long enough for several 2 s polls, short enough to keep the test quick.
_WATCH_SECONDS = 5

#: Counts every /api/graph request the page makes, so the test measures the
#: traffic itself rather than a flag the page sets about its own intentions.
_COUNT_FETCHES = """
window.__graphFetches = 0;
var realFetch = window.fetch;
window.fetch = function(resource, init) {
    var url = typeof resource === 'string' ? resource : (resource && resource.url) || '';
    if (url.indexOf('/api/graph') !== -1) window.__graphFetches++;
    return realFetch.apply(this, arguments);
};
"""

_SET_VISIBILITY = """
Object.defineProperty(document, 'visibilityState', {
    configurable: true,
    get: function() { return arguments.length, '%s'; }
});
Object.defineProperty(document, 'hidden', {
    configurable: true,
    get: function() { return '%s' === 'hidden'; }
});
document.dispatchEvent(new Event('visibilitychange'));
"""


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    """The metaseed UI on its own port, with throwaway dataset storage."""
    cwd = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    datasets_dir = tmp_path_factory.mktemp("graph-rests-datasets")
    env = {**os.environ, "METASEED_DATASETS_DIR": str(datasets_dir)}

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
        reachable = sock.connect_ex(("127.0.0.1", PORT)) == 0
        sock.close()
        if reachable:
            break
        time.sleep(0.5)
    else:
        output = proc.stdout.read().decode() if proc.stdout else ""
        proc.terminate()
        raise RuntimeError(f"Server failed to start. Output: {output}")

    time.sleep(0.5)
    yield proc
    proc.terminate()
    proc.wait()


@pytest.fixture
def browser(server):
    """Headless Chrome pointed at this module's server."""
    _ = server
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--window-size=1920,1200")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")

    driver = webdriver.Chrome(options=options)
    driver.implicitly_wait(5)
    yield driver
    driver.quit()


def _graph_fetches(driver) -> int:
    return int(driver.execute_script("return window.__graphFetches;"))


def _open_dataset_with_the_graph_showing(driver) -> None:
    # The bundled example gives the graph something to draw, and the dataset
    # page is where the Graph button lives; the entity form has neither.
    driver.get(f"{BASE_URL}/load-example/miappe/1.2")
    driver.get(f"{BASE_URL}/dataset/miappe-1_2-example/edit")
    WebDriverWait(driver, 10).until(
        lambda d: d.find_elements(By.CSS_SELECTOR, "[data-testid='btn-view-graph']")
    )
    container = driver.find_element(By.ID, "graph-container")
    if "hidden" in container.get_attribute("class"):
        driver.find_element(By.CSS_SELECTOR, "[data-testid='btn-view-graph']").click()
    WebDriverWait(driver, 10).until(
        lambda d: (
            "hidden"
            not in d.find_element(By.ID, "graph-container").get_attribute("class")
        )
    )


def test_a_visible_graph_keeps_itself_up_to_date(browser) -> None:
    """The counterpart: resting while hidden must not cost the live refresh."""
    _open_dataset_with_the_graph_showing(browser)
    browser.execute_script(_COUNT_FETCHES)

    time.sleep(_WATCH_SECONDS)

    assert _graph_fetches(browser) > 0, "a visible graph must still poll for changes"


def test_a_backgrounded_tab_stops_fetching(browser) -> None:
    _open_dataset_with_the_graph_showing(browser)
    browser.execute_script(_COUNT_FETCHES)
    browser.execute_script(_SET_VISIBILITY % ("hidden", "hidden"))
    browser.execute_script("window.__graphFetches = 0;")

    time.sleep(_WATCH_SECONDS)

    assert _graph_fetches(browser) == 0, (
        "a background tab kept reloading the dataset from disk every 2 seconds"
    )


def test_returning_to_the_tab_refreshes_and_resumes(browser) -> None:
    # The whole sequence, because "fetching resumes" is true of a page that
    # never stopped: it must rest first for resuming to mean anything.
    _open_dataset_with_the_graph_showing(browser)
    browser.execute_script(_COUNT_FETCHES)
    browser.execute_script(_SET_VISIBILITY % ("hidden", "hidden"))
    browser.execute_script("window.__graphFetches = 0;")

    time.sleep(_WATCH_SECONDS)
    assert _graph_fetches(browser) == 0, "the graph must rest while the tab is hidden"

    browser.execute_script(_SET_VISIBILITY % ("visible", "visible"))

    WebDriverWait(browser, 10).until(lambda d: _graph_fetches(d) > 0)

    time.sleep(_WATCH_SECONDS)
    assert _graph_fetches(browser) > 1, "polling must resume, not fetch once and stop"
