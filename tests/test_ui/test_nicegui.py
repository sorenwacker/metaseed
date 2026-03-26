"""NiceGUI native tests for the web interface.

Uses NiceGUI's built-in testing framework which is faster and more reliable
than Selenium for testing NiceGUI applications.

Tests use example data from the YAML specs for realistic, domain-appropriate values.

See: https://nicegui.io/documentation/section_testing
"""

import pytest
from nicegui import ui
from nicegui.testing import User

from miappe_api import miappe

# Register NiceGUI testing plugin
pytest_plugins = ["nicegui.testing.user_plugin"]

# Mark all tests as UI tests
pytestmark = pytest.mark.ui


# Get profile for example data
PROFILE = miappe()


class TestUIBasics:
    """Test basic UI functionality."""

    async def test_page_loads(self, user: User, app) -> None:
        """Test that the main page loads correctly."""
        _ = app
        await user.open("/")
        await user.should_see("MIAPPE-API")
        await user.should_see("Project")

    async def test_profile_selector_visible(self, user: User, app) -> None:
        """Test that the profile selector is visible."""
        _ = app
        await user.open("/")
        await user.should_see("miappe")

    async def test_investigation_button_visible(self, user: User, app) -> None:
        """Test that Investigation button is visible (root entity)."""
        _ = app
        await user.open("/")
        await user.should_see("+ Investigation")


class TestCreateInvestigation:
    """Test creating Investigation entities using spec examples."""

    async def test_create_investigation_from_spec_example(self, user: User, app) -> None:
        """Test creating an Investigation using example from spec."""
        _ = app
        await user.open("/")

        example = PROFILE.Investigation.example_data
        assert example, "Investigation should have example data in spec"

        # Click new Investigation
        user.find("+ Investigation").click()
        await user.should_see("Required Fields")

        # Fill in required fields from spec example
        unique_id_input = user.find(kind=ui.input, marker="unique_id")
        unique_id_input.type(example["unique_id"])

        title_input = user.find(kind=ui.input, marker="title")
        title_input.type(example["title"])

        # Click Create
        user.find("Create").click()

        # Should see the entity in tree
        await user.should_see(example["title"])
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

    async def test_investigation_form_uses_realistic_example_values(self, user: User, app) -> None:
        """Test that spec examples provide realistic domain values."""
        _ = app
        await user.open("/")

        example = PROFILE.Investigation.example_data

        # Verify example has domain-specific content
        assert "unique_id" in example
        assert "title" in example
        assert "Drought" in example["title"] or "Wheat" in example["title"]

        # Create using example
        user.find("+ Investigation").click()
        user.find(kind=ui.input, marker="unique_id").type(example["unique_id"])
        title_input = user.find(kind=ui.input, marker="title")
        title_input.type(example["title"])
        user.find("Create").click()

        await user.should_see(example["title"])


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

        unique_id_input = user.find(kind=ui.input, marker="unique_id")
        unique_id_input.type("TEST-VALUE")

        user.find("Clear").click()
        await user.should_see("Required Fields")


class TestSpecExamples:
    """Test that all entities have example data in specs."""

    def test_all_entities_have_examples(self) -> None:
        """Verify all MIAPPE entities have example data defined."""
        missing_examples = []

        for entity_name in PROFILE.entities:
            helper = getattr(PROFILE, entity_name)
            if not helper.example_data:
                missing_examples.append(entity_name)

        assert not missing_examples, f"Entities missing example data: {missing_examples}"

    def test_examples_contain_required_fields(self) -> None:
        """Verify examples include all required fields."""
        incomplete = []

        for entity_name in PROFILE.entities:
            helper = getattr(PROFILE, entity_name)
            example = helper.example_data
            required = set(helper.required_fields)

            if example:
                provided = set(example.keys())
                missing = required - provided
                if missing:
                    incomplete.append(f"{entity_name}: missing {missing}")

        assert not incomplete, f"Examples missing required fields: {incomplete}"

    def test_investigation_example_has_realistic_values(self) -> None:
        """Verify Investigation example uses domain-specific terminology."""
        example = PROFILE.Investigation.example_data

        # Should have agriculture/phenotyping related content
        title = example.get("title", "")
        assert any(
            term in title.lower()
            for term in ["drought", "wheat", "cultivar", "phenotyp", "plant", "field"]
        ), f"Investigation title should use domain terminology: {title}"

    def test_study_example_has_realistic_values(self) -> None:
        """Verify Study example uses domain-specific terminology."""
        example = PROFILE.Study.example_data

        # Should have experiment-related content
        assert "latitude" in example or "longitude" in example
        assert "start_date" in example or "end_date" in example

    def test_biological_material_example_has_scientific_names(self) -> None:
        """Verify BiologicalMaterial example uses scientific nomenclature."""
        example = PROFILE.BiologicalMaterial.example_data

        # Should have genus/species
        assert "genus" in example or "organism" in example
        assert "Triticum" in str(example) or "species" in example

    def test_person_example_has_contact_info(self) -> None:
        """Verify Person example has realistic contact information."""
        example = PROFILE.Person.example_data

        assert "name" in example
        assert "email" in example or "institution" in example


class TestEntityCreationProgrammatic:
    """Test creating entities programmatically using spec examples."""

    def test_create_all_entities_from_examples(self) -> None:
        """Test that all entities can be created with their example data."""
        for entity_name in PROFILE.entities:
            helper = getattr(PROFILE, entity_name)
            example = helper.example_data

            if example:
                # Filter to only include required fields
                required_data = {k: v for k, v in example.items() if k in helper.required_fields}

                # Should not raise validation error
                instance = helper.create(**required_data)
                assert instance is not None, f"Failed to create {entity_name}"

    def test_investigation_validates_with_example(self) -> None:
        """Test Investigation creation with full example data."""
        example = PROFILE.Investigation.example_data
        inv = PROFILE.Investigation.create(
            unique_id=example["unique_id"],
            title=example["title"],
        )
        assert inv.unique_id == example["unique_id"]
        assert inv.title == example["title"]

    def test_study_validates_with_example(self) -> None:
        """Test Study creation with full example data."""
        example = PROFILE.Study.example_data
        study = PROFILE.Study.create(
            unique_id=example["unique_id"],
            title=example["title"],
        )
        assert study.unique_id == example["unique_id"]
        assert study.title == example["title"]
