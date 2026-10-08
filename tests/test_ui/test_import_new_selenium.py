"""The New Dataset screen's repository section answers in place, in a browser.

The route is tested without a browser. What only a browser shows is whether
the section is on the screen and whether htmx sends the form with the button
that was pressed. The list sent here is one the application refuses before
fetching anything: no repository is contacted and no dataset is saved.
"""

from __future__ import annotations

import pytest
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions
from selenium.webdriver.support.ui import WebDriverWait

from metaseed.ui.datasets import MAX_IMPORTED_AT_ONCE
from tests.test_ui.test_selenium import (  # noqa: F401
    BASE_URL,
    browser,
    click_button,
    server,
)

pytestmark = pytest.mark.selenium


def _visible(driver, test_id: str):
    return WebDriverWait(driver, 10).until(
        expected_conditions.visibility_of_element_located(
            (By.CSS_SELECTOR, f"[data-testid='{test_id}']")
        )
    )


def test_a_repository_button_sends_the_list_and_the_answer_appears(browser) -> None:  # noqa: F811
    browser.get(BASE_URL)
    click_button(browser, "btn-new-dataset")

    _visible(browser, "import-new-values").send_keys(
        "\n".join(f"PRJEB{n}" for n in range(MAX_IMPORTED_AT_ONCE + 1))
    )
    click_button(browser, "btn-import-new-ena-import")

    assert str(MAX_IMPORTED_AT_ONCE) in _visible(browser, "import-problem").text
