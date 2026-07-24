"""Parse ISA-Tab tab-delimited files into metaseed entity dicts.

The inverse of the writer in :mod:`metaseed.isatab`: a generic row parser plus
entity extractors used by the MetaboLights importer to recover Samples,
DataFiles and Metabolites from a study's ``s_*.txt`` / ``a_*.txt`` / ``m_*.tsv``
files, because the ISA-JSON payload leaves those arrays empty (issue #146).

The row parser is entity-agnostic so a future ISA/MIAPPE ISA-Tab import can reuse
it. Stdlib only; no I/O.
"""

from __future__ import annotations

import re
from typing import Any

TAB = "\t"

# ISA-Tab "qualified" columns: ``Characteristics[Organism]``, ``Factor Value[Dose]``.
_QUALIFIED = re.compile(r"^(Characteristics|Factor Value|Parameter Value)\[(.+)\]$")

# Assay columns naming a data file (raw or derived spectral data, etc.).
_DATA_FILE_COLUMN = re.compile(r"Data File$")


def _split_lines(text: str) -> list[str]:
    return [line for line in text.splitlines() if line.strip()]


def read_rows(text: str) -> list[dict[str, str]]:
    """Parse a tab-delimited ISA-Tab file into rows keyed by column header.

    Duplicate headers — ISA-Tab repeats ``Term Source REF`` /
    ``Term Accession Number`` after each qualified column — are disambiguated by
    suffixing repeats with ``.<n>`` so no column is dropped.

    Args:
        text: The full text of an ISA-Tab file.

    Returns:
        One dict per data row, mapping (de-duplicated) header to cell value.
    """
    lines = _split_lines(text)
    if len(lines) < 2:
        return []
    headers = _dedupe(h.strip() for h in lines[0].split(TAB))
    rows: list[dict[str, str]] = []
    for line in lines[1:]:
        cells = line.split(TAB)
        rows.append(
            {
                h: (cells[i].strip() if i < len(cells) else "")
                for i, h in enumerate(headers)
            }
        )
    return rows


def _dedupe(headers: Any) -> list[str]:
    seen: dict[str, int] = {}
    out: list[str] = []
    for header in headers:
        if header in seen:
            seen[header] += 1
            out.append(f"{header}.{seen[header]}")
        else:
            seen[header] = 0
            out.append(header)
    return out


def _positional_rows(text: str) -> tuple[list[str], list[list[str]]]:
    """Return (headers, data-cell-rows) preserving original column order.

    Qualified columns (``Characteristics[X]``) are followed positionally by their
    ``Term Source REF`` / ``Term Accession Number``, so the extractors need the
    raw order rather than a de-duplicated dict.
    """
    lines = _split_lines(text)
    if len(lines) < 2:
        return [], []
    headers = [h.strip() for h in lines[0].split(TAB)]
    rows = [[c.strip() for c in line.split(TAB)] for line in lines[1:]]
    return headers, rows


def _cell(headers: list[str], cells: list[str], column: str) -> str:
    if column in headers:
        index = headers.index(column)
        if index < len(cells):
            return cells[index]
    return ""


def _trailing_accession(headers: list[str], cells: list[str], start: int) -> str:
    """The ``Term Accession Number`` immediately qualifying column ``start``."""
    for offset in (1, 2):
        index = start + offset
        if index < len(headers) and headers[index] == "Term Accession Number":
            return cells[index] if index < len(cells) else ""
    return ""


def read_samples(text: str) -> list[dict[str, Any]]:
    """Extract Sample entities from a study (``s_*.txt``) file.

    One Sample per row. ``Sample Name`` is the identifier, ``Source Name`` the
    parent link, and each ``Characteristics[...]`` / ``Factor Value[...]`` column
    becomes a child dict ``{"category", "value", "term_accession"?}``.
    """
    headers, rows = _positional_rows(text)
    samples: list[dict[str, Any]] = []
    for cells in rows:
        name = _cell(headers, cells, "Sample Name") or _cell(
            headers, cells, "Source Name"
        )
        if not name:
            continue
        sample: dict[str, Any] = {"name": name}
        source = _cell(headers, cells, "Source Name")
        if source:
            sample["source"] = source
        characteristics: list[dict[str, str]] = []
        factor_values: list[dict[str, str]] = []
        for index, header in enumerate(headers):
            match = _QUALIFIED.match(header)
            if not match:
                continue
            value = cells[index] if index < len(cells) else ""
            if not value:
                continue
            child: dict[str, str] = {"category": match.group(2), "value": value}
            accession = _trailing_accession(headers, cells, index)
            if accession:
                child["term_accession"] = accession
            if match.group(1) == "Characteristics":
                characteristics.append(child)
            elif match.group(1) == "Factor Value":
                factor_values.append(child)
        if characteristics:
            sample["characteristics"] = characteristics
        if factor_values:
            sample["factor_values"] = factor_values
        samples.append(sample)
    return samples


def read_data_files(text: str) -> list[dict[str, str]]:
    """Extract DataFile entities from an assay (``a_*.txt``) file.

    Every column whose header ends in ``Data File`` (e.g. ``Raw Spectral Data
    File``, ``Derived Spectral Data File``) yields one DataFile per non-empty
    value, linked to the row's ``Sample Name``.
    """
    headers, rows = _positional_rows(text)
    data_columns = [h for h in headers if _DATA_FILE_COLUMN.search(h)]
    files: list[dict[str, str]] = []
    seen: set[str] = set()
    for cells in rows:
        sample = _cell(headers, cells, "Sample Name")
        for column in data_columns:
            filename = _cell(headers, cells, column)
            if not filename or filename in seen:
                continue
            seen.add(filename)
            entry = {"name": filename, "kind": column}
            if sample:
                entry["sample"] = sample
            files.append(entry)
    return files


# MAF columns kept as Metabolite fields (a stable subset of the ~150-column file).
_MAF_FIELDS = (
    "database_identifier",
    "chemical_formula",
    "smiles",
    "inchi",
    "metabolite_identification",
    "mass_to_charge",
    "retention_time",
)


def read_metabolites(text: str) -> list[dict[str, str]]:
    """Extract Metabolite entities from a MAF (``m_*.tsv``) file.

    One Metabolite per row, keeping the stable identifying columns
    (:data:`_MAF_FIELDS`). Rows with no identifier and no name are skipped.
    """
    metabolites: list[dict[str, str]] = []
    for row in read_rows(text):
        entry = {field: row[field] for field in _MAF_FIELDS if row.get(field)}
        if entry.get("database_identifier") or entry.get("metabolite_identification"):
            metabolites.append(entry)
    return metabolites
