"""An entity's field list in the explorer panel scrolls with the panel.

The list was its own scroll box, capped at 400 px inside a panel that already
scrolls, so an entity with many fields showed a few of them in a small window
and left the rest of the panel blank.
"""

from __future__ import annotations

import pytest
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select, WebDriverWait

from tests.test_ui.test_selenium import (  # noqa: F401
    BASE_URL,
    browser,
    server,
)

pytestmark = pytest.mark.selenium

_OPEN_THE_LARGEST_ENTITY = """
const nodes = ERD.getNodes().get().filter(n => n.data && n.data.fields);
nodes.sort((a, b) => b.data.fields.length - a.data.fields.length);
selectEntity(nodes[0].id);
return nodes[0].data.fields.length;
"""

_LIST = """
const list = document.querySelector('#editor-content .field-diff-list');
return {scroll: list.scrollHeight, client: list.clientHeight};
"""


def test_the_field_list_is_not_a_scroll_box_of_its_own(browser) -> None:  # noqa: F811
    browser.get(f"{BASE_URL}/explore/")
    Select(browser.find_element(By.ID, "base-profile")).select_by_value("miappe")
    browser.find_element(By.ID, "compare-btn").click()
    WebDriverWait(browser, 20).until(
        lambda d: d.execute_script(
            "return Boolean(typeof ERD !== 'undefined' && ERD.getNetwork() && ERD.getNodes().length)"
        )
    )

    fields = browser.execute_script(_OPEN_THE_LARGEST_ENTITY)
    WebDriverWait(browser, 5).until(
        lambda d: d.find_element(
            By.CSS_SELECTOR, "#editor-content .field-diff-list"
        ).is_displayed()
    )
    size = browser.execute_script(_LIST)

    assert fields > 10, (
        "the test needs an entity with more fields than fit in a small box"
    )
    assert size["scroll"] <= size["client"] + 1, (
        f"the {fields} fields scroll inside their own box of {size['client']} px"
    )
