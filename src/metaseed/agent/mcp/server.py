"""MCP server implementation for metadata extraction.

This module implements a Model Context Protocol (MCP) server that exposes
metaseed functionality to MCP clients like Claude Desktop.

Resources:
    - profile://list - List all available profiles
    - profile://{name}/{version} - Get profile schema
    - profile://{name}/{version}/entity/{entity} - Get entity definition

Tools:
    Registered via register_*_tools at server construction. Groups include
    profile, dataset, entity, extraction (parse_source_file, analyze_mapping,
    extract_entities, validate_extracted, export_metadata), validation, and
    ontology tools. See the tools subpackage for the authoritative list.

Prompts:
    - extraction_guide - Instructions for metadata extraction
    - field_mapping_help - Help for mapping columns to fields
"""

from __future__ import annotations

import json
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from mcp.server.fastmcp import FastMCP

from metaseed.agent.parsers.registry import create_default_registry
from metaseed.specs.loader import SpecLoader, SpecLoadError

if TYPE_CHECKING:
    from metaseed.agent.mcp.context import MCPContext
    from metaseed.ui.dataset_manager import DatasetManagerFactory
    from metaseed.ui.state import AppState


@dataclass
class _MCPStateHolder:
    """Singleton holder for MCP standalone state.

    Avoids global variables by encapsulating state in a class instance.
    """

    state: AppState | None = None
    factory: DatasetManagerFactory | None = field(default=None)

    def get_or_create_state(self) -> AppState:
        """Get cached state or create new one."""
        if self.state is None:
            from metaseed.ui.state import AppState

            self.state = AppState()
        return self.state

    def get_or_create_factory(self) -> DatasetManagerFactory:
        """Get cached factory or create new one."""
        if self.factory is None:
            from metaseed.ui.dataset_manager import DatasetManagerFactory

            self.factory = DatasetManagerFactory()
        return self.factory

    def reset(self) -> None:
        """Reset all cached state."""
        self.state = None
        self.factory = None


# Single instance for standalone mode
_standalone = _MCPStateHolder()

# Context variable for request-scoped MCP context
_context_var: ContextVar[MCPContext | None] = ContextVar("mcp_context", default=None)


def set_context(context: MCPContext | None) -> None:
    """Set the MCP context for dependency injection.

    Args:
        context: MCPContext instance with all dependencies, or None to clear.
    """
    _context_var.set(context)


def get_context() -> MCPContext | None:
    """Get the current MCP context if set."""
    return _context_var.get()


def get_mcp_state():
    """Get the shared MCP state.

    Prefers context if available, otherwise uses a cached standalone state.
    This function maintains backward compatibility for standalone MCP server mode.

    The standalone state is cached to ensure all MCP tools share the same state
    across calls (e.g., create_dataset followed by create_entity).
    """
    ctx = _context_var.get()
    if ctx is not None:
        return ctx.state

    return _standalone.get_or_create_state()


def get_standalone_factory() -> DatasetManagerFactory:
    """Get the standalone dataset factory."""
    return _standalone.get_or_create_factory()


def set_mcp_state(state):
    """Set the MCP state for tests and standalone mode.

    Creates a new context with the given state, allowing tests
    to inject state without going through the full app initialization.
    """
    from metaseed.agent.mcp.context import MCPContext
    from metaseed.repositories.memory import MemoryEntityRepository
    from metaseed.ui.dataset_manager import DatasetManagerFactory
    from metaseed.ui.services.entities import EntityService

    context = MCPContext(
        state=state,
        get_entity_service=lambda: EntityService(MemoryEntityRepository(state)),
        dataset_factory=DatasetManagerFactory(),
    )
    set_context(context)
    # Also update standalone state for consistency
    _standalone.state = state


def reset_mcp_state():
    """Reset the MCP state (for tests).

    Clears both the context and standalone state cache.
    """
    _standalone.reset()
    set_context(None)


