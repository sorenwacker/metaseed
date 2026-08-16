"""Controlled-vocabulary (ontology term) compliance checks for exports.

Repository submissions (PRIDE PX, MetaboLights) carry ontology-term accessions —
PSI-MS instrument/modification terms, UBERON tissue terms, NCBITaxon organisms,
ChEBI metabolite identifiers. This module resolves those accessions against OLS4
(via whichever :class:`~metaseed.services.term_check.TermSource` is configured,
OLS4 by default) and reports the ones
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

    from metaseed.services.term_check import TermSource


def validate_cv_terms(
    terms: Iterable[tuple[str, str | None]],
    *,
    service: TermSource | None = None,
) -> list[ValidationError]:
    """Resolve ontology-term accessions and report the ones that do not exist.

    Args:
        terms: ``(field_path, accession)`` pairs. Empty accessions are skipped,
            as are values that are not accession-shaped (the ontology service
            skips anything without ``:`` or ``_``, e.g. free text).
        service: Ontology service to resolve against. Defaults to the
            context-scoped :func:`~metaseed.services.terms.get_term_source`,
            which holds whichever adapters are configured.
            Inject a stub in tests to avoid a live OLS4 call.

    Returns:
        One ``ValidationError`` (rule ``cv_compliance``) per accession that the
        service reports as absent. A transient OLS4 outage is treated as valid
        (the service fails open), so an outage does not flag every term.
    """
    from metaseed.services.term_check import check_term

    # `service` is passed through as given, None included: check_term resolves
    # it inside a guard that turns a source which cannot be built into
    # NOT_CHECKED. Resolving it here reinstated the crash that guard exists to
    # prevent, out of a function declared to return a list of errors.
    errors: list[ValidationError] = []
    for field_path, accession in terms:
        if not accession:
            continue
        verdict = check_term(str(accession), None, service)
        message = verdict.message
        if verdict.is_problem:
            errors.append(
                ValidationError(
                    field=field_path,
                    message=message or f"CV term '{accession}' did not resolve",
                    rule="cv_compliance",
                )
            )
    return errors
