"""Tests to verify example data files load correctly.

These tests ensure that the example YAML files in the examples/ directory
can be successfully loaded and validated against the corresponding models.
"""

from pathlib import Path

import pytest
import yaml

from metaseed.models import get_model
from metaseed.specs.loader import SpecLoader

EXAMPLES_DIR = Path(__file__).parent.parent / "examples"


def get_all_example_files() -> list[tuple[str, str, Path]]:
    """Get all example files with their profile and version.

    Returns:
        List of (profile_name, version, file_path) tuples.
    """
    examples = []
    if not EXAMPLES_DIR.exists():
        return examples

    for profile_dir in EXAMPLES_DIR.iterdir():
        if not profile_dir.is_dir():
            continue
        profile_name = profile_dir.name

        for version_dir in profile_dir.iterdir():
            if not version_dir.is_dir():
                continue
            version = version_dir.name

            for yaml_file in version_dir.glob("*.yaml"):
                examples.append((profile_name, version, yaml_file))

    return examples


def get_root_entity(profile: str, version: str) -> str:
    """Get the root entity type for a profile/version."""
    loader = SpecLoader(profile=profile)
    spec = loader.load_profile(version, profile)
    return spec.root_entity or "Investigation"


class TestExampleFilesLoad:
    """Tests that all example files can be loaded and validated."""

    @pytest.mark.parametrize(
        "profile,version,example_file",
        get_all_example_files(),
        ids=lambda x: str(x) if isinstance(x, Path) else x,
    )
    def test_example_loads_as_root_entity(
        self, profile: str, version: str, example_file: Path
    ) -> None:
        """Each example file should load as a valid root entity model."""
        # Load the YAML file
        with open(example_file, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        # Get the root entity type for this profile
        root_entity = get_root_entity(profile, version)

        # Get the model for this profile/version
        Model = get_model(root_entity, version, profile=profile)

        # This should not raise a validation error
        instance = Model(**data)

        # Verify basic structure
        assert instance is not None
        if hasattr(instance, "model_dump"):
            dumped = instance.model_dump(exclude_none=True)
            # Should have at least one field populated
            assert len(dumped) > 0


class TestExampleFilesHaveRequiredFields:
    """Tests that example files contain required metadata fields."""

    @pytest.mark.parametrize(
        "profile,version,example_file",
        get_all_example_files(),
        ids=lambda x: str(x) if isinstance(x, Path) else x,
    )
    def test_example_has_identifier(self, profile: str, version: str, example_file: Path) -> None:
        """Each example should have a unique identifier field."""
        with open(example_file, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        # Check for common identifier field names (varies by profile)
        identifier_fields = ["unique_id", "identifier", "id", "occurrenceID"]
        has_identifier = any(field in data and data[field] for field in identifier_fields)
        assert has_identifier, f"Example {example_file.name} missing identifier field"

    @pytest.mark.parametrize(
        "profile,version,example_file",
        get_all_example_files(),
        ids=lambda x: str(x) if isinstance(x, Path) else x,
    )
    def test_example_has_title(self, profile: str, version: str, example_file: Path) -> None:
        """Each example should have a title field (except darwin-core)."""
        # darwin-core uses Occurrence as root which doesn't have title
        if profile == "darwin-core":
            pytest.skip("darwin-core Occurrence doesn't have a title field")

        with open(example_file, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        assert data.get("title"), f"Example {example_file.name} missing title"
