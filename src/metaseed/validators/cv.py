"""Controlled-vocabulary (ontology term) compliance checks for exports.

Repository submissions (PRIDE PX, MetaboLights) carry ontology-term accessions —
PSI-MS instrument/modification terms, UBERON tissue terms, NCBITaxon organisms,
ChEBI metabolite identifiers. This module resolves those accessions against OLS4
(via :class:`~metaseed.services.ontology.OntologyService`) and reports the ones
that do not exist, so a submission can be checked for CV compliance before it is
sent.

The resolution is shared here; each adapter collects its own CV-bearing fields
(see ``metaseed.pride.validate_cv`` / ``metaseed.metabolights.validate_cv``).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from metaseed.validators.base import ValidationError

if TYPE_CHECKING:
    from collections.abc import Iterable

    from metaseed.services.ontology import OntologyService


def validate_cv_terms(
    terms: Iterable[tuple[str, str | None]],
    *,
    service: OntologyService | None = None,
) -> list[ValidationError]:
    """Resolve ontology-term accessions and report the ones that do not exist.

    Args:
        terms: ``(field_path, accession)`` pairs. Empty accessions are skipped,
            as are values that are not accession-shaped (the ontology service
            skips anything without ``:`` or ``_``, e.g. free text).
        service: Ontology service to resolve against. Defaults to the
            context-scoped :func:`~metaseed.services.ontology.get_ontology_service`.
            Inject a stub in tests to avoid a live OLS4 call.

    Returns:
        One ``ValidationError`` (rule ``cv_compliance``) per accession that the
        service reports as absent. A transient OLS4 outage is treated as valid
        (the service fails open), so an outage does not flag every term.
    """
    if service is None:
        from metaseed.services.ontology import get_ontology_service

        service = get_ontology_service()

    errors: list[ValidationError] = []
    for field_path, accession in terms:
        if not accession:
            continue
        is_valid, message = service.validate_term_sync(str(accession))
        if not is_valid:
            errors.append(
                ValidationError(
                    field=field_path,
                    message=message or f"CV term '{accession}' did not resolve",
                    rule="cv_compliance",
                )
            )
    return errors
