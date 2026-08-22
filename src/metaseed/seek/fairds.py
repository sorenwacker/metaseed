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

SEEK reads the ISA hierarchy *positionally* — Investigation → Study →
ObservationUnit → Sample → Assay — not by ``rdf:type``, so a Study's children are
read as ObservationUnits whatever they claim to be. Profiles do not model that
level, treating the observation unit as carried by the sample, so this exporter
synthesises one ``ppeo:observation_unit`` per Sample beneath a Study. Without it a
Sample is read as an empty ObservationUnit and neither it nor its Assays arrive,
since SEEK reaches Assays through ``observation_units -> samples -> assays``.

Known limitation: a property definition uses one global
``schema:<field>`` URI, so a field name reused across entities with different
constraints resolves to a single (last-written) definition.
"""

from __future__ import annotations

import logging
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

from metaseed.seek.naming import property_uri
from metaseed.seek.roles import JERM_CLASSES as _JERM
from metaseed.seek.roles import (
    entity_jerm_class,
    role_from_annotation,
    unmapped_entities,
)

if TYPE_CHECKING:
    from metaseed.api.client import MetaseedClient
    from metaseed.specs.schema import EntityDefSpec, FieldSpec, ProfileSpec

# Core fields emitted as native schema.org triples (or the identifier), so they
# do not get a property definition of their own.
from metaseed.seek.values import CORE_FIELDS as _CORE_FIELDS
from metaseed.seek.values import profile_of

logger = logging.getLogger(__name__)

JERM = Namespace("http://jermontology.org/ontology/JERMOntology#")
# MIAPPE's ontology. SEEK types the ObservationUnit level from PPEO while the
# rest of the ISA hierarchy is JERM.
PPEO = Namespace("http://purl.org/ppeo/PPEO.owl#")
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
    # Percent-encoded, so a name with a space yields a URI rdflib can serialize
    # and SEEK accepts -- and the same one provisioning registered.
    prop = URIRef(property_uri(name))
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

    SEEK does not build a type from property definitions alone: its importer
    walks the ``jerm:Investigation`` / ``jerm:Study`` / ``jerm:Assay`` instances
    and derives one Extended Metadata Type per level from the annotations those
    instances carry. A definitions-only file answered "no new Extended Metadata
    Types". So beside the definitions this emits one skeleton instance per ISA
    level, chained by ``jerm:hasPart``, each carrying a placeholder value for
    every non-core field of the entity that fills that role.

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
    _emit_skeleton_instances(graph, profile)
    serialized: str = graph.serialize(format="turtle")
    return serialized


#: The ISA levels SEEK derives Extended Metadata Types for, top down.
_EXTENDED_METADATA_LEVELS = ("Investigation", "Study", "Assay")


def _emit_skeleton_instances(graph: Graph, profile: ProfileSpec) -> None:
    """Emit one placeholder instance per ISA level, chained by ``jerm:hasPart``.

    Each level is filled by the first entity whose JERM class is that level and
    carries that entity's non-core fields. A level no entity fills is still
    emitted, empty, so the chain SEEK walks positionally stays intact.
    """
    by_level: dict[str, EntityDefSpec] = {}
    for name, entity in profile.entities.items():
        role = entity.seek.role if entity.seek else None
        level = entity_jerm_class(name, role, entity.ontology_term)
        if level in _EXTENDED_METADATA_LEVELS:
            by_level.setdefault(level, entity)

    parent: URIRef | None = None
    path = ""
    for level in _EXTENDED_METADATA_LEVELS:
        prefix = _ROLE_PREFIX[level]
        path = f"{path}/{prefix}_template" if path else f"{prefix}_template"
        uri = URIRef(_BASE + path)
        identity = f"{profile.name}-{level.lower()}-template"
        graph.add((uri, RDF.type, JERM[level]))
        graph.add((uri, SCHEMA.identifier, Literal(identity)))
        graph.add((uri, SCHEMA.title, Literal(identity)))
        graph.add((uri, SCHEMA.name, Literal(identity)))
        if parent is not None:
            graph.add((parent, JERM.hasPart, uri))
        filler = by_level.get(level)
        if filler is not None:
            for field in filler.fields:
                if field.is_nested() or field.name in _CORE_FIELDS:
                    continue
                graph.add((uri, URIRef(property_uri(field.name)), Literal("")))
        parent = uri


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
    profile = profile_of(client)
    fields = {
        name: {f.name: f for f in entity.fields}
        for name, entity in profile.entities.items()
    }
    # An explicit seek.role wins; failing that, the class the entity's own
    # annotation names. Resolved once here rather than at each call site, so
    # everything reading ``roles`` sees the annotation too — the map held only
    # hand-set roles, which is why a profile faithfully derived from JERM
    # exported almost nothing (#234).
    roles: dict[str, str] = {}
    for name, entity in profile.entities.items():
        role = entity.seek.role if entity.seek else None
        resolved = role or role_from_annotation(entity.ontology_term)
        if resolved:
            roles[name] = resolved

    skipped = unmapped_entities(profile)
    if skipped:
        # Said out loud: the export does not fail for these, it simply produces
        # less than its author expects, which is the whole complaint in #234.
        logger.warning(
            "SEEK export maps no JERM class for %s; %s will not be exported. "
            "Give each a seek.role, or annotate it with the class it represents.",
            ", ".join(skipped),
            "they" if len(skipped) > 1 else "it",
        )

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
            the root). An entity is emitted when it resolves to a JERM class —
            either via a profile-declared SEEK role or the default
            :data:`_JERM` mapping (the profile role takes precedence).

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
        # The spec says which field identifies the entity; prefer it. Guessing at
        # conventional names alone falls through to the internal node id for a
        # profile that keys its Sample on e.g. ``sample_name``, which then leaks
        # an opaque, run-specific string into the exported URIs and titles.
        for name, spec in fields.get(node.entity_type, {}).items():
            if getattr(spec, "is_identifier", False) and data.get(name):
                return str(data[name])
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

    def walk(node: Any, parent_path: str, parent_uri: URIRef | None = None) -> None:
        """Emit ``node`` and its descendants beneath ``parent_path``.

        An entity with no JERM class is not exported, but it does not take its
        descendants with it: they are emitted against the nearest mapped
        ancestor instead. Dropping a whole subtree because one level in the
        middle has no mapping loses content silently — ``unmapped_entities``
        warns about the unmapped entity, never about what hung beneath it.
        """
        mapping = resolve(node.entity_type)
        seg = segment(node)
        if mapping is None or seg is None:
            for child in node.children:
                walk(child, parent_path, parent_uri)
            return
        jerm_class = mapping[0]
        path = f"{parent_path}/{seg}" if parent_path else seg
        uri = URIRef(_BASE + path)

        if parent_uri is not None:
            # Added here rather than by the caller so a node surfaced from
            # under an unmapped parent is attached too.
            graph.add((parent_uri, JERM.hasPart, uri))

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
                # Percent-encoded through the same helper provisioning uses: a
                # field named with a space is what SEEK matches an imported
                # sample to its attribute by, and rdflib refuses to serialize
                # the unencoded form at all.
                graph.add((uri, URIRef(property_uri(key)), Literal(value)))
                if key in entity_fields:
                    used[key] = entity_fields[key]

        for child in node.children:
            child_seg = segment(child)
            if child_seg is None:
                walk(child, path, uri)
                continue
            child_mapping = resolve(child.entity_type)
            if jerm_class == "Study" and child_mapping and child_mapping[0] == "Sample":
                # SEEK reads the ISA hierarchy positionally, so a Study's children
                # are ObservationUnits whatever their rdf:type says. A Sample
                # placed directly under a Study is therefore read as an empty
                # ObservationUnit and never arrives. Profiles do not model that
                # level -- the observation unit is carried by the sample -- so
                # synthesise one per sample here, keeping specs free of it.
                ou_path = f"{path}/obs_{_slug(node_identity(child))}"
                ou_uri = URIRef(_BASE + ou_path)
                identity = node_identity(child)
                graph.add((ou_uri, RDF.type, PPEO.observation_unit))
                graph.add((ou_uri, SCHEMA.identifier, Literal(identity)))
                graph.add((ou_uri, SCHEMA.title, Literal(identity)))
                graph.add((ou_uri, SCHEMA.name, Literal(identity)))
                graph.add((uri, JERM.hasPart, ou_uri))
                walk(child, ou_path, ou_uri)
                continue
            walk(child, path, uri)

    for root in client.get_tree():
        walk(root, "")

    # Property definitions -> SEEK builds Extended Metadata attributes from these.
    for name, spec in used.items():
        _emit_property_definition(graph, name, spec)

    serialized: str = graph.serialize(format="turtle")
    return serialized
