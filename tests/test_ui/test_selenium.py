"""Selenium E2E tests for the NiceGUI web interface."""

import threading
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

from miappe_api.ui.app import MIAPPEApp

pytestmark = pytest.mark.ui  # Mark all tests in this module as UI tests


class TestUICreateEntities:
    """Test creating entities through the web interface."""

    @pytest.fixture(scope="class")
    def app_server(self) -> Generator[MIAPPEApp, None, None]:
        """Start the NiceGUI app in a background thread."""
        app = MIAPPEApp()

        # Run in a daemon thread so it stops when tests finish
        def run_server():
            app.run(host="127.0.0.1", port=8099)

        server_thread = threading.Thread(target=run_server, daemon=True)
        server_thread.start()

        # Wait for server to start
        time.sleep(2)

        yield app

    @pytest.fixture(scope="class")
    def driver(self, app_server: MIAPPEApp) -> Generator[webdriver.Chrome, None, None]:
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

    def test_create_investigation(self, driver: webdriver.Chrome, app_server: MIAPPEApp) -> None:
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

        # Fill in required fields
        unique_id_input = driver.find_element(
            By.CSS_SELECTOR, "[data-testid='input-unique-id'] input"
        )
        unique_id_input.send_keys("INV-TEST-001")

        title_input = driver.find_element(By.CSS_SELECTOR, "[data-testid='input-title'] input")
        title_input.send_keys("Test Investigation from Selenium")

        # Click create button
        create_btn = driver.find_element(
            By.CSS_SELECTOR, "[data-testid='btn-create-investigation']"
        )
        create_btn.click()

        # Wait for success notification or tree update
        time.sleep(1)

        # Verify the entity was added to the backend
        assert len(app_server.entity_tree) == 1
        node = app_server.entity_tree[0]
        assert node.entity_type == "Investigation"
        assert node.instance.unique_id == "INV-TEST-001"
        assert node.instance.title == "Test Investigation from Selenium"

    def test_create_study_under_investigation(
        self, driver: webdriver.Chrome, app_server: MIAPPEApp
    ) -> None:
        """Test creating a Study under an existing Investigation."""
        # First ensure we have an Investigation
        if not app_server.entity_tree:
            pytest.skip("No Investigation exists from previous test")

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

        # Fill in Study fields
        unique_id_input = driver.find_element(
            By.CSS_SELECTOR, "[data-testid='input-unique-id'] input"
        )
        unique_id_input.send_keys("STU-TEST-001")

        title_input = driver.find_element(By.CSS_SELECTOR, "[data-testid='input-title'] input")
        title_input.send_keys("Test Study from Selenium")

        # Click create
        create_btn = driver.find_element(By.CSS_SELECTOR, "[data-testid='btn-create-study']")
        create_btn.click()

        # Wait and verify
        time.sleep(1)

        # Study should be a child of the Investigation
        inv_node = app_server.entity_tree[0]
        assert len(inv_node.children) == 1
        study_node = inv_node.children[0]
        assert study_node.entity_type == "Study"
        assert study_node.instance.unique_id == "STU-TEST-001"

    def test_tree_shows_hierarchy(self, driver: webdriver.Chrome, app_server: MIAPPEApp) -> None:
        """Test that the tree view shows the correct hierarchy."""
        driver.get("http://127.0.0.1:8099")

        # Wait for tree nodes
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "[data-testid^='tree-node-']"))
        )

        # Count tree nodes (should be 2: Investigation and Study)
        tree_nodes = driver.find_elements(By.CSS_SELECTOR, "[data-testid^='tree-node-']")
        assert len(tree_nodes) >= 2

        # Verify the backend tree structure
        assert len(app_server.entity_tree) >= 1
        inv_node = app_server.entity_tree[0]
        assert inv_node.entity_type == "Investigation"
        assert len(inv_node.children) >= 1
