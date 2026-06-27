"""Tests to verify example data files load correctly.

These tests ensure that the example YAML files in the examples/ directory
can be successfully loaded and validated against the corresponding models.
Also validates inline entity examples from spec definitions.
"""

from collections.abc import Callable
from functools import lru_cache
from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from metaseed.models import get_model
from metaseed.specs.loader import SpecLoader, SpecLoadError
from metaseed.specs.schema import EntityDefSpec, FieldSpec, FieldType

EXAMPLES_DIR = Path(__file__).parent.parent / "src" / "metaseed" / "examples"

# Common field names used across different profiles
IDENTIFIER_FIELDS = frozenset(
    {
        "unique_id",
        "identifier",
        "id",
        "occurrenceID",
        "alias",
        "internal_study_id",
        "study_id",
        "investigation_id",
    }
)

TITLE_FIELDS = frozenset({"title", "study_title", "investigation_title"})

# Profiles that don't have standard title fields
PROFILES_WITHOUT_TITLE = frozenset({"darwin-core", "ena", "dissco"})


@lru_cache(maxsize=32)
def _get_cached_loader(profile: str) -> SpecLoader:
    """Get a cached SpecLoader instance for a profile."""
    return SpecLoader(profile=profile)


def _try_load_entity(
    loader: SpecLoader, entity_name: str, version: str, profile: str
) -> EntityDefSpec | None:
    """Try to load an entity spec, returning None if not found."""
    try:
        return loader.load_entity(entity_name, version, profile)
    except (KeyError, FileNotFoundError, ValueError, SpecLoadError):
        return None


def _is_entity_type(loader: SpecLoader, items: str, version: str, profile: str) -> bool:
    """Check if items refers to an entity type (not a primitive)."""
    return _try_load_entity(loader, items, version, profile) is not None


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
        # Validate only built-in (repo) specs. User-defined specs under the
        # data directory are runtime artifacts, not part of the test suite;
        # enumerating them makes the suite depend on the developer's machine.
        if loader.is_user_defined(profile):
            continue
        for version in loader.list_versions(profile):
            try:
                profile_spec = loader.load_profile(version, profile)
                for entity_name, entity_def in profile_spec.entities.items():
                    if entity_def.example:
                        examples.append(
                            (profile, version, entity_name, entity_def.example)
                        )
            except (KeyError, FileNotFoundError, yaml.YAMLError, SpecLoadError):
                # Skip profiles that fail to load
                continue

    return examples


def get_root_entity(profile: str, version: str) -> str:
    """Get the root entity type for a profile/version."""
    loader = _get_cached_loader(profile)
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
    loader = _get_cached_loader(profile)
    entity_spec = loader.load_entity(entity_name, version, profile)
    return [
        f.name
        for f in entity_spec.fields
        if f.required and not f.parent_ref  # parent_ref fields are auto-filled
    ]


def traverse_entity_tree(
    data: Any,
    profile: str,
    version: str,
    entity_name: str,
    visitor: Callable[[dict, EntityDefSpec, FieldSpec, str, Any], list[str]],
    path: str = "",
) -> list[str]:
    """Generic entity tree traversal with visitor callback.

    Recursively traverses entity data, calling the visitor function for each field.
    The visitor can inspect the field and value to collect errors/warnings.

    Args:
        data: The data to traverse (dict or None).
        profile: Profile name.
        version: Profile version.
        entity_name: Entity name for this data.
        visitor: Callback function(data, entity_spec, field, path, value) -> list[str].
        path: Current path for error messages.

    Returns:
        Collected results from all visitor calls.
    """
    results: list[str] = []
    if data is None or not isinstance(data, dict):
        return results

    loader = _get_cached_loader(profile)
    entity_spec = _try_load_entity(loader, entity_name, version, profile)
    if entity_spec is None:
        return results

    for field in entity_spec.fields:
        if field.parent_ref:
            continue  # Skip parent_ref fields (auto-filled)

        field_path = f"{path}.{field.name}" if path else field.name
        value = data.get(field.name)

        # Call visitor for this field
        results.extend(visitor(data, entity_spec, field, field_path, value))

        # Recurse into nested entities
        if value is None:
            continue

        if (
            field.type == FieldType.LIST
            and field.items
            and _is_entity_type(loader, field.items, version, profile)
            and isinstance(value, list)
        ):
            for i, item in enumerate(value):
                if isinstance(item, dict):
                    item_path = f"{field_path}[{i}]"
                    results.extend(
                        traverse_entity_tree(
                            item, profile, version, field.items, visitor, item_path
                        )
                    )

        elif field.type == FieldType.ENTITY and field.items and isinstance(value, dict):
            results.extend(
                traverse_entity_tree(
                    value, profile, version, field.items, visitor, field_path
                )
            )

    return results


def _check_required_fields_visitor(
    data: dict, entity_spec: EntityDefSpec, field: FieldSpec, path: str, value: Any
) -> list[str]:
    """Visitor that checks for missing required fields."""
    if field.required and (value is None or value in ("", [])):
        return [f"Missing required field: {path}"]
    return []


def _check_empty_entity_lists_visitor(
    data: dict, entity_spec: EntityDefSpec, field: FieldSpec, path: str, value: Any
) -> list[str]:
    """Visitor that checks for empty entity list fields."""
    if field.reference:
        return []  # Skip reference fields (links to other entities)

    if field.type == FieldType.LIST and field.items and (value is None or value == []):
        # Only report if it's potentially an entity list (has items defined)
        return [f"Empty entity list: {path} (type: {field.items})"]
    return []


