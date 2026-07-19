"""Tests for metabolights CV-term compliance.

The collection logic is checked directly (pure, no network); end-to-end
resolution runs against live OLS4 under ``@pytest.mark.network``. Note that
building a Sample with an ``organism_term`` accession resolves it against OLS4 at
creation time (facade.helper), so the end-to-end test is network-marked for that
reason too.
"""

from __future__ import annotations

import pytest

from metaseed import MetaseedClient
from metaseed.metabolights import validate_cv
from metaseed.metabolights.validate import _cv_terms

# --- CV term collection (pure; no network) ---------------------------------


def test_cv_terms_collects_organism_and_metabolite_accessions():
    entities = [
        {"_type": "Sample", "organism_term": "NCBITaxon:9606"},
        {
            "_type": "Assay",
            "metabolites": [
                {"metabolite_identification": "g", "database_identifier": "CHEBI:17234"},
                {"metabolite_identification": "x", "database_identifier": "CHEBI:0000000"},
            ],
        },
    ]
    collected = dict(_cv_terms(entities))
    assert collected["Sample[0].organism_term"] == "NCBITaxon:9606"
    assert collected["Assay[0].metabolites[0].database_identifier"] == "CHEBI:17234"
    assert collected["Assay[0].metabolites[1].database_identifier"] == "CHEBI:0000000"


# --- CV resolution against live OLS4 ---------------------------------------


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


@pytest.mark.network
def test_valid_cv_terms_resolve():
    client = _client(
        organism_term="NCBITaxon:9606",
        metabolites=[{"metabolite_identification": "g", "database_identifier": "CHEBI:17234"}],
    )
    assert validate_cv(client) == []


@pytest.mark.network
def test_unknown_organism_and_metabolite_terms_are_reported():
    client = _client(
        organism_term="NCBITaxon:9606",
        metabolites=[{"metabolite_identification": "x", "database_identifier": "CHEBI:0000000"}],
    )
    errors = validate_cv(client)
    assert [e.field for e in errors] == [
        "Assay[0].metabolites[0].database_identifier"
    ]
    assert errors[0].rule == "cv_compliance"
