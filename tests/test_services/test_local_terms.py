"""A vocabulary can be carried rather than fetched.

OLS4 does not host `co_321`, which MIAPPE names beside `to`; a consortium's own
list exists nowhere public; a laptop in a glasshouse has no network. A local
vocabulary answers the same two questions as the remote service, so the same
check works against either — and asking the local one first is what makes a
term the remote service cannot see validate at all.
"""

from __future__ import annotations

import json

import pytest

from metaseed.services.local_terms import ChainedTermSource, LocalVocabulary
from metaseed.services.term_check import Outcome, check_term

CROP_TERMS = {"CO_321:0000123": "plant height", "CO_321:0000456": "grain yield"}


@pytest.fixture
def crop_ontology(tmp_path):
    path = tmp_path / "co_321.json"
    path.write_text(json.dumps({"ontology": "co_321", "terms": CROP_TERMS}))
    return LocalVocabulary.from_file(path)


class TestAVocabularyInAFile:
    def test_it_knows_its_terms(self, crop_ontology) -> None:
        assert crop_ontology.get_term_sync("CO_321:0000123").label == "plant height"

    def test_it_does_not_invent_terms(self, crop_ontology) -> None:
        assert crop_ontology.get_term_sync("CO_321:9999999") is None

    def test_it_knows_which_ontology_it_is(self, crop_ontology) -> None:
        assert crop_ontology.has_ontology_sync("CO_321") is True
        assert crop_ontology.has_ontology_sync("to") is False

    def test_a_file_that_does_not_say_what_it_is_is_refused(self, tmp_path) -> None:
        path = tmp_path / "nameless.json"
        path.write_text(json.dumps({"terms": CROP_TERMS}))

        with pytest.raises(ValueError, match="which ontology"):
            LocalVocabulary.from_file(path)

    def test_it_can_be_searched_for_a_picker(self, crop_ontology) -> None:
        assert [t.id for t in crop_ontology.search_sync("height")] == ["CO_321:0000123"]


class TestAskingLocalFirst:
    class _Remote:
        """A remote that carries `to` and has never heard of crop ontology."""

        def get_term_sync(self, term_id: str) -> object | None:
            return object() if term_id.lower().startswith("to:") else None

        def has_ontology_sync(self, ontology_id: str) -> bool | None:
            return ontology_id == "to"

    def test_a_term_the_remote_cannot_see_validates_locally(
        self, crop_ontology
    ) -> None:
        source = ChainedTermSource(local=[crop_ontology], remote=self._Remote())

        verdict = check_term("CO_321:0000123", ["to", "co_321"], source)

        assert verdict.outcome is Outcome.OK

    def test_a_wrong_term_in_a_carried_vocabulary_is_reported(
        self, crop_ontology
    ) -> None:
        """The local list is authoritative for its own ontology: falling through
        to the remote would answer about a vocabulary it does not hold."""
        source = ChainedTermSource(local=[crop_ontology], remote=self._Remote())

        verdict = check_term("CO_321:9999999", ["co_321"], source)

        assert verdict.outcome is Outcome.NOT_FOUND

    def test_the_remote_still_answers_for_what_it_carries(self, crop_ontology) -> None:
        source = ChainedTermSource(local=[crop_ontology], remote=self._Remote())

        assert check_term("TO:0000387", ["to"], source).outcome is Outcome.OK

    def test_with_no_network_and_no_local_copy_nothing_is_claimed(self) -> None:
        source = ChainedTermSource(local=[], remote=None)

        verdict = check_term("TO:0000387", ["to"], source)

        assert verdict.outcome is Outcome.NOT_CHECKED
        assert not verdict.is_problem


class TestVocabulariesLiveApartFromSpecs:
    """A spec names an ontology and nothing else. The vocabulary is its own
    artifact, versioned separately, and extended by adding a file — not by
    editing the snapshot someone else maintains."""

    def _store(self, tmp_path, *files):
        from metaseed.services.local_terms import VocabularyStore

        for name, payload in files:
            (tmp_path / name).write_text(json.dumps(payload))
        return VocabularyStore.from_directory(tmp_path)

    def test_a_second_file_extends_the_first(self, tmp_path) -> None:
        store = self._store(
            tmp_path,
            ("co_321.10-snapshot.json", {"ontology": "co_321", "terms": CROP_TERMS}),
            (
                "co_321.20-consortium.json",
                {"ontology": "co_321", "terms": {"CO_321:9000001": "tiller angle"}},
            ),
        )

        vocabulary = store.vocabularies["co_321"]
        assert vocabulary.get_term_sync("CO_321:0000123") is not None, "snapshot kept"
        assert vocabulary.get_term_sync("CO_321:9000001") is not None, "extension added"

    def test_an_added_term_remembers_where_it_came_from(self, tmp_path) -> None:
        store = self._store(
            tmp_path,
            ("co_321.10-snapshot.json", {"ontology": "co_321", "terms": CROP_TERMS}),
            (
                "co_321.20-consortium.json",
                {"ontology": "co_321", "terms": {"CO_321:9000001": "tiller angle"}},
            ),
        )

        assert "consortium" in store.source_of("CO_321:9000001")
        assert "snapshot" in store.source_of("CO_321:0000123")

    def test_the_store_answers_as_a_term_source(self, tmp_path) -> None:
        store = self._store(
            tmp_path, ("co_321.json", {"ontology": "co_321", "terms": CROP_TERMS})
        )

        verdict = check_term("CO_321:0000123", ["co_321"], store.as_source())

        assert verdict.outcome is Outcome.OK

    def test_an_empty_installation_claims_nothing(self, tmp_path) -> None:
        from metaseed.services.local_terms import VocabularyStore

        store = VocabularyStore.from_directory(tmp_path / "does-not-exist")

        assert check_term("TO:1", ["to"], store.as_source()).outcome is (
            Outcome.NOT_CHECKED
        )
