"""Interactive facade for creating profile entities.

This module provides a user-friendly API with tab completion and help
for creating MIAPPE, ISA, and other profile entities.
"""

from __future__ import annotations

from typing import Any, Self

from pydantic import BaseModel

from miappe_api.models import get_model
from miappe_api.specs.loader import SpecLoader
from miappe_api.specs.schema import EntitySpec, FieldSpec, FieldType


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
    ) -> None:
        """Initialize the entity helper.

        Args:
            entity_name: Name of the entity (e.g., "Investigation").
            spec: Entity specification from YAML.
            model: Generated Pydantic model class.
            profile: Profile name (e.g., "miappe", "isa").
            version: Profile version (e.g., "1.1").
        """
        self._name = entity_name
        self._spec = spec
        self._model = model
        self._profile = profile
        self._version = version

    @property
    def name(self: Self) -> str:
        """Entity name."""
        return self._name

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
    def nested_fields(self: Self) -> dict[str, str]:
        """Fields that contain nested entities. Returns {field_name: entity_type}."""
        nested = {}
        for f in self._spec.fields:
            if f.type == FieldType.LIST and f.items:
                if f.items not in ("string", "int", "float", "bool"):
                    nested[f.name] = f.items
            elif f.type == FieldType.ENTITY and f.items:
                nested[f.name] = f.items
        return nested

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
                info = {
                    "name": f.name,
                    "type": f.type.value,
                    "required": f.required,
                    "description": f.description,
                }
                if f.ontology_term:
                    info["ontology_term"] = f.ontology_term
                if f.items:
                    info["items"] = f.items
                if f.constraints:
                    info["constraints"] = {
                        k: v for k, v in f.constraints.model_dump().items() if v is not None
                    }
                return info
        raise KeyError(f"Field '{field_name}' not found in {self._name}")

    def help(self: Self) -> None:
        """Print detailed help for this entity."""
        print(f"\n{'=' * 60}")
        print(f"{self._name} ({self._profile} v{self._version})")
        print("=" * 60)

        if self._spec.description:
            print(f"\n{self._spec.description}")

        if self._spec.ontology_term:
            print(f"\nOntology: {self._spec.ontology_term}")

        print(f"\n--- Required Fields ({len(self.required_fields)}) ---")
        for f in self._spec.fields:
            if f.required:
                self._print_field(f)

        print(f"\n--- Optional Fields ({len(self.optional_fields)}) ---")
        for f in self._spec.fields:
            if not f.required:
                self._print_field(f)

        print()

    def _print_field(self: Self, f: FieldSpec) -> None:
        """Print a single field's information."""
        type_str = f.type.value
        if f.items:
            type_str = f"list[{f.items}]" if f.type == FieldType.LIST else f.items

        req = "*" if f.required else " "
        print(f"  {req} {f.name}: {type_str}")
        if f.description:
            # Wrap long descriptions
            desc = f.description[:70] + "..." if len(f.description) > 70 else f.description
            print(f"      {desc}")

    def example(self: Self) -> None:
        """Print example code for creating this entity."""
        print(f"\n# Create a {self._name}")
        print(f"{self._name} = profile.{self._name}")
        print()

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
        print(f"instance = {self._name}.create(")
        print(f"    {args_str}")
        print(")")

    def create(self: Self, **kwargs: Any) -> BaseModel:
        """Create an instance of this entity.

        Args:
            **kwargs: Field values for the entity.

        Returns:
            New entity instance.

        Example:
            >>> inv = profile.Investigation.create(
            ...     unique_id="INV-001",
            ...     title="My Investigation",
            ... )
        """
        return self._model(**kwargs)

    def __call__(self: Self, **kwargs: Any) -> BaseModel:
        """Create an instance (shorthand for create()).

        Example:
            >>> inv = profile.Investigation(unique_id="INV-001", title="My Investigation")
        """
        return self.create(**kwargs)

    def __repr__(self: Self) -> str:
        return f"<{self._name}: {len(self.required_fields)} required, {len(self.optional_fields)} optional fields>"


