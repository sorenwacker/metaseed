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

from metaseed.seek.roles import JERM_CLASSES as _JERM
from metaseed.specs.loader import SpecLoader

if TYPE_CHECKING:
    from metaseed.api.client import MetaseedClient
    from metaseed.specs.schema import FieldSpec, ProfileSpec

# Core fields emitted as native schema.org triples (or the identifier), so they
# do not get a property definition of their own.
_CORE_FIELDS = frozenset({"identifier", "unique_id", "title", "name", "description"})

JERM = Namespace("http://jermontology.org/ontology/JERMOntology#")
SCHEMA = Namespace("http://schema.org/")
FAIR = Namespace("http://fairbydesign.nl/ontology/")
_BASE = "http://fairbydesign.nl/ontology/"

EXPORTED_TYPES: frozenset[str] = frozenset(_JERM)
"""Entity type names that :func:`to_fair_data_station_rdf` actually emits.

Any node whose ``entity_type`` is not in this set is skipped during export, so
callers (e.g. the ``/seek`` page's "Will emit" preview) can filter to it instead
of counting every node and overstating what the download contains.
"""


def _slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-") or "x"


def _emit_property_definition(graph: Graph, name: str, spec: FieldSpec) -> None:
    """Emit one ``rdf:Property`` definition SEEK turns into an EMT attribute."""
    prop = SCHEMA[name]
    graph.add((prop, RDF.type, RDF.Property))
    graph.add((prop, RDFS.label, Literal(name)))
    if spec.description:
        graph.add((prop, SCHEMA.description, Literal(spec.description)))
    pattern = spec.constraints.pattern if spec.constraints else None
    if pattern:
        graph.add((prop, SCHEMA.valuePattern, Literal(pattern)))
    graph.add((prop, SCHEMA.valueRequired, Literal(spec.required)))


def to_fair_data_station_model_rdf(profile: ProfileSpec) -> str:
    """Render a profile's field *definitions* as FAIR Data Station Turtle (no data).

    Unlike :func:`to_fair_data_station_rdf` (which defines only the fields a
    dataset actually populated), this emits a property definition for **every**
    non-core field in the profile. A SEEK admin feeds it to the admin "Extended
    Metadata Types → create from FAIR Data Station TTL" flow to define the custom
    metadata the JSON:API cannot create — the model half of the hybrid flow.

    As in the data exporter, a field name reused across entities resolves to a
    single (last-wins) global ``schema:<field>`` definition.
    """
    graph = Graph()
    graph.bind("jerm", JERM)
    graph.bind("schema", SCHEMA)
    graph.bind("fair", FAIR)
    seen: set[str] = set()
    for entity in profile.entities.values():
        for field in entity.fields:
            if field.is_nested() or field.name in _CORE_FIELDS or field.name in seen:
                continue
            seen.add(field.name)
            _emit_property_definition(graph, field.name, field)
    serialized: str = graph.serialize(format="turtle")
    return serialized


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
    letting a profile pick the emitted ``jerm:`` class instead of the built-in
    name map. Note it overrides the ``rdf:type`` only — nodes keep their position
    in the tree, which is what SEEK's positional reader actually consumes (see the
    module docstring), so declaring ``role=ObservationUnit`` re-types but does not
    itself insert an ObservationUnit level.
    """
    # A dataset built from a derived spec (e.g. imported via
    # ``metaseed.seek.importer``) carries its ProfileSpec in memory and has no
    # file to load; fall back to loading by name for installed profiles.
    in_memory = getattr(client._facade, "_spec", None)
    profile = in_memory or SpecLoader().load_profile(client.version, client.profile)
    fields = {
        name: {f.name: f for f in entity.fields}
        for name, entity in profile.entities.items()
    }
    roles: dict[str, str] = {
        name: entity.seek.role
        for name, entity in profile.entities.items()
        if entity.seek and entity.seek.role
    }
    return fields, roles


def exportable_entity_types(client: MetaseedClient) -> frozenset[str]:
    """Entity type names the FDS export will emit for ``client``'s profile.

    The built-in JERM-mapped names (:data:`EXPORTED_TYPES`) plus any entity the
    profile maps via ``seek.role``. The ``/seek`` preview uses this (rather than
    the static :data:`EXPORTED_TYPES`) so a custom profile that makes a
    non-JERM-named entity exportable purely through a role is still counted and
    downloadable, matching what :func:`to_fair_data_station_rdf` actually emits.
    """
    _fields, roles = _profile_index(client)
    return EXPORTED_TYPES | frozenset(roles)


def to_fair_data_station_rdf(client: MetaseedClient) -> str:  # noqa: C901
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

        identity = node_identity(node)
        graph.add((uri, RDF.type, JERM[jerm_class]))
        graph.add((uri, SCHEMA.identifier, Literal(identity)))

        data = values_by_node.get(node.id, {})
        # SEEK derives a resource's (required) title/name from schema:title /
        # schema:name, not schema:identifier. Emit both for every instance,
        # falling back to the identity when the entity has no title/name field,
        # so identifier-keyed entities (e.g. a MIAPPE Sample) still import.
        title_value = data.get("title") or data.get("name") or identity
        graph.add((uri, SCHEMA.title, Literal(title_value)))
        graph.add((uri, SCHEMA.name, Literal(data.get("name") or title_value)))

        entity_fields = fields.get(node.entity_type, {})
        for key, value in data.items():
            if key.startswith("_") or key in (
                "identifier",
                "unique_id",
                "title",
                "name",
            ):
                continue
            if value in (None, "", [], {}) or not isinstance(
                value, (str, int, float, bool)
            ):
                continue
            if key == "description":
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
        _emit_property_definition(graph, name, spec)

    serialized: str = graph.serialize(format="turtle")
    return serialized
