"""Entity helper for schema information and instance creation.

This module provides the EntityHelper class that wraps entity specifications
and provides tab completion, field information, and guided entity creation.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any, Self, cast

from pydantic import BaseModel

from metaseed.specs.schema import PRIMITIVE_TYPES, EntitySpec, FieldSpec, FieldType

__all__ = ["EntityHelper", "validate_ontology_term"]

logger = logging.getLogger(__name__)


def validate_ontology_term(term_id: str) -> tuple[bool, str | None]:
    """Validate an ontology term exists in OLS4, in any ontology.

    Kept for callers that hold a term and no field: the exported public API and
    the MCP tools. Where a :class:`~metaseed.specs.schema.FieldSpec` is at hand,
    :func:`metaseed.services.term_check.check_term` is the better question — it
    reads the ontologies the field names, and distinguishes "wrong" from "could
    not be checked".

    Uses the centralized OntologyService with caching and rate limiting.
    Network failures are treated as valid (fail-open) to avoid blocking work.

    Args:
        term_id: Ontology term ID (e.g., "PATO:0000001", "GO:0008150").

    Returns:
        Tuple of (is_valid, warning_message). Warning is None if valid.
    """
    from metaseed.services.ontology import get_ontology_service

    service = get_ontology_service()
    return service.validate_term_sync(term_id)


class EntityHelper:
    """Helper class providing info and creation methods for an entity.

    Provides tab completion, field information, and guided entity creation.
    """

    def __init__(
        self: Self,
        entity_name: str,
        spec: EntitySpec,
        model: type[BaseModel],
        profile: str,
        version: str,
        store_callback: Callable[[str, dict[str, Any]], Any] | None = None,
    ) -> None:
        """Initialize the entity helper.

        Args:
            entity_name: Name of the entity (e.g., "Investigation").
            spec: Entity specification from YAML.
            model: Generated Pydantic model class.
            profile: Profile name (e.g., "miappe", "isa").
            version: Profile version (e.g., "1.1").
            store_callback: Optional callback to store created entities.
        """
        self._name = entity_name
        self._spec = spec
        self._model = model
        self._profile = profile
        self._version = version
        self._store_callback = store_callback
        # Set dynamic docstring for Jupyter ? support
        self.__doc__ = self._build_docstring()

    @property
    def name(self: Self) -> str:
        """Entity name."""
        return self._name

    @property
    def model(self: Self) -> type[BaseModel]:
        """The generated Pydantic model for this entity type."""
        return self._model

    @property
    def description(self: Self) -> str:
        """Entity description from spec."""
        return self._spec.description

    @property
    def ontology_term(self: Self) -> str | None:
        """Ontology term for this entity."""
        return self._spec.ontology_term

    @property
    def required_fields(self: Self) -> list[str]:
        """List of required field names."""
        return [f.name for f in self._spec.fields if f.required]

    @property
    def optional_fields(self: Self) -> list[str]:
        """List of optional field names."""
        return [f.name for f in self._spec.fields if not f.required]

    @property
    def all_fields(self: Self) -> list[str]:
        """List of all field names."""
        return [f.name for f in self._spec.fields]

    @property
    def fields_by_tier(self: Self) -> dict[str, list[str]]:
        """Field names grouped into required / recommended / optional (#98).

        A completeness indicator can read this instead of hard-coding per-profile
        field lists. ``required`` remains the validation source of truth: any
        field with ``required: true`` lands in ``required`` (as does a field
        whose advisory ``tier`` is ``"required"``). Otherwise the advisory
        ``tier`` decides, defaulting to ``optional``.
        """
        tiers: dict[str, list[str]] = {
            "required": [],
            "recommended": [],
            "optional": [],
        }
        for f in self._spec.fields:
            if f.required or f.tier == "required":
                tiers["required"].append(f.name)
            elif f.tier == "recommended":
                tiers["recommended"].append(f.name)
            else:
                tiers["optional"].append(f.name)
        return tiers

    @property
    def nested_fields(self: Self) -> dict[str, str]:
        """Fields that contain nested entities. Returns {field_name: entity_type}."""
        nested = {}
        for f in self._spec.fields:
            if f.type == FieldType.LIST and f.items:
                if f.items not in PRIMITIVE_TYPES:
                    nested[f.name] = f.items
            elif f.type == FieldType.ENTITY and f.items:
                nested[f.name] = f.items
        return nested

    @property
    def owned_child_fields(self: Self) -> dict[str, str]:
        """Nested fields explicitly marked ``owns: true`` -- possibly empty.

        Unlike :attr:`child_fields`, this never falls back to all nested fields.
        It lets a profile that uses ownership markers say an entity has *no*
        tree children (e.g. one whose only nested fields are embedded
        value-objects like OntologyAnnotation/Comment), which the all-or-nothing
        fallback of ``child_fields`` cannot express.
        """
        return {
            f.name: f.items
            for f in self._spec.fields
            if f.owns and f.is_nested() and f.items
        }

    @property
    def child_fields(self: Self) -> dict[str, str]:
        """Owning-parent (containment) relationship fields {field_name: entity_type}.

        When any nested field on the entity is marked ``owns: true`` in the spec,
        only the owned fields are returned — letting a consumer identify the
        containment relationships and skip plain lookups (e.g. an entity-typed
        reference to an OntologyAnnotation) without heuristics (#137). When no
        nested field is marked, every nested field is returned, so
        ``child_fields`` equals :attr:`nested_fields` for un-migrated profiles.
        """
        owned = {
            f.name: f.items
            for f in self._spec.fields
            if f.owns and f.is_nested() and f.items
        }
        if owned:
            return owned
        return self.nested_fields

    @property
    def reference_fields(self: Self) -> dict[str, tuple[str, str]]:
        """Fields that reference other entities by ID.

        Returns {field_name: (target_entity, target_field)}.
        Example: {"sample_ref": ("Sample", "alias")}

        Uses the `reference` field in specs (format: "Entity.field").
        """
        refs = {}
        for f in self._spec.fields:
            if f.reference:
                parts = f.reference.split(".", 1)
                if len(parts) == 2:
                    refs[f.name] = (parts[0], parts[1])
        return refs

    @property
    def identifier_field(self: Self) -> str | None:
        """Field name used as the entity identifier (for indexing/node IDs).

        A field explicitly marked ``is_identifier`` in the spec wins. Absent a
        declared identifier, the convention is the first non-reference field in
        the entity definition. This value is consumed for index keys and node
        IDs; display labels are handled separately by derive_label / get_label.
        Reference fields (e.g., run_ref, sample_ref) are skipped since they point
        to other entities rather than identifying this one.
        """
        for f in self._spec.fields:
            if f.is_identifier:
                return f.name
        for f in self._spec.fields:
            # Skip reference fields (these point to other entities)
            if f.reference:
                continue
            return f.name
        return None

    @property
    def example_data(self: Self) -> dict[str, Any]:
        """Example values for this entity from the spec.

        Returns:
            Dictionary of field names to example values.
            Empty dict if no example defined.
        """
        return self._spec.example or {}

    def field_info(self: Self, field_name: str) -> dict[str, Any]:
        """Get detailed information about a field.

        Args:
            field_name: Name of the field.

        Returns:
            Dictionary with field details.

        Raises:
            KeyError: If field not found.
        """
        for f in self._spec.fields:
            if f.name == field_name:
                info: dict[str, Any] = {
                    "name": f.name,
                    "type": f.type.value,
                    "required": f.required,
                    "description": f.description,
                }
                if f.ontology_term:
                    info["ontology_term"] = f.ontology_term
                if f.ontologies:
                    info["ontologies"] = f.ontologies
                if f.items:
                    info["items"] = f.items
                if f.constraints:
                    info["constraints"] = {
                        k: v
                        for k, v in f.constraints.model_dump().items()
                        if v is not None
                    }
                self._add_metadata(info, f)
                return info
        raise KeyError(f"Field '{field_name}' not found in {self._name}")

    @staticmethod
    def _add_metadata(info: dict[str, Any], f: FieldSpec) -> None:
        """Attach the richer #98 field metadata to a field-info dict.

        ``example``/``unit``/``label``/``tier`` are copied when present.
        ``options`` is the field's declared ``options``, falling back to a
        ``constraints.enum`` when unset, so an enumerated field surfaces its
        allowed values without the author restating them.
        """
        if f.example is not None:
            info["example"] = f.example
        options = f.options
        if options is None and f.constraints and f.constraints.enum:
            options = f.constraints.enum
        if options:
            info["options"] = options
        if f.unit:
            info["unit"] = f.unit
        if f.label:
            info["label"] = f.label
        if f.tier:
            info["tier"] = f.tier

    def get_label(self: Self, instance: BaseModel | dict[str, Any]) -> str:
        """Get a human-readable label for an entity instance.

        Looks for common identifier fields in order of preference:
        - title (for Investigation, Study)
        - name (for Person, Factor)
        - first_name + last_name (for Person)
        - unique_id / identifier
        - Falls back to first non-empty string field from spec

        Args:
            instance: Entity instance (Pydantic model or dict).

        Returns:
            Human-readable label string.
        """
        from metaseed.repositories.helpers import derive_label

        if hasattr(instance, "model_dump"):
            data = instance.model_dump()
        elif isinstance(instance, dict):
            data = instance
        else:
            return f"{self._name}"

        return derive_label(self._name, data, spec=self._spec)

    def help(self: Self) -> None:
        """Print detailed help for this entity."""
        print(f"\n{'=' * 60}")  # noqa: T201
        print(f"{self._name} ({self._profile} v{self._version})")  # noqa: T201
        print("=" * 60)  # noqa: T201

        if self._spec.description:
            print(f"\n{self._spec.description}")  # noqa: T201

        if self._spec.ontology_term:
            print(f"\nOntology: {self._spec.ontology_term}")  # noqa: T201

        print(f"\n--- Required Fields ({len(self.required_fields)}) ---")  # noqa: T201
        for f in self._spec.fields:
            if f.required:
                self._print_field(f)

        print(f"\n--- Optional Fields ({len(self.optional_fields)}) ---")  # noqa: T201
        for f in self._spec.fields:
            if not f.required:
                self._print_field(f)

        print()  # noqa: T201

    def _print_field(self: Self, f: FieldSpec) -> None:
        """Print a single field's information."""
        type_str = f.type.value
        if f.items:
            type_str = f"list[{f.items}]" if f.type == FieldType.LIST else f.items

        req = "*" if f.required else " "
        print(f"  {req} {f.name}: {type_str}")  # noqa: T201
        if f.description:
            # Wrap long descriptions
            desc = (
                f.description[:70] + "..." if len(f.description) > 70 else f.description
            )
            print(f"      {desc}")  # noqa: T201

    def example(self: Self) -> None:
        """Print example code for creating this entity."""
        print(f"\n# Create a {self._name}")  # noqa: T201
        print(f"{self._name} = profile.{self._name}")  # noqa: T201
        print()  # noqa: T201

        # Use spec example if available
        spec_example = self._spec.example or {}

        # Build example with required fields
        args = []
        for f in self._spec.fields:
            if f.required:
                # Use spec example value if available
                if f.name in spec_example:
                    val = spec_example[f.name]
                    if isinstance(val, str):
                        args.append(f'{f.name}="{val}"')
                    else:
                        args.append(f"{f.name}={val}")
                elif f.type == FieldType.STRING:
                    args.append(f'{f.name}="..."')
                elif f.type == FieldType.INTEGER:
                    args.append(f"{f.name}=0")
                elif f.type == FieldType.FLOAT:
                    args.append(f"{f.name}=0.0")
                elif f.type == FieldType.BOOLEAN:
                    args.append(f"{f.name}=True")
                elif f.type == FieldType.DATE:
                    args.append(f"{f.name}=datetime.date.today()")
                elif f.type == FieldType.LIST:
                    args.append(f"{f.name}=[]")
                else:
                    args.append(f'{f.name}="..."')

        args_str = ",\n    ".join(args)
        print(f"instance = {self._name}.create(")  # noqa: T201
        print(f"    {args_str}")  # noqa: T201
        print(")")  # noqa: T201

    def validate_ontology_terms(
        self: Self, data: dict[str, Any] | BaseModel, warn: bool = True
    ) -> list[str]:
        """Validate ontology term fields in entity data.

        Checks each value against the ontologies its field names, not merely
        that the term exists somewhere: a field declaring ``ontologies: ["to"]``
        does not accept a phenotype term (issue #215).

        A value that could not be checked — an OLS outage, or a label rather
        than an identifier — is not reported. It is not a fault in the data,
        and someone else's downtime must not fill a researcher's screen with
        errors.

        Args:
            data: Entity data as dict or Pydantic model.
            warn: If True, log warnings for invalid terms.

        Returns:
            List of warning messages for invalid terms.
        """
        warnings: list[str] = []

        if hasattr(data, "model_dump"):
            data = data.model_dump(exclude_none=True)
        elif not isinstance(data, dict):
            return warnings

        from metaseed.services.term_check import check_entity_terms

        for field_name, verdict in check_entity_terms(self._spec.fields, data).items():
            if not verdict.is_problem or not verdict.message:
                continue
            full_warning = f"{self._name}.{field_name}: {verdict.message}"
            warnings.append(full_warning)
            if warn:
                logger.warning(full_warning)

        return warnings

    def create(self: Self, skip_validation: bool = False, **kwargs: Any) -> BaseModel:
        """Create an instance of this entity.

        Args:
            skip_validation: If True, skip Pydantic validation. Use this for
                progressive editing where entities are saved with incomplete data.
            **kwargs: Field values for the entity.

        Returns:
            New entity instance.

        Note:
            Pydantic may modify nested dict values in-place during validation.
            If you need to reuse the input data, make a deep copy first:
            ``import copy; data = copy.deepcopy(original_data)``

            Ontology term fields are validated against OLS4. Invalid terms
            generate warnings but do not prevent entity creation.

            When skip_validation=True, the instance is created without type
            checking. Call validate_entity() separately to check for issues.

        Example:
            >>> inv = profile.Investigation.create(
            ...     unique_id="INV-001",
            ...     title="My Investigation",
            ... )

            >>> # Create draft with incomplete data
            >>> draft = profile.Investigation.create(
            ...     skip_validation=True,
            ...     title="Work in progress",
            ... )
        """
        if skip_validation:
            # Skipping validation must also skip the ontology check: it resolves
            # terms against OLS over the network, so running it here made every
            # draft creation do live I/O (and made loading an example with many
            # ontology_term fields issue one request per entity).
            return self._model.model_construct(**kwargs)

        # Deliberately no ontology check here. ``validate_ontology_terms``
        # resolves each term against OLS over the network, so running it as a
        # side effect of construction meant one request per entity every time a
        # dataset was loaded from disk or an example was materialised. It stays
        # available as an explicit call (see the MCP ontology tools) and as part
        # of validation, where the cost is expected.
        return self._model(**kwargs)

    def __call__(self: Self, **kwargs: Any) -> BaseModel:
        """Create an instance and store it automatically.

        Example:
            >>> inv = m.Investigation(unique_id="INV-001", title="My Investigation")
            >>> m.list_entities("Investigation")  # inv is stored
        """
        if self._store_callback:
            node = self._store_callback(self._name, kwargs)
            return cast("BaseModel", node.instance)
        return self.create(**kwargs)

    def __repr__(self: Self) -> str:
        return f"<{self._name}: {len(self.required_fields)} required, {len(self.optional_fields)} optional fields>"

    def _build_docstring(self: Self) -> str:
        """Build a docstring with field information for Jupyter ? support."""
        lines = [
            f"{self._name} ({self._profile} v{self._version})",
            "",
            self._spec.description or "",
            "",
        ]

        if self._spec.ontology_term:
            lines.append(f"Ontology: {self._spec.ontology_term}")
            lines.append("")

        # Required fields
        required = [f for f in self._spec.fields if f.required]
        if required:
            lines.append("Required Fields:")
            for field in required:
                field_type = self._format_field_type(field)
                lines.append(f"    {field.name}: {field_type}")
            lines.append("")

        # Optional fields
        optional = [f for f in self._spec.fields if not f.required]
        if optional:
            lines.append("Optional Fields:")
            for field in optional:
                field_type = self._format_field_type(field)
                lines.append(f"    {field.name}: {field_type}")
            lines.append("")

        lines.append("Usage:")
        lines.append(f"    inv = m.{self._name}(field=value, ...)")
        lines.append(f"    m.{self._name}.help()  # Detailed field info")

        return "\n".join(lines)

    def _format_field_type(self: Self, field: FieldSpec) -> str:
        """Format field type for display."""
        if field.type == FieldType.LIST:
            item_type = field.items or "any"
            return f"list[{item_type}]"
        if field.type == FieldType.ENTITY:
            return field.items or "entity"
        return field.type.value
