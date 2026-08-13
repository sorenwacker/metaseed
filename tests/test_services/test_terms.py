"""The router that decides where a term is looked up.

The rule under test is the one that makes local vocabularies safe to configure:
a source claiming an ontology answers for it alone. Without it, a list somebody
deliberately narrowed would be silently widened again by whatever public
service sits behind it.
"""

from __future__ import annotations

import json

import pytest

from metaseed.services.local_terms import LocalTerm, LocalVocabulary
from metaseed.services.term_check import Outcome, TermSource, check_term
from metaseed.services.terms import (
    TermRouter,
    get_term_source,
    register_term_source,
    reset_term_sources,
)


@pytest.fixture(autouse=True)
def _clean_router():
    reset_term_sources()
    yield
    reset_term_sources()


class _Remote:
    """A stand-in for OLS: knows some terms, claims some ontologies."""

    def __init__(self, terms=(), ontologies=("to", "pato"), *, down: bool = False):
        self.terms = set(terms)
        self.ontologies = set(ontologies)
        self.down = down
        self.asked: list[str] = []

    def get_term_sync(self, term_id: str):
        self.asked.append(term_id)
        if self.down:
            raise ConnectionError("OLS is not answering")
        return LocalTerm(term_id) if term_id in self.terms else None

    def has_ontology_sync(self, ontology_id: str):
        if self.down:
            return None
        return ontology_id in self.ontologies

    def search_sync(self, query: str, ontology: str | None = None, limit: int = 20):
        return [
            LocalTerm(t, t) for t in sorted(self.terms) if query.lower() in t.lower()
        ]


CROP = LocalVocabulary(
    ontology_id="co_321",
    terms={"CO_321:0000123": "plant height"},
    source="co_321.json",
)


class TestOlsIsOneSourceAmongSeveral:
    def test_a_local_vocabulary_answers_for_a_term_ols_cannot_see(self) -> None:
        router = TermRouter([CROP, _Remote()])

        assert router.get_term_sync("CO_321:0000123") is not None

    def test_the_claiming_source_is_asked_alone(self) -> None:
        """A term absent from the vocabulary that owns it is absent.

        Falling through to a public service here would re-admit terms the local
        list left out on purpose.
        """
        remote = _Remote(terms={"CO_321:0009999"}, ontologies={"co_321"})
        router = TermRouter([CROP, remote])

        assert router.get_term_sync("CO_321:0009999") is None
        assert remote.asked == [], "the remote was consulted about a claimed ontology"

    def test_an_unclaimed_ontology_falls_through_to_the_remote(self) -> None:
        remote = _Remote(terms={"TO:0000387"})
        router = TermRouter([CROP, remote])

        assert router.get_term_sync("TO:0000387") is not None

    def test_a_failing_source_does_not_stop_the_next_one(self) -> None:
        router = TermRouter([_Remote(down=True), _Remote(terms={"TO:0000387"})])

        assert router.get_term_sync("TO:0000387") is not None


class TestWhatTheRouterWillNotClaim:
    def test_unknown_beats_false_when_a_source_could_not_answer(self) -> None:
        """``False`` here would turn an outage into hundreds of false errors."""
        router = TermRouter([_Remote(down=True)])

        assert router.has_ontology_sync("to") is None

    def test_carried_nowhere_is_said_plainly(self) -> None:
        router = TermRouter([_Remote(ontologies={"to"})])

        assert router.has_ontology_sync("co_321") is False

    def test_an_uncarried_ontology_is_not_checked_rather_than_wrong(self) -> None:
        verdict = check_term("CO_321:0000123", ["co_321"], TermRouter([_Remote()]))

        assert verdict.outcome is Outcome.NOT_CHECKED
        assert not verdict.is_problem


