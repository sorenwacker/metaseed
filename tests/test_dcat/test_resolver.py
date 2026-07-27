"""Tests for the DCAT resolver (spec-driven mapping).

The mapping is now declared by each root-entity field's ``dcat`` annotation;
the resolver reads those plus explicit CatalogMetadata (explicit-wins).
"""

from __future__ import annotations

from metaseed.dcat import build_dcat_catalog, build_dcat_dataset
from metaseed.dcat.resolver import build_dcat_dataset_from_entities
from metaseed.repositories.dataset_repository import CatalogMetadata
from metaseed.specs.loader import SpecLoader
from metaseed.specs.schema import FieldSpec, FieldType


def _fields(*pairs: tuple[str, str | None]) -> list[FieldSpec]:
    """Build root field specs from (name, dcat) pairs."""
    return [FieldSpec(name=n, type=FieldType.STRING, dcat=d) for n, d in pairs]


class TestAnnotatedDerivation:
    def test_derives_each_annotated_property(self):
        fields = _fields(
            ("unique_id", "dct:identifier"),
            ("title", "dct:title"),
            ("description", "dct:description"),
            ("submission_date", "dct:issued"),
            ("license", "dct:license"),
            ("pubs", "dct:relation"),
        )
        root = {
            "unique_id": "INV-1",
            "title": "Drought trial",
            "description": "desc",
            "submission_date": "2024-01-01",
            "license": "CC-BY-4.0",
            "pubs": ["doi:1", "doi:2"],
        }
        ds = build_dcat_dataset(
            root_fields=fields, root_entity=root, modified="2024-02"
        )

        assert ds.identifier == "INV-1"
        assert ds.title == "Drought trial"
        assert ds.issued == "2024-01-01"
        assert ds.license == "CC-BY-4.0"
        assert ds.modified == "2024-02"
        assert ds.related == ["doi:1", "doi:2"]

    def test_contact_point_from_annotated_contacts(self):
        fields = _fields(("contacts", "dcat:contactPoint"))
        root = {"contacts": [{"name": "Jane Doe", "email": "jane@x.org"}]}
        ds = build_dcat_dataset(root_fields=fields, root_entity=root)

        assert ds.contact_point is not None
        assert ds.contact_point.name == "Jane Doe"
        assert ds.contact_point.email == "jane@x.org"

    def test_publisher_from_annotated_field(self):
        # ENA-style: center_name -> dct:publisher
        fields = _fields(("center_name", "dct:publisher"))
        ds = build_dcat_dataset(
            root_fields=fields, root_entity={"center_name": "Example Center"}
        )

        assert ds.publisher is not None
        assert ds.publisher.name == "Example Center"

    def test_unannotated_fields_ignored(self):
        fields = _fields(("title", "dct:title"), ("internal_note", None))
        ds = build_dcat_dataset(
            root_fields=fields, root_entity={"title": "T", "internal_note": "x"}
        )
        assert ds.title == "T"


class TestRecordRootedAndOverrides:
    def test_no_annotations_uses_catalog_metadata(self):
        cm = CatalogMetadata(
            title="Occurrence dataset",
            description="obs",
            publisher="GBIF",
            license="CC0-1.0",
            keywords=["birds"],
            themes=["biodiversity"],
        )
        ds = build_dcat_dataset(
            root_fields=[], catalog_metadata=cm, fallback_identifier="occ-1"
        )
        assert ds.title == "Occurrence dataset"
        assert ds.publisher is not None and ds.publisher.name == "GBIF"
        assert ds.keywords == ["birds"]
        assert ds.identifier == "occ-1"

    def test_explicit_overrides_derived(self):
        fields = _fields(("title", "dct:title"), ("description", "dct:description"))
        root = {"title": "Derived", "description": "Derived desc"}
        cm = CatalogMetadata(title="Explicit")
        ds = build_dcat_dataset(
            root_fields=fields, root_entity=root, catalog_metadata=cm
        )
        assert ds.title == "Explicit"
        assert ds.description == "Derived desc"

    def test_fallback_identifier_and_title(self):
        ds = build_dcat_dataset(root_fields=[], fallback_identifier="ds-7")
        assert ds.identifier == "ds-7"
        assert ds.title == "ds-7"


class TestFromEntities:
    def test_finds_root_and_strips_metadata(self):
        fields = _fields(("title", "dct:title"), ("unique_id", "dct:identifier"))
        entities = [
            {"_type": "Investigation", "title": "Trial", "unique_id": "INV-1"},
            {"_type": "Study", "_parent_unique_id": "INV-1", "title": "S1"},
        ]
        ds = build_dcat_dataset_from_entities(
            root_fields=fields,
            root_entity_type="Investigation",
            entities=entities,
            identifier="my-ds",
        )
        assert ds.title == "Trial"
        assert ds.identifier == "INV-1"


