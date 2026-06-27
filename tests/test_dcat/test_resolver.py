"""Tests for the DCAT resolver (#27).

Verify that a metaseed dataset resolves into the DCAT intermediate model:
derivation from a container-rooted profile's root entity, explicit
CatalogMetadata for record-rooted profiles, and explicit-wins precedence.
"""

from __future__ import annotations

from metaseed.dcat import build_dcat_catalog, build_dcat_dataset
from metaseed.repositories.dataset_repository import CatalogMetadata


class TestContainerRootedDerivation:
    """MIAPPE/ISA/ENA derive DCAT properties from the root entity."""

    def test_miappe_investigation_derives_dataset(self):
        root = {
            "unique_id": "INV-1",
            "title": "Drought trial",
            "description": "A drought experiment",
            "submission_date": "2024-01-01",
            "license": "CC-BY-4.0",
            "contacts": [{"name": "Jane Doe", "email": "jane@example.org"}],
            "associated_publications": ["doi:10.1/x"],
        }
        ds = build_dcat_dataset(profile="miappe", root_entity=root, modified="2024-02")

        assert ds.identifier == "INV-1"
        assert ds.title == "Drought trial"
        assert ds.description == "A drought experiment"
        assert ds.issued == "2024-01-01"
        assert ds.license == "CC-BY-4.0"
        assert ds.modified == "2024-02"
        assert ds.contact_point is not None
        assert ds.contact_point.name == "Jane Doe"
        assert ds.contact_point.email == "jane@example.org"
        assert ds.related == ["doi:10.1/x"]

    def test_ena_study_derives_from_accession(self):
        root = {"accession": "PRJEB1", "title": "T", "description": "D"}
        ds = build_dcat_dataset(profile="ena", root_entity=root)

        assert ds.identifier == "PRJEB1"
        assert ds.title == "T"


class TestRecordRootedProfiles:
    """Darwin Core / DiSSCo have no field map; rely on explicit metadata."""

    def test_uses_catalog_metadata_when_no_field_map(self):
        cm = CatalogMetadata(
            title="Occurrence dataset",
            description="Observations",
            publisher="GBIF node",
            license="CC0-1.0",
            keywords=["birds"],
            themes=["biodiversity"],
        )
        ds = build_dcat_dataset(
            profile="darwin-core",
            root_entity={"occurrenceID": "OCC-1"},  # not a dataset description
            catalog_metadata=cm,
            fallback_identifier="my-occurrences",
        )

        assert ds.title == "Occurrence dataset"
        assert ds.description == "Observations"
        assert ds.publisher is not None
        assert ds.publisher.name == "GBIF node"
        assert ds.license == "CC0-1.0"
        assert ds.keywords == ["birds"]
        assert ds.themes == ["biodiversity"]
        assert ds.identifier == "my-occurrences"

    def test_fallback_identifier_and_title_when_nothing_else(self):
        ds = build_dcat_dataset(profile="darwin-core", fallback_identifier="ds-7")
        assert ds.identifier == "ds-7"
        assert ds.title == "ds-7"


class TestPrecedence:
    """Explicit CatalogMetadata overrides values derived from the root entity."""

    def test_explicit_title_overrides_derived(self):
        root = {"title": "Derived title", "description": "Derived desc"}
        cm = CatalogMetadata(title="Explicit title")
        ds = build_dcat_dataset(profile="miappe", root_entity=root, catalog_metadata=cm)

        assert ds.title == "Explicit title"
        # description not overridden -> falls back to derived
        assert ds.description == "Derived desc"

    def test_explicit_contact_overrides_derived_contacts(self):
        root = {"contacts": [{"name": "Root Contact", "email": "root@x.org"}]}
        cm = CatalogMetadata(contact_name="Explicit", contact_email="e@x.org")
        ds = build_dcat_dataset(profile="miappe", root_entity=root, catalog_metadata=cm)

        assert ds.contact_point is not None
        assert ds.contact_point.name == "Explicit"


class TestCatalog:
    def test_build_catalog_wraps_datasets(self):
        ds = build_dcat_dataset(profile="ena", fallback_identifier="d1")
        cat = build_dcat_catalog(
            title="My Catalog",
            description="desc",
            publisher="Org",
            datasets=[ds],
        )

        assert cat.title == "My Catalog"
        assert cat.publisher is not None
        assert cat.publisher.name == "Org"
        assert len(cat.datasets) == 1
