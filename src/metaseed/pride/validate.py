"""CV-term compliance for a ``pride`` dataset.

Collects the controlled-vocabulary accessions a ``pride`` Dataset carries
(instrument, modification, and custom-attribute ``cv_accession`` values, plus the
sample ``tissue_accession``) and resolves them against OLS4, reporting any that
do not exist. This is the CV half of PRIDE submission validation; structural PX
checks live with the exporter.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from metaseed.validators.cv import validate_cv_terms

if TYPE_CHECKING:
    from metaseed.api.client import MetaseedClient
    from metaseed.services.ontology import OntologyService
    from metaseed.validators.base import ValidationError


def _cv_terms(dataset: dict[str, Any]) -> list[tuple[str, str | None]]:
    """Collect ``(field_path, accession)`` pairs from a pride Dataset."""
    terms: list[tuple[str, str | None]] = []
    for i, instrument in enumerate(dataset.get("instruments") or []):
        terms.append((f"instruments[{i}].cv_accession", instrument.get("cv_accession")))
    for i, modification in enumerate(dataset.get("modifications") or []):
        terms.append(
            (f"modifications[{i}].cv_accession", modification.get("cv_accession"))
        )
    for i, sample in enumerate(dataset.get("samples") or []):
        terms.append((f"samples[{i}].tissue_accession", sample.get("tissue_accession")))
        for j, attr in enumerate(sample.get("custom_attributes") or []):
            terms.append(
                (
                    f"samples[{i}].custom_attributes[{j}].cv_accession",
                    attr.get("cv_accession"),
                )
            )
    return terms


def validate_cv(
    client: MetaseedClient,
    *,
    service: OntologyService | None = None,
) -> list[ValidationError]:
    """Report ``pride`` CV-term accessions that do not resolve against OLS4.

    Args:
        client: A MetaseedClient bound to the ``pride`` profile.
        service: Optional ontology service (injected in tests).

    Returns:
        One ``ValidationError`` per unresolved accession; empty when the dataset
        has no CV terms or all resolve.
    """
    entities = client.serialize()["entities"]
    datasets = [e for e in entities if e.get("_type") == "Dataset"]
    if not datasets:
        return []
    return validate_cv_terms(_cv_terms(datasets[0]), service=service)
