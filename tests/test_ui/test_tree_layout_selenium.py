"""The Tree button lays a specification out as its containment tree, in a browser.

Where the button is and which script defines the toggle is gated without a
browser (test_tree_layout_is_shared.py). That the graph actually rearranges is
the script's doing against a live vis-network, which only a browser runs.
"""

from __future__ import annotations

import pytest
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select, WebDriverWait

from tests.test_ui.test_selenium import (  # noqa: F401
    BASE_URL,
    browser,
    click_button,
    server,
)

pytestmark = pytest.mark.selenium

_LEVELS = """
const network = ERD.getNetwork();
const positions = network.getPositions();
const ids = Object.keys(positions);
const ys = ids.map(id => Math.round(positions[id].y));
const top = ids.reduce((a, b) => positions[a].y <= positions[b].y ? a : b);
const node = ERD.getNodes().get(top) || ERD.getNodes().get(Number(top));
return {nodes: ids.length, levels: new Set(ys).size, top: String(node.label)};
"""


def test_tree_puts_the_root_on_top_and_layout_leaves_the_tree(browser) -> None:  # noqa: F811
    browser.get(f"{BASE_URL}/explore/")
    Select(browser.find_element(By.ID, "base-profile")).select_by_value("miappe")
    browser.find_element(By.ID, "compare-btn").click()
    WebDriverWait(browser, 20).until(
        lambda d: d.execute_script(
            "return Boolean(typeof ERD !== 'undefined' && ERD.getNetwork() && ERD.getNodes().length)"
        )
    )

    click_button(browser, "btn-tree-layout")

    tree = browser.execute_script(_LEVELS)
    button = browser.find_element(By.ID, "btn-hierarchical")
    assert "active" in button.get_attribute("class")
    assert tree["levels"] < tree["nodes"], (
        "a tree shares levels; a free arrangement does not"
    )
    assert "Investigation" in tree["top"]

    browser.execute_script("autoLayout()")

    assert "active" not in button.get_attribute("class")
