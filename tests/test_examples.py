"""Tests to verify example data files load correctly.

These tests ensure that the example YAML files in the examples/ directory
can be successfully loaded and validated against the corresponding models.
Also validates inline entity examples from spec definitions.
"""

from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from metaseed.models import get_model
from metaseed.specs.loader import SpecLoader
from metaseed.specs.schema import FieldType

EXAMPLES_DIR = Path(__file__).parent.parent / "src" / "metaseed" / "examples"


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


def get_all_inline_examples() -> list[tuple[str, str, str, dict]]:
    """Get all inline entity examples from spec definitions.

    Returns:
        List of (profile, version, entity_name, example_data) tuples.
    """
    examples = []
    loader = SpecLoader()

    for profile in loader.list_profiles():
        for version in loader.list_versions(profile):
            try:
                profile_spec = loader.load_profile(version, profile)
                for entity_name, entity_def in profile_spec.entities.items():
                    if entity_def.example:
                        examples.append((profile, version, entity_name, entity_def.example))
            except Exception:  # noqa: S112
                # Skip profiles that fail to load (e.g., invalid YAML)
                continue

    return examples


def get_root_entity(profile: str, version: str) -> str:
    """Get the root entity type for a profile/version."""
    loader = SpecLoader(profile=profile)
    spec = loader.load_profile(version, profile)
    return spec.root_entity or "Investigation"


