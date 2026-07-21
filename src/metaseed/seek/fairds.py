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

Known limitations (SEEK reads the ISA hierarchy *positionally* — Investigation →
Study → ObservationUnit → Sample → Assay — not by ``rdf:type``): the metaseed ISA
profile has no ObservationUnit level, so entities below Study land one level too
high on import (a Study's Samples are read as ObservationUnits). Investigation and
Study round-trip cleanly today; a follow-up must insert the ObservationUnit layer
for full sample/assay fidelity. Also, a property definition uses one global
``schema:<field>`` URI, so a field name reused across entities with different
constraints resolves to a single (last-written) definition.
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


def _slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-") or "x"


# Default id-prefix per JERM role (for readable URIs).
_ROLE_PREFIX = {
    "Investigation": "inv",
    "Study": "stu",
    "ObservationUnit": "obs",
    "Assay": "assay",
    "Sample": "sample",
}


def _profile_index(
    client: MetaseedClient,
) -> tuple[dict[str, dict[str, FieldSpec]], dict[str, str]]:
    """Return (entity -> {field name -> spec}, entity -> SEEK role) for the profile.

    The role comes from the entity's ``seek.role`` when the profile declares one,
    letting a profile drive the ISA mapping instead of the built-in name map.
    """
    profile = SpecLoader().load_profile(client.version, client.profile)
    fields = {
        name: {f.name: f for f in entity.fields}
        for name, entity in profile.entities.items()
    }
    roles = {
        name: entity.seek.role
        for name, entity in profile.entities.items()
        if entity.seek and entity.seek.role
    }
    return fields, roles


def to_fair_data_station_rdf(client: MetaseedClient) -> str:
    """Render a metaseed ISA dataset as FAIR Data Station Turtle RDF.

    Args:
        client: A MetaseedClient holding an ISA-style dataset (Investigation at
            the root). Only entities mapped in :data:`_JERM` are emitted.

    Returns:
        A Turtle string SEEK's "Import from FAIR Data Station" accepts.
    """
    fields, roles = _profile_index(client)
    values_by_node = {
        e.get("_node_id"): e for e in client.serialize().get("entities", [])
    }

    def resolve(entity_type: str) -> tuple[str, str] | None:
        """(JERM class, URI prefix) for an entity type — profile role wins."""
        role = roles.get(entity_type)
        if role:
            return role, _ROLE_PREFIX.get(role, _slug(role).lower())
        return _JERM.get(entity_type)

    graph = Graph()
    graph.bind("jerm", JERM)
    graph.bind("schema", SCHEMA)
    graph.bind("fair", FAIR)
    used: dict[str, FieldSpec] = {}

    def node_identity(node: Any) -> str:
        """The entity's own identifier, from its data — not the display label.

        ``node.label`` is the value of the entity's *first* spec field, which is
        the identifier only for some entities (e.g. Study's is ``study_id``), so
        it would collide sample siblings onto one URI. Use the real id field.
        """
        data = values_by_node.get(node.id, {})
        return str(
            data.get("identifier")
            or data.get("unique_id")
            or data.get("name")
            or node.id
        )

    def segment(node: Any) -> str | None:
        mapping = resolve(node.entity_type)
        if mapping is None:
            return None
        return f"{mapping[1]}_{_slug(node_identity(node))}"

    def walk(node: Any, parent_path: str) -> None:
        mapping = resolve(node.entity_type)
        seg = segment(node)
        if mapping is None or seg is None:
            return
        jerm_class = mapping[0]
        path = f"{parent_path}/{seg}" if parent_path else seg
        uri = URIRef(_BASE + path)

        graph.add((uri, RDF.type, JERM[jerm_class]))
        graph.add((uri, SCHEMA.identifier, Literal(node_identity(node))))

        entity_fields = fields.get(node.entity_type, {})
        for key, value in values_by_node.get(node.id, {}).items():
            if key.startswith("_") or key in ("identifier", "unique_id"):
                continue
            if value in (None, "", [], {}) or not isinstance(
                value, (str, int, float, bool)
            ):
                continue
            if key == "title":
                graph.add((uri, SCHEMA.title, Literal(value)))
            elif key == "name":
                graph.add((uri, SCHEMA.name, Literal(value)))
            elif key == "description":
                graph.add((uri, SCHEMA.description, Literal(value)))
            else:
                graph.add((uri, SCHEMA[key], Literal(value)))
                if key in entity_fields:
                    used[key] = entity_fields[key]

        for child in node.children:
            child_seg = segment(child)
            if child_seg is not None:
                graph.add((uri, JERM.hasPart, URIRef(f"{_BASE}{path}/{child_seg}")))
            walk(child, path)

    for root in client.get_tree():
        walk(root, "")

    # Property definitions -> SEEK builds Extended Metadata attributes from these.
    for name, spec in used.items():
        prop = SCHEMA[name]
        graph.add((prop, RDF.type, RDF.Property))
        graph.add((prop, RDFS.label, Literal(name)))
        if spec.description:
            graph.add((prop, SCHEMA.description, Literal(spec.description)))
        pattern = spec.constraints.pattern if spec.constraints else None
        if pattern:
            graph.add((prop, SCHEMA.valuePattern, Literal(pattern)))
        graph.add((prop, SCHEMA.valueRequired, Literal(spec.required)))

    serialized: str = graph.serialize(format="turtle")
    return serialized
