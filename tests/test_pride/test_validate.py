"""Tests for pride CV-term compliance (hermetic; injected ontology service)."""

from __future__ import annotations

from metaseed import MetaseedClient
from metaseed.pride import validate_cv


class _FakeService:
    KNOWN = {"MS:1000031", "UBERON:0002107"}

    def validate_term_sync(self, term_id: str) -> tuple[bool, str | None]:
        if ":" not in term_id and "_" not in term_id:
            return True, None
        if term_id in self.KNOWN:
            return True, None
        return False, f"Ontology term '{term_id}' not found in OLS4"


def _client(**dataset_extra) -> MetaseedClient:
    client = MetaseedClient("pride", "1.0")
    data = {"accession": "PXD000001", "title": "t", **dataset_extra}
    client.create_entity("Dataset", data, skip_validation=True)
    return client


def test_valid_cv_terms_pass():
    client = _client(
        instruments=[{"name": "orbitrap", "cv_accession": "MS:1000031"}],
        samples=[
            {
                "name": "S",
                "species": "h",
                "ncbi_taxonomy_id": "9606",
                "tissue_accession": "UBERON:0002107",
            }
        ],
    )
    assert validate_cv(client, service=_FakeService()) == []


def test_unknown_cv_terms_are_reported():
    client = _client(
        instruments=[{"name": "x", "cv_accession": "MS:9999999"}],
        modifications=[{"name": "ox", "cv_accession": "MS:1000031"}],
    )
    errors = validate_cv(client, service=_FakeService())
    assert len(errors) == 1
    assert errors[0].field == "instruments[0].cv_accession"
    assert errors[0].rule == "cv_compliance"


def test_custom_attribute_cv_terms_are_checked():
    client = _client(
        samples=[
            {
                "name": "S",
                "species": "h",
                "ncbi_taxonomy_id": "9606",
                "custom_attributes": [{"name": "x", "cv_accession": "MS:0000000"}],
            }
        ]
    )
    errors = validate_cv(client, service=_FakeService())
    assert len(errors) == 1
    assert "custom_attributes[0].cv_accession" in errors[0].field


def test_no_dataset_yields_no_errors():
    assert validate_cv(MetaseedClient("pride", "1.0"), service=_FakeService()) == []
