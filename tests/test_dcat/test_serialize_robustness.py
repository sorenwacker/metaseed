"""Robustness tests for DCAT serialization (hardening).

User-supplied values (identifiers, URLs, emails) must never produce RDF that
rdflib refuses to serialize. These pin the safe handling of values that are not
valid IRIs.
"""

from __future__ import annotations

import pytest

from metaseed.dcat import build_dcat_catalog, build_dcat_dataset
from metaseed.dcat.model import DcatContactPoint, DcatDistribution

pytest.importorskip("rdflib")

import rdflib

from metaseed.dcat.serialize import to_jsonld, to_turtle


def _reparses(turtle: str) -> int:
    return len(rdflib.Graph().parse(data=turtle, format="turtle"))


def test_identifier_with_spaces_serializes():
    ds = build_dcat_dataset(root_fields=[], fallback_identifier="My Dataset 2024")
    turtle = to_turtle(ds)  # must not raise
    assert _reparses(turtle) >= 1
    to_jsonld(ds)  # must not raise either


def test_identifier_with_odd_characters_serializes():
    ds = build_dcat_dataset(root_fields=[], fallback_identifier="acc/2024:v1 <x>")
    assert _reparses(to_turtle(ds)) >= 1


def test_invalid_license_or_relation_falls_back_to_literal():
    # A license-ish value that is not a valid IRI must not break serialization.
    ds = build_dcat_dataset(root_fields=[], fallback_identifier="d1")
    ds.license = "Creative Commons BY 4.0"
    ds.related = ["see paper, 2024"]
    assert _reparses(to_turtle(ds)) >= 1


def test_invalid_distribution_url_and_email_serialize():
    ds = build_dcat_dataset(root_fields=[], fallback_identifier="d1")
    ds.contact_point = DcatContactPoint(name="A B", email="not an email")
    ds.distributions = [
        DcatDistribution(
            access_url="http://ex.org/a file.ttl", media_type="text/turtle"
        )
    ]
    assert _reparses(to_turtle(ds)) >= 1


def test_catalog_with_spacey_dataset_identifier():
    ds = build_dcat_dataset(root_fields=[], fallback_identifier="My DS")
    cat = build_dcat_catalog(title="C", datasets=[ds])
    assert _reparses(to_turtle(cat)) >= 1
