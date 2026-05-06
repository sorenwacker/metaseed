"""Selenium end-to-end tests demonstrating validation rules display.

Tests that validation rules are shown to users during validation,
and demonstrates creating entities with all fields filled.
"""

import socket
import subprocess
import time

import pytest
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from tests.test_ui.examples import INV_EXAMPLE

# Delay constants
FILL_DELAY = 0.1
CLICK_DELAY = 0.5

BASE_URL = "http://127.0.0.1:8082"


@pytest.fixture(scope="module")
def server():
    """Start the Metaseed server for testing."""
    from pathlib import Path

    cwd = Path(__file__).resolve().parent.parent.parent

    proc = subprocess.Popen(
        ["uv", "run", "uvicorn", "metaseed.ui.app:app", "--port", "8082"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        cwd=cwd,
    )

    # Wait for server to be ready
    max_attempts = 30
    for _ in range(max_attempts):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex(("127.0.0.1", 8082))
            sock.close()
            if result == 0:
                break
        except Exception:
            pass  # Keep trying until server starts
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
def browser(server):
    """Create a Chrome browser for testing."""
    _ = server
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--window-size=1920,1200")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")

    driver = webdriver.Chrome(options=options)
    driver.implicitly_wait(5)

    # Reset server state before each test
    import urllib.request

    try:
        req = urllib.request.Request(f"{BASE_URL}/reset", method="POST")
        urllib.request.urlopen(req, timeout=5)
    except Exception:
        pass  # Server reset is best-effort

    yield driver
    driver.quit()


def fill_field(driver, testid: str, value: str, trigger_change: bool = False):
    """Fill a form field by data-testid."""
    element = driver.find_element(By.CSS_SELECTOR, f"[data-testid='{testid}']")
    element.clear()
    element.send_keys(value)

    if trigger_change:
        driver.execute_script(
            "arguments[0].dispatchEvent(new Event('change', {bubbles: true}))", element
        )
        time.sleep(CLICK_DELAY)

    time.sleep(FILL_DELAY)


def click_button(driver, testid: str):
    """Click a button by data-testid using JavaScript for reliability."""
    button = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, f"[data-testid='{testid}']"))
    )
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", button)
    time.sleep(0.2)
    # Use JavaScript click to avoid click interception issues
    driver.execute_script("arguments[0].click();", button)
    time.sleep(CLICK_DELAY)


def element_exists(driver, testid: str) -> bool:
    """Check if an element with given data-testid exists."""
    elements = driver.find_elements(By.CSS_SELECTOR, f"[data-testid='{testid}']")
    return len(elements) > 0


def start_new_investigation(driver, profile: str = "miappe", version: str = "1.1"):
    """Start creating a new Investigation by selecting profile."""
    click_button(driver, "btn-new-investigation")
    click_button(driver, f"profile-{profile}-v{version}")


@pytest.mark.ui
class TestValidationRulesDisplay:
    """Test that validation rules are displayed."""

    def test_validation_shows_errors_for_missing_required(self, browser):
        """Verify validation shows errors for missing required fields."""
        browser.get(BASE_URL)
        time.sleep(1)

        start_new_investigation(browser)
        fill_field(browser, "input-unique-id", "INV-ERR-001")
        # Leave title empty to cause validation error

        click_button(browser, "btn-validate")
        time.sleep(CLICK_DELAY)

        # Check validation errors
        assert element_exists(browser, "validation-errors")

        # Verify error mentions title
        errors_div = browser.find_element(By.CSS_SELECTOR, "[data-testid='validation-errors']")
        assert "title" in errors_div.text.lower()

    def test_validation_shows_pattern_error(self, browser):
        """Verify validation shows pattern error for invalid unique_id."""
        browser.get(BASE_URL)
        time.sleep(1)

        start_new_investigation(browser)
        fill_field(browser, "input-unique-id", "INV INVALID!")  # Invalid pattern (has spaces)
        fill_field(browser, "input-title", "Test Investigation")

        click_button(browser, "btn-validate")
        time.sleep(CLICK_DELAY)

        # Check validation errors
        assert element_exists(browser, "validation-errors")

        # Verify error mentions unique_id
        assert element_exists(browser, "validation-error-unique_id")

    def test_create_and_validate_investigation(self, browser):
        """Create an investigation and verify validation button works."""
        browser.get(BASE_URL)
        time.sleep(1)

        start_new_investigation(browser)
        fill_field(browser, "input-unique-id", "INV-VAL-001")
        fill_field(browser, "input-title", "Validation Test Investigation")

        # Click Create
        click_button(browser, "btn-create")
        time.sleep(1)

        # Should be in edit mode
        assert element_exists(browser, "btn-update")

        # Click Validate
        click_button(browser, "btn-validate")
        time.sleep(CLICK_DELAY)

        # Should show validation result (either success or errors)
        has_success = element_exists(browser, "validation-success")
        has_errors = element_exists(browser, "validation-errors")
        assert has_success or has_errors, "Validation should produce a result"


