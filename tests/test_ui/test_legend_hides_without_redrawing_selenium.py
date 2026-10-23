"""Unticking a legend type hides its nodes without redrawing the graph.

The legend once cleared the canvas and added the remaining nodes back, so
every click laid the whole graph out again from scratch. A hidden type now
stays in the graph, out of sight and out of the layout simulation: the
visible nodes keep their places, and the hidden ones come back where they were.
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

PORT = 8086
BASE_URL = f"http://127.0.0.1:{PORT}"

#: How far, in graph units, a node may be from where it was and still count
#: as not moved; a fresh layout scatters nodes by hundreds.
_STILL = 1.0

#: Every node in the graph with its position; getPositions() leaves hidden
#: nodes out, so it cannot tell a hidden node from a removed one.
_POSITIONS = """
var out = {};
graphData.nodes.getIds().forEach(function(id) {
    var n = graphNetwork.body.nodes[id];
    if (n) out[String(id)] = {x: n.x, y: n.y};
});
return out;
"""


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    """The metaseed UI on its own port, with throwaway dataset storage."""
    cwd = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    datasets_dir = tmp_path_factory.mktemp("legend-hides-datasets")
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


def _open_the_graph(driver) -> None:
    driver.get(f"{BASE_URL}/load-example/miappe/1.2")
    driver.get(f"{BASE_URL}/dataset/miappe-1_2-example/edit")
    WebDriverWait(driver, 10).until(
        lambda d: d.find_element(
            By.CSS_SELECTOR, "[data-testid='btn-view-graph']"
        ).is_displayed()
    )
    if "hidden" in driver.find_element(By.ID, "graph-container").get_attribute("class"):
        driver.find_element(By.CSS_SELECTOR, "[data-testid='btn-view-graph']").click()
    WebDriverWait(driver, 10).until(
        lambda d: d.execute_script(
            "return typeof graphNetwork !== 'undefined' && graphNetwork"
            " && graphData.nodes.length > 0;"
        )
    )
    # A settled graph, so that any later movement is the legend's doing.
    driver.find_element(By.CSS_SELECTOR, "[data-testid='btn-graph-physics']").click()


def _a_type_with_nodes(driver) -> tuple[str, list[str]]:
    # The type with the fewest nodes, so most of the graph stays visible.
    return driver.execute_script(
        """
        var byType = {};
        allGraphNodes.forEach(function(n) {
            (byType[n.group] = byType[n.group] || []).push(String(n.id));
        });
        var best = null;
        Object.keys(byType).forEach(function(t) {
            if (!best || byType[t].length < byType[best].length) best = t;
        });
        return [best, byType[best]];
        """
    )


def _toggle(driver, group: str) -> None:
    item = driver.find_element(
        By.CSS_SELECTOR, f".graph-legend-item[data-type='{group}'] input"
    )
    WebDriverWait(driver, 5).until(lambda _d: item.is_displayed())
    item.click()


def _moved(before: dict, after: dict, ids) -> list[str]:
    return [
        i
        for i in ids
        if abs(before[i]["x"] - after[i]["x"]) > _STILL
        or abs(before[i]["y"] - after[i]["y"]) > _STILL
    ]


def test_unticking_a_type_leaves_the_rest_where_it_was(browser) -> None:
    _open_the_graph(browser)
    group, hidden_ids = _a_type_with_nodes(browser)
    before = browser.execute_script(_POSITIONS)
    visible_ids = [i for i in before if i not in hidden_ids]

    _toggle(browser, group)
    after = browser.execute_script(_POSITIONS)

    assert set(after) == set(before), (
        "the hidden type's nodes were removed from the graph"
    )
    assert not _moved(before, after, visible_ids), (
        "unticking a type laid the graph out again"
    )


def test_a_hidden_type_takes_no_part_in_the_layout(browser) -> None:
    _open_the_graph(browser)
    group, hidden_ids = _a_type_with_nodes(browser)
    _toggle(browser, group)
    # Physics back on: the hidden nodes must still neither move nor push.
    browser.find_element(By.CSS_SELECTOR, "[data-testid='btn-graph-physics']").click()

    simulated = browser.execute_script(
        "return graphNetwork.physics.physicsBody.physicsNodeIndices.map(String);"
    )
    held = browser.execute_script(_POSITIONS)
    time.sleep(2)
    later = browser.execute_script(_POSITIONS)

    assert not set(hidden_ids) & set(simulated), (
        "hidden nodes are still in the simulation"
    )
    assert not _moved(held, later, hidden_ids), "hidden nodes kept moving"


def test_ticking_a_type_again_shows_it_where_it_was(browser) -> None:
    _open_the_graph(browser)
    group, hidden_ids = _a_type_with_nodes(browser)
    _toggle(browser, group)
    held = browser.execute_script(_POSITIONS)

    _toggle(browser, group)
    shown = browser.execute_script(_POSITIONS)

    assert all(i in shown for i in hidden_ids), "the type did not come back"
    assert not _moved(held, shown, hidden_ids), "the type came back somewhere else"
