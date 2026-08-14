"""pride/2.0 identifies a Publication by its doi, not its title (#249).

1.0 declared no identifier, so inference fell back to the first field —
title, a display label two submissions can share. Moving the marker changes
index keys and node ids for written datasets, which is why this is a new
MAJOR version rather than an edit in place; `compare_specs` reports the
change as breaking, and correctly so. The doi-or-pubmed_id question from the
issue is answered with a value-dependent rule (#211): a publication without
a pubmed_id must carry a doi.
"""

from __future__ import annotations

from metaseed.specs.loader import SpecLoader
from metaseed.validators.api import validate


def test_doi_is_the_declared_identifier() -> None:
    spec = SpecLoader().load_profile("2.0", "pride")
    publication = spec.entities["Publication"]

    assert next((f.name for f in publication.fields if f.is_identifier), None) == "doi"


def test_a_publication_needs_a_doi_or_a_pubmed_id() -> None:
    errors = validate(
        {"title": "Shared title"},
        entity="Publication",
        version="2.0",
        profile="pride",
    )
    identity = [e for e in errors if e.rule == "publication_identity"]
    assert identity, [(e.rule, e.message) for e in errors]


def test_either_identifier_satisfies_the_rule() -> None:
    for data in (
        {"doi": "10.1234/abc"},
        {"pubmed_id": "12345"},
    ):
        errors = validate(data, entity="Publication", version="2.0", profile="pride")
        assert not [e for e in errors if e.rule == "publication_identity"], data


def test_one_point_oh_is_untouched() -> None:
    """Datasets written against 1.0 keep their index keys and node ids."""
    spec = SpecLoader().load_profile("1.0", "pride")
    publication = spec.entities["Publication"]

    assert not any(f.is_identifier for f in publication.fields)
