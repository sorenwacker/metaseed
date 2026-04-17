"""Dataset validation with reference integrity checking.

This module provides validation for entire datasets, checking that
references between entities are valid.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Self

import yaml

from metaseed.profiles import ProfileFactory
from metaseed.specs.loader import SpecLoader
from metaseed.validators.base import ValidationError
from metaseed.validators.engine import create_engine_for_entity


@dataclass
class DatasetValidationResult:
    """Result of dataset validation.

    Attributes:
        errors: List of validation errors.
        warnings: List of validation warnings.
        entity_counts: Count of entities by type.
        files_checked: List of files that were validated.
    """

    errors: list[ValidationError] = field(default_factory=list)
    warnings: list[ValidationError] = field(default_factory=list)
    entity_counts: dict[str, int] = field(default_factory=dict)
    files_checked: list[Path] = field(default_factory=list)

    @property
    def is_valid(self: Self) -> bool:
        """Return True if no errors were found."""
        return len(self.errors) == 0

    def merge(self: Self, other: DatasetValidationResult) -> None:
        """Merge another result into this one.

        Args:
            other: The result to merge.
        """
        self.errors.extend(other.errors)
        self.warnings.extend(other.warnings)
        self.files_checked.extend(other.files_checked)
        for entity_type, count in other.entity_counts.items():
            self.entity_counts[entity_type] = self.entity_counts.get(entity_type, 0) + count


class IdRegistry:
    """Tracks entity IDs for reference validation.

    Used to collect all IDs in a first pass, then validate references
    in a second pass.

    Example:
        >>> registry = IdRegistry()
        >>> registry.register("study", "STU001")
        >>> registry.exists("study", "STU001")
        True
        >>> registry.exists("study", "STU999")
        False
    """

    def __init__(self: Self) -> None:
        """Initialize an empty ID registry."""
        self._ids: dict[str, set[str]] = {}

    def register(self: Self, entity_type: str, entity_id: str) -> None:
        """Register an entity ID.

        Args:
            entity_type: The type of entity (e.g., "study", "observation_unit").
            entity_id: The unique ID of the entity.
        """
        if entity_type not in self._ids:
            self._ids[entity_type] = set()
        self._ids[entity_type].add(entity_id)

    def exists(self: Self, entity_type: str, entity_id: str) -> bool:
        """Check if an entity ID exists.

        Args:
            entity_type: The type of entity.
            entity_id: The ID to check.

        Returns:
            True if the ID exists for the given entity type.
        """
        return entity_id in self._ids.get(entity_type, set())

    def get_ids(self: Self, entity_type: str) -> set[str]:
        """Get all registered IDs for an entity type.

        Args:
            entity_type: The type of entity.

        Returns:
            Set of registered IDs, or empty set if none.
        """
        return self._ids.get(entity_type, set()).copy()

    def get_all_types(self: Self) -> list[str]:
        """Get all registered entity types.

        Returns:
            List of entity type names.
        """
        return list(self._ids.keys())


class DatasetValidator:
    """Validates datasets with reference integrity checking.

    Performs two-pass validation:
    1. First pass: Collect all entity IDs into registry
    2. Second pass: Validate each entity and check references

    Example:
        >>> validator = DatasetValidator("miappe", "1.1")
        >>> result = validator.validate_directory(Path("./my_project"))
        >>> if not result.is_valid:
        ...     for error in result.errors:
        ...         print(error)
    """

    def __init__(
        self: Self,
        profile: str | None = None,
        version: str | None = None,
    ) -> None:
        """Initialize the dataset validator.

        Args:
            profile: Profile name. If None, uses default profile.
            version: Profile version. If None, uses latest version.
        """
        factory = ProfileFactory()

        if profile is None:
            profile = factory.get_default_profile()

        if version is None:
            version = factory.get_latest_version(profile)
            if version is None:
                raise ValueError(f"No versions found for profile: {profile}")

        self.profile = profile
        self.version = version
        self._loader = SpecLoader(profile=profile)
        self._registry = IdRegistry()
        self._reference_fields: dict[str, list[tuple[str, str]]] = {}
        self._load_reference_fields()

    def _load_reference_fields(self: Self) -> None:
        """Load reference field definitions from specs."""
        try:
            entities = self._loader.list_entities(self.version)
        except Exception:
            return

        for entity_name in entities:
            try:
                spec = self._loader.load_entity(entity_name, self.version)
                refs = []
                for f in spec.fields:
                    if f.ref:
                        refs.append((f.name, f.ref))
                if refs:
                    self._reference_fields[entity_name] = refs
            except Exception:
                continue

    def _detect_entity_type(self: Self, data: dict[str, Any]) -> str | None:
        """Detect entity type from data structure.

        Args:
            data: The data dictionary.

        Returns:
            Entity type name, or None if not detected.
        """
        # Check for explicit type field
        if "_type" in data:
            return str(data["_type"]).lower()

        # Check for studies field (likely investigation)
        if "studies" in data and isinstance(data.get("studies"), list):
            return "investigation"

        # Check for observation_units field (likely study)
        if "observation_units" in data and isinstance(data.get("observation_units"), list):
            return "study"

        return None

    def _collect_ids(
        self: Self,
        data: dict[str, Any],
        entity_type: str,
    ) -> None:
        """Recursively collect entity IDs into the registry.

        Args:
            data: Entity data dictionary.
            entity_type: Type of the entity.
        """
        # Register this entity's ID
        if "unique_id" in data:
            self._registry.register(entity_type, data["unique_id"])

        # Recursively collect from nested lists
        try:
            spec = self._loader.load_entity(entity_type, self.version)
        except Exception:
            return

        for f in spec.fields:
            if f.type.value == "list" and f.items:
                items = data.get(f.name, [])
                if not isinstance(items, list):
                    continue

                # Convert items type to snake_case entity name
                item_entity = self._to_snake_case(f.items)
                for item in items:
                    if isinstance(item, dict):
                        self._collect_ids(item, item_entity)

    def _to_snake_case(self: Self, name: str) -> str:
        """Convert PascalCase to snake_case."""
        import re

        s1 = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
        return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s1).lower()

    def _validate_references(
        self: Self,
        data: dict[str, Any],
        entity_type: str,
        path: str = "",
    ) -> list[ValidationError]:
        """Validate references in entity data.

        Args:
            data: Entity data dictionary.
            entity_type: Type of the entity.
            path: Current path for error reporting.

        Returns:
            List of reference validation errors.
        """
        errors: list[ValidationError] = []

        # Check reference fields for this entity type
        if entity_type in self._reference_fields:
            for field_name, ref_type in self._reference_fields[entity_type]:
                ref_value = data.get(field_name)
                if ref_value is not None:
                    ref_entity = self._to_snake_case(ref_type)
                    if not self._registry.exists(ref_entity, ref_value):
                        field_path = f"{path}.{field_name}" if path else field_name
                        errors.append(
                            ValidationError(
                                field=field_path,
                                message=f"Reference not found: {ref_type} '{ref_value}'",
                                rule="reference_integrity",
                            )
                        )

        # Recursively validate nested entities
        try:
            spec = self._loader.load_entity(entity_type, self.version)
        except Exception:
            return errors

        for f in spec.fields:
            if f.type.value == "list" and f.items:
                items = data.get(f.name, [])
                if not isinstance(items, list):
                    continue

                item_entity = self._to_snake_case(f.items)
                for i, item in enumerate(items):
                    if isinstance(item, dict):
                        item_path = f"{path}.{f.name}[{i}]" if path else f"{f.name}[{i}]"
                        errors.extend(self._validate_references(item, item_entity, item_path))

        return errors

    def _validate_entity(
        self: Self,
        data: dict[str, Any],
        entity_type: str,
        path: str = "",
    ) -> list[ValidationError]:
        """Validate entity data against spec.

        Args:
            data: Entity data dictionary.
            entity_type: Type of the entity.
            path: Current path for error reporting.

        Returns:
            List of validation errors.
        """
        errors: list[ValidationError] = []

        # Validate against spec rules
        try:
            engine = create_engine_for_entity(entity_type, self.version, self.profile)
            for error in engine.validate(data):
                field_path = f"{path}.{error.field}" if path else error.field
                errors.append(
                    ValidationError(
                        field=field_path,
                        message=error.message,
                        rule=error.rule,
                    )
                )
        except Exception:
            pass

        # Recursively validate nested entities
        try:
            spec = self._loader.load_entity(entity_type, self.version)
        except Exception:
            return errors

        for f in spec.fields:
            if f.type.value == "list" and f.items:
                items = data.get(f.name, [])
                if not isinstance(items, list):
                    continue

                item_entity = self._to_snake_case(f.items)
                for i, item in enumerate(items):
                    if isinstance(item, dict):
                        item_path = f"{path}.{f.name}[{i}]" if path else f"{f.name}[{i}]"
                        errors.extend(self._validate_entity(item, item_entity, item_path))

        return errors

    def _count_entities(
        self: Self,
        data: dict[str, Any],
        entity_type: str,
        counts: dict[str, int],
    ) -> None:
        """Count entities by type.

        Args:
            data: Entity data dictionary.
            entity_type: Type of the entity.
            counts: Dictionary to update with counts.
        """
        counts[entity_type] = counts.get(entity_type, 0) + 1

        try:
            spec = self._loader.load_entity(entity_type, self.version)
        except Exception:
            return

        for f in spec.fields:
            if f.type.value == "list" and f.items:
                items = data.get(f.name, [])
                if not isinstance(items, list):
                    continue

                item_entity = self._to_snake_case(f.items)
                for item in items:
                    if isinstance(item, dict):
                        self._count_entities(item, item_entity, counts)

    def validate_file(self: Self, path: Path) -> DatasetValidationResult:
        """Validate a single file.

        Args:
            path: Path to the YAML/JSON file.

        Returns:
            Validation result for the file.
        """
        result = DatasetValidationResult()
        result.files_checked.append(path)

        # Load the file
        try:
            content = path.read_text(encoding="utf-8")
            data = yaml.safe_load(content)
            if data is None:
                data = {}
        except yaml.YAMLError as e:
            result.errors.append(
                ValidationError(
                    field=str(path),
                    message=f"Invalid YAML: {e}",
                    rule="yaml_syntax",
                )
            )
            return result
        except OSError as e:
            result.errors.append(
                ValidationError(
                    field=str(path),
                    message=f"Cannot read file: {e}",
                    rule="file_access",
                )
            )
            return result

        # Detect entity type
        entity_type = self._detect_entity_type(data)
        if entity_type is None:
            entity_type = "investigation"  # Default assumption

        # Reset registry for single file validation
        self._registry = IdRegistry()

        # Pass 1: Collect IDs
        self._collect_ids(data, entity_type)

        # Pass 2: Validate entity structure
        result.errors.extend(self._validate_entity(data, entity_type))

        # Pass 3: Validate references
        result.errors.extend(self._validate_references(data, entity_type))

        # Count entities
        self._count_entities(data, entity_type, result.entity_counts)

        return result

    def validate_directory(self: Self, path: Path) -> DatasetValidationResult:
        """Validate all YAML/JSON files in a directory.

        Args:
            path: Path to the directory.

        Returns:
            Combined validation result for all files.
        """
        result = DatasetValidationResult()

        # Reset registry for directory validation
        self._registry = IdRegistry()

        # Find all YAML and JSON files
        files = list(path.glob("**/*.yaml")) + list(path.glob("**/*.yml"))
        files.extend(path.glob("**/*.json"))

        if not files:
            result.warnings.append(
                ValidationError(
                    field=str(path),
                    message="No YAML or JSON files found",
                    rule="file_discovery",
                )
            )
            return result

        # Pass 1: Collect all IDs from all files
        file_data: list[tuple[Path, dict[str, Any], str]] = []
        for file_path in files:
            try:
                content = file_path.read_text(encoding="utf-8")
                data = yaml.safe_load(content)
                if data is None:
                    continue

                entity_type = self._detect_entity_type(data)
                if entity_type is None:
                    entity_type = "investigation"

                self._collect_ids(data, entity_type)
                file_data.append((file_path, data, entity_type))
                result.files_checked.append(file_path)
            except yaml.YAMLError as e:
                result.errors.append(
                    ValidationError(
                        field=str(file_path),
                        message=f"Invalid YAML: {e}",
                        rule="yaml_syntax",
                    )
                )
            except OSError as e:
                result.errors.append(
                    ValidationError(
                        field=str(file_path),
                        message=f"Cannot read file: {e}",
                        rule="file_access",
                    )
                )

        # Pass 2: Validate all files
        for file_path, data, entity_type in file_data:
            # Validate entity structure
            errors = self._validate_entity(data, entity_type)
            for error in errors:
                result.errors.append(
                    ValidationError(
                        field=f"{file_path}:{error.field}",
                        message=error.message,
                        rule=error.rule,
                    )
                )

            # Validate references
            ref_errors = self._validate_references(data, entity_type)
            for error in ref_errors:
                result.errors.append(
                    ValidationError(
                        field=f"{file_path}:{error.field}",
                        message=error.message,
                        rule=error.rule,
                    )
                )

            # Count entities
            self._count_entities(data, entity_type, result.entity_counts)

        return result
