"""Validation for a ``pride`` dataset — CV terms and PX submission structure.

``validate_cv`` resolves the dataset's controlled-vocabulary accessions against
OLS4. ``validate_submission`` checks the generated ``submission.px`` against the
ProteomeXchange submission-file rules (mandatory ``MTD`` fields, a valid
``submission_type``, ``reason_for_partial`` for PARTIAL, and a well-formed file
mapping) — the ProteomeXchange validator's rules, applied without the Java tool.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from metaseed.validators.base import ValidationError
from metaseed.validators.cv import validate_cv_terms

if TYPE_CHECKING:
    from metaseed.api.client import MetaseedClient
    from metaseed.services.ontology import OntologyService


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


# --- PX submission structure ------------------------------------------------

# MTD fields the PX submission file requires exactly once.
_REQUIRED_SINGLE = (
    "submitter_name",
    "submitter_email",
    "submitter_affiliation",
    "submitter_pride_login",
    "lab_head_name",
    "lab_head_email",
    "lab_head_affiliation",
    "project_title",
    "project_description",
    "keywords",
    "submission_type",
)
# MTD fields the PX submission file requires at least once (1..N).
_REQUIRED_MULTI = ("experiment_type", "species", "tissue", "instrument")
_SUBMISSION_TYPES = ("COMPLETE", "PARTIAL")
_VALID_FILE_TYPES = frozenset(
    {
        "RAW",
        "PEAK",
        "RESULT",
        "SEARCH",
        "QUANT",
        "GEL",
        "FASTA",
        "SPECTRUM_LIBRARY",
        "MS_IMAGE_DATA",
        "OTHER",
    }
)


def _parse_submission(text: str) -> tuple[dict[str, list[str]], list[list[str]]]:
    """Split a submission.px into its MTD map and its FME file rows."""
    mtd: dict[str, list[str]] = {}
    files: list[list[str]] = []
    for line in text.splitlines():
        if line.startswith("MTD\t"):
            parts = line.split("\t", 2)
            if len(parts) == 3:
                mtd.setdefault(parts[1], []).append(parts[2])
        elif line.startswith("FME\t"):
            files.append(line.split("\t"))
    return mtd, files


def _err(message: str, field: str = "submission.px") -> ValidationError:
    return ValidationError(field=field, message=message, rule="px_structure")


def validate_submission(client: MetaseedClient) -> list[ValidationError]:
    """Check a ``pride`` dataset's ``submission.px`` for PX structural compliance.

    Applies the ProteomeXchange submission-file rules to the document produced by
    :func:`metaseed.pride.to_pride_submission`: mandatory ``MTD`` fields present,
    ``submission_type`` one of COMPLETE/PARTIAL, ``reason_for_partial`` present
    for PARTIAL, and a well-formed file mapping (at least one RAW file, valid file
    types, and — per submission type — a RESULT (COMPLETE) or SEARCH (PARTIAL)
    file). This does not invoke the official Java ``px-submission-tool``; it
    encodes the same rules.

    Args:
        client: A MetaseedClient bound to the ``pride`` profile.

    Returns:
        One ``ValidationError`` (rule ``px_structure``) per rule the generated
        submission violates; empty when it is structurally compliant.
    """
    from metaseed.pride.export import to_pride_submission

    text = to_pride_submission(client).get("submission.px")
    if not text:
        return [_err("no submission.px generated (dataset has no Dataset entity)")]

    mtd, files = _parse_submission(text)
    errors: list[ValidationError] = []

    for key in _REQUIRED_SINGLE:
        if not mtd.get(key):
            errors.append(_err(f"missing required metadata field '{key}'", key))
    for key in _REQUIRED_MULTI:
        if not mtd.get(key):
            errors.append(
                _err(f"missing required metadata field '{key}' (at least one)", key)
            )

    submission_type = (mtd.get("submission_type") or [""])[0]
    if submission_type and submission_type not in _SUBMISSION_TYPES:
        errors.append(
            _err(
                f"submission_type must be one of {', '.join(_SUBMISSION_TYPES)}, "
                f"got '{submission_type}'",
                "submission_type",
            )
        )
    if submission_type == "PARTIAL" and not mtd.get("reason_for_partial"):
        errors.append(
            _err("PARTIAL submissions require 'reason_for_partial'", "reason_for_partial")
        )

    # File mapping: FME columns are file_id, file_type, file_path.
    file_types = [row[2] for row in files if len(row) >= 3]
    if files:
        for row in files:
            ftype = row[2] if len(row) >= 3 else ""
            if ftype not in _VALID_FILE_TYPES:
                errors.append(_err(f"invalid file_type '{ftype}' in file mapping"))
        if "RAW" not in file_types:
            errors.append(_err("file mapping must include at least one RAW file"))
        if submission_type == "COMPLETE" and "RESULT" not in file_types:
            errors.append(_err("COMPLETE submissions require at least one RESULT file"))
        if submission_type == "PARTIAL" and "SEARCH" not in file_types:
            errors.append(_err("PARTIAL submissions require at least one SEARCH file"))

    return errors
