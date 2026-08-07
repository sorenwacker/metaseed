"""Mapping a profile field onto a SEEK sample-attribute type.

Shared by the two projections that build Sample Types: the profile-time one in
:mod:`metaseed.seek.provision` (for the FAIR-Data-Station file route, which
matches samples by attribute PID) and the dataset-time one in
:mod:`metaseed.seek.isa_types` (for the ISA-JSON compliant API route, where each
assay owns its own type).

Titles rather than ids: SEEK resolves ``sample_attribute_type`` by either, and
the numeric ids are per-instance while the titles are stable.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from metaseed.specs.schema import FieldType

if TYPE_CHECKING:
    from metaseed.specs.schema import FieldSpec

# metaseed scalar FieldType -> SEEK base sample-attribute-type title.
_ATTR_TYPE_TITLE: dict[FieldType, str] = {
    FieldType.STRING: "String",
    FieldType.INTEGER: "Integer",
    FieldType.FLOAT: "Real number",
    FieldType.BOOLEAN: "Boolean",
    FieldType.DATE: "Date",
    FieldType.DATETIME: "Date time",
    FieldType.URI: "Web link",
    # ontology_term is an open OLS lookup, not a closed set -> a plain string
    # attribute (a Controlled Vocabulary needs a fixed term list, which only an
    # ``enum`` field provides).
    FieldType.ONTOLOGY_TERM: "String",
}
CV_TYPE_TITLE = "Controlled Vocabulary"
CV_LIST_TYPE_TITLE = "Controlled Vocabulary List"
LIST_FALLBACK_TITLE = "Text"  # a list of primitives with no enum -> free text


def is_cv_field(field: FieldSpec) -> bool:
    """A field becomes a Controlled Vocabulary iff it declares a closed enum."""
    return bool(field.constraints and field.constraints.enum)


def attribute_type_title(field: FieldSpec) -> str:
    """SEEK base attribute-type title for a (non-nested) field."""
    if is_cv_field(field):
        return CV_LIST_TYPE_TITLE if field.type == FieldType.LIST else CV_TYPE_TITLE
    if field.type == FieldType.LIST:
        return LIST_FALLBACK_TITLE
    return _ATTR_TYPE_TITLE.get(field.type, "String")
