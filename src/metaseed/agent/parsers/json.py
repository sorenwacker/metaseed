"""JSON file parser."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from metaseed.agent.parsers.registry import ParsedContent, ParsedTable


class JSONParser:
    """Parser for JSON files."""

    extensions = [".json"]
    mime_types = ["application/json"]

    def can_parse(self, path: Path) -> bool:
        """Check if this parser can handle the file."""
        return path.suffix.lower() in self.extensions

    def parse(self, path: Path) -> ParsedContent:
        """Parse JSON file into structured content."""
        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        tables = []
        text_blocks = []

        # Handle different JSON structures
        if isinstance(data, list):
            # Array of objects -> table
            table = self._list_to_table(data, path.stem)
            if table:
                tables.append(table)
        elif isinstance(data, dict):
            # Object - look for arrays inside
            for key, value in data.items():
                if isinstance(value, list) and value and isinstance(value[0], dict):
                    table = self._list_to_table(value, key)
                    if table:
                        tables.append(table)
                elif isinstance(value, str):
                    text_blocks.append(f"{key}: {value}")

        return ParsedContent(
            source_path=str(path),
            format="json",
            tables=tables,
            text_blocks=text_blocks,
            metadata={"structure": "array" if isinstance(data, list) else "object"},
        )

    def _list_to_table(self, items: list[Any], name: str) -> ParsedTable | None:
        """Convert list of dicts to table."""
        if not items:
            return None

        # Only handle list of dicts
        if not all(isinstance(item, dict) for item in items):
            return None

        # Collect all keys as headers
        headers: list[str] = []
        for item in items:
            for key in item:
                if key not in headers:
                    headers.append(key)

        # Build rows
        rows: list[list[Any]] = []
        for item in items:
            row = [self._serialize_value(item.get(h)) for h in headers]
            rows.append(row)

        return ParsedTable(
            name=name,
            headers=headers,
            rows=rows,
        )

    def _serialize_value(self, value: Any) -> Any:
        """Serialize a value for table storage."""
        if value is None:
            return ""
        if isinstance(value, dict | list):
            return json.dumps(value)
        return value
