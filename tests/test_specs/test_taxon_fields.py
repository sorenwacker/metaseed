"""A taxon field stores an NCBI Taxonomy term and exports as its number.

As an ``integer`` a taxon got a number box and no lookup; as an ``ontology_term``
scoped to NCBITaxon it is chosen by name. ENA's TAXON_ID and a SEEK taxon
attribute hold the bare number, so every export writes that. See
docs/api/schema-specs.md#taxon-fields.
"""

from __future__ import annotations

import copy

import pytest
from rdflib import Graph, Literal

from metaseed import MetaseedClient
from metaseed.ena.export import to_ena_xml
from metaseed.seek.attribute_types import attribute_type_title
from metaseed.seek.fairds import to_fair_data_station_rdf
from metaseed.specs.loader import SpecLoader
from metaseed.specs.schema import FieldSpec, FieldType
from metaseed.specs.taxon import export_values, is_taxon_field, taxon_number

TAXON = FieldSpec(
    name="taxon_id", type=FieldType.ONTOLOGY_TERM, ontologies=["ncbitaxon"]
)


@pytest.mark.parametrize(
    ("value", "number"),
    [
        ("NCBITaxon:3702", 3702),
        ("NCBITaxon_3702", 3702),
        ("http://purl.obolibrary.org/obo/NCBITaxon_3702", 3702),
        ("3702", 3702),
        (3702, 3702),
        ("Arabidopsis thaliana", None),
        ("GO:0008150", None),
        (0, None),
        (True, None),
    ],
)
def test_a_taxon_value_reads_as_its_ncbi_number(value, number) -> None:
    assert taxon_number(value) == number


def test_only_an_ontology_term_scoped_to_ncbitaxon_is_a_taxon_field() -> None:
    assert is_taxon_field(TAXON)
    assert not is_taxon_field(FieldSpec(name="taxon_id", type=FieldType.INTEGER))
    assert not is_taxon_field(
        FieldSpec(
            name="t", type=FieldType.ONTOLOGY_TERM, ontologies=["ncbitaxon", "go"]
        )
    )


def test_export_values_turn_a_taxon_term_into_its_number() -> None:
    other = FieldSpec(name="tissue", type=FieldType.ONTOLOGY_TERM, ontologies=["po"])
    values = {"taxon_id": "NCBITaxon:3702", "tissue": "PO:0025034"}

    assert export_values([TAXON, other], values) == {
        "taxon_id": 3702,
        "tissue": "PO:0025034",
    }
    assert export_values([TAXON], {"taxon_id": "Arabidopsis"}) == {}


def test_seek_provisions_a_taxon_field_as_an_integer() -> None:
    assert attribute_type_title(TAXON) == "Integer"


def _client() -> MetaseedClient:
    spec = copy.deepcopy(SpecLoader().load_profile("1.0", "ena"))
    sample = spec.entities["Sample"]
    sample.fields = [
        f.model_copy(
            update={
                "type": FieldType.ONTOLOGY_TERM,
                "ontologies": ["ncbitaxon"],
                "constraints": None,
                "example": "NCBITaxon:3702",
            }
        )
        if f.name == "taxon_id"
        else f
        for f in sample.fields
    ]
    spec.validation_rules = [r for r in spec.validation_rules if r.field != "taxon_id"]
    client = MetaseedClient.from_spec(spec)
    study = client.create_entity(
        "Study", {"alias": "S1", "title": "T"}, skip_validation=True
    )
    client.create_entity(
        "Sample",
        {
            "alias": "SA1",
            "taxon_id": "NCBITaxon:3702",
            "scientific_name": "A. thaliana",
        },
        parent_id=study.id,
        skip_validation=True,
    )
    return client


def test_ena_writes_the_ncbi_number() -> None:
    xml = to_ena_xml(_client())["sample.xml"]

    assert "<TAXON_ID>3702</TAXON_ID>" in xml


def test_the_fair_data_station_file_writes_the_ncbi_number() -> None:
    graph = Graph().parse(data=to_fair_data_station_rdf(_client()), format="turtle")

    values = {o for _, p, o in graph if str(p).endswith("taxon_id")}
    assert values == {Literal(3702)}
