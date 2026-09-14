"""An identifier resolves within its entity type (ADR 006).

The store and the loader looked identifiers up by value alone. A record of one
type whose identifying value equals another record's identifier replaced that
record in the lookup: a DCAT QualityCertificate identified by its ``target``
(the dataset's IRI) took the Dataset's place, and on reload every child of the
Dataset was attached under the certificate, cut off from the catalogue.
"""

from __future__ import annotations

import pytest

from metaseed.facade import ProfileFacade
from metaseed.specs.schema import EntityDefSpec, FieldSpec, FieldType, ProfileSpec

DATASET_IRI = "https://example.org/dataset/1"


@pytest.fixture
def facade() -> ProfileFacade:
    """Catalog > Dataset > (Certificate, Note); a Certificate is keyed by its target."""
    entities = {
        "Catalog": EntityDefSpec(
            fields=[
                FieldSpec(name="identifier", type=FieldType.STRING, required=True),
                FieldSpec(name="datasets", type=FieldType.LIST, items="Dataset"),
            ]
        ),
        "Dataset": EntityDefSpec(
            fields=[
                FieldSpec(name="identifier", type=FieldType.STRING, required=True),
                FieldSpec(
                    name="certificates", type=FieldType.LIST, items="Certificate"
                ),
                FieldSpec(name="notes", type=FieldType.LIST, items="Note"),
            ]
        ),
        "Certificate": EntityDefSpec(
            fields=[
                FieldSpec(name="target", type=FieldType.STRING),
                FieldSpec(name="body", type=FieldType.STRING),
            ]
        ),
        "Note": EntityDefSpec(fields=[FieldSpec(name="text", type=FieldType.STRING)]),
    }
    spec = ProfileSpec(
        name="test-scoped-lookups",
        version="1.0",
        root_entity="Catalog",
        entities=entities,
    )
    facade = ProfileFacade("test-scoped-lookups", "1.0", spec=spec)
    catalog = facade.add_entity(
        "Catalog", {"identifier": "https://example.org/catalog"}
    )
    dataset = facade.add_entity(
        "Dataset", {"identifier": DATASET_IRI}, parent_id=catalog.id
    )
    facade.add_entity(
        "Certificate",
        {"target": DATASET_IRI, "body": "https://example.org/cert.pdf"},
        parent_id=dataset.id,
    )
    facade.add_entity("Note", {"text": "checked"}, parent_id=dataset.id)
    return facade


def _reloaded(facade: ProfileFacade) -> ProfileFacade:
    reloaded = ProfileFacade("test-scoped-lookups", "1.0", spec=facade._spec)
    reloaded.load_from_dict(facade.to_dict())
    return reloaded


def test_a_reload_keeps_a_dataset_under_its_catalog_with_all_its_children(
    facade: ProfileFacade,
) -> None:
    reloaded = _reloaded(facade)

    roots = reloaded.get_roots()
    assert [r.entity_type for r in roots] == ["Catalog"]
    datasets = [c for c in roots[0].children if c.entity_type == "Dataset"]
    assert len(datasets) == 1, "the Dataset left its catalogue"
    assert sorted(c.entity_type for c in datasets[0].children) == [
        "Certificate",
        "Note",
    ]


def test_a_typed_lookup_returns_the_record_of_that_type(facade: ProfileFacade) -> None:
    for store in (facade, _reloaded(facade)):
        found = store.get_entity_by_ref(DATASET_IRI, entity_type="Dataset")
        assert found is not None
        assert found.entity_type == "Dataset"
        certificate = store.get_entity_by_ref(DATASET_IRI, entity_type="Certificate")
        assert certificate is not None
        assert certificate.entity_type == "Certificate"
