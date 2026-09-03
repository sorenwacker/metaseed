"""Tests for the FAIR Data Station Turtle RDF generator.

Hermetic — builds a small ISA dataset and parses the emitted Turtle back with
rdflib (no SEEK / network). SEEK's own reader accepts this format (verified
manually against a live instance).
"""

from __future__ import annotations

from rdflib import RDF, RDFS, Graph, Literal, Namespace

from metaseed import MetaseedClient
from metaseed.seek.fairds import (
    EXPORTED_TYPES,
    exportable_entity_types,
    to_fair_data_station_model_rdf,
    to_fair_data_station_rdf,
)

JERM = Namespace("http://jermontology.org/ontology/JERMOntology#")
SCHEMA = Namespace("http://schema.org/")


def _dataset() -> MetaseedClient:
    client = MetaseedClient("isa", "1.0")
    inv = client.create_entity(
        "Investigation",
        {"identifier": "INV1", "title": "My Investigation", "description": "d"},
        skip_validation=True,
    )
    client.create_entity(
        "Study",
        # 'filename' is a non-core field -> exercises the property-definition path.
        {"identifier": "STU1", "title": "Study one", "filename": "s_study.txt"},
        parent_id=inv.id,
        skip_validation=True,
    )
    return client


def _graph() -> Graph:
    graph = Graph()
    graph.parse(data=to_fair_data_station_rdf(_dataset()), format="turtle")
    return graph


def test_investigation_typed_and_titled():
    graph = _graph()
    inv = next(graph.subjects(RDF.type, JERM.Investigation))
    assert (inv, SCHEMA.identifier, None) in graph
    assert str(next(graph.objects(inv, SCHEMA.title))) == "My Investigation"


def test_hierarchy_via_haspart():
    graph = _graph()
    inv = next(graph.subjects(RDF.type, JERM.Investigation))
    study = next(graph.objects(inv, JERM.hasPart))
    assert (study, RDF.type, JERM.Study) in graph


def test_sample_siblings_get_distinct_uris_and_names():
    # Regression: sample identity must come from the entity's own id/name field,
    # not node.label (Sample's first field is study_id) — else siblings collapse.
    client = MetaseedClient("isa", "1.0")
    inv = client.create_entity(
        "Investigation", {"identifier": "INV1", "title": "I"}, skip_validation=True
    )
    study = client.create_entity(
        "Study",
        {"identifier": "STU1", "title": "S"},
        parent_id=inv.id,
        skip_validation=True,
    )
    client.create_entity(
        "Sample", {"name": "sample-a"}, parent_id=study.id, skip_validation=True
    )
    client.create_entity(
        "Sample", {"name": "sample-b"}, parent_id=study.id, skip_validation=True
    )
    graph = Graph()
    graph.parse(data=to_fair_data_station_rdf(client), format="turtle")

    samples = set(graph.subjects(RDF.type, JERM.Sample))
    assert len(samples) == 2  # siblings are distinct resources, not merged
    names = {str(o) for s in samples for o in graph.objects(s, SCHEMA.name)}
    assert names == {"sample-a", "sample-b"}  # name emitted as schema:name


def test_identifier_keyed_entity_gets_title_from_identifier():
    # SEEK requires every resource to have a title (from schema:title), which it
    # imposes as a required Sample Type attribute. A MIAPPE Sample is keyed by
    # unique_id and has no title/name field, so schema:title must fall back to the
    # identity — else the import fails validating the sample.
    client = MetaseedClient("miappe", "1.2")
    inv = client.create_entity(
        "Investigation", {"unique_id": "INV1", "title": "I"}, skip_validation=True
    )
    study = client.create_entity(
        "Study",
        {"unique_id": "STU1", "title": "S"},
        parent_id=inv.id,
        skip_validation=True,
    )
    ou = client.create_entity(
        "ObservationUnit",
        {"unique_id": "OU1"},
        parent_id=study.id,
        skip_validation=True,
    )
    client.create_entity(
        "Sample", {"unique_id": "SAMPLE-1"}, parent_id=ou.id, skip_validation=True
    )
    graph = Graph()
    graph.parse(data=to_fair_data_station_rdf(client), format="turtle")

    sample = next(graph.subjects(RDF.type, JERM.Sample))
    assert str(next(graph.objects(sample, SCHEMA.title))) == "SAMPLE-1"
    assert str(next(graph.objects(sample, SCHEMA.name))) == "SAMPLE-1"


def test_field_property_definitions_carry_label_and_required():
    graph = _graph()
    # every schema property used as a predicate on a resource is declared with a
    # label + valueRequired so SEEK can build an Extended Metadata attribute.
    props = set(graph.subjects(RDF.type, RDF.Property))
    assert props  # at least one non-core field was emitted with a definition
    for prop in props:
        assert (prop, RDFS.label, None) in graph
        assert (prop, SCHEMA.valueRequired, None) in graph


def test_entity_seek_role_overrides_jerm_type(monkeypatch):
    # A profile's entity.seek.role drives the JERM type in the export.
    from metaseed.specs.loader import SpecLoader
    from metaseed.specs.schema import SeekEntityConfig

    real = SpecLoader.load_profile

    def patched(self, version, profile=None, **kw):
        spec = real(self, version, profile, **kw)
        spec.entities["Investigation"].seek = SeekEntityConfig(role="Study")
        return spec

    monkeypatch.setattr(SpecLoader, "load_profile", patched)
    client = MetaseedClient("isa", "1.0")
    client.create_entity(
        "Investigation", {"identifier": "I1", "title": "T"}, skip_validation=True
    )
    graph = Graph()
    graph.parse(data=to_fair_data_station_rdf(client), format="turtle")
    assert (None, RDF.type, JERM.Study) in graph  # role override applied
    assert (None, RDF.type, JERM.Investigation) not in graph


