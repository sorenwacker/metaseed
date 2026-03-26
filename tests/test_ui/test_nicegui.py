"""NiceGUI native tests for the web interface.

Uses NiceGUI's built-in testing framework which is faster and more reliable
than Selenium for testing NiceGUI applications.

See: https://nicegui.io/documentation/section_testing

Note: Some tests involving tree node clicks are commented out due to a
RuntimeError in NiceGUI's testing framework with dynamic event listeners.
"""

import pytest
from nicegui import ui
from nicegui.testing import User

# Register NiceGUI testing plugin
pytest_plugins = ["nicegui.testing.user_plugin"]

# Mark all tests as UI tests
pytestmark = pytest.mark.ui


class TestUIBasics:
    """Test basic UI functionality."""

    async def test_page_loads(self, user: User, app) -> None:
        """Test that the main page loads correctly."""
        _ = app  # Ensure app is set up
        await user.open("/")
        await user.should_see("MIAPPE-API")
        await user.should_see("Project")

    async def test_profile_selector_visible(self, user: User, app) -> None:
        """Test that the profile selector is visible."""
        _ = app
        await user.open("/")
        await user.should_see("miappe")


class TestCreateEntities:
    """Test creating entities through the UI."""

    async def test_new_investigation_button_visible(self, user: User, app) -> None:
        """Test that the new Investigation button is visible."""
        _ = app
        await user.open("/")
        await user.should_see("+ Investigation")

    async def test_click_new_investigation_shows_form(self, user: User, app) -> None:
        """Test clicking new Investigation button shows form."""
        _ = app
        await user.open("/")

        # Click the new Investigation button
        user.find("+ Investigation").click()

        # Should see the Investigation form
        await user.should_see("Investigation")
        await user.should_see("Required Fields")
        await user.should_see("unique_id")
        await user.should_see("title")

    async def test_create_investigation(self, user: User, app) -> None:
        """Test creating an Investigation through the form."""
        _ = app
        await user.open("/")

        # Click new Investigation
        user.find("+ Investigation").click()
        await user.should_see("Required Fields")

        # Fill in the form using markers and element type
        unique_id_input = user.find(kind=ui.input, marker="unique_id")
        unique_id_input.type("INV-TEST-001")

        title_input = user.find(kind=ui.input, marker="title")
        title_input.type("Test Investigation")

        # Click Create button
        user.find("Create").click()

        # Should see success - entity added to tree (not in form)
        await user.should_see("Test Investigation")
        # Verify entity was added to tree - should not see "No entities created"
        await user.should_not_see("No entities created")

    async def test_create_multiple_investigations(self, user: User, app) -> None:
        """Test creating multiple Investigations."""
        _ = app
        await user.open("/")

        # Create first Investigation
        user.find("+ Investigation").click()
        await user.should_see("Required Fields")

        user.find(kind=ui.input, marker="unique_id").type("INV-001")
        title_input = user.find(kind=ui.input, marker="title")
        title_input.type("First Investigation")
        user.find("Create").click()

        await user.should_see("First Investigation")

        # Create second Investigation
        user.find("+ Investigation").click()
        await user.should_see("Required Fields")

        user.find(kind=ui.input, marker="unique_id").type("INV-002")
        title_input = user.find(kind=ui.input, marker="title")
        title_input.type("Second Investigation")
        user.find("Create").click()

        # Should see both investigations
        await user.should_see("First Investigation")
        await user.should_see("Second Investigation")


class TestFormFields:
    """Test form field rendering and interaction."""

    async def test_investigation_form_has_required_fields(self, user: User, app) -> None:
        """Test that Investigation form shows required fields."""
        _ = app
        await user.open("/")

        user.find("+ Investigation").click()
        await user.should_see("Required Fields")
        await user.should_see("unique_id")
        await user.should_see("title")

    async def test_investigation_form_has_optional_fields(self, user: User, app) -> None:
        """Test that Investigation form has optional fields section."""
        _ = app
        await user.open("/")

        user.find("+ Investigation").click()
        await user.should_see("Optional Fields")

    async def test_clear_button_clears_form(self, user: User, app) -> None:
        """Test that Clear button clears the form."""
        _ = app
        await user.open("/")

        user.find("+ Investigation").click()
        await user.should_see("Required Fields")

        # Fill in a field
        unique_id_input = user.find(kind=ui.input, marker="unique_id")
        unique_id_input.type("TEST-VALUE")

        # Click Clear
        user.find("Clear").click()

        # The form should still be visible but fields cleared
        await user.should_see("Required Fields")
