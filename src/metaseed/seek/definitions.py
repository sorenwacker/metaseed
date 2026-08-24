"""Deriving template-bound profile entities from SEEK ISA Template definitions.

A SEEK instance is configured from ISA Template JSON files (the format
``POST /templates/populate_template`` takes, and the one *Download ISA
Templates* writes). Those files are the source of truth for a Sample Type's
columns — attribute type, required flag, title attribute, ISA tag, vocabulary —
and the JSON:API never exposes them once installed. A profile that must match
the installed templates column for column is therefore derived from the files
rather than written by hand: :func:`entity_from_isa_template` turns one template
into an entity definition, and :func:`apply_isa_templates` merges a set of them
into an existing profile document, replacing the fields of every entity that
names one of the templates while keeping what only the profile knows (an
``Input`` field's ``reference``, ontology terms, identity markers).

The mapping is reversible: :func:`metaseed.seek.templates.to_isa_template_json`
renders the derived entity back into the same attributes, which is what makes
"column for column" testable.
"""

from __future__ import annotations

from typing import Any

# SEEK attribute type title -> the metaseed field type that carries it. Types
# with no metaseed counterpart keep ``string``/``uri``/``list`` and record the
# exact SEEK type in ``seek_attribute_type`` so nothing is lost on the way back.
_FIELD_TYPE_FOR: dict[str, str] = {
    "String": "string",
    "Text": "string",
    "Integer": "integer",
    "Real number": "float",
    "Boolean": "boolean",
    "Date": "date",
    "Date time": "datetime",
    "ENA custom date": "string",
    "Web link": "uri",
    "URI": "uri",
    "Registered Data file": "uri",
    "Registered Sample": "string",
    "Registered Sample List": "list",
    "Controlled Vocabulary": "string",
    "Controlled Vocabulary List": "list",
}
# SEEK types the metaseed field type names on its own; every other type is
# kept explicitly.
_IMPLIED_BY_FIELD_TYPE = frozenset(
    {"String", "Integer", "Real number", "Boolean", "Date", "Date time", "Web link"}
)
# Field attributes only the profile knows; a re-derivation keeps them.
_KEPT_FROM_PROFILE = (
    "reference",
    "ontology_term",
    "ontologies",
    "within",
    "is_identifier",
    "is_label",
    "codename",
    "unit",
    "dcat",
    "example",
)


def field_from_template_attribute(attribute: dict[str, Any]) -> dict[str, Any]:
    """One template attribute as a profile field definition (a plain dict).

    Args:
        attribute: An entry of a template's ``data`` list — ``name``,
            ``dataType``, and optionally ``description``, ``required``,
            ``title``, ``isaTag``, ``CVList``, ``allowCVFreeText``.

    Returns:
        The field as it is written in a profile YAML.

    Raises:
        ValueError: If the attribute's ``dataType`` is one this mapping does
            not know; guessing a field type would silently change the column.
    """
    seek_type = attribute["dataType"]
    if seek_type not in _FIELD_TYPE_FOR:
        raise ValueError(
            f"attribute {attribute.get('name')!r} has SEEK type {seek_type!r}, "
            f"which has no profile mapping (known: {sorted(_FIELD_TYPE_FOR)})"
        )
    field: dict[str, Any] = {
        "name": attribute["name"],
        "type": _FIELD_TYPE_FOR[seek_type],
    }
    if field["type"] == "list":
        field["items"] = "string"
    if attribute.get("required"):
        field["required"] = True
    if attribute.get("description"):
        field["description"] = attribute["description"]
    if attribute.get("isaTag"):
        field["isa_tag"] = attribute["isaTag"]
    if attribute.get("title"):
        field["is_label"] = True
    if seek_type not in _IMPLIED_BY_FIELD_TYPE:
        field["seek_attribute_type"] = seek_type
    if seek_type.startswith("Controlled Vocabulary"):
        terms = list(attribute.get("CVList") or [])
        if terms:
            field["constraints"] = {"enum": terms}
        # Populating the template makes SEEK create a vocabulary named after
        # the attribute; that is the one the column binds.
        field["seek_controlled_vocab"] = attribute["name"]
        if attribute.get("allowCVFreeText"):
            field["seek_cv_free_text"] = True
    return field


def entity_from_isa_template(template: dict[str, Any]) -> dict[str, Any]:
    """A template as a template-bound Sample-role entity definition.

    Args:
        template: One entry of a template file's ``data`` list — ``metadata``
            (``name``, ``level``, ...) and ``data`` (the attributes).

    Returns:
        The entity as written in a profile YAML: its fields, and
        ``seek: {role: Sample, template: <name>}``.
    """
    metadata = template["metadata"]
    return {
        "description": (
            f"`{metadata['name']}` sample type, version {metadata.get('version', '')}, "
            f"attached at ISA level `{metadata.get('level', '')}`."
        ),
        "fields": [field_from_template_attribute(a) for a in template["data"]],
        "seek": {"role": "Sample", "template": metadata["name"]},
    }


def apply_isa_templates(
    profile: dict[str, Any], templates: list[dict[str, Any]]
) -> dict[str, list[str]]:
    """Re-derive every entity of ``profile`` that names one of ``templates``.

    An entity whose ``seek.template`` matches a template's name gets that
    template's attributes as its fields. Per field, what only the profile knows
    (:data:`_KEPT_FROM_PROFILE`) is carried over from the field of the same
    name; a field the template does not have is dropped, since the column does
    not exist in SEEK.

    Args:
        profile: A profile document (as loaded from YAML); modified in place.
        templates: Template entries (each file's ``data`` list, concatenated).

    Returns:
        Entity name -> the template it was re-derived from, for reporting.
        Entities naming a template not in ``templates`` are left untouched.
    """
    by_name = {t["metadata"]["name"]: t for t in templates}
    applied: dict[str, list[str]] = {}
    for entity_name, entity in profile.get("entities", {}).items():
        template_name = (entity.get("seek") or {}).get("template")
        if not template_name or template_name not in by_name:
            continue
        old_fields = {f["name"]: f for f in entity.get("fields", [])}
        derived = entity_from_isa_template(by_name[template_name])
        # The template's title attribute is the entity's label; a label the
        # profile had put elsewhere would make two.
        kept = tuple(
            k
            for k in _KEPT_FROM_PROFILE
            if not (
                k == "is_label" and any(f.get("is_label") for f in derived["fields"])
            )
        )
        new_fields = []
        for field in derived["fields"]:
            previous = old_fields.get(field["name"], {})
            for key in kept:
                if key in previous and key not in field:
                    field[key] = previous[key]
            new_fields.append(field)
        entity["fields"] = new_fields
        entity["seek"] = {**(entity.get("seek") or {}), **derived["seek"]}
        applied[entity_name] = [
            f["name"]
            for f in old_fields.values()
            if f["name"] not in {x["name"] for x in new_fields}
        ]
    return applied
