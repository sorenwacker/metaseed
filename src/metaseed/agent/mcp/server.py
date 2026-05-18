"""MCP server implementation for metadata extraction.

This module implements a Model Context Protocol (MCP) server that exposes
metaseed functionality to MCP clients like Claude Desktop.

Resources:
    - profile://list - List all available profiles
    - profile://{name}/{version} - Get profile schema
    - profile://{name}/{version}/entity/{entity} - Get entity definition

Tools:
    - list_profiles - List available profiles with versions
    - get_profile_schema - Get full profile schema
    - parse_file - Parse a file and return structure
    - analyze_mapping - Suggest column mappings for an entity
    - extract_entities - Extract entity instances from file
    - validate_extracted - Validate extracted data
    - export_metadata - Export to YAML/JSON

Prompts:
    - extraction_guide - Instructions for metadata extraction
    - field_mapping_help - Help for mapping columns to fields
"""

from __future__ import annotations

import json

from mcp.server.fastmcp import FastMCP

from metaseed.agent.parsers.registry import create_default_registry
from metaseed.specs.loader import SpecLoader, SpecLoadError

# Global state for MCP server
# Uses FileEntityRepository for file-based synchronization with UI
_mcp_state = None
_entity_service = None


def get_mcp_state():
    """Get the shared MCP state, creating it if needed."""
    global _mcp_state
    if _mcp_state is None:
        from metaseed.ui.state import AppState

        _mcp_state = AppState()
    return _mcp_state


def set_mcp_state(state):
    """Set the MCP state (called by UI to share state)."""
    global _mcp_state, _entity_service
    _mcp_state = state
    _entity_service = None  # Reset service to use new state


def get_entity_service():
    """Get the entity service for operations.

    Uses MemoryEntityRepository wrapping the MCP state so that
    state changes are reflected immediately.
    """
    global _entity_service
    if _entity_service is None:
        from metaseed.repositories.memory import MemoryEntityRepository
        from metaseed.ui.services.entities import EntityService

        state = get_mcp_state()
        repo = MemoryEntityRepository(state)
        _entity_service = EntityService(repo)

    return _entity_service


def reset_entity_service():
    """Reset the entity service (called when dataset changes)."""
    global _entity_service
    _entity_service = None


def create_server(name: str = "metaseed") -> FastMCP:
    """Create and configure the MCP server.

    Args:
        name: Server name.

    Returns:
        Configured FastMCP server instance.
    """
    mcp = FastMCP(name=name)
    _parser_registry = create_default_registry()

    # =========================================================================
    # Resources - Read-only data access
    # =========================================================================

    @mcp.resource("profile://list")
    def list_profiles_resource() -> str:
        """List all available profiles."""
        loader = SpecLoader()
        profiles = loader.list_profiles()
        return json.dumps({"profiles": profiles})

    @mcp.resource("profile://{name}/{version}")
    def get_profile_resource(name: str, version: str) -> str:
        """Get profile schema."""
        loader = SpecLoader(profile=name)
        try:
            spec = loader.load_profile(version=version, profile=name)
            return json.dumps(
                {
                    "name": spec.name,
                    "version": spec.version,
                    "display_name": spec.display_name,
                    "description": spec.description,
                    "root_entity": spec.root_entity,
                    "entities": spec.list_entities(),
                }
            )
        except SpecLoadError as e:
            return json.dumps({"error": str(e)})

    @mcp.resource("profile://{name}/{version}/entity/{entity}")
    def get_entity_resource(name: str, version: str, entity: str) -> str:
        """Get entity definition."""
        loader = SpecLoader(profile=name)
        try:
            entity_spec = loader.load_entity(entity, version=version, profile=name)
            fields = []
            for field in entity_spec.fields:
                fields.append(
                    {
                        "name": field.name,
                        "type": field.type.value,
                        "required": field.required,
                        "description": field.description,
                    }
                )
            return json.dumps(
                {
                    "name": entity,
                    "description": entity_spec.description,
                    "ontology_term": entity_spec.ontology_term,
                    "fields": fields,
                }
            )
        except SpecLoadError as e:
            return json.dumps({"error": str(e)})

    # =========================================================================
    # Register tools from submodules
    # =========================================================================

    from metaseed.agent.mcp.tools.datasets import register_dataset_tools
    from metaseed.agent.mcp.tools.entities import register_entity_tools
    from metaseed.agent.mcp.tools.extraction import register_extraction_tools
    from metaseed.agent.mcp.tools.profiles import register_profile_tools
    from metaseed.agent.mcp.tools.validation import register_validation_tools

    register_profile_tools(mcp)
    register_dataset_tools(mcp, get_mcp_state, reset_entity_service)
    register_entity_tools(mcp, get_entity_service)
    register_extraction_tools(mcp, _parser_registry)
    register_validation_tools(mcp, get_mcp_state)

    # =========================================================================
    # Prompts - Guided workflows
    # =========================================================================

    @mcp.prompt()
    def extraction_guide(profile: str) -> str:
        """Guide for extracting metadata from files."""
        return f"""# Metadata Extraction Guide for {profile}

## Overview
This guide helps you extract structured metadata from source files (CSV, Excel, JSON)
into standardized formats like MIAPPE, ISA, or Darwin Core.

## Workflow

### 1. Discover Available Profiles
Use `list_profiles` to see available metadata standards.

### 2. Understand the Schema
Use `get_profile_schema` to see entities and their fields.

### 3. Parse Source File
Use `parse_source_file` to understand the structure of your data.

### 4. Analyze Mappings
Use `analyze_mapping` to get suggested column-to-field mappings.

### 5. Extract Entities
Use `extract_entities` with your mapping to extract data.

### 6. Validate
Use `validate_extracted` to check for errors.

### 7. Export
Use `export_metadata` to format the final output.

## Tips
- Start with the root entity (usually Investigation)
- Map required fields first
- Use parent_id references to link nested entities
"""

    @mcp.prompt()
    def field_mapping_help(entity: str, _profile: str) -> str:
        """Help for mapping source columns to entity fields."""
        return f"""# Field Mapping Help for {entity}

## Common Patterns

1. **Direct Match**: Column name matches field name
   - "title" -> title
   - "description" -> description

2. **Case Variations**:
   - "Title" -> title
   - "DESCRIPTION" -> description

3. **Codename Match**: Column matches field codename
   - "DM-29" -> unique_id (if that's the codename)

4. **Semantic Match**: Similar meaning
   - "name" -> title
   - "id" -> unique_id

## Confidence Scores
- 1.0 = Exact match
- 0.8-0.9 = Close match (case difference, minor variation)
- 0.5-0.7 = Semantic match
- Below 0.5 = Manual review recommended

## Required Fields
Check `get_field_spec` for which fields are required.

## Validation
After mapping, use `validate_extracted` to verify data quality.
"""

    return mcp


# Server instance for import
mcp = create_server()


def run_server():
    """Run the MCP server."""
    mcp.run()


if __name__ == "__main__":
    run_server()
