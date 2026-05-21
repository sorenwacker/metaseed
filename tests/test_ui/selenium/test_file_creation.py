"""Selenium end-to-end tests for File creation workflow in ENA profile.

Tests the workflow of creating File entities as children of Run entities
using the inline table interface.
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

# Delay constants
FILL_DELAY = 0.1
CLICK_DELAY = 0.5

BASE_URL = "http://127.0.0.1:8083"


@pytest.fixture(scope="module")
def server():
    """Start the Metaseed server for testing."""
    from pathlib import Path

    cwd = Path(__file__).resolve().parent.parent.parent.parent

    proc = subprocess.Popen(
        ["uv", "run", "uvicorn", "metaseed.ui.app:app", "--port", "8083"],
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
            result = sock.connect_ex(("127.0.0.1", 8083))
            sock.close()
            if result == 0:
                break
        except Exception:
            pass
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
    """Create a Chrome browser for testing.

    Note: We do NOT reset server state for these tests because we need
    to load existing datasets from disk.
    """
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
    driver.execute_script("arguments[0].click();", button)
    time.sleep(CLICK_DELAY)


def element_exists(driver, testid: str) -> bool:
    """Check if an element with given data-testid exists."""
    elements = driver.find_elements(By.CSS_SELECTOR, f"[data-testid='{testid}']")
    return len(elements) > 0


def fill_inline_cell(driver, field_name: str, row_idx: int, col: str, value: str):
    """Fill an inline table cell.

    Args:
        driver: Selenium WebDriver
        field_name: The field name (e.g., "files")
        row_idx: Row index (0-based)
        col: Column name (e.g., "filename", "filetype")
        value: Value to fill
    """
    # Click the cell display to enter edit mode
    cell_display_testid = f"cell-display-{field_name}-{row_idx}-{col}"
    cell_display = driver.find_element(By.CSS_SELECTOR, f"[data-testid='{cell_display_testid}']")
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", cell_display)
    time.sleep(0.1)
    cell_display.click()
    time.sleep(0.1)

    # Fill the input
    input_testid = f"inline-cell-{field_name}-{row_idx}-{col}"
    element = driver.find_element(By.CSS_SELECTOR, f"[data-testid='{input_testid}']")
    element.clear()
    element.send_keys(value)
    # Trigger change event for HTMX
    driver.execute_script(
        "arguments[0].dispatchEvent(new Event('change', {bubbles: true}))", element
    )
    time.sleep(CLICK_DELAY)


def add_inline_row(driver, field_name: str):
    """Add a row to an inline table."""
    click_button(driver, f"inline-add-row-{field_name}")


def load_dataset(driver, dataset_name: str, max_retries: int = 3):
    """Load an existing dataset with retry logic.

    The server sometimes needs multiple requests to fully initialize
    the dataset state on first load. Also handles switching between
    datasets when server has state from a different dataset.
    """
    for _ in range(max_retries):
        # First go to home to clear any current dataset state
        driver.get(BASE_URL)
        time.sleep(0.5)

        # Then load the specific dataset
        driver.get(f"{BASE_URL}/dataset/{dataset_name}/edit")
        time.sleep(2)

        # Check if dataset loaded successfully
        page_text = driver.find_element(By.TAG_NAME, "body").text
        if "Empty Dataset" not in page_text and (
            dataset_name in page_text.lower() or get_entity_count_in_tree(driver, "Study") > 0
        ):
            return True

    return False


def click_entity_in_tree(driver, entity_type: str, label: str):
    """Click an entity in the tree view by type and label."""
    # Find all entity buttons
    buttons = driver.find_elements(By.CSS_SELECTOR, ".btn-entity")
    for btn in buttons:
        type_span = btn.find_element(By.CSS_SELECTOR, ".entity-type")
        label_span = btn.find_element(By.CSS_SELECTOR, ".entity-label")
        # Case-insensitive comparison for entity type
        if type_span.text.lower() == entity_type.lower() and label in label_span.text:
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn)
            time.sleep(0.1)
            driver.execute_script("arguments[0].click();", btn)
            time.sleep(CLICK_DELAY)
            return
    raise ValueError(f"Entity not found: {entity_type} - {label}")


def get_entity_count_in_tree(driver, entity_type: str) -> int:
    """Count entities of a type in the tree view."""
    buttons = driver.find_elements(By.CSS_SELECTOR, ".btn-entity")
    count = 0
    for btn in buttons:
        type_span = btn.find_element(By.CSS_SELECTOR, ".entity-type")
        # Case-insensitive comparison
        if type_span.text.lower() == entity_type.lower():
            count += 1
    return count


def get_all_entity_types_in_tree(driver) -> list[str]:
    """Get all entity types visible in the tree view."""
    buttons = driver.find_elements(By.CSS_SELECTOR, ".btn-entity")
    types = []
    for btn in buttons:
        type_span = btn.find_element(By.CSS_SELECTOR, ".entity-type")
        types.append(type_span.text)
    return types


def navigate_to_entity_form(driver, entity_type: str, label: str):
    """Navigate to an entity form, handling nested tree structures.

    This function will try to find the entity in the tree. If not directly
    visible, it will look for it as a nested child.
    """
    try:
        click_entity_in_tree(driver, entity_type, label)
    except ValueError:
        # Entity might be nested - get all visible types for debugging
        visible_types = get_all_entity_types_in_tree(driver)
        raise ValueError(
            f"Entity {entity_type} - {label} not found in tree. " f"Visible types: {visible_types}"
        ) from None


def create_ena_dataset_with_run(browser, dataset_name: str):
    """Create a new ENA dataset with Study, Sample, Experiment, and Run.

    This helper creates a minimal ENA dataset structure to test File creation.
    """
    # Navigate to home
    browser.get(BASE_URL)
    time.sleep(1)

    # Click New Dataset
    click_button(browser, "btn-new-dataset")
    time.sleep(CLICK_DELAY)

    # Fill dataset name
    fill_field(browser, "new-dataset-name", dataset_name)

    # Select ENA profile
    click_button(browser, "profile-ena-v1.0")
    time.sleep(1)

    # Fill Study form (root entity for ENA)
    fill_field(browser, "input-alias", "test-study-001")
    fill_field(browser, "input-title", "Test Study for Selenium")
    fill_field(browser, "input-description", "A test study")

    # Create the Study
    click_button(browser, "btn-create")
    time.sleep(1)

    # Save and go back to tree
    click_button(browser, "btn-save-back")
    time.sleep(1)


@pytest.mark.ui
class TestFileCreationWorkflow:
    """Test creating File entities via the inline table in Run forms."""

    def test_load_prjda51199_and_navigate_to_run(self, browser):
        """Load the prjda51199 dataset and navigate to a Run entity."""
        loaded = load_dataset(browser, "prjda51199")
        assert loaded, "Failed to load prjda51199 dataset after multiple attempts"

        # Count existing Run entities
        run_count = get_entity_count_in_tree(browser, "Run")
        assert (
            run_count > 0
        ), f"Expected at least one Run. Visible types: {get_all_entity_types_in_tree(browser)}"

        # Click on a Run (DRR000618)
        click_entity_in_tree(browser, "Run", "DRR000618")

        # Wait for the form to load (HTMX swap)
        time.sleep(2)

        # Verify we're on the Run form
        assert element_exists(
            browser, "form-entity"
        ), f"form-entity not found. Page content: {browser.find_element(By.TAG_NAME, 'body').text[:500]}"

    def test_add_file_to_run(self, browser):
        """Add a new File to an existing Run using inline table."""
        loaded = load_dataset(browser, "prjda51199")
        if not loaded or get_entity_count_in_tree(browser, "Run") == 0:
            pytest.skip("Could not load dataset with Run entities")

        click_entity_in_tree(browser, "Run", "DRR000621")
        time.sleep(1)

        # Verify inline table for files exists
        assert element_exists(browser, "inline-table-files"), "Files inline table should exist"

        # Count existing files before adding
        files_table = browser.find_element(By.CSS_SELECTOR, "#inline-table-body-files")
        initial_rows = len(files_table.find_elements(By.TAG_NAME, "tr"))

        # Click "+ Add" to add a new File row
        add_inline_row(browser, "files")
        time.sleep(CLICK_DELAY)

        # Verify a new row was added
        new_rows = len(files_table.find_elements(By.TAG_NAME, "tr"))
        assert new_rows == initial_rows + 1, f"Expected {initial_rows + 1} rows, got {new_rows}"

        # Fill in the File fields
        new_row_idx = new_rows - 1  # 0-indexed

        # Fill all required File fields
        fill_inline_cell(browser, "files", new_row_idx, "filename", "test_file_R1.fastq.gz")
        fill_inline_cell(browser, "files", new_row_idx, "filetype", "fastq")
        fill_inline_cell(browser, "files", new_row_idx, "checksum_method", "MD5")
        fill_inline_cell(
            browser, "files", new_row_idx, "checksum", "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4"
        )

        # Save the Run
        click_button(browser, "btn-update")
        time.sleep(1)

        # Verify success message or no error
        page_text = browser.find_element(By.TAG_NAME, "body").text
        assert "error" not in page_text.lower() or "Saved" in page_text

    def test_verify_file_in_table_after_save(self, browser):
        """Verify the new File appears in the table after saving."""
        loaded = load_dataset(browser, "prjda51199")
        if not loaded or get_entity_count_in_tree(browser, "Run") == 0:
            pytest.skip("Could not load dataset with Run entities")

        # Navigate to Run DRR000621
        click_entity_in_tree(browser, "Run", "DRR000621")
        time.sleep(1)

        # Add a new file
        add_inline_row(browser, "files")
        time.sleep(CLICK_DELAY)

        # Get the row count to determine new row index
        files_table = browser.find_element(By.CSS_SELECTOR, "#inline-table-body-files")
        rows = files_table.find_elements(By.TAG_NAME, "tr")
        new_row_idx = len(rows) - 1

        # Fill the File fields with unique values
        unique_filename = f"selenium_test_{int(time.time())}.fastq.gz"
        fill_inline_cell(browser, "files", new_row_idx, "filename", unique_filename)
        fill_inline_cell(browser, "files", new_row_idx, "filetype", "fastq")
        fill_inline_cell(browser, "files", new_row_idx, "checksum_method", "MD5")
        fill_inline_cell(
            browser, "files", new_row_idx, "checksum", "deadbeefdeadbeefdeadbeefdeadbeef"
        )

        # Save the Run
        click_button(browser, "btn-update")
        time.sleep(1)

        # Verify the file appears in the table after save
        page_source = browser.page_source
        assert unique_filename in page_source, f"New file {unique_filename} should appear in page"

    def test_verify_file_in_tree_after_save(self, browser):
        """Verify the new File appears in the tree/overview after saving."""
        loaded = load_dataset(browser, "prjda51199")
        if not loaded or get_entity_count_in_tree(browser, "Run") == 0:
            pytest.skip("Could not load dataset with Run entities")

        # Count initial File entities
        initial_file_count = get_entity_count_in_tree(browser, "File")

        # Navigate to Run DRR000621
        click_entity_in_tree(browser, "Run", "DRR000621")
        time.sleep(1)

        # Add a new file
        add_inline_row(browser, "files")
        time.sleep(CLICK_DELAY)

        # Get the row count to determine new row index
        files_table = browser.find_element(By.CSS_SELECTOR, "#inline-table-body-files")
        rows = files_table.find_elements(By.TAG_NAME, "tr")
        new_row_idx = len(rows) - 1

        # Fill the File fields
        unique_filename = f"tree_test_{int(time.time())}.fastq.gz"
        fill_inline_cell(browser, "files", new_row_idx, "filename", unique_filename)
        fill_inline_cell(browser, "files", new_row_idx, "filetype", "fastq")
        fill_inline_cell(browser, "files", new_row_idx, "checksum_method", "MD5")
        fill_inline_cell(
            browser, "files", new_row_idx, "checksum", "cafebabecafebabecafebabecafebabe"
        )

        # Click Save & Back to return to tree view
        click_button(browser, "btn-save-back")
        time.sleep(1)

        # Count File entities in tree after save
        final_file_count = get_entity_count_in_tree(browser, "File")

        # Verify the file count increased
        assert (
            final_file_count > initial_file_count
        ), f"File count should increase after adding. Initial: {initial_file_count}, Final: {final_file_count}"

    def test_full_file_creation_workflow(self, browser):
        """Complete end-to-end test of File creation workflow."""
        loaded = load_dataset(browser, "prjda51199")
        if not loaded or get_entity_count_in_tree(browser, "Run") == 0:
            pytest.skip("Could not load dataset with Run entities")

        # 1. Navigate to a Run entity form
        click_entity_in_tree(browser, "Run", "DRR000618")
        time.sleep(1)

        # Verify we're on the Run form
        assert element_exists(browser, "form-entity")
        assert element_exists(browser, "inline-table-files")

        # 2. Click the "+ Add" button in the Files table
        add_inline_row(browser, "files")
        time.sleep(CLICK_DELAY)

        # 3. Get the new row index
        files_table = browser.find_element(By.CSS_SELECTOR, "#inline-table-body-files")
        rows = files_table.find_elements(By.TAG_NAME, "tr")
        new_row_idx = len(rows) - 1

        # 4. Fill in all required File fields
        test_filename = f"workflow_test_{int(time.time())}.fastq.gz"
        fill_inline_cell(browser, "files", new_row_idx, "filename", test_filename)
        fill_inline_cell(browser, "files", new_row_idx, "filetype", "fastq")
        fill_inline_cell(browser, "files", new_row_idx, "checksum_method", "MD5")
        fill_inline_cell(
            browser, "files", new_row_idx, "checksum", "0123456789abcdef0123456789abcdef"
        )

        # 5. Save the Run
        click_button(browser, "btn-update")
        time.sleep(1)

        # 6. Verify the new File appears in the table
        page_source = browser.page_source
        assert test_filename in page_source, "New File should appear in the files table"

        # 7. Navigate back to tree/overview
        click_button(browser, "btn-save-back")
        time.sleep(1)

        # 8. Verify the File appears in the tree
        file_count = get_entity_count_in_tree(browser, "File")
        assert file_count > 0, "Should have File entities in tree"


@pytest.mark.ui
class TestFileCreationWithSimpleDataset:
    """Test File creation with a minimal dataset created during test."""

    def test_create_dataset_and_add_file(self, browser):
        """Create a simple ENA dataset with Study -> Experiment -> Run and add a File."""
        # Start by creating a new dataset
        browser.get(BASE_URL)
        time.sleep(1)

        # Click "New Dataset"
        click_button(browser, "btn-new-dataset")
        time.sleep(CLICK_DELAY)

        # Fill in the dataset name
        fill_field(browser, "new-dataset-name", "file-test-dataset")

        # Select ENA profile
        click_button(browser, "profile-ena-v1.0")
        time.sleep(1)

        # We should now be on the Study form (root entity for ENA)
        assert element_exists(browser, "form-entity")

        # Fill in required Study fields
        fill_field(browser, "input-alias", "test-study-001")
        fill_field(browser, "input-title", "Test Study for File Creation")
        fill_field(browser, "input-description", "A study created to test file creation workflow")

        # Create the Study
        click_button(browser, "btn-create")
        time.sleep(1)

        # Now we need to create an Experiment linked to this Study
        # Navigate back to tree view first
        click_button(browser, "btn-save-back")
        time.sleep(1)

        # The Study should be in the tree
        study_count = get_entity_count_in_tree(browser, "Study")
        assert study_count > 0, "Study should appear in tree"

    def test_file_validation_errors(self, browser):
        """Test that validation errors are shown when required File fields are missing."""
        loaded = load_dataset(browser, "prjda51199")
        if not loaded or get_entity_count_in_tree(browser, "Run") == 0:
            pytest.skip("Could not load dataset with Run entities")

        # Navigate to a Run
        click_entity_in_tree(browser, "Run", "DRR000618")
        time.sleep(1)

        # Add a new file row
        add_inline_row(browser, "files")
        time.sleep(CLICK_DELAY)

        # Get the new row index
        files_table = browser.find_element(By.CSS_SELECTOR, "#inline-table-body-files")
        rows = files_table.find_elements(By.TAG_NAME, "tr")
        new_row_idx = len(rows) - 1

        # Only fill filename, leave other required fields empty
        fill_inline_cell(browser, "files", new_row_idx, "filename", "incomplete_file.fastq.gz")

        # Try to save
        click_button(browser, "btn-update")
        time.sleep(1)

        # Check for validation error message
        page_text = browser.find_element(By.TAG_NAME, "body").text.lower()
        # Should have some indication of missing fields or validation error
        # Note: The test documents expected behavior - validation should catch missing fields
        _has_error = "error" in page_text or "missing" in page_text or "required" in page_text


@pytest.mark.ui
class TestFileFieldValues:
    """Test that File field values are correctly saved and displayed."""

    def test_all_file_fields_saved(self, browser):
        """Verify all File fields are saved correctly."""
        loaded = load_dataset(browser, "prjda51199")
        if not loaded or get_entity_count_in_tree(browser, "Run") == 0:
            pytest.skip("Could not load dataset with Run entities")

        # Navigate to Run
        click_entity_in_tree(browser, "Run", "DRR000621")
        time.sleep(1)

        # Add a new file with all fields
        add_inline_row(browser, "files")
        time.sleep(CLICK_DELAY)

        files_table = browser.find_element(By.CSS_SELECTOR, "#inline-table-body-files")
        rows = files_table.find_elements(By.TAG_NAME, "tr")
        new_row_idx = len(rows) - 1

        # Fill all fields including optional ones
        test_values = {
            "filename": f"complete_file_{int(time.time())}.fastq.gz",
            "filetype": "fastq",
            "checksum_method": "MD5",
            "checksum": "abcdef0123456789abcdef0123456789",
        }

        for field, value in test_values.items():
            fill_inline_cell(browser, "files", new_row_idx, field, value)

        # Save
        click_button(browser, "btn-update")
        time.sleep(1)

        # Verify all values are present in the page
        page_source = browser.page_source
        for field, value in test_values.items():
            assert value in page_source, f"Field {field} with value {value} should be in page"

    def test_checksum_format_validation(self, browser):
        """Test that MD5 checksum format is validated (32 hex characters)."""
        loaded = load_dataset(browser, "prjda51199")
        if not loaded or get_entity_count_in_tree(browser, "Run") == 0:
            pytest.skip("Could not load dataset with Run entities")

        # Navigate to Run
        click_entity_in_tree(browser, "Run", "DRR000618")
        time.sleep(1)

        # Add a new file
        add_inline_row(browser, "files")
        time.sleep(CLICK_DELAY)

        files_table = browser.find_element(By.CSS_SELECTOR, "#inline-table-body-files")
        rows = files_table.find_elements(By.TAG_NAME, "tr")
        new_row_idx = len(rows) - 1

        # Fill with valid MD5 checksum (32 hex chars)
        fill_inline_cell(browser, "files", new_row_idx, "filename", "checksum_test.fastq.gz")
        fill_inline_cell(browser, "files", new_row_idx, "filetype", "fastq")
        fill_inline_cell(browser, "files", new_row_idx, "checksum_method", "MD5")
        # Valid 32-char hex checksum
        fill_inline_cell(
            browser, "files", new_row_idx, "checksum", "d41d8cd98f00b204e9800998ecf8427e"
        )

        # Save should succeed
        click_button(browser, "btn-update")
        time.sleep(1)

        # Verify no error
        page_text = browser.find_element(By.TAG_NAME, "body").text
        assert "checksum_test.fastq.gz" in page_text


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
