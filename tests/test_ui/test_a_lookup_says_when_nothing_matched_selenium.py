"""A lookup that finds nothing says so; it never closes or goes blank (261126).

Typing "tomato" into a field showed nothing at all: the inline suggestions of a
reference field returned without a dropdown on no match, the search dialog of
such a field emptied its results, and a failed request only reached the
console. The ontology dialog said "No terms found" without naming the ontology,
so a field restricted to NCBITaxon read as a broken lookup.

The page's own functions run in a real browser against a stubbed ``fetch``, so
each case (no match, request failed) is fixed rather than depending on OLS.
See docs/guides/ontology-lookup.md, *When nothing is found*.
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

_ANSWER_EMPTY = """
window.fetch = function() {
    return Promise.resolve(new Response(JSON.stringify({results: [], not_asked: []}),
        {headers: {'Content-Type': 'application/json'}}));
};
"""

_FAIL = """
window.fetch = function() { return Promise.reject(new TypeError('Failed to fetch')); };
"""

_ADD_INPUT = """
var input = document.createElement('input');
input.id = 'probe-input';
document.body.appendChild(input);
var results = document.getElementById('ontology-modal-results');
if (!results) {
    results = document.createElement('div');
    results.id = 'ontology-modal-results';
    document.body.appendChild(results);
}
"""


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    """The metaseed UI on its own port, with throwaway dataset storage."""
    cwd = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    env = {
        **os.environ,
        "METASEED_DATASETS_DIR": str(tmp_path_factory.mktemp("lookup-datasets")),
    }
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
def page(server):
    """A dataset page, which loads lookup.js and the lookup dialog."""
    _ = server
    options = Options()
    for arg in ("--headless=new", "--window-size=1920,1200", "--no-sandbox"):
        options.add_argument(arg)
    driver = webdriver.Chrome(options=options)
    driver.get(f"{BASE_URL}/load-example/miappe/1.2")
    driver.get(f"{BASE_URL}/dataset/miappe-1_2-example/edit")
    WebDriverWait(driver, 10).until(
        lambda d: d.execute_script("return typeof loadModalResults === 'function'")
    )
    driver.execute_script(_ADD_INPUT)
    yield driver
    driver.quit()


def _visible_text(driver, selector: str) -> str:
    WebDriverWait(driver, 5).until(
        lambda d: any(
            e.is_displayed() and e.text.strip()
            for e in d.find_elements(By.CSS_SELECTOR, selector)
        )
    )
    return " ".join(
        e.text
        for e in driver.find_elements(By.CSS_SELECTOR, selector)
        if e.is_displayed()
    )


def test_inline_suggestions_say_nothing_matched(page) -> None:
    page.execute_script(_ANSWER_EMPTY)
    page.execute_script(
        "fetchLookupSuggestions(document.getElementById('probe-input'), 'Study', 'tomato');"
    )

    assert 'No Study matches "tomato"' in _visible_text(page, ".autocomplete-dropdown")


def test_inline_suggestions_say_the_lookup_failed(page) -> None:
    page.execute_script(_FAIL)
    page.execute_script(
        "fetchLookupSuggestions(document.getElementById('probe-input'), 'Study', 'tomato');"
    )

    assert "Lookup failed" in _visible_text(page, ".autocomplete-dropdown")


def test_the_entity_dialog_says_nothing_matched(page) -> None:
    page.execute_script(_ANSWER_EMPTY)
    page.execute_script(
        "document.getElementById('lookup-modal').classList.remove('hidden');"
        "loadModalResults('Study', 'tomato');"
    )

    assert 'No Study matches "tomato"' in _visible_text(page, "#lookup-modal-results")


def test_the_ontology_dialog_names_the_ontology_it_searched(page) -> None:
    page.execute_script(_ANSWER_EMPTY)
    page.execute_script(
        "ontologyModalOntologies = 'NCBITaxon'; loadOntologyModalResults('tomato');"
    )

    assert 'No terms found for "tomato" in NCBITaxon' in _visible_text(
        page, "#ontology-modal-results"
    )


def test_the_ontology_dialog_without_a_restriction_says_any_ontology(page) -> None:
    page.execute_script(_ANSWER_EMPTY)
    page.execute_script(
        "ontologyModalOntologies = null; loadOntologyModalResults('tomato');"
    )

    assert 'No terms found for "tomato" in any ontology' in _visible_text(
        page, "#ontology-modal-results"
    )
