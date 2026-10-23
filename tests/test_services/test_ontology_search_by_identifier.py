"""Typing a term's identifier finds that term first.

OLS searches names, so "3702" in an NCBITaxon field listed organisms with 3702
in their name and never Arabidopsis thaliana, NCBITaxon:3702.
"""

from __future__ import annotations

import httpx
import pytest

from metaseed.services.ontology import OntologyService

ARABIDOPSIS = {
    "obo_id": "NCBITaxon:3702",
    "short_form": "NCBITaxon_3702",
    "label": "Arabidopsis thaliana",
    "ontology_prefix": "NCBITaxon",
}
NEAR = {
    "obo_id": "NCBITaxon:37020",
    "short_form": "NCBITaxon_37020",
    "label": "Oryzomys palustris",
    "ontology_prefix": "NCBITaxon",
}
NAMED = {
    "obo_id": "NCBITaxon:1280343",
    "short_form": "NCBITaxon_1280343",
    "label": "Bradyrhizobium sp. LCM 3702",
    "ontology_prefix": "NCBITaxon",
}


@pytest.fixture
def ols(monkeypatch):
    """OLS as it answers: by name unless asked by the identifier fields."""

    def get(self, url, params=None, **kwargs):
        by_id = "obo_id" in (params or {}).get("queryFields", "")
        docs = [ARABIDOPSIS, NEAR] if by_id else [NAMED]
        return httpx.Response(
            200, json={"response": {"docs": docs}}, request=httpx.Request("GET", url)
        )

    monkeypatch.setattr(httpx.Client, "get", get)


@pytest.mark.parametrize(
    "query",
    [
        "3702",
        "NCBITaxon:3702",
        "ncbitaxon:3702",
        "NCBITaxon_3702",
        "http://purl.obolibrary.org/obo/NCBITaxon_3702",
    ],
)
def test_an_identifier_finds_its_term_first(ols, query) -> None:
    results = OntologyService(cache_ttl=0).search_sync(query, ontology="ncbitaxon")

    assert results[0].term_id == "NCBITaxon:3702"
    assert "NCBITaxon:37020" not in [r.term_id for r in results]
    assert "NCBITaxon:1280343" in [r.term_id for r in results]


def test_a_name_is_searched_by_name_only(ols) -> None:
    results = OntologyService(cache_ttl=0).search_sync(
        "Arabidopsis", ontology="ncbitaxon"
    )

    assert [r.term_id for r in results] == ["NCBITaxon:1280343"]