def expand_optional_fields(driver):
    """Expand the optional fields section if collapsed."""
    try:
        toggle = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, "[data-testid='section-optional-toggle']")
            )
        )
        parent = toggle.find_element(By.XPATH, "..")
        content = parent.find_element(By.CSS_SELECTOR, ".collapsible-content")
        if not content.is_displayed():
            driver.execute_script("arguments[0].click();", toggle)
            time.sleep(CLICK_DELAY)
            WebDriverWait(driver, 10).until(EC.visibility_of(content))
    except Exception:
        pass  # Section may not be collapsible


@pytest.mark.ui
class TestCreateInvestigationAllFields:
    """Test creating an Investigation with all fields filled."""

    def test_create_investigation_all_fields(self, browser):
        """Create an Investigation filling all available fields from YAML example."""
        browser.get(BASE_URL)
        time.sleep(1)

        start_new_investigation(browser)

        # Fill required fields
        fill_field(browser, "input-unique-id", INV_EXAMPLE["unique_id"])
        fill_field(browser, "input-title", INV_EXAMPLE["title"])

        # Expand optional fields section
        expand_optional_fields(browser)

        # Fill all optional scalar fields from YAML example
        fill_field(browser, "input-description", INV_EXAMPLE["description"])
        fill_field(browser, "input-submission-date", INV_EXAMPLE["submission_date"])
        fill_field(browser, "input-public-release-date", INV_EXAMPLE["public_release_date"])
        fill_field(browser, "input-license", INV_EXAMPLE["license"])

        # Fill associated_publications (textarea, one per line)
        pubs = INV_EXAMPLE.get("associated_publications", [])
        if pubs:
            fill_field(browser, "input-associated-publications", "\n".join(pubs))

        # Create the investigation
        click_button(browser, "btn-create")
        time.sleep(1)

        # Should be in edit mode after creation
        assert element_exists(browser, "btn-update")

        # Verify all fields were saved by checking they appear in the form
        unique_id_field = browser.find_element(By.CSS_SELECTOR, "[data-testid='input-unique-id']")
        assert unique_id_field.get_attribute("value") == INV_EXAMPLE["unique_id"]

        title_field = browser.find_element(By.CSS_SELECTOR, "[data-testid='input-title']")
        assert title_field.get_attribute("value") == INV_EXAMPLE["title"]

        # Expand optional fields to verify they persisted
        expand_optional_fields(browser)

        desc_field = browser.find_element(By.CSS_SELECTOR, "[data-testid='input-description']")
        assert INV_EXAMPLE["description"] in desc_field.get_attribute("value")

    def test_update_investigation_fields(self, browser):
        """Create an investigation, update fields, and verify changes persist."""
        browser.get(BASE_URL)
        time.sleep(1)

        # Create initial investigation
        start_new_investigation(browser)
        fill_field(browser, "input-unique-id", "INV-UPDATE-TEST")
        fill_field(browser, "input-title", "Original Title")
        click_button(browser, "btn-create")
        time.sleep(1)

        assert element_exists(browser, "btn-update")

        # Update the title
        title_field = browser.find_element(By.CSS_SELECTOR, "[data-testid='input-title']")
        title_field.clear()
        title_field.send_keys("Updated Title")
        time.sleep(FILL_DELAY)

        # Click Update
        click_button(browser, "btn-update")
        time.sleep(1)

        # Verify title was updated
        title_field = browser.find_element(By.CSS_SELECTOR, "[data-testid='input-title']")
        assert title_field.get_attribute("value") == "Updated Title"

    def test_miappe_version_auto_populated(self, browser):
        """Verify miappe_version is auto-populated and readonly."""
        browser.get(BASE_URL)
        time.sleep(1)

        start_new_investigation(browser)

        # Expand optional fields to see miappe_version
        expand_optional_fields(browser)

        # Find miappe_version input
        version_input = browser.find_element(
            By.CSS_SELECTOR, "[data-testid='input-miappe-version']"
        )

        # Verify it has a value (auto-populated)
        assert version_input.get_attribute("value") == "1.1"

        # Verify it is readonly
        assert version_input.get_attribute("readonly") is not None
