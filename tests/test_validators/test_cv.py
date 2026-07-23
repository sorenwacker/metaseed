"""Tests for the shared CV-term compliance helper.

Two tiers: the dev/CI tests below stub the ontology service (fast, hermetic, no
OLS4 rate limits); the ``@pytest.mark.network`` test at the end resolves against
live OLS4 and is meant to run before releases.
"""

from __future__ import annotations

import pytest

from metaseed.validators.cv import validate_cv_terms


class _FakeService:
    """Stub ontology service: KNOWN accessions resolve, others 404.

    Mirrors OntologyService.validate_term_sync's contract, including skipping
    values that are not accession-shaped and failing open on outages.
    """

    KNOWN = {"MS:1000031", "CHEBI:17234"}

    def __init__(self, *, outage: bool = False) -> None:
        self.outage = outage
        self.calls: list[str] = []

    def validate_term_sync(self, term_id: str) -> tuple[bool, str | None]:
        self.calls.append(term_id)
        if self.outage:
            return True, None  # fail-open
        if ":" not in term_id and "_" not in term_id:
            return True, None  # not accession-shaped
        if term_id in self.KNOWN:
            return True, None
        return False, f"Ontology term '{term_id}' not found in OLS4"


def test_unresolved_terms_are_reported():
    svc = _FakeService()
    errors = validate_cv_terms(
        [("a.term", "MS:1000031"), ("b.term", "MS:9999999")], service=svc
    )
    assert len(errors) == 1
    assert errors[0].field == "b.term"
    assert errors[0].rule == "cv_compliance"
    assert "MS:9999999" in errors[0].message


def test_empty_and_none_accessions_are_skipped():
    svc = _FakeService()
    errors = validate_cv_terms(
        [("a", None), ("b", ""), ("c", "MS:1000031")], service=svc
    )
    assert errors == []
    assert svc.calls == ["MS:1000031"]  # None/empty never reach the service


def test_free_text_is_not_flagged():
    # The service skips non-accession-shaped values; free text must not error.
    errors = validate_cv_terms([("a", "liver")], service=_FakeService())
    assert errors == []


def test_outage_fails_open():
    errors = validate_cv_terms([("a", "MS:9999999")], service=_FakeService(outage=True))
    assert errors == []


@pytest.mark.network
def test_resolves_against_live_ols4():
    # Release tier: real OLS4. MS:1000031 is a real PSI-MS term; MS:9999999 is not.
    errors = validate_cv_terms([("good", "MS:1000031"), ("bad", "MS:9999999")])
    assert [e.field for e in errors] == ["bad"]
    assert errors[0].rule == "cv_compliance"
