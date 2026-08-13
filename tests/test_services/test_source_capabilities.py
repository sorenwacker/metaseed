"""What a term source says about itself before it is asked (#247, sections 1 and 4).

Autocomplete debounces at 300 ms. plan07 measured OLS answering PO in 51 seconds
and PATO in 32 against 20-55 ms from a local store: the feature was unusable
while looking fully implemented, and nothing in the system could tell the
difference. Latency is therefore a property a source declares, not a quality of
service discovered from a user complaint — so a deployment can validate against
a slow source and offer typeahead from a fast one.

Cost is the same kind of statement: GAZ is ~180 MB, ChEBI and NCBITaxon are the
same class, and a consumer that materialises sources needs to decide rather than
find out mid-import.

Two rules shape every test here. A source that declares nothing keeps working
exactly as it does today — silence means "as good as it has always been", never
"unusable" — and a source left out of a search is **reported**, because a
silently shorter result list is indistinguishable from there being nothing to
find.
"""

from __future__ import annotations

from metaseed.services.local_terms import LocalTerm, LocalVocabulary
from metaseed.services.term_check import Materialisation, SourceCapabilities
from metaseed.services.terms import TermRouter


class _Fast:
    """A local store: answers in milliseconds, cheap to hold."""

    def __init__(self, *terms: str) -> None:
        self.terms = terms

    def get_term_sync(self, term_id: str) -> object | None:
        return LocalTerm(term_id) if term_id in self.terms else None

    def has_ontology_sync(self, ontology_id: str) -> bool | None:
        return True

    def search_sync(self, query, ontology=None, limit=20):
        return [LocalTerm(t, t) for t in self.terms if query.lower() in t.lower()]

    def capabilities(self) -> SourceCapabilities:
        return SourceCapabilities(name="fast", interactive=True)


class _Slow(_Fast):
    """A source that has measured itself and knows it cannot serve typeahead."""

    def capabilities(self) -> SourceCapabilities:
        return SourceCapabilities(
            name="slow",
            interactive=False,
            materialisation=Materialisation.LARGE,
            note="51s for PO",
        )


class _Undeclared(_Fast):
    """An adapter written before any of this existed."""

    capabilities = None  # type: ignore[assignment]


class TestWhatASourceDeclares:
    def test_silence_means_what_it_does_today(self) -> None:
        """An adapter that declares nothing must not become unusable for it."""
        declared = TermRouter([_Undeclared("TO:1")]).describe()

        assert len(declared) == 1
        assert declared[0].interactive is True
        assert declared[0].materialisation is Materialisation.UNKNOWN

    def test_a_source_is_named_in_what_it_declares(self) -> None:
        declared = TermRouter([_Slow("TO:1")]).describe()

        assert declared[0].name == "slow"
        assert declared[0].note == "51s for PO"

    def test_cost_is_declarable(self) -> None:
        assert (
            TermRouter([_Slow()]).describe()[0].materialisation is Materialisation.LARGE
        )

    def test_a_shipped_local_vocabulary_declares_itself(self) -> None:
        vocabulary = LocalVocabulary(ontology_id="co_321", terms={"CO_321:1": "x"})

        capabilities = vocabulary.capabilities()

        assert capabilities.interactive is True
        assert capabilities.materialisation is Materialisation.CHEAP


class TestSearchingInteractively:
    def test_a_slow_source_is_left_out(self) -> None:
        router = TermRouter([_Fast("TO:1"), _Slow("TO:2")])

        hits = router.search_sync("TO", interactive=True)

        assert [h.id for h in hits] == ["TO:1"]

    def test_it_is_asked_when_latency_does_not_matter(self) -> None:
        """Validation is not typeahead: a slow source is still the right source
        to ask whether a term exists."""
        router = TermRouter([_Fast("TO:1"), _Slow("TO:2")])

        hits = router.search_sync("TO")

        assert {h.id for h in hits} == {"TO:1", "TO:2"}

    def test_an_undeclared_source_is_still_asked(self) -> None:
        router = TermRouter([_Undeclared("TO:1")])

        assert router.search_sync("TO", interactive=True)

    def test_the_omission_is_reportable(self) -> None:
        """A shorter list of results looks exactly like there being less to
        find. The consumer has to be able to say which sources were skipped."""
        router = TermRouter([_Fast("TO:1"), _Slow("TO:2")])

        assert router.not_interactive() == ["slow"]

    def test_nothing_to_report_when_every_source_is_fast(self) -> None:
        assert TermRouter([_Fast("TO:1")]).not_interactive() == []


class TestTheRouterSpeaksForItself:
    def test_it_is_interactive_when_any_source_is(self) -> None:
        router = TermRouter([_Slow("TO:2"), _Fast("TO:1")])

        assert router.capabilities().interactive is True

    def test_it_is_not_when_none_are(self) -> None:
        assert TermRouter([_Slow("TO:2")]).capabilities().interactive is False

    def test_it_reports_the_most_expensive_source_it_holds(self) -> None:
        """A consumer deciding whether to materialise needs the worst case, not
        an average of one."""
        router = TermRouter([_Fast("TO:1"), _Slow("TO:2")])

        assert router.capabilities().materialisation is Materialisation.LARGE


class TestThePickerAsksInteractively:
    """The route behind the term picker, where the wait is a person's (#247)."""

    def test_it_leaves_out_a_source_that_cannot_answer_in_time(self, monkeypatch):
        from fastapi.testclient import TestClient

        from metaseed.services.terms import register_term_source, reset_term_sources
        from metaseed.ui.app import create_app
        from metaseed.ui.state import AppState

        reset_term_sources()
        try:
            router = register_term_source(_Slow("TO:0000387"), first=True)
            router.sources = [_Slow("TO:0000387"), _Fast("TO:0000001")]

            client = TestClient(create_app(AppState()))
            payload = client.get("/api/ontology/search", params={"q": "TO"}).json()

            assert [r["value"] for r in payload["results"]] == ["TO:0000001"]
            assert payload["not_asked"] == ["slow"]
        finally:
            reset_term_sources()

    def test_nothing_is_reported_when_every_source_answered(self, monkeypatch):
        from fastapi.testclient import TestClient

        from metaseed.services.terms import register_term_source, reset_term_sources
        from metaseed.ui.app import create_app
        from metaseed.ui.state import AppState

        reset_term_sources()
        try:
            router = register_term_source(_Fast("TO:0000001"), first=True)
            router.sources = [_Fast("TO:0000001")]

            client = TestClient(create_app(AppState()))
            payload = client.get("/api/ontology/search", params={"q": "TO"}).json()

            assert payload["not_asked"] == []
        finally:
            reset_term_sources()