class TestRealSpecIntegration:
    """The annotations in the shipped profiles drive a real card end to end."""

    def test_miappe_example_resolves_via_spec_annotations(self):
        spec = SpecLoader(profile="miappe").load_profile("1.2", "miappe")
        inv = spec.entities["Investigation"]
        ds = build_dcat_dataset(root_fields=inv.fields, root_entity=inv.example or {})
        assert ds.title  # dct:title annotation drove this
        assert ds.license  # dct:license annotation drove this

    def test_ena_publisher_from_center_name(self):
        spec = SpecLoader(profile="ena").load_profile("1.0", "ena")
        study = spec.entities["Study"]
        ds = build_dcat_dataset(
            root_fields=study.fields,
            root_entity={
                "accession": "PRJ1",
                "title": "T",
                "center_name": "Example Center",
            },
        )
        assert ds.publisher is not None and ds.publisher.name == "Example Center"

    def test_the_ena_accession_is_a_source_not_this_record_s_identity(self):
        """A metaseed card describes a dataset derived from the ENA record, not
        the ENA record itself.

        Claiming ``PRJ1`` as ``dct:identifier`` makes two records assert the same
        identity, so a harvester treats this card as a duplicate of ENA's — and
        any FAIR score it earns is borrowed from ENA's persistent identifier.
        """
        spec = SpecLoader(profile="ena").load_profile("1.0", "ena")
        study = spec.entities["Study"]

        ds = build_dcat_dataset(
            root_fields=study.fields,
            root_entity={"accession": "PRJ1", "title": "T"},
            fallback_identifier="local-dataset",
        )

        assert ds.source == ["PRJ1"], "the accession must be recorded as provenance"
        assert ds.identifier != "PRJ1", "the card must not claim ENA's identifier"
        assert ds.identifier == "local-dataset"

    def test_a_platform_that_originated_the_dataset_can_claim_the_accession(self):
        """Which way the derivation runs is not knowable from the field.

        A dataset authored here for submission, whose accession ENA assigned to
        *it*, really is identified by that accession. The spec makes the claim
        that is safe either way; a caller that knows it is the origin promotes
        it. Without this the safe default would be a ceiling, not a default.
        """
        spec = SpecLoader(profile="ena").load_profile("1.0", "ena")
        study = spec.entities["Study"]

        ds = build_dcat_dataset(
            root_fields=study.fields,
            root_entity={"accession": "PRJ1", "title": "T"},
            fallback_identifier="PRJ1",
        )

        assert ds.identifier == "PRJ1"
        assert ds.source == ["PRJ1"]


class TestCatalog:
    def test_build_catalog_wraps_datasets(self):
        ds = build_dcat_dataset(root_fields=[], fallback_identifier="d1")
        cat = build_dcat_catalog(title="C", publisher="Org", datasets=[ds])
        assert cat.title == "C"
        assert cat.publisher is not None and cat.publisher.name == "Org"
        assert len(cat.datasets) == 1


class TestImportableProfilesDescribeThemselves:
    """PRIDE and MetaboLights are container-rooted: their root entity already
    holds title, description and dates, so a card built from one should not be
    untitled. Both shipped with no ``dcat`` annotations at all, which made every
    card for an imported proteomics or metabolomics dataset unusable.
    """

    def test_pride_derives_its_descriptive_metadata(self):
        spec = SpecLoader(profile="pride").load_profile("1.0", "pride")

        ds = build_dcat_dataset(
            root_fields=spec.entities["Dataset"].fields,
            root_entity={
                "identifier": "local-1",
                "accession": "PXD000001",
                "title": "TMT spikes",
                "description": "A proteomics submission.",
                "keywords": ["proteomics", "TMT"],
                "announcement_date": "2012-03-07",
            },
            fallback_identifier="unused",
        )

        assert ds.title == "TMT spikes"
        assert ds.description == "A proteomics submission."
        assert ds.keywords == ["proteomics", "TMT"]
        assert ds.source == ["PXD000001"], "the PXD accession is provenance"
        assert ds.identifier == "local-1", "not the PRIDE accession"

    def test_metabolights_derives_its_descriptive_metadata(self):
        spec = SpecLoader(profile="metabolights").load_profile("1.0", "metabolights")

        ds = build_dcat_dataset(
            root_fields=spec.entities["Investigation"].fields,
            root_entity={
                "identifier": "local-2",
                "accession": "MTBLS1",
                "title": "A metabolomics study",
                "description": "Urine samples.",
                "submission_date": "2012-01-01",
                "public_release_date": "2013-01-01",
            },
            fallback_identifier="unused",
        )

        assert ds.title == "A metabolomics study"
        assert ds.description == "Urine samples."
        assert ds.issued == "2012-01-01"
        assert ds.source == ["MTBLS1"]
        assert ds.identifier == "local-2"
