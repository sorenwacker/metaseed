"""Profile tools for MCP server."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from metaseed.specs.loader import SpecLoader, SpecLoadError

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP


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
                fields = []
                for field in entity_def.fields:
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
                    fields.append(field_info)

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
                    field_info["constraints"] = field.constraints.model_dump(exclude_none=True)
                if field.items:
                    field_info["items"] = field.items
                if field.example:
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
