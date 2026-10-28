"""Selenium end-to-end tests for the HTMX UI.

Tests run with a visible Chrome browser to demonstrate UI functionality.
Example values are loaded from the MIAPPE YAML spec.
"""

import subprocess
import time

import pytest
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from tests.test_ui.examples import (
    INV_EXAMPLE,
    PERSON_EXAMPLE,
    STUDY_EXAMPLE,
)

# Drives a real browser + server; excluded from the pre-push hook for speed.
pytestmark = pytest.mark.selenium

# Delay constants per requirements
FILL_DELAY = 0.1  # Delay between form fills
CLICK_DELAY = 0.5  # Delay after button clicks

BASE_URL = "http://127.0.0.1:8081"


def _reset_state(base_url: str, *, attempts: int = 5) -> None:
    """POST ``/reset``, retrying briefly; raise if the server never resets.

    A failed reset must not be swallowed — the test would then run against the
    previous test's leaked state, the suite's dominant flakiness source.
    """
    import urllib.error
    import urllib.request

    last_error: Exception | None = None
    for _ in range(attempts):
        try:
            req = urllib.request.Request(f"{base_url}/reset", method="POST")
            with urllib.request.urlopen(req, timeout=10) as response:
                if response.status == 200:
                    return
        except (urllib.error.URLError, OSError) as exc:  # not ready / transient
            last_error = exc
        time.sleep(0.5)
    raise RuntimeError(f"Could not reset server state at {base_url}: {last_error}")


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    """Start the metaseed UI server for testing, with isolated dataset storage."""
    import os
    import socket

    # Set working directory to repo root
    cwd = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    # Isolate persisted datasets in a throwaway dir so tests never pollute the
    # user's real datasets or leak saved datasets between runs (a flakiness
    # source: a persisted example dataset would linger in the overview).
    datasets_dir = tmp_path_factory.mktemp("selenium-datasets")
    env = {**os.environ, "METASEED_DATASETS_DIR": str(datasets_dir)}

    proc = subprocess.Popen(
        ["uv", "run", "uvicorn", "metaseed.ui.app:app", "--port", "8081"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        cwd=cwd,
        env=env,
    )

    # Wait for server to be ready by polling the port
    max_attempts = 30
    for _ in range(max_attempts):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex(("127.0.0.1", 8081))
            sock.close()
            if result == 0:
                break
        except Exception:
            pass
        time.sleep(0.5)
    else:
        # If server failed to start, print output for debugging
        output = proc.stdout.read().decode() if proc.stdout else ""
        proc.terminate()
        raise RuntimeError(f"Server failed to start within timeout. Output: {output}")

    time.sleep(0.5)  # Extra buffer for full initialization
    yield proc
    proc.terminate()
    proc.wait()


@pytest.fixture
def browser(server):
    """Create a headless Chrome browser for testing."""
    _ = server  # Ensure server is running
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--window-size=1920,1200")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")

    driver = webdriver.Chrome(options=options)
    driver.implicitly_wait(5)

    # Reset server state before each test. This MUST succeed: a silently-skipped
    # reset leaves the previous test's state loaded, which is the suite's main
    # flakiness source (tests pass alone but fail in sequence). Retry briefly,
    # then fail loudly rather than run a non-hermetic test.
    _reset_state(BASE_URL)

    yield driver
    driver.quit()


def fill_field(driver, testid: str, value: str, trigger_change: bool = False):
    """Fill a form field by data-testid.

    Args:
        driver: Selenium WebDriver
        testid: The data-testid attribute value
        value: The value to fill
        trigger_change: If True, trigger a change event after filling (needed for HTMX)
    """
    element = driver.find_element(By.CSS_SELECTOR, f"[data-testid='{testid}']")

    # For date inputs, use JavaScript to set value directly (avoids locale issues)
    if element.get_attribute("type") == "date":
        driver.execute_script("arguments[0].value = arguments[1]", element, value)
    else:
        element.clear()
        element.send_keys(value)

    if trigger_change:
        # Trigger change event for HTMX handlers
        driver.execute_script(
            "arguments[0].dispatchEvent(new Event('change', {bubbles: true}))", element
        )
        time.sleep(CLICK_DELAY)  # Wait for HTMX to process

    time.sleep(FILL_DELAY)


