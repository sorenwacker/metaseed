"""Binding a DCAT card to where and how a dataset is published.

metaseed resolves what a dataset *is* from its profile. Where it can be fetched,
what identifies it, and what may be done with it belong to whatever platform
publishes it — a repository deposit, a data portal, a lab's own site. This module
is how that platform supplies them.

The rule it enforces: **the publication's identity is the publisher's, never the
content's.** A card resolved from an imported dataset carries the repository
accession it came from; publishing replaces that identity with the publisher's
own and keeps the accession as provenance. See ``docs/architecture/dcat.md``.

Pure and dependency-free, so a host can build a published card without the
``metaseed[dcat]`` extra and serialize it elsewhere.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

from metaseed.dcat.model import DcatAgent, DcatDataset, DcatDistribution

if TYPE_CHECKING:
    from collections.abc import Iterable

# Landing pages for the repositories metaseed can import from. A profile absent
# here has no repository to point at, and guessing a URL would produce a link
# that does not resolve — worse than no link.
ORIGIN_LANDING_PAGE: dict[str, str] = {
    "ena": "https://www.ebi.ac.uk/ena/browser/view/{accession}",
    "pride": "https://www.ebi.ac.uk/pride/archive/projects/{accession}",
    "metabolights": "https://www.ebi.ac.uk/metabolights/{accession}",
}

_SPDX_LICENSE = "https://spdx.org/licenses/{identifier}.html"


class PublicationContext(BaseModel):
    """What the publisher knows and metaseed cannot derive.

    Only ``landing_page`` is required: without somewhere to fetch the dataset
    nothing else is assessable, and it can always stand in as the identifier.
    """

    model_config = ConfigDict(extra="forbid")

    landing_page: str
    """The stable public URL of the published dataset."""
    identifier: str | None = None
    """A DOI once minted; the landing page identifies the record until then."""
    license: str | None = None
    """SPDX identifier or licence URL."""
    version: str | None = None
    is_version_of: str | None = None
    """Set only when this publication is a copy of another record."""
    publisher: DcatAgent | None = None
    distributions: list[DcatDistribution] = []
    """Where the published dataset can actually be fetched."""
    source: list[str] = []
    """Records this dataset was derived from."""
    conforms_to: list[str] = []
    issued: str | None = None
    modified: str | None = None


def spdx_license_uri(value: str | None) -> str | None:
    """Turn a bare SPDX identifier into its URI; leave a URL alone.

    A machine-readable licence has to be something a consumer can resolve and
    match, so ``"CC-BY-4.0"`` is upgraded while an explicit URL passes through
    unchanged.
    """
    if not value:
        return None
    if "://" in value:
        return value
    return _SPDX_LICENSE.format(identifier=value)


def origin_url(profile: str, accession: str) -> str | None:
    """Landing page for a record in the repository ``profile`` names.

    Constructing the URL is the only part of origin linking metaseed can do
    honestly. Deciding that the dataset *was derived from* that record stays with
    the caller: nothing in a dataset records that it was imported, and a dataset
    authored here for submission carries an accession too, with the derivation
    running the other way.

    Returns:
        The URL, or ``None`` when the profile has no repository or the accession
        is empty.
    """
    template = ORIGIN_LANDING_PAGE.get(profile)
    if not template or not accession:
        return None
    return template.format(accession=accession)


def _merged(derived: Iterable[str], supplied: Iterable[str]) -> list[str]:
    """Both sets of claims, de-duplicated, in first-seen order."""
    seen: dict[str, None] = {}
    for value in (*derived, *supplied):
        if value:
            seen.setdefault(value, None)
    return list(seen)


def build_published_dataset(
    dataset: DcatDataset,
    context: PublicationContext,
) -> DcatDataset:
    """Return a copy of ``dataset`` bound to where and how it is published.

    Any identifier derived from the content — a repository accession, a local
    investigation id — is replaced by the publisher's. It is not lost: it stays
    in ``source`` when the caller supplies it there, and in the distribution
    files the card points at.

    Args:
        dataset: The card as resolved from the dataset's profile.
        context: What the publishing platform knows.

    Returns:
        A new card. The input is never mutated, so one resolved card can be
        published to several destinations.
    """
    published = dataset.model_copy(deep=True)

    published.identifier = context.identifier or context.landing_page
    published.landing_page = context.landing_page
    published.license = spdx_license_uri(context.license) or spdx_license_uri(
        dataset.license
    )
    if context.publisher is not None:
        published.publisher = context.publisher
    if context.version is not None:
        published.version = context.version
    if context.is_version_of is not None:
        published.is_version_of = context.is_version_of
    if context.issued is not None:
        published.issued = context.issued
    if context.modified is not None:
        published.modified = context.modified
    if context.distributions:
        # Replaced, not extended: a path the card was resolved with is not where
        # the published dataset can be fetched from.
        published.distributions = list(context.distributions)
    published.source = _merged(dataset.source, context.source)
    published.conforms_to = _merged(dataset.conforms_to, context.conforms_to)

    return published