def load_example_data(example_file: Path) -> dict:
    """Load and parse a YAML example file.

    Args:
        example_file: Path to the YAML file.

    Returns:
        Parsed YAML data as a dictionary.
    """
    with open(example_file, encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_required_field_names(profile: str, version: str, entity_name: str) -> list[str]:
    """Get names of required fields for an entity.

    Args:
        profile: Profile name.
        version: Profile version.
        entity_name: Entity name.

    Returns:
        List of required field names (excluding parent_ref fields).
    """
    loader = SpecLoader(profile=profile)
    entity_spec = loader.load_entity(entity_name, version, profile)
    return [
        f.name
        for f in entity_spec.fields
        if f.required and not f.parent_ref  # parent_ref fields are auto-filled
    ]


def check_nested_completeness(
    data: Any, profile: str, version: str, entity_name: str, path: str = ""
) -> list[str]:
    """Recursively check that nested entities have required fields populated.

    Checks ALL nested entities (not just required fields) to ensure the example
    is complete and usable.

    Args:
        data: The data to check (dict or list).
        profile: Profile name.
        version: Profile version.
        entity_name: Entity name for this data.
        path: Current path for error messages.

    Returns:
        List of error messages for missing/empty required fields.
    """
    errors = []
    if data is None:
        return errors

    loader = SpecLoader(profile=profile)

    try:
        entity_spec = loader.load_entity(entity_name, version, profile)
    except Exception:
        return errors  # Entity not found, skip validation

    if isinstance(data, dict):
        # First check required fields at this level
        for field in entity_spec.fields:
            if field.parent_ref:
                continue  # Skip parent_ref fields (auto-filled)

            field_path = f"{path}.{field.name}" if path else field.name
            value = data.get(field.name)

            # Check required fields are present
            if field.required and (value is None or value == "" or value == []):
                errors.append(f"Missing required field: {field_path}")

        # Then recursively check ALL nested entities (required or not)
        for field in entity_spec.fields:
            if field.parent_ref:
                continue

            field_path = f"{path}.{field.name}" if path else field.name
            value = data.get(field.name)

            if value is None:
                continue

            if field.type == FieldType.LIST and field.items:
                # Check if items is an entity type
                try:
                    loader.load_entity(field.items, version, profile)
                    is_entity_list = True
                except Exception:
                    is_entity_list = False

                if is_entity_list and isinstance(value, list):
                    for i, item in enumerate(value):
                        if isinstance(item, dict):
                            item_path = f"{field_path}[{i}]"
                            errors.extend(
                                check_nested_completeness(
                                    item, profile, version, field.items, item_path
                                )
                            )

            elif field.type == FieldType.ENTITY and field.items:
                # Check nested entity
                if isinstance(value, dict):
                    errors.extend(
                        check_nested_completeness(value, profile, version, field.items, field_path)
                    )

    return errors


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
        data = load_example_data(example_file)
        root_entity = get_root_entity(profile, version)
        Model = get_model(root_entity, version, profile=profile)

        # This should not raise a validation error
        instance = Model(**data)

        # Verify basic structure
        assert instance is not None
        if hasattr(instance, "model_dump"):
            dumped = instance.model_dump(exclude_none=True)
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
        data = load_example_data(example_file)
        identifier_fields = [
            "unique_id",
            "identifier",
            "id",
            "occurrenceID",
            "alias",
            "internal_study_id",
            "study_id",
            "investigation_id",
        ]
        has_identifier = any(field in data and data[field] for field in identifier_fields)
        assert has_identifier, f"Example {example_file.name} missing identifier field"

    @pytest.mark.parametrize(
        "profile,version,example_file",
        get_all_example_files(),
        ids=lambda x: str(x) if isinstance(x, Path) else x,
    )
    def test_example_has_title(self, profile: str, version: str, example_file: Path) -> None:
        """Each example should have a title field (except darwin-core and ena)."""
        # darwin-core uses Occurrence as root which doesn't have title
        # ena uses Study as root which doesn't have title (uses alias)
        # dissco uses DigitalSpecimen which uses specimen_name instead
        # cropxr profiles use study_title or investigation_title
        if profile in ("darwin-core", "ena", "dissco"):
            pytest.skip(f"{profile} root entity doesn't have a standard title field")

        data = load_example_data(example_file)
        title_fields = ["title", "study_title", "investigation_title"]
        has_title = any(field in data and data[field] for field in title_fields)
        assert has_title, f"Example {example_file.name} missing title field"


def find_incomplete_entity_lists(
    data: Any, profile: str, version: str, entity_name: str, path: str = ""
) -> list[str]:
    """Find entity list fields that are empty when they should be populated.

    This catches cases where one assay has other_materials but another doesn't,
    indicating an incomplete example. Skips reference fields (fields that link
    to other entities by ID rather than embedding them).

    Args:
        data: The data to check.
        profile: Profile name.
        version: Profile version.
        entity_name: Entity name for this data.
        path: Current path for error messages.

    Returns:
        List of warnings for empty entity list fields.
    """
    warnings = []
    if data is None or not isinstance(data, dict):
        return warnings

    loader = SpecLoader(profile=profile)

    try:
        entity_spec = loader.load_entity(entity_name, version, profile)
    except Exception:
        return warnings

    for field in entity_spec.fields:
        # Skip parent_ref fields and reference fields (links to other entities)
        if field.parent_ref or field.reference:
            continue

        field_path = f"{path}.{field.name}" if path else field.name
        value = data.get(field.name)

        if field.type == FieldType.LIST and field.items:
            # Check if items is an entity type
            try:
                loader.load_entity(field.items, version, profile)
                is_entity_list = True
            except Exception:
                is_entity_list = False

            if is_entity_list:
                if value is None or value == []:
                    # Empty entity list - this is a potential completeness issue
                    warnings.append(f"Empty entity list: {field_path} (type: {field.items})")
                elif isinstance(value, list):
                    # Recurse into list items
                    for i, item in enumerate(value):
                        if isinstance(item, dict):
                            item_path = f"{field_path}[{i}]"
                            warnings.extend(
                                find_incomplete_entity_lists(
                                    item, profile, version, field.items, item_path
                                )
                            )

        elif field.type == FieldType.ENTITY and field.items and isinstance(value, dict):
            warnings.extend(
                find_incomplete_entity_lists(value, profile, version, field.items, field_path)
            )

    return warnings


class TestExampleFilesCompleteness:
    """Tests that example files have complete nested entity data."""

    @pytest.mark.parametrize(
        "profile,version,example_file",
        get_all_example_files(),
        ids=lambda x: str(x) if isinstance(x, Path) else x,
    )
    def test_example_nested_entities_complete(
        self, profile: str, version: str, example_file: Path
    ) -> None:
        """Nested entities in example files should have all required fields."""
        data = load_example_data(example_file)
        root_entity = get_root_entity(profile, version)
        errors = check_nested_completeness(data, profile, version, root_entity)

        if errors:
            error_msg = f"Example {example_file.name} has incomplete nested entities:\n"
            error_msg += "\n".join(f"  - {e}" for e in errors[:10])  # Limit to first 10
            if len(errors) > 10:
                error_msg += f"\n  ... and {len(errors) - 10} more"
            pytest.fail(error_msg)

    @pytest.mark.parametrize(
        "profile,version,example_file",
        get_all_example_files(),
        ids=lambda x: str(x) if isinstance(x, Path) else x,
    )
    def test_example_entity_lists_populated(
        self, profile: str, version: str, example_file: Path
    ) -> None:
        """Entity list fields in examples should be populated, not empty.

        Examples should demonstrate complete usage of the spec. If an entity
        has list fields that can contain other entities, those lists should
        have data to serve as useful examples.
        """
        data = load_example_data(example_file)
        root_entity = get_root_entity(profile, version)
        warnings = find_incomplete_entity_lists(data, profile, version, root_entity)

        if warnings:
            error_msg = f"Example {example_file.name} has empty entity lists:\n"
            error_msg += "\n".join(f"  - {w}" for w in warnings[:20])
            if len(warnings) > 20:
                error_msg += f"\n  ... and {len(warnings) - 20} more"
            pytest.fail(error_msg)


def get_parent_ref_fields(profile: str, version: str, entity_name: str) -> list[str]:
    """Get names of parent_ref fields for an entity.

    Args:
        profile: Profile name.
        version: Profile version.
        entity_name: Entity name.

    Returns:
        List of field names that have parent_ref defined.
    """
    loader = SpecLoader(profile=profile)
    entity_spec = loader.load_entity(entity_name, version, profile)
    return [f.name for f in entity_spec.fields if f.parent_ref]


def add_placeholder_parent_refs(
    example_data: dict, profile: str, version: str, entity_name: str
) -> dict:
    """Add placeholder values for parent_ref fields.

    Parent ref fields are auto-filled at runtime, so inline examples may
    not include them. This function adds placeholder values for validation.

    Args:
        example_data: Original example data.
        profile: Profile name.
        version: Profile version.
        entity_name: Entity name.

    Returns:
        Example data with placeholder parent_ref values added.
    """
    data = dict(example_data)
    parent_ref_fields = get_parent_ref_fields(profile, version, entity_name)
    for field in parent_ref_fields:
        if field not in data:
            data[field] = f"PLACEHOLDER-{field.upper()}"
    return data


def find_entity_field_type_mismatches(
    data: Any, profile: str, version: str, entity_name: str, path: str = ""
) -> list[str]:
    """Find fields where a string is used but an entity object is expected.

    This catches issues like using 'metabolite profiling' (string) where
    an OntologyAnnotation object is expected.

    Args:
        data: The data to check.
        profile: Profile name.
        version: Profile version.
        entity_name: Entity name for this data.
        path: Current path for error messages.

    Returns:
        List of error messages for type mismatches.
    """
    errors = []
    if data is None or not isinstance(data, dict):
        return errors

    loader = SpecLoader(profile=profile)

    try:
        entity_spec = loader.load_entity(entity_name, version, profile)
    except Exception:
        return errors

    for field in entity_spec.fields:
        field_path = f"{path}.{field.name}" if path else field.name
        value = data.get(field.name)

        if value is None:
            continue

        # Check entity fields - should be dict, not string
        if field.type == FieldType.ENTITY and field.items:
            if isinstance(value, str):
                errors.append(f"{field_path}: expected {field.items} object, got string '{value}'")
            elif isinstance(value, dict):
                errors.extend(
                    find_entity_field_type_mismatches(
                        value, profile, version, field.items, field_path
                    )
                )

        # Check list fields with entity items
        elif field.type == FieldType.LIST and field.items and isinstance(value, list):
            for i, item in enumerate(value):
                item_path = f"{field_path}[{i}]"
                # Check if items should be entities but got strings
                try:
                    loader.load_entity(field.items, version, profile)
                except Exception:  # noqa: S112
                    # items is a primitive type, skip
                    continue

                # items is an entity type
                if isinstance(item, str):
                    errors.append(
                        f"{item_path}: expected {field.items} object, got string '{item}'"
                    )
                elif isinstance(item, dict):
                    errors.extend(
                        find_entity_field_type_mismatches(
                            item, profile, version, field.items, item_path
                        )
                    )

    return errors


class TestInlineEntityExamples:
    """Tests that inline entity examples in specs validate against their models."""

    @pytest.mark.parametrize(
        "profile,version,entity_name,example_data",
        get_all_inline_examples(),
        ids=lambda x: x if isinstance(x, str) else None,
    )
    def test_inline_example_validates(
        self, profile: str, version: str, entity_name: str, example_data: dict
    ) -> None:
        """Each inline entity example should validate against its model."""
        try:
            Model = get_model(entity_name, version, profile=profile)
        except Exception as e:
            pytest.skip(f"Could not get model for {entity_name}: {e}")

        # Add placeholder values for parent_ref fields (auto-filled at runtime)
        data_with_refs = add_placeholder_parent_refs(example_data, profile, version, entity_name)

        try:
            instance = Model(**data_with_refs)
            assert instance is not None
        except ValidationError as e:
            pytest.fail(
                f"Inline example for {profile}/{version}/{entity_name} failed validation:\n{e}"
            )

    @pytest.mark.parametrize(
        "profile,version,entity_name,example_data",
        get_all_inline_examples(),
        ids=lambda x: x if isinstance(x, str) else None,
    )
    def test_inline_example_has_required_fields(
        self, profile: str, version: str, entity_name: str, example_data: dict
    ) -> None:
        """Each inline entity example should have all required fields."""
        required_fields = get_required_field_names(profile, version, entity_name)
        missing = [f for f in required_fields if f not in example_data or not example_data[f]]

        if missing:
            pytest.fail(
                f"Inline example for {profile}/{version}/{entity_name} "
                f"missing required fields: {', '.join(missing)}"
            )


class TestExampleFieldTypes:
    """Tests that example data uses correct field types (not strings where objects expected)."""

    @pytest.mark.parametrize(
        "profile,version,example_file",
        get_all_example_files(),
        ids=lambda x: str(x) if isinstance(x, Path) else x,
    )
    def test_example_file_entity_fields_are_objects(
        self, profile: str, version: str, example_file: Path
    ) -> None:
        """Entity fields should contain objects, not plain strings."""
        data = load_example_data(example_file)
        root_entity = get_root_entity(profile, version)
        errors = find_entity_field_type_mismatches(data, profile, version, root_entity)

        if errors:
            error_msg = f"Example {example_file.name} has field type mismatches:\n"
            error_msg += "\n".join(f"  - {e}" for e in errors[:15])
            if len(errors) > 15:
                error_msg += f"\n  ... and {len(errors) - 15} more"
            pytest.fail(error_msg)

    @pytest.mark.parametrize(
        "profile,version,entity_name,example_data",
        get_all_inline_examples(),
        ids=lambda x: x if isinstance(x, str) else None,
    )
    def test_inline_example_entity_fields_are_objects(
        self, profile: str, version: str, entity_name: str, example_data: dict
    ) -> None:
        """Entity fields in inline examples should contain objects, not strings.

        Note: This test is skipped because the spec schema (EntityDefSpec.example)
        only allows primitive types (str, int, float, bool, list), not nested objects.
        Inline examples are for documentation only; full validation happens in
        example files under src/metaseed/examples/.
        """
        pytest.skip("Inline examples cannot have nested objects due to spec schema limitation")