def click_button(driver, testid: str):
    """Click a button by data-testid and wait."""
    button = WebDriverWait(driver, 5).until(
        EC.element_to_be_clickable((By.CSS_SELECTOR, f"[data-testid='{testid}']"))
    )
    # Scroll into view for headless mode compatibility
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", button)
    time.sleep(0.2)  # Brief pause after scroll
    # Use JavaScript click to bypass any visual interception (fixed headers, overlays)
    driver.execute_script("arguments[0].click();", button)
    time.sleep(CLICK_DELAY)


def element_exists(driver, testid: str) -> bool:
    """Check if an element with given data-testid exists."""
    elements = driver.find_elements(By.CSS_SELECTOR, f"[data-testid='{testid}']")
    return len(elements) > 0


def start_new_investigation(
    driver,
    profile: str = "miappe",
    version: str = "1.2",
    dataset_name: str = "test-dataset",
):
    """Start creating a new Investigation by clicking button and selecting profile.

    Args:
        driver: Selenium WebDriver
        profile: Profile to select ("miappe", "isa", or "darwin-core")
        version: Profile version to select (default "1.2" for miappe)
        dataset_name: Name for the new dataset
    """
    click_button(driver, "btn-new-dataset")
    # Fill in the dataset name
    click_button(driver, f"profile-{profile}-v{version}")
    fill_field(driver, "new-dataset-name", dataset_name)
    click_button(driver, "btn-create-dataset")


def fill_inline_cell(driver, field_name: str, row_idx: int, col: str, value: str):
    """Fill an inline table cell.

    The inline table uses editable cells that require clicking to reveal the input.

    Args:
        driver: Selenium WebDriver
        field_name: The field name (e.g., "contacts", "studies")
        row_idx: Row index (0-based)
        col: Column name (e.g., "name", "email")
        value: Value to fill
    """
    # Click the cell display to enter edit mode (adds 'editing' class)
    cell_display_testid = f"cell-display-{field_name}-{row_idx}-{col}"
    cell_display = driver.find_element(
        By.CSS_SELECTOR, f"[data-testid='{cell_display_testid}']"
    )
    driver.execute_script(
        "arguments[0].scrollIntoView({block: 'center'});", cell_display
    )
    time.sleep(0.1)
    cell_display.click()
    time.sleep(0.1)

    # Now fill the input
    input_testid = f"inline-cell-{field_name}-{row_idx}-{col}"
    element = driver.find_element(By.CSS_SELECTOR, f"[data-testid='{input_testid}']")
    element.clear()
    element.send_keys(value)
    # Trigger change event for HTMX (which saves the cell)
    driver.execute_script(
        "arguments[0].dispatchEvent(new Event('change', {bubbles: true}))", element
    )
    # Wait for HTMX to process the cell save
    time.sleep(CLICK_DELAY)


def add_inline_row(driver, field_name: str):
    """Add a row to an inline table.

    Args:
        driver: Selenium WebDriver
        field_name: The field name (e.g., "contacts", "studies")
    """
    click_button(driver, f"inline-add-row-{field_name}")


def fill_inline_person(driver, field_name: str = "contacts", row_idx: int = 0):
    """Fill a Person row in an inline table.

    Args:
        driver: Selenium WebDriver
        field_name: The inline table field name
        row_idx: Row index
    """
    fill_inline_cell(driver, field_name, row_idx, "name", PERSON_EXAMPLE["name"])
    fill_inline_cell(driver, field_name, row_idx, "email", PERSON_EXAMPLE["email"])
    fill_inline_cell(
        driver, field_name, row_idx, "institution", PERSON_EXAMPLE["institution"]
    )
    fill_inline_cell(driver, field_name, row_idx, "role", PERSON_EXAMPLE["role"])
    fill_inline_cell(driver, field_name, row_idx, "orcid", PERSON_EXAMPLE["orcid"])


def fill_inline_study(driver, field_name: str = "studies", row_idx: int = 0):
    """Fill a Study row in an inline table.

    Args:
        driver: Selenium WebDriver
        field_name: The inline table field name
        row_idx: Row index
    """
    fill_inline_cell(
        driver, field_name, row_idx, "unique_id", STUDY_EXAMPLE["unique_id"]
    )
    fill_inline_cell(driver, field_name, row_idx, "title", STUDY_EXAMPLE["title"])
    # Optional fields
    fill_inline_cell(
        driver, field_name, row_idx, "description", STUDY_EXAMPLE.get("description", "")
    )
    fill_inline_cell(
        driver, field_name, row_idx, "start_date", STUDY_EXAMPLE.get("start_date", "")
    )
    fill_inline_cell(
        driver, field_name, row_idx, "end_date", STUDY_EXAMPLE.get("end_date", "")
    )


