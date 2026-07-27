"""Binding a card to where and how a dataset is published.

metaseed cannot know a landing page, a DOI, or a licence — those belong to
whatever platform publishes the dataset. This is the seam it supplies them
through, and the rule it enforces: the publication's identity is the publisher's,
never the content's.
"""

from __future__ import annotations

import pytest

from metaseed.dcat.model import DcatAgent, DcatDataset, DcatDistribution
from metaseed.dcat.publication import (
    PublicationContext,
    build_published_dataset,
    origin_url,
    spdx_license_uri,
)

LANDING = "https://data.example.org/d/abc123"
DOI = "https://doi.org/10.5281/zenodo.1234567"


def _imported_card() -> DcatDataset:
    """A card as resolved from a dataset imported from ENA."""
    return DcatDataset(
        identifier="PRJEB12345",
        title="Derived study",
        license="CC-BY-3.0",
        source=["PRJEB12345"],
        distributions=[DcatDistribution(download_url="file:///tmp/local.yaml")],
    )


def test_the_publisher_s_identifier_replaces_one_derived_from_content() -> None:
    """The card must not go out claiming the accession it was derived from."""
    published = build_published_dataset(
        _imported_card(), PublicationContext(landing_page=LANDING, identifier=DOI)
    )

    assert published.identifier == DOI
    assert published.identifier != "PRJEB12345"
    assert published.landing_page == LANDING


def test_the_landing_page_identifies_the_record_when_there_is_no_doi() -> None:
    published = build_published_dataset(
        _imported_card(), PublicationContext(landing_page=LANDING)
    )

    assert published.identifier == LANDING


def test_the_origin_survives_as_provenance() -> None:
    """Replacing the identity must not lose where the dataset came from."""
    published = build_published_dataset(
        _imported_card(),
        PublicationContext(
            landing_page=LANDING,
            identifier=DOI,
            source=[origin_url("ena", "PRJEB12345") or ""],
        ),
    )

    assert "PRJEB12345" in " ".join(published.source)
    assert "PRJEB12345" not in (published.identifier or "")


def test_the_publisher_s_licence_wins_over_the_derived_one() -> None:
    published = build_published_dataset(
        _imported_card(),
        PublicationContext(landing_page=LANDING, license="CC-BY-4.0"),
    )

    assert published.license == "https://spdx.org/licenses/CC-BY-4.0.html"
    assert "3.0" not in (published.license or "")


def test_a_derived_licence_is_kept_and_normalised_when_none_is_supplied() -> None:
    published = build_published_dataset(
        _imported_card(), PublicationContext(landing_page=LANDING)
    )

    assert published.license == "https://spdx.org/licenses/CC-BY-3.0.html"


def test_distributions_are_replaced_not_appended() -> None:
    """The local file path the card was resolved with is not where the published
    dataset can be fetched from, so it must not survive alongside the real one."""
    published = build_published_dataset(
        _imported_card(),
        PublicationContext(
            landing_page=LANDING,
            distributions=[
                DcatDistribution(download_url=f"{LANDING}.ttl"),
                DcatDistribution(download_url=f"{LANDING}.jsonld"),
            ],
        ),
    )

    assert [d.download_url for d in published.distributions] == [
        f"{LANDING}.ttl",
        f"{LANDING}.jsonld",
    ]


def test_publishing_does_not_mutate_the_card_it_was_given() -> None:
    """The same resolved card is published more than once — to a staging URL and
    a real one — so an in-place edit would leak the first into the second."""
    card = _imported_card()
    before = card.model_dump()

    build_published_dataset(
        card, PublicationContext(landing_page=LANDING, identifier=DOI)
    )

    assert card.model_dump() == before


def test_supplied_and_derived_provenance_are_merged_without_duplicates() -> None:
    published = build_published_dataset(
        DcatDataset(identifier="x", source=["urn:a"], conforms_to=["urn:std"]),
        PublicationContext(
            landing_page=LANDING, source=["urn:a", "urn:b"], conforms_to=["urn:std"]
        ),
    )

    assert published.source == ["urn:a", "urn:b"]
    assert published.conforms_to == ["urn:std"]


def test_the_publisher_and_version_come_from_the_context() -> None:
    published = build_published_dataset(
        DcatDataset(identifier="x"),
        PublicationContext(
            landing_page=LANDING,
            version="2",
            is_version_of="https://data.example.org/d/abc122",
            publisher=DcatAgent(name="Example Org", uri="https://example.org"),
        ),
    )

    assert published.version == "2"
    assert published.is_version_of == "https://data.example.org/d/abc122"
    assert published.publisher is not None and published.publisher.name == "Example Org"


@pytest.mark.parametrize(
    ("profile", "accession", "expected"),
    [
        ("ena", "PRJEB12345", "https://www.ebi.ac.uk/ena/browser/view/PRJEB12345"),
        (
            "pride",
            "PXD000001",
            "https://www.ebi.ac.uk/pride/archive/projects/PXD000001",
        ),
        ("metabolights", "MTBLS1", "https://www.ebi.ac.uk/metabolights/MTBLS1"),
    ],
)
def test_origin_url_per_repository(profile: str, accession: str, expected: str) -> None:
    assert origin_url(profile, accession) == expected


@pytest.mark.parametrize(
    ("profile", "accession"),
    [("miappe", "X"), ("ena", ""), ("a-spec-builder-profile", "X")],
)
def test_origin_url_is_none_when_there_is_no_repository_to_point_at(
    profile: str, accession: str
) -> None:
    """Guessing a URL for a profile with no repository would produce a link that
    does not resolve, which is worse than no link."""
    assert origin_url(profile, accession) is None


def test_spdx_license_uri_upgrades_an_identifier() -> None:
    assert spdx_license_uri("CC-BY-4.0") == "https://spdx.org/licenses/CC-BY-4.0.html"
    assert spdx_license_uri("MIT") == "https://spdx.org/licenses/MIT.html"


def test_spdx_license_uri_leaves_a_url_untouched() -> None:
    url = "https://creativecommons.org/licenses/by/4.0/"

    assert spdx_license_uri(url) == url
    assert spdx_license_uri(None) is None