class ProfileFacade:
    """Interactive facade for a profile (MIAPPE, ISA, etc.).

    Provides tab completion and help for all entities in the profile.

    Example:
        >>> from miappe_api.facade import ProfileFacade
        >>> miappe = ProfileFacade("miappe", "1.1")
        >>> miappe.entities  # List all entities
        >>> miappe.Investigation.help()  # Show help for Investigation
        >>> inv = miappe.Investigation(unique_id="INV-001", title="My Investigation")
    """

    def __init__(self: Self, profile: str = "miappe", version: str | None = None) -> None:
        """Initialize the profile facade.

        Args:
            profile: Profile name (e.g., "miappe", "isa").
            version: Profile version. If None, uses the latest available.
        """
        self._profile = profile.lower()
        self._loader = SpecLoader(profile=self._profile)

        # Get version
        if version is None:
            versions = self._loader.list_versions()
            if not versions:
                raise ValueError(f"No versions found for profile: {profile}")
            version = versions[-1]  # Use latest
        self._version = version

        # Load all entities
        self._entities: dict[str, EntityHelper] = {}
        self._load_entities()

    def _load_entities(self: Self) -> None:
        """Load all entity helpers for this profile."""
        entity_names = self._loader.list_entities(self._version)

        for name in entity_names:
            spec = self._loader.load_entity(name, self._version)
            model = get_model(name, self._version, self._profile)
            self._entities[name] = EntityHelper(
                entity_name=name,
                spec=spec,
                model=model,
                profile=self._profile,
                version=self._version,
            )

    @property
    def profile(self: Self) -> str:
        """Profile name."""
        return self._profile

    @property
    def version(self: Self) -> str:
        """Profile version."""
        return self._version

    @property
    def entities(self: Self) -> list[str]:
        """List of available entity names."""
        return sorted(self._entities.keys())

    def __getattr__(self: Self, name: str) -> EntityHelper:
        """Get an entity helper by name (enables tab completion).

        Args:
            name: Entity name (e.g., "Investigation", "Study").

        Returns:
            EntityHelper for the entity.

        Raises:
            AttributeError: If entity not found.
        """
        if name.startswith("_"):
            raise AttributeError(name)

        # Try exact match
        if name in self._entities:
            return self._entities[name]

        # Try case-insensitive match
        for entity_name, helper in self._entities.items():
            if entity_name.lower() == name.lower():
                return helper

        raise AttributeError(
            f"Entity '{name}' not found in {self._profile} v{self._version}. "
            f"Available: {', '.join(self.entities)}"
        )

    def __dir__(self: Self) -> list[str]:
        """Enable tab completion for entities."""
        return list(self._entities.keys()) + [
            "profile",
            "version",
            "entities",
            "help",
            "search",
        ]

    def help(self: Self, entity_name: str | None = None) -> None:
        """Print help for the profile or a specific entity.

        Args:
            entity_name: If provided, show help for that entity.
                        If None, show profile overview.
        """
        if entity_name:
            helper = getattr(self, entity_name)
            helper.help()
            return

        print(f"\n{'=' * 60}")
        print(f"{self._profile.upper()} Profile v{self._version}")
        print("=" * 60)

        print(f"\nEntities ({len(self._entities)}):")
        for name in sorted(self._entities.keys()):
            helper = self._entities[name]
            req = len(helper.required_fields)
            opt = len(helper.optional_fields)
            print(f"  {name}: {req} required, {opt} optional fields")

        print("\nUsage:")
        print("  profile.Investigation.help()    # Show Investigation fields")
        print("  profile.Investigation.example() # Show example code")
        print("  inv = profile.Investigation(    # Create an instance")
        print("      unique_id='...', title='...'")
        print("  )")
        print()

    def search(self: Self, query: str) -> list[str]:
        """Search for entities or fields containing the query string.

        Args:
            query: Search string (case-insensitive).

        Returns:
            List of matching entity or field names.
        """
        query = query.lower()
        results = []

        for name, helper in self._entities.items():
            # Check entity name
            if query in name.lower():
                results.append(f"{name} (entity)")

            # Check field names
            for field in helper.all_fields:
                if query in field.lower():
                    results.append(f"{name}.{field}")

        return sorted(set(results))

    def __repr__(self: Self) -> str:
        return f"<ProfileFacade: {self._profile} v{self._version} ({len(self._entities)} entities)>"


# Convenience instances for common profiles
def miappe(version: str = "1.1") -> ProfileFacade:
    """Get MIAPPE profile facade.

    Args:
        version: MIAPPE version (default: "1.1").

    Returns:
        ProfileFacade for MIAPPE.

    Example:
        >>> from miappe_api.facade import miappe
        >>> m = miappe()
        >>> m.Investigation.help()
    """
    return ProfileFacade("miappe", version)


def isa(version: str = "1.0") -> ProfileFacade:
    """Get ISA profile facade.

    Args:
        version: ISA version (default: "1.0").

    Returns:
        ProfileFacade for ISA.

    Example:
        >>> from miappe_api.facade import isa
        >>> i = isa()
        >>> i.Investigation.help()
    """
    return ProfileFacade("isa", version)
