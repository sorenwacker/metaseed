"""Profile tools for MCP server."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from metaseed.specs.loader import SpecLoader, SpecLoadError
from metaseed.specs.schema import EntityDefSpec, FieldSpec

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP


def _load_entity_def(
    entity_type: str, profile: str, version: str
) -> tuple[EntityDefSpec | None, str | None]:
    """Load entity definition from a profile.

    Args:
        entity_type: Entity type name.
        profile: Profile name.
        version: Profile version.

    Returns:
        Tuple of (entity_def, error_message). One will be None.
    """
    loader = SpecLoader(profile=profile)
    try:
        spec = loader.load_profile(version=version, profile=profile)
        entity_def = spec.entities.get(entity_type)
        if not entity_def:
            return None, f"Entity '{entity_type}' not found in {profile} v{version}"
        return entity_def, None
    except SpecLoadError as e:
        return None, str(e)


def _field_to_dict(field: FieldSpec) -> dict:
    """Convert a FieldSpec to a dictionary for JSON serialization.

    Args:
        field: FieldSpec object.

    Returns:
        Dictionary with field properties.
    """
    field_info = {
        "name": field.name,
        "type": field.type.value,
        "required": field.required,
        "description": field.description,
    }
    if field.codename:
        field_info["codename"] = field.codename
    if field.items:
        field_info["items"] = field.items
    return field_info


def _identifier_info(entity_def: Any) -> tuple[str | None, str | None]:
    """Return an entity's identifier field and a note if it deviates.

    The identifier is the first non-reference field (matching the runtime
    EntityHelper convention). A note is returned for entities that break the
    common ``unique_id`` pattern - e.g. Person keys on ``name`` and has no
    ``unique_id`` field - so agents stop assuming ``unique_id`` everywhere.

    Args:
        entity_def: Entity definition spec with a ``fields`` list.

    Returns:
        Tuple of (identifier_field, note). note is None when the entity follows
        the usual ``unique_id`` convention.
    """
    field_names = {f.name for f in entity_def.fields}
    identifier = next((f.name for f in entity_def.fields if not f.reference), None)
    note = None
    if identifier and identifier != "unique_id" and "unique_id" not in field_names:
        note = (
            f"Unlike most entities, this type has no 'unique_id' field; "
            f"its identifier is '{identifier}'."
        )
    return identifier, note


def register_profile_tools(mcp: FastMCP) -> None:
    """Register profile tools with the MCP server.

    Args:
        mcp: FastMCP server instance.
    """

    @mcp.tool()
    def list_profiles() -> str:
        """List all available profiles with their versions.

        Returns a JSON array of profiles, each with name and available versions.
        Use this to discover what metadata standards are available.
        """
        loader = SpecLoader()
        profiles = loader.list_profiles()
        result = []

        for profile in profiles:
            versions = loader.list_versions(profile)
            result.append(
                {
                    "name": profile,
                    "versions": versions,
                    "latest": versions[-1] if versions else None,
                }
            )

        return json.dumps(result, indent=2)

    @mcp.tool()
    def get_profile_schema(profile: str, version: str) -> str:
        """Get the full schema for a profile including all entities.

        Args:
            profile: Profile name (e.g., "miappe", "isa", "darwin-core").
            version: Profile version (e.g., "1.1", "1.0").

        Returns:
            JSON object with profile metadata and list of entities with their fields.
        """
        loader = SpecLoader(profile=profile)
        try:
            spec = loader.load_profile(version=version, profile=profile)
            entities = {}

            for entity_name in spec.list_entities():
                entity_def = spec.entities[entity_name]
                fields = [_field_to_dict(f) for f in entity_def.fields]

                entities[entity_name] = {
                    "description": entity_def.description,
                    "ontology_term": entity_def.ontology_term,
                    "fields": fields,
                }

            return json.dumps(
                {
                    "name": spec.name,
                    "version": spec.version,
                    "display_name": spec.display_name,
                    "description": spec.description,
                    "root_entity": spec.root_entity,
                    "entities": entities,
                },
                indent=2,
            )
        except SpecLoadError as e:
            return json.dumps({"error": str(e)})

    @mcp.tool()
    def get_field_spec(entity_type: str, field_name: str | None = None) -> str:
        """Get detailed specification for entity fields.

        Returns field definitions including type, constraints, description,
        and ontology terms.

        Args:
            entity_type: Entity type (e.g., "Investigation").
            field_name: Optional specific field name. If not provided, returns all fields.

        Returns:
            JSON with field specifications.
        """
        from metaseed.agent.mcp.server import get_mcp_state

        state = get_mcp_state()

        try:
            facade = state.get_or_create_facade()

            helper = getattr(facade, entity_type, None)
            if not helper:
                return json.dumps({"error": f"Unknown entity type: {entity_type}"})

            fields = []
            for field in helper._spec.fields:
                if field_name and field.name != field_name:
                    continue

                field_info = {
                    "name": field.name,
                    "type": field.type.value,
                    "required": field.required,
                    "description": field.description,
                }
                if field.codename:
                    field_info["codename"] = field.codename
                if field.ontology_term:
                    field_info["ontology_term"] = field.ontology_term
                if field.constraints:
                    field_info["constraints"] = field.constraints.model_dump(
                        exclude_none=True
                    )
                if field.items:
                    field_info["items"] = field.items
                if hasattr(field, "example") and field.example:
                    field_info["example"] = field.example

                fields.append(field_info)

            if field_name:
                if fields:
                    return json.dumps(fields[0], indent=2)
                return json.dumps({"error": f"Field not found: {field_name}"})

            return json.dumps(
                {
                    "entity_type": entity_type,
                    "field_count": len(fields),
                    "required_count": sum(1 for f in fields if f["required"]),
                    "fields": fields,
                },
                indent=2,
            )
        except Exception as e:
            return json.dumps({"error": str(e)})

    @mcp.tool()
    def get_entity_fields(entity_type: str, profile: str, version: str) -> str:
        """Get all fields for a specific entity type.

        Returns field definitions including name, type, required status,
        description, and other metadata. Useful for understanding what
        data is needed to create an entity.

        Args:
            entity_type: Entity type name (e.g., "Investigation", "Study").
            profile: Profile name (e.g., "miappe", "isa").
            version: Profile version (e.g., "1.2", "1.0").

        Returns:
            JSON with entity_type, profile, version, field_count,
            required_count, and list of field definitions.
        """
        entity_def, error = _load_entity_def(entity_type, profile, version)
        if error:
            return json.dumps({"error": error})

        fields = [_field_to_dict(f) for f in entity_def.fields]
        identifier, note = _identifier_info(entity_def)

        payload: dict[str, Any] = {
            "entity_type": entity_type,
            "profile": profile,
            "version": version,
            "identifier_field": identifier,
            "field_count": len(fields),
            "required_count": sum(1 for f in fields if f["required"]),
            "fields": fields,
        }
        if note:
            payload["note"] = note
        return json.dumps(payload, indent=2)

    @mcp.tool()
    def get_required_fields(entity_type: str, profile: str, version: str) -> str:
        """Get only the required field names for an entity type.

        Returns a simple list of field names that are mandatory when
        creating an entity. Use this for quick validation checks.

        Args:
            entity_type: Entity type name (e.g., "Investigation", "Study").
            profile: Profile name (e.g., "miappe", "isa").
            version: Profile version (e.g., "1.2", "1.0").

        Returns:
            JSON with entity_type, profile, version, and required_fields list.
        """
        entity_def, error = _load_entity_def(entity_type, profile, version)
        if error:
            return json.dumps({"error": error})

        required_fields = [f.name for f in entity_def.fields if f.required]
        identifier, note = _identifier_info(entity_def)

        payload: dict[str, Any] = {
            "entity_type": entity_type,
            "profile": profile,
            "version": version,
            "identifier_field": identifier,
            "required_fields": required_fields,
        }
        if note:
            payload["note"] = note
        return json.dumps(payload, indent=2)

    @mcp.tool()
    def get_entity_template(entity_type: str, profile: str, version: str) -> str:
        """Get a template for creating an entity with placeholder values.

        Returns a template object with placeholder values by field type:
        - string (required): "<required>"
        - integer: 0
        - float: 0.0
        - date: "YYYY-MM-DD"
        - datetime: "YYYY-MM-DDTHH:MM:SS"
        - uri: "https://example.com"
        - list: []
        - boolean: false
        - optional fields: null

        Args:
            entity_type: Entity type name (e.g., "Investigation", "Study").
            profile: Profile name (e.g., "miappe", "isa").
            version: Profile version (e.g., "1.2", "1.0").

        Returns:
            JSON with entity_type, template object, and _required list.
        """
        from metaseed.specs.schema import FieldType

        entity_def, error = _load_entity_def(entity_type, profile, version)
        if error:
            return json.dumps({"error": error})

        template = {}
        required_fields = []

        for field in entity_def.fields:
            if field.required:
                required_fields.append(field.name)
                # Required field placeholders by type
                if field.type == FieldType.STRING:
                    template[field.name] = "<required>"
                elif field.type == FieldType.INTEGER:
                    template[field.name] = 0
                elif field.type == FieldType.FLOAT:
                    template[field.name] = 0.0
                elif field.type == FieldType.DATE:
                    template[field.name] = "YYYY-MM-DD"
                elif field.type == FieldType.DATETIME:
                    template[field.name] = "YYYY-MM-DDTHH:MM:SS"
                elif field.type == FieldType.URI:
                    template[field.name] = "https://example.com"
                elif field.type == FieldType.BOOLEAN:
                    template[field.name] = False
                elif field.type == FieldType.LIST:
                    template[field.name] = []
                elif field.type == FieldType.ENTITY:
                    template[field.name] = None
                else:
                    template[field.name] = "<required>"
            else:
                # Optional fields are null
                template[field.name] = None

        identifier, note = _identifier_info(entity_def)
        payload: dict[str, Any] = {
            "entity_type": entity_type,
            "identifier_field": identifier,
            "template": template,
            "_required": required_fields,
        }
        if note:
            payload["note"] = note
        return json.dumps(payload, indent=2)
