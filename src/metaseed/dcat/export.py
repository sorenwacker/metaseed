"""The DCAT card as an adapter export.

A host offering this hands the user the catalogue record for their dataset:
what it is, who published it, under what licence, and what it was derived from —
the description a portal or a FAIR-assessment tool ingests, as opposed to the
domain content the profile describes.

Emits the **dataset**, not a ``dcat:Catalog`` wrapping it. A catalogue serializes
to a JSON-LD ``@graph``, which is the wrong shape for a consumer that asked about
one dataset, and it is the shape that cannot be embedded in a page as-is.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from metaseed.api.client import MetaseedClient
    from metaseed.dcat.model import DcatDataset
    from metaseed.repositories.dataset_repository import CatalogMetadata


def build_card(
    client: MetaseedClient,
    *,
    catalog_metadata: CatalogMetadata | None = None,
    identifier: str | None = None,
) -> DcatDataset | None:
    """Resolve the client's dataset into a DCAT card, or None when it is empty.

    Args:
        client: A client holding the dataset to describe.
        catalog_metadata: Explicit dataset-level metadata, which wins over
            anything derived from the profile's ``dcat`` annotations.
        identifier: Identity for the card when the profile derives none. A
            caller that knows it originated the dataset passes the accession
            here; see ``docs/architecture/dcat.md``.

    Returns:
        The card, or ``None`` when the client holds no entities — there is
        nothing to describe, and an empty card would look like a real one.
    """
    from metaseed.dcat.resolver import build_dcat_dataset_from_entities
    from metaseed.specs.loader import SpecLoader

    facade = client.facade
    entities = facade.to_dict()
    if not entities:
        return None

    spec = SpecLoader(profile=facade.profile).load_profile(
        facade.version, facade.profile
    )
    root_def = spec.entities.get(spec.root_entity)

    return build_dcat_dataset_from_entities(
        root_fields=root_def.fields if root_def else [],
        root_entity_type=spec.root_entity,
        entities=entities,
        catalog_metadata=catalog_metadata,
        identifier=identifier or facade.profile,
    )


def to_dcat(client: MetaseedClient) -> dict[str, str]:
    """Render the client's dataset as a DCAT card in both serializations.

    Args:
        client: A client holding the dataset to describe.

    Returns:
        ``{"dcat.jsonld": ..., "dcat.ttl": ...}``, or an empty mapping when the
        dataset holds no entities, which hosts report as nothing to export.

    Raises:
        ModuleNotFoundError: If the ``metaseed[dcat]`` extra is not installed.
    """
    card = build_card(client)
    if card is None:
        return {}

    from metaseed.dcat.serialize import to_jsonld, to_turtle

    return {"dcat.jsonld": to_jsonld(card), "dcat.ttl": to_turtle(card)}