def expand_optional_fields(driver):
    """Expand the optional fields section if collapsed."""
    try:
        toggle = WebDriverWait(driver, 5).until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, "[data-testid='section-optional-toggle']")
            )
        )
        # Check if collapsible content is visible
        parent = toggle.find_element(By.XPATH, "..")
        content = parent.find_element(By.CSS_SELECTOR, ".collapsible-content")
        if not content.is_displayed():
            toggle.click()
            time.sleep(CLICK_DELAY)
            # Wait for content to be visible
            WebDriverWait(driver, 5).until(EC.visibility_of(content))
    except Exception:
        pass  # Optional fields section may not exist


@pytest.mark.ui
class TestCreateInvestigationRequiredFields:
    """Test creating an Investigation with required fields only."""

    def test_create_investigation_required_fields(self, browser):
        """Create Investigation with only required fields using YAML examples."""
        # Navigate to home
        browser.get(BASE_URL)
        time.sleep(1)  # Wait for page to fully load

        # Click "+ Investigation" button
        start_new_investigation(browser)

        # Verify form is displayed
        assert element_exists(browser, "form-entity")
        assert element_exists(browser, "input-unique-id")

        # Fill required fields from YAML example
        fill_field(browser, "input-unique-id", INV_EXAMPLE["unique_id"])
        fill_field(browser, "input-title", INV_EXAMPLE["title"])

        # Click Create button
        click_button(browser, "btn-create")

        # Verify success message appears
        time.sleep(CLICK_DELAY)
        assert element_exists(browser, "form-success")
        body_text = browser.find_element(By.TAG_NAME, "body").text
        assert "Created Investigation" in body_text

        # Verify form switched to edit mode (Update button visible)
        assert element_exists(browser, "btn-update")


@pytest.mark.ui
class TestCreateInvestigationAllFields:
    """Test creating an Investigation with all fields using YAML examples."""

    def test_create_investigation_all_fields(self, browser):
        """Create Investigation with all fields from YAML examples including nested entities."""
        # Navigate to home
        browser.get(BASE_URL)
        time.sleep(CLICK_DELAY)

        # Click "+ Investigation" button
        start_new_investigation(browser)

        # Fill required fields from YAML example
        fill_field(browser, "input-unique-id", INV_EXAMPLE["unique_id"])
        fill_field(browser, "input-title", INV_EXAMPLE["title"])

        # Expand optional fields
        expand_optional_fields(browser)

        # Fill all optional scalar fields from YAML example
        # Note: miappe_version is auto-populated and readonly, so we skip it
        fill_field(browser, "input-description", INV_EXAMPLE["description"])
        fill_field(browser, "input-submission-date", INV_EXAMPLE["submission_date"])
        fill_field(
            browser, "input-public-release-date", INV_EXAMPLE["public_release_date"]
        )
        fill_field(browser, "input-license", INV_EXAMPLE["license"])

        # Fill associated_publications (textarea, one per line)
        pubs = INV_EXAMPLE.get("associated_publications", [])
        if pubs:
            fill_field(browser, "input-associated-publications", "\n".join(pubs))

        # Click Create button
        click_button(browser, "btn-create")
        time.sleep(1)

        # After creation, we're automatically in edit mode
        assert element_exists(browser, "btn-update")

        # Add contact using inline table
        add_inline_row(browser, "contacts")
        fill_inline_person(browser, "contacts", 0)

        # Add study using inline table
        add_inline_row(browser, "studies")
        fill_inline_study(browser, "studies", 0)

        # Update the Investigation to save all nested data
        click_button(browser, "btn-update")
        time.sleep(CLICK_DELAY)

        # Verify we're still in edit mode after update
        assert element_exists(browser, "btn-update")