def _check_type_mismatch_visitor(
    data: dict, entity_spec: EntityDefSpec, field: FieldSpec, path: str, value: Any
) -> list[str]:
    """Visitor that checks for type mismatches (strings where objects expected)."""
    errors = []
    if value is None:
        return errors

    # Check entity fields - should be dict, not string
    if field.type == FieldType.ENTITY and field.items:
        if isinstance(value, str):
            errors.append(
                f"{path}: expected {field.items} object, got string '{value}'"
            )

    # Check list fields with entity items - items should be dicts, not strings
    elif field.type == FieldType.LIST and field.items and isinstance(value, list):
        for i, item in enumerate(value):
            if isinstance(item, str):
                # This will be checked only if items is an entity type
                # The traversal handles this, but we flag strings in entity lists
                errors.append(
                    f"{path}[{i}]: expected {field.items} object, got string '{item}'"
                )

    return errors


def check_nested_completeness(
    data: Any, profile: str, version: str, entity_name: str, path: str = ""
) -> list[str]:
    """Recursively check that nested entities have required fields populated.

    Args:
        data: The data to check (dict or list).
        profile: Profile name.
        version: Profile version.
        entity_name: Entity name for this data.
        path: Current path for error messages.

    Returns:
        List of error messages for missing/empty required fields.
    """
    return traverse_entity_tree(
        data, profile, version, entity_name, _check_required_fields_visitor, path
    )


def find_incomplete_entity_lists(
    data: Any, profile: str, version: str, entity_name: str, path: str = ""
) -> list[str]:
    """Find entity list fields that are empty when they should be populated.

    Args:
        data: The data to check.
        profile: Profile name.
        version: Profile version.
        entity_name: Entity name for this data.
        path: Current path for error messages.

    Returns:
        List of warnings for empty entity list fields.
    """
    # Custom traversal needed here because we only want to report empty lists
    # for entity types, not primitive lists
    warnings: list[str] = []
    if data is None or not isinstance(data, dict):
        return warnings

    loader = _get_cached_loader(profile)
    entity_spec = _try_load_entity(loader, entity_name, version, profile)
    if entity_spec is None:
        return warnings

    for field in entity_spec.fields:
        if field.parent_ref or field.reference:
            continue

        field_path = f"{path}.{field.name}" if path else field.name
        value = data.get(field.name)

        if field.type == FieldType.LIST and field.items:
            if _is_entity_type(loader, field.items, version, profile):
                # Only warn about empty lists if the field is required
                if (value is None or value == []) and field.required:
                    warnings.append(
                        f"Empty entity list: {field_path} (type: {field.items})"
                    )
                elif isinstance(value, list):
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
                find_incomplete_entity_lists(
                    value, profile, version, field.items, field_path
                )
            )

    return warnings


def find_entity_field_type_mismatches(
    data: Any, profile: str, version: str, entity_name: str, path: str = ""
) -> list[str]:
    """Find fields where a string is used but an entity object is expected.

    Args:
        data: The data to check.
        profile: Profile name.
        version: Profile version.
        entity_name: Entity name for this data.
        path: Current path for error messages.

    Returns:
        List of error messages for type mismatches.
    """
    errors: list[str] = []
    if data is None or not isinstance(data, dict):
        return errors

    loader = _get_cached_loader(profile)
    entity_spec = _try_load_entity(loader, entity_name, version, profile)
    if entity_spec is None:
        return errors

    for field in entity_spec.fields:
        field_path = f"{path}.{field.name}" if path else field.name
        value = data.get(field.name)

        if value is None:
            continue

        if field.type == FieldType.ENTITY and field.items:
            if isinstance(value, str):
                errors.append(
                    f"{field_path}: expected {field.items} object, got string '{value}'"
                )
            elif isinstance(value, dict):
                errors.extend(
                    find_entity_field_type_mismatches(
                        value, profile, version, field.items, field_path
                    )
                )

        elif (
            field.type == FieldType.LIST
            and field.items
            and isinstance(value, list)
            and _is_entity_type(loader, field.items, version, profile)
        ):
            for i, item in enumerate(value):
                item_path = f"{field_path}[{i}]"
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
    def test_example_has_identifier(
        self, profile: str, version: str, example_file: Path
    ) -> None:
        """Each example should have a unique identifier field."""
        data = load_example_data(example_file)
        has_identifier = any(
            field in data and data[field] for field in IDENTIFIER_FIELDS
        )
        assert has_identifier, f"Example {example_file.name} missing identifier field"

    @pytest.mark.parametrize(
        "profile,version,example_file",
        get_all_example_files(),
        ids=lambda x: str(x) if isinstance(x, Path) else x,
    )
    def test_example_has_title(
        self, profile: str, version: str, example_file: Path
    ) -> None:
        """Each example should have a title field (except certain profiles)."""
        if profile in PROFILES_WITHOUT_TITLE:
            pytest.skip(f"{profile} root entity doesn't have a standard title field")

        data = load_example_data(example_file)
        has_title = any(field in data and data[field] for field in TITLE_FIELDS)
        assert has_title, f"Example {example_file.name} missing title field"


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
            error_msg += "\n".join(f"  - {e}" for e in errors[:10])
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
    loader = _get_cached_loader(profile)
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
        except (KeyError, ValueError, FileNotFoundError, SpecLoadError) as e:
            pytest.skip(f"Could not get model for {entity_name}: {e}")

        data_with_refs = add_placeholder_parent_refs(
            example_data, profile, version, entity_name
        )

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
        missing = [
            f for f in required_fields if f not in example_data or not example_data[f]
        ]

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
