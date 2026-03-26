"""Selenium E2E tests for the NiceGUI web interface."""

import os
import shutil
import socket
import subprocess
import sys
import time
from collections.abc import Generator

import pytest
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

pytestmark = pytest.mark.ui  # Mark all tests in this module as UI tests


def wait_for_port(port: int, timeout: float = 10.0) -> bool:
    """Wait for a port to become available."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                return True
        except OSError:
            time.sleep(0.5)
    return False


class TestUICreateEntities:
    """Test creating entities through the web interface."""

    @pytest.fixture(scope="class")
    def app_server(self) -> Generator[subprocess.Popen, None, None]:
        """Start the NiceGUI app in a subprocess."""
        # Find the miappe CLI in the venv
        miappe_cmd = shutil.which("miappe")
        if not miappe_cmd:
            # Fallback to running via Python
            miappe_cmd = sys.executable
            args = [
                miappe_cmd,
                "-c",
                "from miappe_api.ui import run_ui; run_ui(port=8099)",
            ]
        else:
            args = [miappe_cmd, "ui", "--port", "8099"]

        # Remove pytest environment variables so NiceGUI doesn't detect pytest
        env = os.environ.copy()
        env.pop("PYTEST_CURRENT_TEST", None)

        # Start the server as a subprocess
        proc = subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )

        # Wait for server to be ready
        if not wait_for_port(8099, timeout=20):
            stdout, stderr = proc.communicate(timeout=1)
            proc.terminate()
            pytest.fail(
                f"Server did not start within timeout.\n"
                f"stdout: {stdout.decode()}\nstderr: {stderr.decode()}"
            )

        yield proc

        # Cleanup
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()

    @pytest.fixture(scope="class")
    def driver(self, app_server: subprocess.Popen) -> Generator[webdriver.Chrome, None, None]:
        """Create a headless Chrome WebDriver."""
        _ = app_server  # Ensure server is started before creating driver
        options = Options()
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")

        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        driver.implicitly_wait(10)

        yield driver

        driver.quit()

    def test_page_loads(self, driver: webdriver.Chrome) -> None:
        """Test that the main page loads correctly."""
        driver.get("http://127.0.0.1:8099")

        # Wait for the page to load
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, "//*[contains(text(), 'MIAPPE-API')]"))
        )

        assert "MIAPPE-API" in driver.page_source

    def test_create_investigation(self, driver: webdriver.Chrome) -> None:
        """Test creating an Investigation through the UI."""
        driver.get("http://127.0.0.1:8099")

        # Wait for page load
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, "[data-testid='btn-new-investigation']")
            )
        )

        # Click the "+ Investigation" button
        new_btn = driver.find_element(By.CSS_SELECTOR, "[data-testid='btn-new-investigation']")
        new_btn.click()

        # Wait for the form to appear
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "[data-testid='input-unique-id']"))
        )

        # Wait a bit for form to fully render
        time.sleep(0.5)

        # Fill in required fields (NiceGUI inputs have the input nested inside)
        unique_id_container = driver.find_element(
            By.CSS_SELECTOR, "[data-testid='input-unique-id']"
        )
        unique_id_input = unique_id_container.find_element(By.TAG_NAME, "input")
        unique_id_input.send_keys("INV-TEST-001")

        title_container = driver.find_element(By.CSS_SELECTOR, "[data-testid='input-title']")
        title_input = title_container.find_element(By.TAG_NAME, "input")
        title_input.send_keys("Test Investigation from Selenium")

        # Click create button
        create_btn = driver.find_element(
            By.CSS_SELECTOR, "[data-testid='btn-create-investigation']"
        )
        create_btn.click()

        # Wait for tree node to appear (entity was created)
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "[data-testid^='tree-node-']"))
        )

        # Verify the entity appears in the tree with correct label
        tree_node = driver.find_element(By.CSS_SELECTOR, "[data-testid^='tree-node-']")
        assert "Test Investigation from Selenium" in tree_node.text

    def test_create_study_under_investigation(self, driver: webdriver.Chrome) -> None:
        """Test creating a Study under an existing Investigation."""
        driver.get("http://127.0.0.1:8099")

        # Wait for page and tree to load
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "[data-testid^='tree-node-']"))
        )

        # Click on the Investigation in the tree
        tree_node = driver.find_element(By.CSS_SELECTOR, "[data-testid^='tree-node-']")
        tree_node.click()

        # Wait for the detail view with "Add Child Entities"
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "[data-testid='btn-add-child-study']"))
        )

        # Click "+ Study" button
        add_study_btn = driver.find_element(By.CSS_SELECTOR, "[data-testid='btn-add-child-study']")
        add_study_btn.click()

        # Wait for form
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "[data-testid='input-unique-id']"))
        )

        # Wait a bit for form to fully render
        time.sleep(0.5)

        # Fill in Study fields
        unique_id_container = driver.find_element(
            By.CSS_SELECTOR, "[data-testid='input-unique-id']"
        )
        unique_id_input = unique_id_container.find_element(By.TAG_NAME, "input")
        unique_id_input.send_keys("STU-TEST-001")

        title_container = driver.find_element(By.CSS_SELECTOR, "[data-testid='input-title']")
        title_input = title_container.find_element(By.TAG_NAME, "input")
        title_input.send_keys("Test Study from Selenium")

        # Click create
        create_btn = driver.find_element(By.CSS_SELECTOR, "[data-testid='btn-create-study']")
        create_btn.click()

        # Wait for second tree node to appear
        time.sleep(1)
        tree_nodes = driver.find_elements(By.CSS_SELECTOR, "[data-testid^='tree-node-']")
        assert len(tree_nodes) >= 2

    def test_tree_shows_hierarchy(self, driver: webdriver.Chrome) -> None:
        """Test that the tree view shows the correct hierarchy."""
        driver.get("http://127.0.0.1:8099")

        # Wait for tree nodes
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "[data-testid^='tree-node-']"))
        )

        # Count tree nodes (should be at least 2: Investigation and Study)
        tree_nodes = driver.find_elements(By.CSS_SELECTOR, "[data-testid^='tree-node-']")
        assert len(tree_nodes) >= 2

        # Verify Investigation is shown
        page_text = driver.page_source
        assert "Investigation" in page_text