class TestSearchingAcrossSources:
    def test_local_terms_are_offered_before_remote_ones(self) -> None:
        router = TermRouter([CROP, _Remote(terms={"TO:0000387"})])

        hits = router.search_sync("00")

        assert hits[0].id == "CO_321:0000123"
        assert {h.id for h in hits} == {"CO_321:0000123", "TO:0000387"}

    def test_a_term_two_sources_hold_is_offered_once(self) -> None:
        router = TermRouter([CROP, _Remote(terms={"CO_321:0000123"})])

        assert len(router.search_sync("CO_321")) == 1

    def test_a_hit_says_which_source_answered(self) -> None:
        """The file, where the source names one — a picker can then show that a
        term is a local addition rather than a published one."""
        hits = TermRouter([CROP]).search_sync("plant")

        assert hits[0].source == "co_321.json"
        assert hits[0].to_dict()["value"] == "CO_321:0000123"


class TestRegistration:
    def test_a_registered_source_is_asked(self) -> None:
        register_term_source(CROP, first=True)

        assert get_term_source().get_term_sync("CO_321:0000123") is not None

    def test_resetting_forgets_it(self) -> None:
        register_term_source(CROP, first=True)
        reset_term_sources()

        assert CROP not in get_term_source().sources


class TestAdaptersConformStructurally:
    """``TermSource`` is a Protocol: an adapter conforms by having the methods.

    Nothing inherits from it, deliberately — an adapter written elsewhere, for
    a service metaseed has never heard of, must not have to import metaseed to
    be usable. This checks the shipped adapters still answer the protocol's
    questions, which inheritance would have enforced for free.
    """

    @pytest.mark.parametrize("adapter", [LocalVocabulary, TermRouter])
    def test_the_shipped_adapters_answer_the_protocol(self, adapter) -> None:
        for name in ("get_term_sync", "has_ontology_sync"):
            assert callable(getattr(adapter, name, None)), (
                f"{adapter.__name__} does not answer {name}"
            )

    def test_the_ols_service_answers_it_too(self) -> None:
        from metaseed.services.ontology import OntologyService

        for name in (
            "get_term_sync",
            "has_ontology_sync",
            "search_sync",
            "is_within_sync",
        ):
            assert callable(getattr(OntologyService, name, None))

    def test_the_protocol_asks_only_what_an_adapter_can_answer(self) -> None:
        """Two required questions, plus search and branch membership, which a
        source may decline to answer without ceasing to be a source."""
        declared = {
            name
            for name, value in vars(TermSource).items()
            if callable(value) and not name.startswith("_")
        }

        assert declared == {
            "get_term_sync",
            "has_ontology_sync",
            "search_sync",
            "is_within_sync",
        }

    def test_search_is_optional(self) -> None:
        """A source that cannot be browsed is still a source."""

        class ConfirmOnly:
            def get_term_sync(self, term_id):
                return LocalTerm(term_id) if term_id == "TO:1" else None

            def has_ontology_sync(self, ontology_id):
                return ontology_id == "to"

        router = TermRouter([ConfirmOnly()])

        assert router.get_term_sync("TO:1") is not None
        assert router.search_sync("anything") == []


def test_the_default_router_reads_the_configured_directory(
    tmp_path, monkeypatch
) -> None:
    """``METASEED_VOCABULARIES`` is the whole configuration."""
    from metaseed.services.terms import VOCABULARY_DIR_ENV

    (tmp_path / "co_321.json").write_text(
        json.dumps({"ontology": "co_321", "terms": {"CO_321:0000123": "plant height"}})
    )
    monkeypatch.setenv(VOCABULARY_DIR_ENV, str(tmp_path))
    reset_term_sources()

    router = get_term_source()

    assert router.get_term_sync("CO_321:0000123") is not None
    assert router.has_ontology_sync("co_321") is True
    assert router.sources[-1].__class__.__name__ == "OntologyService", (
        "OLS must be asked last, so local vocabularies resolve without a network"
    )


def test_no_configuration_means_ols_alone(monkeypatch) -> None:
    from metaseed.services.terms import VOCABULARY_DIR_ENV

    monkeypatch.delenv(VOCABULARY_DIR_ENV, raising=False)
    reset_term_sources()

    sources = get_term_source().sources

    assert len(sources) == 1
    assert sources[0].__class__.__name__ == "OntologyService"
