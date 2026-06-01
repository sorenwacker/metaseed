"""Parser registry and base types."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol, Self, runtime_checkable

from pydantic import BaseModel, Field


class ParsedContent(BaseModel):
    """Content parsed from a source file."""

    source_path: str
    format: str  # csv, json, excel, text, etc.
    tables: list[ParsedTable] = []  # Tabular data
    text_blocks: list[str] = []  # Free text
    metadata: dict[str, Any] = Field(default_factory=dict)  # File metadata


class ParsedTable(BaseModel):
    """A table of data from a source file."""

    name: str | None = None  # Sheet name, table id, etc.
    headers: list[str]
    rows: list[list[Any]]
    source_location: str | None = None  # Where in file this came from

    @property
    def row_count(self) -> int:
        """Number of data rows."""
        return len(self.rows)

    @property
    def column_count(self) -> int:
        """Number of columns."""
        return len(self.headers)

    def to_dicts(self) -> list[dict[str, Any]]:
        """Convert to list of row dictionaries."""
        return [dict(zip(self.headers, row, strict=False)) for row in self.rows]


@runtime_checkable
class FileParser(Protocol):
    """Protocol for file parsers."""

    extensions: list[str]
    mime_types: list[str]

    def can_parse(self, path: Path) -> bool:
        """Check if this parser can handle the file."""
        ...

    def parse(self, path: Path) -> ParsedContent:
        """Parse file into structured content."""
        ...


class ParserRegistry:
    """Registry of file format parsers."""

    def __init__(self) -> None:
        self._parsers: list[FileParser] = []

    def register(self: Self, parser: FileParser) -> None:
        """Register a parser."""
        self._parsers.append(parser)

    def get_parser(self: Self, path: Path) -> FileParser | None:
        """Get parser for a file."""
        for parser in self._parsers:
            if parser.can_parse(path):
                return parser
        return None

    def parse(self: Self, path: Path) -> ParsedContent:
        """Parse file using appropriate parser.

        Args:
            path: File to parse.

        Returns:
            Parsed content.

        Raises:
            ValueError: If no parser found for file type.
        """
        parser = self.get_parser(path)
        if parser is None:
            raise ValueError(f"No parser found for: {path}")
        return parser.parse(path)

    def supported_extensions(self: Self) -> list[str]:
        """List all supported file extensions."""
        extensions = []
        for parser in self._parsers:
            extensions.extend(parser.extensions)
        return sorted(set(extensions))


def create_default_registry() -> ParserRegistry:
    """Create registry with built-in parsers."""
    from metaseed.agent.parsers.csv import CSVParser
    from metaseed.agent.parsers.excel import ExcelParser
    from metaseed.agent.parsers.json import JSONParser

    registry = ParserRegistry()
    registry.register(CSVParser())
    registry.register(JSONParser())
    registry.register(ExcelParser())
    return registry
