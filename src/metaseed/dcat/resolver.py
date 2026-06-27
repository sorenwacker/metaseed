"""Resolve a metaseed dataset into the DCAT intermediate representation.

The resolver merges two sources for dataset-level metadata, explicit-wins:

1. values derived from the dataset's root entity via the profile field map
   (:mod:`metaseed.dcat.mapping`), and
2. explicit :class:`CatalogMetadata` provided on the dataset.

See docs/architecture/dcat.md.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from metaseed.dcat.mapping import get_field_map
from metaseed.dcat.model import (
    DcatAgent,
    DcatCatalog,
    DcatContactPoint,
    DcatDataset,
)

if TYPE_CHECKING:
    from collections.abc import Iterable

    from metaseed.repositories.dataset_repository import CatalogMetadata


def _first(explicit: Any, derived: Any) -> Any:
    """Return ``explicit`` unless it is empty, else ``derived``."""
    return explicit if explicit not in (None, "", [], {}) else derived


def _as_str_list(value: Any) -> list[str]:
    """Coerce a value into a list of strings (for keyword/relation-like fields)."""
    if value in (None, "", [], {}):
        return []
    if isinstance(value, list):
        return [str(v) for v in value]
    return [str(value)]


def _contact_from(contacts: Any) -> DcatContactPoint | None:
    """Build a contact point from the first entry of a contacts list."""
    if not isinstance(contacts, list) or not contacts:
        return None
    first = contacts[0]
    if not isinstance(first, dict):
        return None
    name = first.get("name") or first.get("full_name")
    if not name:
        parts = [first.get("first_name"), first.get("last_name")]
        name = " ".join(p for p in parts if p) or None
    email = first.get("email")
    if name is None and email is None:
        return None
    return DcatContactPoint(name=name, email=email)


def build_dcat_dataset(
    *,
    profile: str,
    root_entity: dict[str, Any] | None = None,
    catalog_metadata: CatalogMetadata | None = None,
    modified: str | None = None,
    fallback_identifier: str | None = None,
) -> DcatDataset:
    """Build a :class:`DcatDataset` from a dataset's root entity and metadata.

    Args:
        profile: Profile name (selects the field map).
        root_entity: The root entity's field values, if the profile is
            container-rooted; ignored fields are simply absent.
        catalog_metadata: Explicit dataset-level metadata (overrides derived).
        modified: Dataset modification timestamp (``dct:modified``).
        fallback_identifier: Used for identifier/title when nothing else applies
            (typically the dataset name).

    Returns:
        The resolved DCAT dataset (explicit metadata wins over derived).
    """
    fmap = get_field_map(profile)
    root = root_entity or {}
    cm = catalog_metadata

    def derived(field_name: str | None) -> Any:
        return root.get(field_name) if field_name else None

    contact_point = _contact_from(derived(fmap.contacts)) if fmap else None
    if cm and (cm.contact_name or cm.contact_email):
        contact_point = DcatContactPoint(name=cm.contact_name, email=cm.contact_email)

    publisher = DcatAgent(name=cm.publisher) if cm and cm.publisher else None

    title = _first(cm.title if cm else None, derived(fmap.title if fmap else None))
    identifier = derived(fmap.identifier if fmap else None) or fallback_identifier

    return DcatDataset(
        identifier=identifier,
        title=title or fallback_identifier,
        description=_first(
            cm.description if cm else None, derived(fmap.description if fmap else None)
        ),
        issued=_first(
            cm.issued if cm else None, derived(fmap.issued if fmap else None)
        ),
        modified=modified,
        license=_first(
            cm.license if cm else None, derived(fmap.license if fmap else None)
        ),
        publisher=publisher,
        contact_point=contact_point,
        landing_page=cm.landing_page if cm else None,
        keywords=list(cm.keywords) if cm else [],
        themes=list(cm.themes) if cm else [],
        related=_as_str_list(derived(fmap.related if fmap else None)),
    )


def build_dcat_catalog(
    *,
    title: str | None = None,
    description: str | None = None,
    publisher: str | None = None,
    homepage: str | None = None,
    datasets: Iterable[DcatDataset] = (),
) -> DcatCatalog:
    """Build a :class:`DcatCatalog` wrapping the given datasets."""
    return DcatCatalog(
        title=title,
        description=description,
        publisher=DcatAgent(name=publisher) if publisher else None,
        homepage=homepage,
        datasets=list(datasets),
    )
