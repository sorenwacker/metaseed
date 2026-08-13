"""What OLS actually answers about ancestry, and how each answer is read.

The unit tests beside this one fix the *policy* against a stub. These pin the
two readings of a real OLS response that the policy depends on, because both
were wrong in the first implementation and neither is visible without asking the
service:

- a 200 carrying no ancestors is not evidence — OLS returns it for a term it
  does not carry and for one genuinely at the top of its tree alike;
- a 404 is the ontology being absent, not the term being unparented.

Read either as "not beneath" and every Crop Ontology value in a MIAPPE dataset
is reported wrong. Marked ``network`` for the same reason as the accession gate:
answering means asking EBI, so it is a release gate rather than a per-push one.
"""

from __future__ import annotations

import pytest

from metaseed.services.ontology import OntologyService
from metaseed.services.term_check import Outcome, check_term


@pytest.fixture(scope="module")
def service() -> OntologyService:
    return OntologyService()


@pytest.mark.network
class TestWhatOlsCanPlace:
    def test_a_real_descendant(self, service: OntologyService) -> None:
        """`irrigation process` sits beneath `agricultural water process`."""
        assert service.is_within_sync("AGRO:00000006", "AGRO:00000665") is True

    def test_a_term_is_within_itself(self, service: OntologyService) -> None:
        assert service.is_within_sync("PATO:0000001", "PATO:0000001") is True

    def test_an_unrelated_ancestor(self, service: OntologyService) -> None:
        assert service.is_within_sync("AGRO:00000006", "AGRO:00000000") is False

    def test_an_ancestor_in_another_ontology(self, service: OntologyService) -> None:
        assert service.is_within_sync("PATO:0001241", "TO:0000387") is False


@pytest.mark.network
class TestWhatOlsCannotPlace:
    def test_an_ontology_it_does_not_host(self, service: OntologyService) -> None:
        """CO_715 is what MIAPPE names for its event accessions, and OLS does
        not carry it. Answering False here would report every correct value in
        that column as wrong."""
        assert service.is_within_sync("CO_715:0000129", "CO_715:0000006") is None

    def test_an_unusable_identifier(self, service: OntologyService) -> None:
        assert service.is_within_sync("sowing", "CO_715:0000006") is None


@pytest.mark.network
class TestTheVerdictAValidatorSees:
    def test_a_value_outside_the_branch_is_a_problem(self) -> None:
        verdict = check_term("AGRO:00000006", ["agro"], within="AGRO:00000000")

        assert verdict.outcome is Outcome.NOT_IN_BRANCH
        assert verdict.is_problem

    def test_a_value_inside_it_passes(self) -> None:
        verdict = check_term("AGRO:00000006", ["agro"], within="AGRO:00000665")

        assert verdict.outcome is Outcome.OK

    def test_the_shipped_miappe_branch_reports_not_checked(self) -> None:
        """What a MIAPPE event accession does today: `co_715` is carried by no
        configured source, so the value is not checked rather than passed."""
        verdict = check_term("CO_715:0000129", ["co_715"], within="CO_715:0000006")

        assert verdict.outcome is Outcome.NOT_CHECKED
        assert not verdict.is_problem