def get_entity_service():
    """Get the entity service for operations.

    Uses context if available, otherwise creates a fresh service.
    """
    ctx = _context_var.get()
    if ctx is not None:
        return ctx.get_entity_service()

    from metaseed.repositories.memory import MemoryEntityRepository
    from metaseed.ui.services.entities import EntityService

    state = get_mcp_state()
    repo = MemoryEntityRepository(state)
    return EntityService(repo)


def reset_entity_service():
    """Reset the entity service (no-op with context injection).

    With context injection, get_entity_service() creates a fresh service
    each call, so no reset is needed.
    """
    pass


def create_server(
    name: str = "metaseed",
    context: MCPContext | None = None,
) -> FastMCP:
    """Create and configure the MCP server.

    Args:
        name: Server name.
        context: Optional MCPContext for dependency injection.
            If provided, tools will use context dependencies.
            If None, tools will use module-level state (backward compatible).

    Returns:
        Configured FastMCP server instance.
    """
    if context is not None:
        set_context(context)

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
    from metaseed.agent.mcp.tools.ontology import register_ontology_tools
    from metaseed.agent.mcp.tools.profiles import register_profile_tools
    from metaseed.agent.mcp.tools.validation import register_validation_tools

    register_profile_tools(mcp)
    register_dataset_tools(mcp, get_mcp_state, reset_entity_service)
    register_entity_tools(mcp, get_entity_service)
    register_extraction_tools(mcp, _parser_registry)
    register_validation_tools(mcp, get_mcp_state)
    register_ontology_tools(mcp)

    # =========================================================================
    # Prompts - Guided workflows
    # =========================================================================

    @mcp.prompt()
    def extraction_guide(profile: str) -> str:
        """Guide for extracting metadata from files."""
        return f"""# Metadata Extraction Guide for {profile}

## Critical Rules

1. **Only import explicitly stated information** - Never assume, infer, or make up data
2. **Leave fields empty if not mentioned** - Don't fill fields with guesses or defaults
3. **Ask the user when uncertain** - If information is ambiguous, ask for clarification
4. **Quote source text** - When possible, reference the exact text being extracted
5. **Validate parent relationships** - Check that entities are placed under valid parents

## Overview
Extract structured metadata from source files into standardized formats.

## Workflow

### 1. Read the Source File
Read and understand the source document completely before extracting.

### 2. Identify Explicit Information
List only the facts explicitly stated in the document:
- Names, IDs, dates mentioned
- Descriptions and values provided
- Relationships clearly defined

### 3. Map to Schema
Use `get_profile_schema` to see available entities and fields.
Only create entities for which you have explicit data.

### 4. Create Entities with Correct Hierarchy
- Check parent-child relationships in the schema
- PhenotypingSample goes under ObservationUnit, not Study
- Use `get_entity_fields` to see valid parent types

### 5. Validate
Use `validate_dataset` to check for errors.

## What NOT to Do
- Don't create placeholder entities without real data
- Don't guess sample IDs or observation unit IDs
- Don't assume experimental design if not stated
- Don't invent dates, locations, or parameters
- Don't fill optional fields with made-up values

## Tips
- Start with the root entity (usually Investigation)
- Map required fields first
- Ask user about missing required fields
"""

    @mcp.prompt()
    def field_mapping_help(entity: str, profile: str) -> str:
        """Help for mapping source columns to entity fields."""
        return f"""# Field Mapping Help for {entity} ({profile})

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


def run_server(
    transport: str = "stdio",
    host: str = "127.0.0.1",
    port: int = 8001,
) -> None:
    """Run the MCP server.

    Args:
        transport: Transport type ("stdio" or "streamable-http").
        host: Host to bind to for HTTP transport.
        port: Port to bind to for HTTP transport.
    """
    if transport == "streamable-http":
        import uvicorn

        uvicorn.run(mcp.streamable_http_app(), host=host, port=port)
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    run_server()
