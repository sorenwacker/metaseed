"""Pytest configuration for NiceGUI UI tests."""

import pytest

from miappe_api.ui.app import MIAPPEApp


def pytest_configure(config):
    """Configure pytest for NiceGUI testing."""
    # Set the main file for NiceGUI testing
    config.inicfg["main_file"] = "tests/test_ui/main_test.py"


@pytest.fixture
def app():
    """Create and set up the MIAPPEApp for testing.

    This fixture initializes the UI and yields the app instance.
    The NiceGUI user fixture will use this for simulated interactions.
    """
    from nicegui import ui

    # Clear any existing UI elements from previous tests
    ui.page.default_page_builder = None

    test_app = MIAPPEApp()
    test_app._setup_ui()
    yield test_app

    # Clean up after test
    test_app.entity_tree.clear()
    test_app.nodes_by_id.clear()