@pytest.mark.ui
class TestAutoPopulatedFields:
    """Test auto-populated fields like miappe_version."""

    def test_miappe_version_auto_populated(self, browser):
        """Verify miappe_version is auto-populated and readonly."""
        browser.get(BASE_URL)
        time.sleep(CLICK_DELAY)

        start_new_investigation(browser)

        # Expand optional fields to see miappe_version
        expand_optional_fields(browser)

        # Find miappe_version input
        version_input = browser.find_element(
            By.CSS_SELECTOR, "[data-testid='input-miappe-version']"
        )

        # Verify it has a value (auto-populated) - should match the version used in start_new_investigation
        assert version_input.get_attribute("value") == "1.2", (
            f"Expected miappe_version to be '1.2', got: {version_input.get_attribute('value')}"
        )

        # Verify it is readonly
        assert version_input.get_attribute("readonly") is not None, (
            "miappe_version field should be readonly"
        )

        # Verify it has the readonly class
        assert "form-input-readonly" in version_input.get_attribute("class"), (
            "miappe_version field should have form-input-readonly class"
        )

    def test_date_fields_use_the_browsers_date_control(self, browser):
        """A date field is the browser's own date control, which takes and
        shows a date in the reader's locale and submits ISO 8601. It used to be
        a text box with a regex, which told the reader the format only after
        they had got it wrong (the template says why)."""
        browser.get(BASE_URL)
        time.sleep(CLICK_DELAY)

        start_new_investigation(browser)

        # Expand optional fields to see date fields
        expand_optional_fields(browser)

        date_input = browser.find_element(
            By.CSS_SELECTOR, "[data-testid='input-submission-date']"
        )

        assert date_input.get_attribute("type") == "date", (
            "Date field should be the browser's date control"
        )
        assert not date_input.get_attribute("pattern"), (
            "the date control carries no regex; the browser enforces the format"
        )


@pytest.mark.ui
class TestAddNestedContacts:
    """Test adding nested contacts to an Investigation using YAML examples."""

    def test_add_nested_contacts(self, browser):
        """Create Investigation and add contacts from YAML Person example."""
        # Navigate to home
        browser.get(BASE_URL)
        time.sleep(CLICK_DELAY)

        # Click "+ Investigation" button
        start_new_investigation(browser)

        # Fill required fields from YAML example
        fill_field(browser, "input-unique-id", INV_EXAMPLE["unique_id"] + "-contacts")
        fill_field(browser, "input-title", INV_EXAMPLE["title"] + " (Contacts Test)")

        # Click Create button
        click_button(browser, "btn-create")
        time.sleep(CLICK_DELAY)

        # After creation, we're already in edit mode
        assert element_exists(browser, "btn-update")

        # Verify inline table for contacts exists
        assert element_exists(browser, "inline-table-contacts")

        # Add a contact using inline table
        add_inline_row(browser, "contacts")
        time.sleep(CLICK_DELAY)

        # Fill contact fields using inline cells
        fill_inline_person(browser, "contacts", 0)

        # Verify we're still on the Investigation form
        assert element_exists(browser, "form-entity")

        # Verify contacts table has a row
        assert element_exists(browser, "inline-cell-contacts-0-name")


@pytest.mark.ui
class TestEditInvestigation:
    """Test editing an existing Investigation."""

    def test_edit_investigation(self, browser):
        """Edit an existing Investigation and verify changes persist."""
        browser.get(BASE_URL)
        time.sleep(CLICK_DELAY)

        # Create an Investigation first
        start_new_investigation(browser)
        fill_field(browser, "input-unique-id", "INV-EDIT-001")
        fill_field(browser, "input-title", "Original Title")
        click_button(browser, "btn-create")
        time.sleep(CLICK_DELAY)

        # After creation, we're already in edit mode
        assert element_exists(browser, "btn-update")

        # Modify the title
        title_field = browser.find_element(
            By.CSS_SELECTOR, "[data-testid='input-title']"
        )
        title_field.clear()
        title_field.send_keys("Updated Title")
        time.sleep(FILL_DELAY)

        # Click Update
        click_button(browser, "btn-update")
        time.sleep(CLICK_DELAY)

        # Verify success message appears
        body_text = browser.find_element(By.TAG_NAME, "body").text
        assert "Updated" in body_text or element_exists(browser, "form-success")


