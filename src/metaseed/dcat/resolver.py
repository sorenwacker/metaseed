"""Resolve a metaseed dataset into the DCAT intermediate representation.

The mapping from a profile's root-entity fields onto DCAT properties is declared
in the spec itself: each ``FieldSpec`` may carry a ``dcat`` annotation naming the
DCAT/DCAT-AP property it provides (e.g. ``dct:title``, ``dct:issued``,
``dcat:contactPoint``). The resolver reads those annotations and merges in
explicit :class:`CatalogMetadata`, explicit-wins.

See docs/architecture/dcat.md.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from metaseed.dcat.model import (
    DcatAgent,
    DcatCatalog,
    DcatContactPoint,
    DcatDataset,
)

if TYPE_CHECKING:
    from collections.abc import Iterable

    from metaseed.repositories.dataset_repository import CatalogMetadata
    from metaseed.specs.schema import FieldSpec

_EMPTY: tuple[Any, ...] = (None, "", [], {})


def _first(explicit: Any, derived: Any) -> Any:
    """Return ``explicit`` unless it is empty, else ``derived``."""
    return explicit if explicit not in _EMPTY else derived


def _scalar(value: Any) -> str | None:
    """Coerce a value to a single string (first element if it is a list)."""
    if value in _EMPTY:
        return None
    if isinstance(value, list):
        return str(value[0]) if value else None
    return str(value)


def _as_str_list(value: Any) -> list[str]:
    """Coerce a value into a list of strings."""
    if value in _EMPTY:
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
    root_fields: Iterable[FieldSpec] = (),
    root_entity: dict[str, Any] | None = None,
    catalog_metadata: CatalogMetadata | None = None,
    modified: str | None = None,
    fallback_identifier: str | None = None,
) -> DcatDataset:
    """Build a :class:`DcatDataset` from a root entity and its field specs.

    Args:
        root_fields: The root entity's field specs; each field's ``dcat``
            annotation declares the DCAT property it provides.
        root_entity: The root entity's field values.
        catalog_metadata: Explicit dataset-level metadata (overrides derived).
        modified: Dataset modification timestamp (``dct:modified``).
        fallback_identifier: Used for identifier/title when nothing else applies
            (typically the dataset name).

    Returns:
        The resolved DCAT dataset (explicit metadata wins over derived).
    """
    root = root_entity or {}
    cm = catalog_metadata

    # Collect derived values keyed by the DCAT term each field is annotated with.
    derived: dict[str, Any] = {}
    for field in root_fields:
        if field.dcat and root.get(field.name) not in _EMPTY:
            derived[field.dcat] = root[field.name]

    def d(term: str) -> Any:
        return derived.get(term)

    # Contact: from the dcat:contactPoint field (a contacts list), overridden by
    # explicit metadata.
    contact_point = _contact_from(d("dcat:contactPoint"))
    if cm and (cm.contact_name or cm.contact_email):
        contact_point = DcatContactPoint(name=cm.contact_name, email=cm.contact_email)

    # Publisher: explicit metadata, else a field annotated dct:publisher.
    pub_name = (cm.publisher if cm and cm.publisher else None) or _scalar(
        d("dct:publisher")
    )
    publisher = DcatAgent(name=pub_name) if pub_name else None

    identifier = _scalar(d("dct:identifier")) or fallback_identifier
    title = _first(cm.title if cm else None, _scalar(d("dct:title")))

    return DcatDataset(
        identifier=identifier,
        title=title or fallback_identifier,
        description=_first(
            cm.description if cm else None, _scalar(d("dct:description"))
        ),
        issued=_first(cm.issued if cm else None, _scalar(d("dct:issued"))),
        modified=modified,
        license=_first(cm.license if cm else None, _scalar(d("dct:license"))),
        access_rights=_scalar(d("dct:accessRights")),
        publisher=publisher,
        contact_point=contact_point,
        landing_page=(cm.landing_page if cm else None)
        or _scalar(d("dcat:landingPage")),
        keywords=list(cm.keywords)
        if cm and cm.keywords
        else _as_str_list(d("dcat:keyword")),
        themes=list(cm.themes) if cm and cm.themes else _as_str_list(d("dcat:theme")),
        related=_as_str_list(d("dct:relation")),
        source=_as_str_list(d("dct:source")),
        conforms_to=_as_str_list(d("dct:conformsTo")),
    )


def build_dcat_dataset_from_entities(
    *,
    root_fields: Iterable[FieldSpec] = (),
    root_entity_type: str | None,
    entities: list[dict[str, Any]],
    catalog_metadata: CatalogMetadata | None = None,
    modified: str | None = None,
    identifier: str | None = None,
) -> DcatDataset:
    """Build a DCAT dataset from a dataset's serialized entity list.

    Finds the root entity (the one whose ``_type`` is ``root_entity_type``),
    strips its ``_`` metadata keys, and resolves it via
    :func:`build_dcat_dataset` using ``root_fields``.
    """
    root: dict[str, Any] | None = None
    for entity in entities:
        if entity.get("_type") == root_entity_type:
            root = {k: v for k, v in entity.items() if not k.startswith("_")}
            break
    return build_dcat_dataset(
        root_fields=root_fields,
        root_entity=root,
        catalog_metadata=catalog_metadata,
        modified=modified,
        fallback_identifier=identifier,
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
