"""Taxon fields: an NCBI Taxonomy term in the dataset, its number in an export.

A field of type ``ontology_term`` scoped to exactly ``[ncbitaxon]`` stores the
term the lookup returns, ``NCBITaxon:3702``. ENA's ``TAXON_ID`` and a SEEK
taxon attribute hold the bare number, so the exporters write it through
:func:`export_values`. See docs/api/schema-specs.md#taxon-fields.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any

from metaseed.specs.schema import FieldSpec, FieldType

#: The OLS id of NCBI Taxonomy, as a field's ``ontologies`` names it.
TAXON_ONTOLOGY = "ncbitaxon"

_TAXON = re.compile(
    r"(?:(?:https?://purl\.obolibrary\.org/obo/)?NCBITaxon[:_])?(\d+)", re.IGNORECASE
)


def is_taxon_field(field: FieldSpec) -> bool:
    """Whether the field holds an NCBI Taxonomy term and nothing else."""
    ontologies = [o.lower() for o in field.ontologies or []]
    return field.type == FieldType.ONTOLOGY_TERM and ontologies == [TAXON_ONTOLOGY]


def taxon_number(value: Any) -> int | None:
    """The NCBI Taxonomy number a value names.

    Args:
        value: ``NCBITaxon:3702``, ``NCBITaxon_3702``, the term's OBO IRI, or
            the number itself.

    Returns:
        The number, or ``None`` when the value names no NCBI taxon.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    match = _TAXON.fullmatch(str(value).strip())
    number = int(match.group(1)) if match else 0
    return number or None


def export_values(
    fields: Iterable[FieldSpec], values: Mapping[str, Any]
) -> dict[str, Any]:
    """The values with every taxon field written as its NCBI number.

    A taxon value that names no NCBI taxon is left out: a repository refuses
    text where it expects a taxon number, and the rest of the record still goes.

    Args:
        fields: The entity's fields.
        values: The entity's values by field name.

    Returns:
        A copy of ``values`` ready for an export.
    """
    taxon_fields = {f.name for f in fields if is_taxon_field(f)}
    out: dict[str, Any] = {}
    for name, value in values.items():
        if name in taxon_fields and value not in (None, ""):
            number = taxon_number(value)
            if number is None:
                continue
            value = number
        out[name] = value
    return out
