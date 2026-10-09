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

    # Reported: each button sat alone on its row and what it takes was pushed
    # to the far edge of the card, out of sight.
    button = _visible(browser, "btn-import-new-ena-import")
    hint = button.find_element(By.XPATH, "following-sibling::span")
    assert hint.is_displayed()
    gap = hint.rect["x"] - (button.rect["x"] + button.rect["width"])
    assert 0 <= gap <= 40, gap
    assert (
        abs(
            hint.rect["y"]
            + hint.rect["height"] / 2
            - button.rect["y"]
            - button.rect["height"] / 2
        )
        <= 6
    )

    _visible(browser, "import-new-values").send_keys(
        "\n".join(f"PRJEB{n}" for n in range(MAX_IMPORTED_AT_ONCE + 1))
    )
    click_button(browser, "btn-import-new-ena-import")

    assert str(MAX_IMPORTED_AT_ONCE) in _visible(browser, "import-problem").text


@pytest.mark.network
def test_an_import_fills_the_bar_and_announces_the_dataset(browser) -> None:  # noqa: F811
    """One real ENA study, end to end: the bar, the row and the toast are the
    page script's doing, which nothing short of a real import exercises."""
    browser.get(BASE_URL)
    click_button(browser, "btn-new-dataset")
    _visible(browser, "import-new-values").send_keys("PRJDA51199")
    click_button(browser, "btn-import-new-ena-import")

    bar = _visible(browser, "import-progress")
    assert bar.get_attribute("max") == "1"
    toast = WebDriverWait(browser, 120).until(
        expected_conditions.visibility_of_element_located(
            (By.CSS_SELECTOR, "#notification-container .notification-success")
        )
    )
    assert toast.text.startswith("Imported ")

    row = browser.find_element(By.CSS_SELECTOR, "[data-testid='import-row']")
    assert row.get_attribute("data-status") == "imported"
    assert bar.get_attribute("value") == "1"
    assert browser.find_element(By.ID, "import-progress-label").text == "1 of 1 done"
    link = row.find_element(By.CSS_SELECTOR, "[data-testid='import-dataset-link']")
    assert link.text in toast.text
