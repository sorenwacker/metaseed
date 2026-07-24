"""File extraction tools for MCP server."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from metaseed.agent.core import ExtractionContext, parse_file
from metaseed.agent.mapping import FieldMapping, create_mapping, suggest_mapping
from metaseed.agent.parsers.registry import ParserRegistry
from metaseed.specs.loader import SpecLoader, SpecLoadError

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP


def register_extraction_tools(mcp: FastMCP, parser_registry: ParserRegistry) -> None:  # noqa: C901
    """Register file extraction tools with the MCP server.

    Args:
        mcp: FastMCP server instance.
        parser_registry: Parser registry for file parsing.
    """

    @mcp.tool()
    def parse_source_file(file_path: str) -> str:
        """Parse a source file and return its structure.

        Supports CSV, TSV, JSON, and Excel files. Returns information about
        the file structure including tables, headers, and row counts.

        Args:
            file_path: Absolute path to the file to parse.

        Returns:
            JSON object with file format, tables, headers, and sample data.
        """
        path = Path(file_path)
        if not path.exists():
            return json.dumps({"error": f"File not found: {file_path}"})

        try:
            content = parse_file(path, parser_registry)
            tables = []
            for table in content.tables:
                tables.append(
                    {
                        "name": table.name,
                        "headers": table.headers,
                        "row_count": table.row_count,
                        "column_count": table.column_count,
                        "sample_rows": table.rows[:3] if table.rows else [],
                    }
                )

            return json.dumps(
                {
                    "source_path": content.source_path,
                    "format": content.format,
                    "tables": tables,
                    "text_blocks": content.text_blocks[:5]
                    if content.text_blocks
                    else [],
                    "metadata": content.metadata,
                },
                indent=2,
            )
        except ValueError as e:
            return json.dumps({"error": str(e)})

    @mcp.tool()
    def analyze_mapping(
        file_path: str,
        profile: str,
        version: str,
        entity: str,
        table_index: int = 0,
    ) -> str:
        """Analyze a file and suggest column mappings for an entity.

        Compares source file columns with entity field names and suggests
        mappings based on name similarity. Returns confidence scores.

        Args:
            file_path: Path to the source file.
            profile: Profile name (e.g., "miappe").
            version: Profile version (e.g., "1.1").
            entity: Entity name to map to (e.g., "Investigation").
            table_index: Index of table in file (default 0).

        Returns:
            JSON object with suggested mappings and confidence scores.
        """
        path = Path(file_path)
        if not path.exists():
            return json.dumps({"error": f"File not found: {file_path}"})

        try:
            content = parse_file(path, parser_registry)
            if table_index >= len(content.tables):
                return json.dumps({"error": f"Table index {table_index} out of range"})

            table = content.tables[table_index]
            loader = SpecLoader(profile=profile)
            entity_spec = loader.load_entity(entity, version=version, profile=profile)

            mappings = suggest_mapping(table.headers, entity_spec)

            result = {
                "entity": entity,
                "source_columns": table.headers,
                "mappings": [
                    {
                        "field": m.field_name,
                        "column": m.source_column,
                        "confidence": m.confidence,
                        "notes": m.notes,
                    }
                    for m in mappings
                ],
                "unmapped_columns": [
                    col
                    for col in table.headers
                    if col not in [m.source_column for m in mappings if m.source_column]
                ],
            }
            return json.dumps(result, indent=2)

        except (ValueError, SpecLoadError) as e:
            return json.dumps({"error": str(e)})

    @mcp.tool()
    def extract_entities(
        file_path: str,
        profile: str,
        version: str,
        entity: str,
        mapping: str,
        table_index: int = 0,
    ) -> str:
        """Extract entity instances from a file using the provided mapping.

        Uses the column mapping to transform source data into entity instances.

        Args:
            file_path: Path to the source file.
            profile: Profile name.
            version: Profile version.
            entity: Entity name to extract.
            mapping: JSON string of the mapping configuration from analyze_mapping.
            table_index: Index of table in file (default 0).

        Returns:
            JSON object with extracted instances and any errors.
        """
        path = Path(file_path)
        if not path.exists():
            return json.dumps({"error": f"File not found: {file_path}"})

        try:
            # Parse mapping
            mapping_data = json.loads(mapping)
            field_mappings = []
            for m in mapping_data.get("mappings", []):
                field_mappings.append(
                    FieldMapping(
                        field_name=m["field"],
                        source_column=m.get("column"),
                        confidence=m.get("confidence", 1.0),
                        default_value=m.get("default"),
                    )
                )
            column_mapping = create_mapping(entity, field_mappings, table_index)

            # Create context and extract
            ctx = ExtractionContext.from_profile(profile, version)
            ctx.add_source(path)
            ctx.set_mapping(entity, column_mapping)

            result = ctx.extract_entities(0, entity, table_index=table_index)

            return json.dumps(
                {
                    "entity": result.entity,
                    "count": len(result.instances),
                    "instances": result.instances,
                    "errors": [
                        {"field": e.field, "message": e.message, "value": e.value}
                        for e in result.errors
                    ],
                },
                indent=2,
            )

        except (ValueError, SpecLoadError, json.JSONDecodeError, IndexError) as e:
            return json.dumps({"error": str(e)})

    @mcp.tool()
    def export_metadata(data: str, output_format: str = "yaml") -> str:
        """Export extracted metadata to YAML or JSON format.

        Args:
            data: JSON string of extracted data (entity name to instances).
            output_format: "yaml" or "json" (default "yaml").

        Returns:
            Formatted string in the requested format.
        """
        try:
            parsed = json.loads(data)

            if output_format.lower() == "json":
                return json.dumps(parsed, indent=2, ensure_ascii=False)
            import yaml

            result: str = yaml.dump(
                parsed,
                default_flow_style=False,
                sort_keys=False,
                allow_unicode=True,
            )
            return result

        except json.JSONDecodeError as e:
            return json.dumps({"error": f"Invalid JSON: {e}"})
