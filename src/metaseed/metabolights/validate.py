"""CV-term compliance for a ``metabolights`` dataset.

Collects the controlled-vocabulary accessions a ``metabolights`` dataset carries
(the sample ``organism_term`` and each identified metabolite's
``database_identifier``, e.g. a ChEBI id) and resolves them against OLS4,
reporting any that do not exist.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from metaseed.validators.cv import validate_cv_terms

if TYPE_CHECKING:
    from metaseed.api.client import MetaseedClient
    from metaseed.services.ontology import OntologyService
    from metaseed.validators.base import ValidationError


def _cv_terms(entities: list[dict[str, Any]]) -> list[tuple[str, str | None]]:
    """Collect ``(field_path, accession)`` pairs from metabolights entities."""
    terms: list[tuple[str, str | None]] = []
    sample_i = 0
    assay_i = 0
    for entity in entities:
        etype = entity.get("_type")
        if etype == "Sample":
            terms.append(
                (f"Sample[{sample_i}].organism_term", entity.get("organism_term"))
            )
            sample_i += 1
        elif etype == "Assay":
            for j, metabolite in enumerate(entity.get("metabolites") or []):
                terms.append(
                    (
                        f"Assay[{assay_i}].metabolites[{j}].database_identifier",
                        metabolite.get("database_identifier"),
                    )
                )
            assay_i += 1
    return terms


def validate_cv(
    client: MetaseedClient,
    *,
    service: OntologyService | None = None,
) -> list[ValidationError]:
    """Report ``metabolights`` CV-term accessions that do not resolve against OLS4.

    Args:
        client: A MetaseedClient bound to the ``metabolights`` profile.
        service: Optional ontology service (injected in tests).

    Returns:
        One ``ValidationError`` per unresolved accession; empty when there are no
        CV terms or all resolve.
    """
    entities = client.serialize()["entities"]
    return validate_cv_terms(_cv_terms(entities), service=service)
