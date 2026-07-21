"""Generate FAIR Data Station Turtle RDF from a metaseed ISA dataset.

FAIRDOM-SEEK imports this format natively via "Import from FAIR Data Station":
it builds the whole ISA structure (Investigation → Study → Assay/Sample) and
derives Extended Metadata Types from the RDF's non-core property definitions.

The emitted graph has two parts, mirroring SEEK's reader
(``lib/seek/fair_data_station/``):

- **instances** — one resource per entity, typed ``jerm:<Type>``, linked by
  ``jerm:hasPart``, with ``schema:identifier``/``title``/``description`` and one
  triple per populated field;
- **property definitions** — each field property declared ``rdf:type
  rdf:Property`` with ``rdfs:label``, ``schema:description``,
  ``schema:valuePattern`` (from the field's regex/constraint) and
  ``schema:valueRequired`` — SEEK turns these into Extended Metadata attributes.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

try:
    from rdflib import RDF, RDFS, Graph, Literal, Namespace, URIRef
except (
    ModuleNotFoundError
) as exc:  # pragma: no cover - exercised only without the extra
    raise ModuleNotFoundError(
        "SEEK FAIR Data Station export requires rdflib. "
        "Install with: pip install 'metaseed[seek]'"
    ) from exc

from metaseed.specs.loader import SpecLoader

if TYPE_CHECKING:
    from metaseed.api.client import MetaseedClient
    from metaseed.specs.schema import FieldSpec

JERM = Namespace("http://jermontology.org/ontology/JERMOntology#")
SCHEMA = Namespace("http://schema.org/")
FAIR = Namespace("http://fairbydesign.nl/ontology/")
_BASE = "http://fairbydesign.nl/ontology/"

# metaseed entity type -> (JERM class, URI id-prefix). Only ISA-structural and
# sample-bearing entities become FDS resources; other entities are skipped.
_JERM: dict[str, tuple[str, str]] = {
    "Investigation": ("Investigation", "inv"),
    "Study": ("Study", "stu"),
    "ObservationUnit": ("ObservationUnit", "obs"),
    "Assay": ("Assay", "assay"),
    "Sample": ("Sample", "sample"),
    "Source": ("Sample", "source"),
    "Extract": ("Sample", "extract"),
    "LabeledExtract": ("Sample", "lextract"),
    "OtherMaterial": ("Sample", "material"),
}
# Fields carried by SEEK's core annotations (not emitted as extended metadata).
_CORE_FIELDS = {"identifier", "title", "name", "description"}


def _slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-") or "x"


def _field_index(client: MetaseedClient) -> dict[str, dict[str, FieldSpec]]:
    profile = SpecLoader().load_profile(client.version, client.profile)
    return {
        name: {f.name: f for f in entity.fields}
        for name, entity in profile.entities.items()
    }


def to_fair_data_station_rdf(client: MetaseedClient) -> str:
    """Render a metaseed ISA dataset as FAIR Data Station Turtle RDF.

    Args:
        client: A MetaseedClient holding an ISA-style dataset (Investigation at
            the root). Only entities mapped in :data:`_JERM` are emitted.

    Returns:
        A Turtle string SEEK's "Import from FAIR Data Station" accepts.
    """
    fields = _field_index(client)
    values_by_node = {
        e.get("_node_id"): e for e in client.serialize().get("entities", [])
    }

    graph = Graph()
    graph.bind("jerm", JERM)
    graph.bind("schema", SCHEMA)
    graph.bind("fair", FAIR)
    used: dict[str, FieldSpec] = {}

    def walk(node: Any, parent_path: str) -> None:
        mapping = _JERM.get(node.entity_type)
        if mapping is None:
            return
        jerm_class, prefix = mapping
        identifier = node.label or node.id
        segment = f"{prefix}_{_slug(identifier)}"
        path = f"{parent_path}/{segment}" if parent_path else segment
        uri = URIRef(_BASE + path)

        graph.add((uri, RDF.type, JERM[jerm_class]))
        graph.add((uri, SCHEMA.identifier, Literal(identifier)))

        data = values_by_node.get(node.id, {})
        entity_fields = fields.get(node.entity_type, {})
        for key, value in data.items():
            if key.startswith("_") or value in (None, "", [], {}):
                continue
            if key == "title":
                graph.add((uri, SCHEMA.title, Literal(value)))
            elif key == "description":
                graph.add((uri, SCHEMA.description, Literal(value)))
            elif key in _CORE_FIELDS:
                continue
            elif isinstance(value, (str, int, float, bool)):
                graph.add((uri, SCHEMA[key], Literal(value)))
                if key in entity_fields:
                    used[key] = entity_fields[key]

        for child in node.children:
            child_mapping = _JERM.get(child.entity_type)
            if child_mapping is not None:
                child_segment = f"{child_mapping[1]}_{_slug(child.label or child.id)}"
                graph.add((uri, JERM.hasPart, URIRef(f"{_BASE}{path}/{child_segment}")))
            walk(child, path)

    for root in client.get_tree():
        walk(root, "")

    # Property definitions -> SEEK builds Extended Metadata attributes from these.
    for name, spec in used.items():
        prop = SCHEMA[name]
        graph.add((prop, RDF.type, RDF.Property))
        graph.add((prop, RDFS.label, Literal(spec.description or name)))
        if spec.description:
            graph.add((prop, SCHEMA.description, Literal(spec.description)))
        pattern = spec.constraints.pattern if spec.constraints else None
        if pattern:
            graph.add((prop, SCHEMA.valuePattern, Literal(pattern)))
        graph.add((prop, SCHEMA.valueRequired, Literal(spec.required)))

    serialized: str = graph.serialize(format="turtle")
    return serialized
