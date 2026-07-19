"""Tests for metabolights CV-term compliance (hermetic; injected service).

MetaboLights creates ``Sample`` as its own entity, so its ``organism_term``
(an ``ontology_term`` field) is resolved against OLS4 at *creation* time
(facade.helper.validate_ontology_terms). The ``fake_ontology`` fixture patches
the context ontology service so both that coercion and ``validate_cv`` use the
stub — no live OLS4 call.
"""

from __future__ import annotations

import pytest

from metaseed import MetaseedClient
from metaseed.metabolights import validate_cv


class _FakeService:
    KNOWN = {"NCBITaxon:9606", "CHEBI:17234"}

    def validate_term_sync(self, term_id: str) -> tuple[bool, str | None]:
        if ":" not in term_id and "_" not in term_id:
            return True, None
        if term_id in self.KNOWN:
            return True, None
        return False, f"Ontology term '{term_id}' not found in OLS4"


@pytest.fixture
def fake_ontology(monkeypatch):
    """Route the context ontology service to a network-free stub."""
    service = _FakeService()
    monkeypatch.setattr(
        "metaseed.services.ontology.get_ontology_service", lambda: service
    )
    return service


def _client(*, organism_term=None, metabolites=None) -> MetaseedClient:
    client = MetaseedClient("metabolights", "1.0")
    inv = client.create_entity(
        "Investigation",
        {"identifier": "I", "title": "t", "description": "d"},
        skip_validation=True,
    )
    study = client.create_entity(
        "Study",
        {"identifier": "s", "title": "t", "description": "d"},
        parent_id=inv.id,
        skip_validation=True,
    )
    client.create_entity(
        "Sample",
        {"name": "S1", "organism": "h", "organism_term": organism_term},
        parent_id=study.id,
        skip_validation=True,
    )
    client.create_entity(
        "Assay",
        {
            "identifier": "a",
            "filename": "a_1.txt",
            "technology_type": "mass spectrometry",
            "measurement_type": "metabolite profiling",
            "samples": ["S1"],
            "metabolites": metabolites or [],
        },
        parent_id=study.id,
        skip_validation=True,
    )
    return client


def test_valid_cv_terms_pass(fake_ontology):
    client = _client(
        organism_term="NCBITaxon:9606",
        metabolites=[{"metabolite_identification": "g", "database_identifier": "CHEBI:17234"}],
    )
    assert validate_cv(client, service=fake_ontology) == []


def test_unknown_organism_and_metabolite_terms_are_reported(fake_ontology):
    client = _client(
        organism_term="NCBITaxon:0000000",
        metabolites=[
            {"metabolite_identification": "g", "database_identifier": "CHEBI:17234"},
            {"metabolite_identification": "x", "database_identifier": "CHEBI:0000000"},
        ],
    )
    errors = validate_cv(client, service=fake_ontology)
    fields = {e.field for e in errors}
    assert "Sample[0].organism_term" in fields
    assert "Assay[0].metabolites[1].database_identifier" in fields
    assert len(errors) == 2
    assert all(e.rule == "cv_compliance" for e in errors)


def test_free_text_organism_is_not_flagged(fake_ontology):
    # organism_term left unset (import default) or free text must not error.
    client = _client(organism_term=None)
    assert validate_cv(client, service=fake_ontology) == []