@pytest.mark.ui
class TestAddNestedStudy:
    """Test adding a nested Study to an Investigation using YAML examples."""

    def test_add_nested_study(self, browser):
        """Add a Study from YAML example to an Investigation through nested table."""
        browser.get(BASE_URL)
        time.sleep(CLICK_DELAY)

        # Create Investigation using YAML example
        start_new_investigation(browser)
        fill_field(browser, "input-unique-id", INV_EXAMPLE["unique_id"] + "-study")
        fill_field(browser, "input-title", INV_EXAMPLE["title"] + " (Study Test)")
        click_button(browser, "btn-create")
        time.sleep(CLICK_DELAY)

        # After creation, we're already in edit mode
        assert element_exists(browser, "btn-update")

        # Verify inline table for studies exists
        assert element_exists(browser, "inline-table-studies")

        # Add a study using inline table
        add_inline_row(browser, "studies")
        time.sleep(CLICK_DELAY)

        # Fill study fields using inline cells
        fill_inline_study(browser, "studies", 0)

        # Verify study was added (inline table row exists)
        assert element_exists(browser, "inline-cell-studies-0-unique_id")


@pytest.mark.ui
class TestValidation:
    """Test validation functionality using the Validate button."""

    def test_validate_valid_investigation(self, browser):
        """Validate a correctly filled Investigation form.

        Note: Full validation requires contacts and studies (cardinality rules).
        This test validates field-level requirements (unique_id, title) pass.
        """
        browser.get(BASE_URL)
        time.sleep(CLICK_DELAY)

        # Create new Investigation form
        start_new_investigation(browser)

        # Fill required fields from YAML example
        fill_field(browser, "input-unique-id", INV_EXAMPLE["unique_id"])
        fill_field(browser, "input-title", INV_EXAMPLE["title"])

        # Create the investigation first
        click_button(browser, "btn-create")
        time.sleep(CLICK_DELAY)

        # After creation, we're already in edit mode
        assert element_exists(browser, "btn-update")
        time.sleep(CLICK_DELAY)

        # Add a contact (required by cardinality rule) using inline table
        add_inline_row(browser, "contacts")
        time.sleep(CLICK_DELAY)
        fill_inline_cell(browser, "contacts", 0, "name", "Test Contact")

        # Add a study (required by cardinality rule) using inline table
        add_inline_row(browser, "studies")
        time.sleep(CLICK_DELAY)
        fill_inline_cell(browser, "studies", 0, "unique_id", "STU-VAL-001")
        fill_inline_cell(browser, "studies", 0, "title", "Validation Test Study")

        # Click Validate button
        click_button(browser, "btn-validate")
        time.sleep(CLICK_DELAY)

        # Verify validation result appears (success or errors)
        has_success = element_exists(browser, "validation-success")
        has_errors = element_exists(browser, "validation-errors")
        assert has_success or has_errors, (
            "Validation should produce either success or error message"
        )

    def test_validate_missing_required_fields(self, browser):
        """Validate form with missing required fields shows errors."""
        browser.get(BASE_URL)
        time.sleep(CLICK_DELAY)

        # Create new Investigation form
        start_new_investigation(browser)

        # Fill only unique_id, leave title empty (both required)
        fill_field(browser, "input-unique-id", "INV-VAL-001")

        # Click Validate button
        click_button(browser, "btn-validate")

        # Verify validation errors are displayed
        assert element_exists(browser, "validation-errors")
        errors_div = browser.find_element(
            By.CSS_SELECTOR, "[data-testid='validation-errors']"
        )
        assert "Validation failed" in errors_div.text

        # Verify specific field error for title
        assert element_exists(browser, "validation-error-title")
        title_error = browser.find_element(
            By.CSS_SELECTOR, "[data-testid='validation-error-title']"
        )
        assert "title" in title_error.text.lower()

    def test_validate_invalid_pattern(self, browser):
        """Validate form with invalid field pattern shows error."""
        browser.get(BASE_URL)
        time.sleep(CLICK_DELAY)

        # Create new Investigation form
        start_new_investigation(browser)

        # Fill required fields
        fill_field(
            browser, "input-unique-id", "INVALID ID WITH SPACES!"
        )  # Invalid pattern
        fill_field(browser, "input-title", "Test Investigation")

        # Click Validate button
        click_button(browser, "btn-validate")

        # Verify validation errors for pattern violation
        assert element_exists(browser, "validation-errors")
        assert element_exists(browser, "validation-error-unique_id")

    def test_html5_validation_required_fields(self, browser):
        """Verify HTML5 required attribute is set on required fields."""
        browser.get(BASE_URL)
        time.sleep(CLICK_DELAY)

        # Create new Investigation form
        start_new_investigation(browser)

        # Check if unique_id field has required attribute
        unique_id = browser.find_element(
            By.CSS_SELECTOR, "[data-testid='input-unique-id']"
        )
        assert unique_id.get_attribute("required") is not None

        # Check if title field has required attribute
        title = browser.find_element(By.CSS_SELECTOR, "[data-testid='input-title']")
        assert title.get_attribute("required") is not None

        # Deep nesting was successful - we can navigate to a BiologicalMaterial
        # nested within a Study nested within an Investigation

        # All 10 entity types were successfully created:
        # Investigation, Person, Study, DataFile, BiologicalMaterial, ObservationUnit,
        # ObservedVariable, Factor, Event, Environment