def test_exportable_entity_types_is_role_aware(monkeypatch):
    # A profile can make a non-JERM-named entity exportable purely via seek.role;
    # exportable_entity_types must include it so the /seek preview matches output.
    from metaseed.specs.loader import SpecLoader
    from metaseed.specs.schema import EntityDefSpec, SeekEntityConfig

    real = SpecLoader.load_profile

    def patched(self, version, profile=None, **kw):
        spec = real(self, version, profile, **kw)
        spec.entities["Sampling"] = EntityDefSpec(seek=SeekEntityConfig(role="Sample"))
        return spec

    monkeypatch.setattr(SpecLoader, "load_profile", patched)
    client = MetaseedClient("isa", "1.0")
    types = exportable_entity_types(client)
    assert "Sampling" not in EXPORTED_TYPES  # custom name isn't in the JERM map
    assert "Sampling" in types  # ...but the role makes it exportable
    assert types >= EXPORTED_TYPES  # JERM-mapped names still included


def test_model_rdf_defines_every_field_even_unpopulated():
    # The model TTL defines a property for every non-core field, with no dataset.
    from metaseed.specs.schema import (
        Constraints,
        EntityDefSpec,
        FieldSpec,
        FieldType,
        ProfileSpec,
    )

    profile = ProfileSpec(
        name="p",
        version="1.0",
        entities={
            "Sample": EntityDefSpec(
                fields=[
                    FieldSpec(name="identifier", type=FieldType.STRING),  # core
                    FieldSpec(
                        name="tissue",
                        type=FieldType.STRING,
                        required=True,
                        description="tissue type",
                        constraints=Constraints(pattern="^[a-z]+$"),
                    ),
                ]
            )
        },
    )
    graph = Graph()
    graph.parse(data=to_fair_data_station_model_rdf(profile), format="turtle")

    assert (SCHEMA.tissue, RDF.type, RDF.Property) in graph
    assert (SCHEMA.tissue, RDFS.label, None) in graph
    assert (SCHEMA.tissue, SCHEMA.valueRequired, None) in graph
    assert (SCHEMA.tissue, SCHEMA.valuePattern, None) in graph
    # a core field (identifier) is emitted as data, not a property definition
    assert (SCHEMA.identifier, RDF.type, RDF.Property) not in graph


def test_model_rdf_carries_a_skeleton_instance_per_isa_level():
    # SEEK builds Extended Metadata Types from Investigation/Study/Assay
    # instances and the annotations they carry, not from property definitions.
    from metaseed.specs.schema import (
        EntityDefSpec,
        FieldSpec,
        FieldType,
        ProfileSpec,
        SeekEntityConfig,
    )

    profile = ProfileSpec(
        name="p",
        version="1.0",
        root_entity="Investigation",
        entities={
            "Investigation": EntityDefSpec(
                seek=SeekEntityConfig(role="Investigation"),
                fields=[
                    FieldSpec(name="title", type=FieldType.STRING),
                    FieldSpec(name="studies", type=FieldType.LIST, items="Study"),
                ],
            ),
            "Study": EntityDefSpec(
                seek=SeekEntityConfig(role="Study"),
                fields=[
                    FieldSpec(name="title", type=FieldType.STRING),
                    FieldSpec(name="growth_facility", type=FieldType.STRING),
                    FieldSpec(name="assays", type=FieldType.LIST, items="Assay"),
                ],
            ),
            "Assay": EntityDefSpec(
                seek=SeekEntityConfig(role="Assay"),
                fields=[
                    FieldSpec(name="title", type=FieldType.STRING),
                    FieldSpec(name="platform", type=FieldType.STRING, required=True),
                ],
            ),
        },
    )
    graph = Graph()
    graph.parse(data=to_fair_data_station_model_rdf(profile), format="turtle")

    inv = next(graph.subjects(RDF.type, JERM.Investigation))
    stu = next(graph.subjects(RDF.type, JERM.Study))
    assay = next(graph.subjects(RDF.type, JERM.Assay))
    assert (inv, JERM.hasPart, stu) in graph

    # SEEK's FAIR-DS reader reaches an Assay positionally, through
    # Study -> ObservationUnit -> Sample -> Assay, so the skeleton chains those
    # levels rather than linking Study straight to Assay. Walk the chain and
    # confirm it ends at the Assay -- otherwise SEEK builds no Assay Extended
    # Metadata Type (the bug this encodes: it reported "no new EMTs").
    def _child(node):
        return next(graph.objects(node, JERM.hasPart), None)

    obs = _child(stu)
    sample = _child(obs)
    assert (obs, RDF.type, JERM.ObservationUnit) in graph
    assert (sample, RDF.type, JERM.Sample) in graph
    assert _child(sample) == assay, "the Assay must be reachable via obs-unit -> sample"

    for node in (inv, stu, assay):
        assert (node, SCHEMA.identifier, None) in graph
        assert (node, SCHEMA.title, None) in graph
    # every non-core field is carried by the instance filling that role
    assert (stu, SCHEMA.growth_facility, None) in graph
    assert (assay, SCHEMA.platform, None) in graph
    assert (inv, SCHEMA.growth_facility, None) not in graph
    # the empty positional levels carry no non-core predicate, so SEEK makes no
    # Extended Metadata Type for them
    assert (obs, SCHEMA.growth_facility, None) not in graph
    # and the property definitions are still there for the attribute metadata
    assert (SCHEMA.platform, SCHEMA.valueRequired, Literal(True)) in graph
