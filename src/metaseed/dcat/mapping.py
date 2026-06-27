"""Per-profile DCAT field maps.

For container-rooted profiles (MIAPPE/ISA Investigation, ENA Study) the root
entity already carries dataset-level metadata, so a profile can declare how its
root-entity fields map onto DCAT Dataset properties. Record-rooted profiles
(Darwin Core, DiSSCo) have no entry and rely entirely on explicit
``CatalogMetadata``.

This registry is intentionally small and code-level for now; moving the maps
into each ``profile.yaml`` is a possible later refinement.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DcatFieldMap:
    """Names of the root-entity fields that supply DCAT Dataset properties.

    Each attribute holds the root-entity field name to read, or None if the
    profile's root entity does not provide that property.
    """

    title: str | None = None
    description: str | None = None
    identifier: str | None = None
    issued: str | None = None
    available: str | None = None
    license: str | None = None
    contacts: str | None = None
    related: str | None = None


PROFILE_FIELD_MAPS: dict[str, DcatFieldMap] = {
    "miappe": DcatFieldMap(
        title="title",
        description="description",
        identifier="unique_id",
        issued="submission_date",
        available="public_release_date",
        license="license",
        contacts="contacts",
        related="associated_publications",
    ),
    "isa": DcatFieldMap(
        title="title",
        description="description",
        identifier="identifier",
        issued="submission_date",
        available="public_release_date",
        contacts="contacts",
        related="publications",
    ),
    "ena": DcatFieldMap(
        title="title",
        description="description",
        identifier="accession",
        related="pubmed_ids",
    ),
}


def get_field_map(profile: str) -> DcatFieldMap | None:
    """Return the DCAT field map for a profile, or None if it has none."""
    return PROFILE_FIELD_MAPS.get(profile.lower())