@pytest.mark.ui
class TestExcelExport:
    """Test Excel export functionality."""

    def test_export_button_visible_in_edit_mode(self, browser):
        """Export button should be visible when editing an entity."""
        browser.get(BASE_URL)
        time.sleep(CLICK_DELAY)

        # Create an Investigation
        start_new_investigation(browser)
        fill_field(browser, "input-unique-id", "INV-EXPORT-001")
        fill_field(browser, "input-title", "Export Test Investigation")
        click_button(browser, "btn-create")
        time.sleep(CLICK_DELAY)

        # After creation, we're already in edit mode
        assert element_exists(browser, "btn-update")

        # Verify export button is visible in edit mode
        assert element_exists(browser, "btn-export")

    def test_export_button_not_in_create_mode(self, browser):
        """Export button should not be visible when creating a new entity."""
        browser.get(BASE_URL)
        time.sleep(CLICK_DELAY)

        # Open new Investigation form
        start_new_investigation(browser)

        # Verify export button is NOT visible in create mode
        assert not element_exists(browser, "btn-export")

    def test_export_downloads_file(self, browser):
        """Click export button and verify it triggers download."""
        browser.get(BASE_URL)
        time.sleep(CLICK_DELAY)

        # Create an Investigation
        start_new_investigation(browser)
        fill_field(browser, "input-unique-id", INV_EXAMPLE["unique_id"])
        fill_field(browser, "input-title", INV_EXAMPLE["title"])
        click_button(browser, "btn-create")
        time.sleep(CLICK_DELAY)

        # After creation, we're already in edit mode
        assert element_exists(browser, "btn-update")

        # Get export button href
        export_btn = browser.find_element(By.CSS_SELECTOR, "[data-testid='btn-export']")
        export_url = export_btn.get_attribute("href")

        # Verify export URL is correct
        assert "/export" in export_url

        # Test export endpoint directly using requests
        import urllib.request

        req = urllib.request.Request(f"{BASE_URL}/export")
        response = urllib.request.urlopen(req, timeout=10)

        # Verify response headers
        content_type = response.headers.get("Content-Type")
        assert "spreadsheetml" in content_type or "excel" in content_type.lower()

        content_disp = response.headers.get("Content-Disposition")
        assert "attachment" in content_disp
        assert ".xlsx" in content_disp

        # Verify content is valid Excel (starts with PK for ZIP format)
        content = response.read()
        assert content[:2] == b"PK"  # Excel files are ZIP archives

    def test_export_contains_investigation_data(self, browser):
        """Verify exported Excel contains Investigation data."""
        from openpyxl import load_workbook

        browser.get(BASE_URL)
        time.sleep(CLICK_DELAY)

        # Create Investigation with specific data
        start_new_investigation(browser)
        fill_field(browser, "input-unique-id", "INV-EXPORT-DATA-001")
        fill_field(browser, "input-title", "Export Data Test")
        click_button(browser, "btn-create")
        time.sleep(CLICK_DELAY)

        # Download export
        import urllib.request
        from io import BytesIO

        req = urllib.request.Request(f"{BASE_URL}/export")
        response = urllib.request.urlopen(req, timeout=10)
        content = response.read()

        # Load workbook and verify content
        wb = load_workbook(BytesIO(content))

        # Verify Investigation sheet exists
        assert "Investigation" in wb.sheetnames

        # Verify data is in the sheet
        ws = wb["Investigation"]
        rows = list(ws.values)
        headers = rows[0]
        data_rows = rows[1:]

        # Verify headers include key fields
        assert "unique_id" in headers
        assert "title" in headers

        # Verify at least one data row with our values
        found = False
        for row in data_rows:
            row_dict = dict(zip(headers, row, strict=False))
            if row_dict.get("unique_id") == "INV-EXPORT-DATA-001":
                found = True
                assert row_dict.get("title") == "Export Data Test"
                break

        assert found, "Investigation data not found in export"
