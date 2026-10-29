"""The hierarchical layout is the containment tree; references are drawn over it.

Laying out by every edge pulled a referenced node out of its subtree: vis.js's
directed sort ranks nodes by all edges, so a dashed reference from a Sample to
a Source decided the Source's row and column. Only parent-child edges place a
node now. See docs/guides/embedding-the-graph.md.
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

PORT = 8087
BASE_URL = f"http://127.0.0.1:{PORT}"


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    """The metaseed UI on its own port, with throwaway dataset storage."""
    cwd = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    datasets_dir = tmp_path_factory.mktemp("tree-layout-datasets")
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


#: Each node's position, tree depth and containment parent.
_LAYOUT = """
var out = {};
graphData.nodes.get().forEach(function(n) {
    var b = graphNetwork.body.nodes[n.id];
    out[String(n.id)] = {x: b.x, y: b.y, level: n.level, parent: null};
});
graphData.edges.get().forEach(function(e) {
    if (!e.dashes && out[String(e.to)]) out[String(e.to)].parent = String(e.from);
});
return out;
"""


def _hierarchical(driver) -> dict:
    driver.get(f"{BASE_URL}/load-example/isa/1.0")
    driver.get(f"{BASE_URL}/dataset/isa-1_0-example/edit")
    if "hidden" in driver.find_element(By.ID, "graph-container").get_attribute("class"):
        driver.find_element(By.CSS_SELECTOR, "[data-testid='btn-view-graph']").click()
    WebDriverWait(driver, 10).until(
        lambda d: d.execute_script(
            "return typeof graphNetwork !== 'undefined' && graphNetwork"
            " && graphData.nodes.length > 0;"
        )
    )
    assert driver.execute_script(
        "return graphData.edges.get().some(function(e) { return e.dashes; });"
    ), "the example needs a reference edge for this test to mean anything"
    driver.find_element(By.ID, "graph-layout-btn").click()
    time.sleep(1)
    return driver.execute_script(_LAYOUT)


def test_a_row_is_a_tree_depth(browser) -> None:
    layout = _hierarchical(browser)
    rows: dict[int, set[float]] = {}
    for node in layout.values():
        rows.setdefault(node["level"], set()).add(round(node["y"]))
    assert all(len(ys) == 1 for ys in rows.values()), rows
    ordered = [next(iter(rows[level])) for level in sorted(rows)]
    assert ordered == sorted(ordered), "a deeper record sits above a shallower one"


def test_a_subtree_keeps_its_own_columns(browser) -> None:
    layout = _hierarchical(browser)
    span = {i: [n["x"], n["x"]] for i, n in layout.items()}
    for i in sorted(layout, key=lambda i: -layout[i]["level"]):
        parent = layout[i]["parent"]
        if parent:
            span[parent][0] = min(span[parent][0], span[i][0])
            span[parent][1] = max(span[parent][1], span[i][1])
    siblings: dict[str, list[str]] = {}
    for i, n in layout.items():
        siblings.setdefault(n["parent"] or "", []).append(i)
    overlapping = [
        (a, b)
        for group in siblings.values()
        for a in group
        for b in group
        if a < b and span[a][0] <= span[b][1] and span[b][0] <= span[a][1]
    ]
    assert not overlapping, f"subtrees share columns: {overlapping[:3]}"
