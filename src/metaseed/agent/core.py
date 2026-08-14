"""Core extraction context and orchestration logic.

This module provides the ExtractionContext class that manages state for
metadata extraction sessions, including profile selection, source files,
column mappings, and extracted entities.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any, Self, cast

import yaml
from pydantic import BaseModel, StringConstraints, TypeAdapter, ValidationError

from metaseed.agent.mapping import ColumnMapping, FieldMapping, suggest_mapping
from metaseed.agent.parsers import ParsedContent, ParserRegistry
from metaseed.agent.parsers.registry import create_default_registry
from metaseed.specs.loader import SpecLoader
from metaseed.specs.schema import EntitySpec, FieldSpec, ProfileSpec
from metaseed.validators.engine import (
    ValidationEngine,
    create_engine_for_extracted_record,
)


@lru_cache(maxsize=512)
def _pattern_matcher(pattern: str) -> TypeAdapter[str]:
    """Cache a Pydantic string-pattern validator for a spec-supplied regex.

    Pydantic's default engine is the Rust ``regex`` crate — linear-time and
    ReDoS-immune — unlike Python's backtracking ``re``. Used so a malicious
    spec pattern (e.g. ``^(a+)+$``) cannot stall the process.
    """
    return TypeAdapter(Annotated[str, StringConstraints(pattern=pattern)])


def _pattern_matches(pattern: str, value: str) -> bool:
    """Whether ``value`` matches ``pattern`` using the linear (Rust) engine.

    A pattern that will not compile (e.g. Python-only lookbehind/backrefs, none
    of which ship) is treated as unenforceable and passes, rather than crashing
    or falsely rejecting — consistent with the Pydantic model path.
    """
    try:
        adapter = _pattern_matcher(pattern)
    except Exception:
        return True
    try:
        adapter.validate_python(value)
    except ValidationError:
        return False
    return True


class TypeConverter:
    """Converts values to appropriate types based on field specifications."""

    @staticmethod
    def convert(value: Any, field_type: str) -> Any:
        """Convert value to appropriate type.

        Args:
            value: Raw value to convert.
            field_type: Field type string (e.g., "string", "integer").

        Returns:
            Converted value or None if conversion fails.
        """
        if value is None or value == "":
            return None

        converters: dict[str, Callable[[Any], Any]] = {
            "string": str,
            "integer": TypeConverter._to_integer,
            "float": TypeConverter._to_float,
            "boolean": TypeConverter._to_boolean,
            "date": str,
            "datetime": str,
            "uri": str,
            "ontology_term": str,
            "list": TypeConverter._to_list,
        }

        converter = converters.get(field_type)
        if converter:
            return converter(value)
        return value

    @staticmethod
    def _to_integer(value: Any) -> int | None:
        try:
            return int(float(value))
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _to_float(value: Any) -> float | None:
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _to_boolean(value: Any) -> bool | None:
        if isinstance(value, bool):
            return value
        # None for anything unrecognized, honouring convert()'s contract:
        # 'N/A' silently stored as False is data corruption, not a boolean.
        text = str(value).strip().lower()
        if text in ("true", "1", "yes"):
            return True
        if text in ("false", "0", "no"):
            return False
        return None

    @staticmethod
    def _to_list(value: Any) -> list[Any]:
        if isinstance(value, list):
            return value
        if isinstance(value, str) and value.startswith("["):
            try:
                return cast("list[Any]", json.loads(value))
            except json.JSONDecodeError:
                return [value]
        return [value] if value else []


class ValidationIssue(BaseModel):
    """A validation issue found in extracted data.

    This is a plain data record describing one problem with a field; it is not
    an exception and is never raised. Named to avoid implying it can be caught
    like ``pydantic.ValidationError``.

    Attributes:
        field: The field the issue is about. A profile rule spanning several
            fields names all of them, comma-separated.
        message: Human-readable description of the problem.
        value: The offending value, where the issue is about one field's value.
        rule: Name of the profile validation rule that produced the issue, or
            None for the required-field and field-constraint checks.
        kind: What the issue claims — ``"value"`` (something supplied is wrong,
            true now and later) or ``"completeness"`` (something is absent or
            insufficient, true of every dataset mid-entry). The split exists so
            a consumer can block on the first without blocking on the second;
            dropping it here silently upgraded every missing field to a
            blocking error (#review-260813).
    """

    field: str
    message: str
    value: Any = None
    rule: str | None = None
    kind: str = "value"


class ExtractionResult(BaseModel):
    """Result of extracting entities from a source."""

    entity: str
    instances: list[dict[str, Any]]
    errors: list[ValidationIssue] = []


class ExtractionContext:
    """Context for an extraction session.

    Holds state for extracting metadata from source files and mapping them
    to a profile schema.

    Attributes:
        profile: The loaded ProfileSpec.
        sources: List of parsed source files.
        mappings: Dictionary of entity name to column mappings.
        extracted: Dictionary of entity name to extracted instances.
    """

    def __init__(
        self: Self,
        profile: ProfileSpec,
        parser_registry: ParserRegistry | None = None,
    ) -> None:
        """Initialize extraction context.

        Args:
            profile: The profile spec to extract metadata for.
            parser_registry: Optional custom parser registry.
        """
        self.profile = profile
        self.sources: list[ParsedContent] = []
        self.mappings: dict[str, ColumnMapping] = {}
        self.extracted: dict[str, list[dict[str, Any]]] = {}
        self._parser_registry = parser_registry or create_default_registry()
        # One engine per entity, built on first use: validation runs per row and
        # the profile does not change for the life of the context.
        self._rule_engines: dict[str, ValidationEngine] = {}

    @classmethod
    def from_profile(
        cls,
        profile_name: str,
        version: str,
        parser_registry: ParserRegistry | None = None,
    ) -> ExtractionContext:
        """Create context from profile name and version.

        Args:
            profile_name: Name of the profile (e.g., "miappe").
            version: Version of the profile (e.g., "1.1").
            parser_registry: Optional custom parser registry.

        Returns:
            ExtractionContext instance.
        """
        loader = SpecLoader(profile=profile_name)
        profile = loader.load_profile(version=version, profile=profile_name)
        return cls(profile=profile, parser_registry=parser_registry)

    def add_source(self: Self, path: Path) -> ParsedContent:
        """Parse and add a source file.

        Args:
            path: Path to the source file.

        Returns:
            The parsed content.

        Raises:
            ValueError: If no parser can handle the file.
        """
        content = self._parser_registry.parse(path)
        self.sources.append(content)
        return content

    def get_entity_spec(self: Self, entity_name: str) -> EntitySpec:
        """Get entity spec by name.

        Args:
            entity_name: Name of the entity.

        Returns:
            EntitySpec for the entity.

        Raises:
            KeyError: If entity not found.
        """
        return self.profile.get_entity(entity_name)

    def suggest_mapping(
        self: Self,
        source_index: int,
        entity_name: str,
        table_index: int = 0,
    ) -> list[FieldMapping]:
        """Suggest column mappings for an entity.

        Args:
            source_index: Index of the source in self.sources.
            entity_name: Name of the entity to map to.
            table_index: Index of the table within the source.

        Returns:
            List of suggested field mappings.
        """
        if source_index >= len(self.sources):
            raise IndexError(f"Source index {source_index} out of range")

        source = self.sources[source_index]
        if table_index >= len(source.tables):
            raise IndexError(f"Table index {table_index} out of range")

        table = source.tables[table_index]
        entity_spec = self.get_entity_spec(entity_name)

        return suggest_mapping(table.headers, entity_spec)

    def set_mapping(self: Self, entity_name: str, mapping: ColumnMapping) -> None:
        """Set column mapping for an entity.

        Args:
            entity_name: Name of the entity.
            mapping: The column mapping to use.
        """
        self.mappings[entity_name] = mapping

    def extract_entities(
        self: Self,
        source_index: int,
        entity_name: str,
        mapping: ColumnMapping | None = None,
        table_index: int = 0,
    ) -> ExtractionResult:
        """Extract entity instances from a source using mapping.

        Args:
            source_index: Index of the source in self.sources.
            entity_name: Name of the entity to extract.
            mapping: Column mapping to use. Uses stored mapping if None.
            table_index: Index of the table within the source.

        Returns:
            ExtractionResult with instances and any errors.
        """
        if source_index >= len(self.sources):
            raise IndexError(f"Source index {source_index} out of range")

        source = self.sources[source_index]
        if table_index >= len(source.tables):
            raise IndexError(f"Table index {table_index} out of range")

        if mapping is None:
            mapping = self.mappings.get(entity_name)
            if mapping is None:
                raise ValueError(f"No mapping set for entity {entity_name}")

        table = source.tables[table_index]
        entity_spec = self.get_entity_spec(entity_name)
        instances: list[dict[str, Any]] = []
        errors: list[ValidationIssue] = []

        for row_idx, row in enumerate(table.rows):
            row_dict = dict(zip(table.headers, row, strict=False))
            instance = self._extract_row(
                row_dict, entity_spec, mapping, row_idx, errors
            )
            if instance:
                instances.append(instance)

        # Store extracted instances
        if entity_name not in self.extracted:
            self.extracted[entity_name] = []
        self.extracted[entity_name].extend(instances)

        return ExtractionResult(
            entity=entity_name,
            instances=instances,
            errors=errors,
        )

    def _extract_row(
        self: Self,
        row: dict[str, Any],
        entity_spec: EntitySpec,
        mapping: ColumnMapping,
        row_idx: int,
        errors: list[ValidationIssue],
    ) -> dict[str, Any] | None:
        """Extract a single row to entity instance.

        Args:
            row: Row data as column->value dict.
            entity_spec: Entity specification.
            mapping: Column mapping.
            row_idx: Row index for error reporting.
            errors: List to append errors to.

        Returns:
            Extracted instance dict or None if extraction failed.
        """
        instance: dict[str, Any] = {}

        for field_mapping in mapping.fields:
            field_spec = self._find_field(entity_spec, field_mapping.field_name)
            if field_spec is None:
                continue

            if field_mapping.source_column:
                value = row.get(field_mapping.source_column, "")
            elif field_mapping.default_value is not None:
                value = field_mapping.default_value
            else:
                value = None

            # Convert value based on field type
            converted = self._convert_value(value, field_spec)
            if converted is not None:
                instance[field_spec.name] = converted
            elif field_spec.required and value:
                errors.append(
                    ValidationIssue(
                        field=field_spec.name,
                        message=f"Row {row_idx}: Failed to convert value '{value}'",
                        value=value,
                    )
                )

        return instance or None

    def _find_field(
        self: Self, entity_spec: EntitySpec, field_name: str
    ) -> FieldSpec | None:
        """Find field spec by name."""
        for field in entity_spec.fields:
            if field.name == field_name:
                return field
        return None

    def _convert_value(self: Self, value: Any, field_spec: FieldSpec) -> Any:
        """Convert value to appropriate type based on field spec."""
        return TypeConverter.convert(value, field_spec.type.value)

    def validate_instance(
        self: Self,
        data: dict[str, Any],
        entity_name: str,
    ) -> list[ValidationIssue]:
        """Validate an extracted instance against the entity spec and profile rules.

        Checks required fields and field-level constraints, then runs the
        profile's ``validation_rules`` through the shared validation engine.
        A record is flat - its children are extracted separately and its
        siblings are not visible - so the rules that need more than one record
        are not run against it; see
        :func:`~metaseed.validators.engine.create_engine_for_extracted_record`.

        Args:
            data: The instance data to validate.
            entity_name: Name of the entity.

        Returns:
            List of validation issues. Empty if the instance passes.
        """
        entity_spec = self.get_entity_spec(entity_name)
        errors: list[ValidationIssue] = []

        # Check required fields. A field present with a null value is as absent
        # as a missing key, so treat both as a missing required field.
        for field in entity_spec.fields:
            if field.required and (field.name not in data or data[field.name] is None):
                errors.append(
                    ValidationIssue(
                        field=field.name,
                        message=f"Required field '{field.name}' is missing",
                        # Not filled in yet, not wrong: must not block saving
                        # what is already there.
                        kind="completeness",
                    )
                )
            elif field.name in data and data[field.name] is not None:
                field_errors = self._validate_field(data[field.name], field)
                errors.extend(field_errors)

        errors.extend(self._profile_rule_issues(data, entity_name))

        return errors

    def _profile_rule_issues(
        self: Self, data: dict[str, Any], entity_name: str
    ) -> list[ValidationIssue]:
        """Run the profile rules a single extracted record can answer.

        Args:
            data: The instance data to validate.
            entity_name: Name of the entity.

        Returns:
            One issue per rule the record violates, each naming the rule.
        """
        engine = self._rule_engines.get(entity_name)
        if engine is None:
            engine = create_engine_for_extracted_record(entity_name, self.profile)
            self._rule_engines[entity_name] = engine
        return [
            ValidationIssue(
                field=error.field,
                message=error.message,
                value=data.get(error.field),
                rule=error.rule,
                kind=error.kind.value,
            )
            for error in engine.validate(data)
        ]

    def _validate_field(
        self: Self, value: Any, field_spec: FieldSpec
    ) -> list[ValidationIssue]:
        """Validate a single field value."""
        errors: list[ValidationIssue] = []

        if field_spec.constraints:
            constraints = field_spec.constraints

            if constraints.enum and value not in constraints.enum:
                errors.append(
                    ValidationIssue(
                        field=field_spec.name,
                        message=f"Value must be one of: {constraints.enum}",
                        value=value,
                    )
                )

            if constraints.pattern and isinstance(value, str):
                if not _pattern_matches(constraints.pattern, value):
                    errors.append(
                        ValidationIssue(
                            field=field_spec.name,
                            message=f"Value does not match pattern: {constraints.pattern}",
                            value=value,
                        )
                    )

            if constraints.min_length is not None and isinstance(value, str):
                if len(value) < constraints.min_length:
                    errors.append(
                        ValidationIssue(
                            field=field_spec.name,
                            message=f"Value must be at least {constraints.min_length} characters",
                            value=value,
                        )
                    )

            if constraints.max_length is not None and isinstance(value, str):
                if len(value) > constraints.max_length:
                    errors.append(
                        ValidationIssue(
                            field=field_spec.name,
                            message=f"Value must be at most {constraints.max_length} characters",
                            value=value,
                        )
                    )

            if constraints.minimum is not None and isinstance(value, int | float):
                if value < constraints.minimum:
                    errors.append(
                        ValidationIssue(
                            field=field_spec.name,
                            message=f"Value must be at least {constraints.minimum}",
                            value=value,
                        )
                    )

            if constraints.maximum is not None and isinstance(value, int | float):
                if value > constraints.maximum:
                    errors.append(
                        ValidationIssue(
                            field=field_spec.name,
                            message=f"Value must be at most {constraints.maximum}",
                            value=value,
                        )
                    )

            errors.extend(self._validate_cardinality(value, field_spec))

        return errors

    @staticmethod
    def _validate_cardinality(
        value: Any, field_spec: FieldSpec
    ) -> list[ValidationIssue]:
        """Enforce list min_items/max_items constraints for list values."""
        constraints = field_spec.constraints
        if constraints is None or not isinstance(value, list):
            return []

        errors: list[ValidationIssue] = []
        if constraints.min_items is not None and len(value) < constraints.min_items:
            errors.append(
                ValidationIssue(
                    field=field_spec.name,
                    message=f"Must have at least {constraints.min_items} item(s)",
                    value=value,
                )
            )
        if constraints.max_items is not None and len(value) > constraints.max_items:
            errors.append(
                ValidationIssue(
                    field=field_spec.name,
                    message=f"Must have at most {constraints.max_items} item(s)",
                    value=value,
                )
            )
        return errors

    def export_yaml(self: Self, entity_name: str | None = None) -> str:
        """Export extracted entities to YAML.

        Args:
            entity_name: Optional entity name to export. Exports all if None.

        Returns:
            YAML string.
        """
        if entity_name:
            data = {entity_name: self.extracted.get(entity_name, [])}
        else:
            data = self.extracted

        result: str = yaml.dump(
            data, default_flow_style=False, sort_keys=False, allow_unicode=True
        )
        return result

    def export_json(self: Self, entity_name: str | None = None) -> str:
        """Export extracted entities to JSON.

        Args:
            entity_name: Optional entity name to export. Exports all if None.

        Returns:
            JSON string.
        """
        if entity_name:
            data = {entity_name: self.extracted.get(entity_name, [])}
        else:
            data = self.extracted

        return json.dumps(data, indent=2, ensure_ascii=False)


# Convenience functions for stateless usage


def parse_file(path: Path, registry: ParserRegistry | None = None) -> ParsedContent:
    """Parse a file into structured content.

    Args:
        path: Path to the file.
        registry: Optional parser registry.

    Returns:
        Parsed content.
    """
    if registry is None:
        registry = create_default_registry()
    return registry.parse(path)
