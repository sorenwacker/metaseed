"""CSV file parser."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Self

from metaseed.agent.parsers.registry import ParsedContent, ParsedTable


class CSVParser:
    """Parser for CSV files."""

    extensions = [".csv", ".tsv"]
    mime_types = ["text/csv", "text/tab-separated-values"]

    def can_parse(self: Self, path: Path) -> bool:
        """Check if this parser can handle the file."""
        return path.suffix.lower() in self.extensions

    def parse(self: Self, path: Path) -> ParsedContent:
        """Parse CSV file into structured content."""
        # Detect delimiter
        delimiter = "\t" if path.suffix.lower() == ".tsv" else ","

        with open(path, newline="", encoding="utf-8-sig") as f:
            # Sniff the dialect only when the extension does not dictate the
            # delimiter. A .tsv is tab-separated by definition, so never let the
            # sniffer override that (e.g. a header that contains commas).
            sample = f.read(8192)
            f.seek(0)

            if path.suffix.lower() != ".tsv":
                try:
                    dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
                    delimiter = dialect.delimiter
                except csv.Error:
                    pass  # Use default

            reader = csv.reader(f, delimiter=delimiter)
            rows_raw = list(reader)

        if not rows_raw:
            return ParsedContent(
                source_path=str(path),
                format="csv",
                tables=[],
            )

        # First row is headers
        headers = rows_raw[0]
        data_rows: list[list[Any]] = []

        for row in rows_raw[1:]:
            # Pad or trim to match header count
            if len(row) < len(headers):
                row = row + [""] * (len(headers) - len(row))
            elif len(row) > len(headers):
                row = row[: len(headers)]
            data_rows.append(row)

        table = ParsedTable(
            name=path.stem,
            headers=headers,
            rows=data_rows,
        )

        return ParsedContent(
            source_path=str(path),
            format="csv",
            tables=[table],
            metadata={
                "delimiter": delimiter,
                "row_count": len(data_rows),
                "column_count": len(headers),
            },
        )
