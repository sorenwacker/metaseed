"""Tests for pride validation — CV-term compliance and PX submission structure.

CV resolution is tested for real: the collection logic is checked directly (pure,
no network), and end-to-end resolution runs against live OLS4 under
``@pytest.mark.network``. The submission-structure checks need no network.
"""

from __future__ import annotations

import pytest

from metaseed import MetaseedClient
from metaseed.pride import validate_cv, validate_submission
from metaseed.pride.validate import _cv_terms


def _client(**dataset_extra) -> MetaseedClient:
    client = MetaseedClient("pride", "1.0")
    client.create_entity(
        "Dataset",
        {"accession": "PXD000001", "title": "t", **dataset_extra},
        skip_validation=True,
    )
    return client


# --- CV term collection (pure; no network) ---------------------------------


def test_cv_terms_collects_all_cv_bearing_fields():
    dataset = {
        "instruments": [{"name": "o", "cv_accession": "MS:1000031"}],
        "modifications": [{"name": "ox", "cv_accession": "MOD:00425"}],
        "samples": [
            {
                "name": "S",
                "tissue_accession": "UBERON:0002107",
                "custom_attributes": [{"name": "x", "cv_accession": "MS:1000560"}],
            }
        ],
    }
    collected = dict(_cv_terms(dataset))
    assert collected["instruments[0].cv_accession"] == "MS:1000031"
    assert collected["modifications[0].cv_accession"] == "MOD:00425"
    assert collected["samples[0].tissue_accession"] == "UBERON:0002107"
    assert collected["samples[0].custom_attributes[0].cv_accession"] == "MS:1000560"


def test_no_dataset_yields_no_cv_errors():
    assert validate_cv(MetaseedClient("pride", "1.0")) == []


# --- CV resolution against live OLS4 ---------------------------------------


@pytest.mark.network
def test_valid_cv_terms_resolve():
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
    assert validate_cv(client) == []


@pytest.mark.network
def test_unknown_cv_term_is_reported():
    client = _client(instruments=[{"name": "x", "cv_accession": "MS:9999999"}])
    errors = validate_cv(client)
    assert [e.field for e in errors] == ["instruments[0].cv_accession"]
    assert errors[0].rule == "cv_compliance"


# --- PX submission structure (no network) ----------------------------------


def _complete_dataset() -> dict:
    return {
        "accession": "PXD000001",
        "title": "t",
        "description": "d",
        "submission_type": "COMPLETE",
        "experiment_types": ["Shotgun proteomics"],
        "keywords": ["proteomics"],
        "contacts": [
            {
                "role": "submitter",
                "name": "J S",
                "email": "j@x.ac.uk",
                "affiliation": "U",
            },
            {
                "role": "lab head",
                "name": "K L",
                "email": "k@x.ac.uk",
                "affiliation": "U",
            },
        ],
        "species": [{"name": "Homo sapiens"}],
        "instruments": [{"name": "LTQ Orbitrap"}],
        "samples": [
            {"name": "S", "species": "h", "ncbi_taxonomy_id": "9606", "tissue": "liver"}
        ],
        "files": [
            {"filename": "a.raw", "file_type": "RAW"},
            {"filename": "b.mzid", "file_type": "RESULT"},
        ],
    }


def _submission_client(dataset: dict) -> MetaseedClient:
    client = MetaseedClient("pride", "1.0")
    client.create_entity("Dataset", dataset, skip_validation=True)
    return client


def test_complete_submission_passes():
    assert validate_submission(_submission_client(_complete_dataset())) == []


def test_missing_mandatory_fields_are_reported():
    data = _complete_dataset()
    data.pop("instruments")
    data.pop("experiment_types")
    errors = validate_submission(_submission_client(data))
    fields = {e.field for e in errors}
    assert "instrument" in fields
    assert "experiment_type" in fields
    assert all(e.rule == "px_structure" for e in errors)


def test_partial_requires_reason_for_partial():
    data = _complete_dataset()
    data["submission_type"] = "PARTIAL"
    data["files"] = [
        {"filename": "a.raw", "file_type": "RAW"},
        {"filename": "b.mgf", "file_type": "SEARCH"},
    ]
    errors = validate_submission(_submission_client(data))
    assert any(e.field == "reason_for_partial" for e in errors)
    data["reason_for_partial"] = "raw + search only"
    assert validate_submission(_submission_client(data)) == []


def test_file_mapping_requires_raw_and_result():
    data = _complete_dataset()
    data["files"] = [{"filename": "b.mzid", "file_type": "RESULT"}]  # no RAW
    messages = [e.message for e in validate_submission(_submission_client(data))]
    assert any("RAW" in m for m in messages)

    data["files"] = [{"filename": "a.raw", "file_type": "RAW"}]  # COMPLETE, no RESULT
    messages = [e.message for e in validate_submission(_submission_client(data))]
    assert any("RESULT" in m for m in messages)


def test_no_dataset_reports_missing_submission():
    errors = validate_submission(MetaseedClient("pride", "1.0"))
    assert len(errors) == 1
    assert errors[0].rule == "px_structure"
