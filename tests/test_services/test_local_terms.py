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

from metaseed.services.local_terms import LocalVocabulary

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
