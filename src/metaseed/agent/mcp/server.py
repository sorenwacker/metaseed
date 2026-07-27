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
from typing import TYPE_CHECKING

from mcp.server.fastmcp import FastMCP

from metaseed.agent.mcp import context as context_module
from metaseed.agent.mcp.context import MCPContext, ResolveContext
from metaseed.agent.parsers.registry import create_default_registry
from metaseed.specs.loader import SpecLoader, SpecLoadError

if TYPE_CHECKING:
    from metaseed.ui.services.entities import EntityService
    from metaseed.ui.state import AppState


def set_context(context: MCPContext | None) -> None:
    """Bind the session this process serves.

    Writes both the scope binding and the process default, so a tool resolves the
    same session whether or not the ContextVar reaches it — the #32 fix. Passing
    ``None`` clears only the scope binding, leaving the default in place, which
    is what the UI's per-request isolation depends on.
    """
    context_module.set_scope(context)
    if context is not None:
        context_module.set_default_context(context)


def get_context() -> MCPContext | None:
    """The context bound to the current scope, if any."""
    return context_module.bound_context()


def get_mcp_state() -> AppState:
    """The state of the session this process serves.

    A host that serves more than one caller must not use this: it takes no
    argument identifying the caller, so it can only ever answer for the process
    default. Such a host passes ``resolve_context=`` to :func:`create_server`.
    """
    return context_module.resolve_default_context().state


def set_mcp_state(state: AppState) -> None:
    """Bind a session built around ``state`` (tests and standalone use)."""
    from metaseed.repositories.memory import MemoryEntityRepository
    from metaseed.ui.dataset_manager import DatasetManagerFactory
    from metaseed.ui.datasets import auto_save
    from metaseed.ui.services.entities import EntityService

    set_context(
        MCPContext(
            state=state,
            get_entity_service=lambda: EntityService(
                MemoryEntityRepository(state, on_change=auto_save)
            ),
            dataset_factory=DatasetManagerFactory(),
        )
    )


def reset_mcp_state() -> None:
    """Forget the bound session and the process default (for tests)."""
    context_module.clear_context()


def get_entity_service() -> EntityService:
    """The entity service of the session this process serves."""
    return context_module.resolve_default_context().get_entity_service()


SERVER_INSTRUCTIONS = """\
Metaseed builds validated, schema-driven metadata datasets for a chosen \
profile (e.g. MIAPPE, ISA, DiSSCo, Darwin Core, ENA). Each profile defines its \
own entity types, fields, root entity, and parent-child hierarchy.

Follow this order. Do not guess entity types or field names.

1. list_profiles - discover the available standards and versions.
2. create_dataset or load_dataset - a dataset is bound to one profile and \
version.
3. get_profile_schema (and get_profile_relationships) - learn the exact entity \
types, their fields, the root entity, and the valid parent-child hierarchy for \
THIS profile. Only these entity types exist; any other type is rejected.
4. create_entity / batch_create - add entities root-first, placing each under a \
valid parent per the schema.
5. Record only information explicitly present in the source. Never invent, \
infer, or fill placeholder values; leave unknown fields empty.
6. validate_dataset - check the result before finishing.

If a tool reports an unsupported entity type, it lists the types the active \
profile supports; pick one of those rather than guessing again.
"""


def create_server(
    name: str = "metaseed",
    resolve_context: ResolveContext | None = None,
) -> FastMCP:
    """Create and configure the MCP server.

    Args:
        name: Server name.
        resolve_context: How each tool obtains the session it is serving,
            called inside the tool body. A host serving more than one caller
            passes its own, so nothing is shared between them; see
            :func:`metaseed.agent.mcp.caller.current_request` for identifying
            the caller. Omitted, tools serve the single session this process
            has — correct for ``metaseed mcp`` and the web UI, and wrong for
            anything serving two people.

    Returns:
        Configured FastMCP server instance.
    """
    resolve = resolve_context or context_module.resolve_default_context

    mcp = FastMCP(name=name, instructions=SERVER_INSTRUCTIONS)
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
    from metaseed.agent.mcp.tools.spec_builder import register_spec_builder_tools
    from metaseed.agent.mcp.tools.validation import register_validation_tools

    register_profile_tools(mcp, resolve)
    register_dataset_tools(mcp, resolve)
    register_entity_tools(mcp, resolve)
    register_extraction_tools(mcp, _parser_registry)
    register_validation_tools(mcp, resolve)
    register_ontology_tools(mcp, resolve)
    register_spec_builder_tools(mcp, resolve)

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
- Place each entity under a valid parent for this profile
- Use `get_profile_relationships` and `get_entity_fields` to see valid parents

### 5. Validate
Use `validate_dataset` to check for errors.

## What NOT to Do
- Don't create placeholder entities without real data
- Don't guess sample IDs or observation unit IDs
- Don't assume experimental design if not stated
- Don't invent dates, locations, or parameters
- Don't fill optional fields with made-up values

## Tips
- Start with the profile's root entity (see `get_profile_schema`)
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
