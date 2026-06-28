"""Map PRIDE Archive metadata into a ``pride``-profile dataset.

Pure and network-free: it takes an already-fetched PRIDE project record and its
file list (as returned by the PRIDE Archive ``v2`` web service) and builds a
:class:`~metaseed.api.client.MetaseedClient` bound to the ``pride`` profile.

The ``pride`` profile is composed, not flat: a single root ``Dataset`` carries
its ``Species``, ``Instrument``, ``Modification``, ``Contact``, ``Publication``,
``Sample``, and ``DataFile`` records as nested lists. Data files (RAW/mzML/peak
lists) are *referenced* by name and metadata, never downloaded. The Dataset is
created with ``skip_validation`` so a project that omits a field does not abort
the import; call :meth:`MetaseedClient.validate` to report gaps.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from metaseed.api.client import MetaseedClient


def _clean(data: dict[str, Any]) -> dict[str, Any]:
    """Drop empty values so missing PRIDE fields are absent, not blank."""
    return {k: v for k, v in data.items() if v not in (None, "", [], {})}


def _clean_all(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Clean every dict and drop any that become empty."""
    cleaned = [_clean(r) for r in rows]
    return [r for r in cleaned if r]


def _taxon_id(accession: Any) -> str | None:
    """Extract the numeric tax id from a CV accession (e.g. ``NEWT:554``)."""
    if not isinstance(accession, str) or ":" not in accession:
        return accession if isinstance(accession, str) and accession else None
    tail = accession.rsplit(":", 1)[-1]
    return tail or None


def _species(project: dict[str, Any]) -> list[dict[str, Any]]:
    """Map PRIDE ``organisms`` CV params into ``Species`` records."""
    rows = []
    for org in project.get("organisms") or []:
        rows.append(
            {
                "name": org.get("name"),
                "ncbi_taxonomy_id": _taxon_id(org.get("accession")),
            }
        )
    return _clean_all(rows)


def _samples(project: dict[str, Any]) -> list[dict[str, Any]]:
    """Synthesize ``Sample`` records from project-level organism metadata.

    The PRIDE project endpoint does not expose individual biological samples,
    so one ``Sample`` is derived per organism, enriched with the project's first
    organism part and disease when present.
    """
    parts = project.get("organismParts") or []
    diseases = project.get("diseases") or []
    tissue = parts[0].get("name") if parts else None
    disease = diseases[0].get("name") if diseases else None

    rows = []
    for org in project.get("organisms") or []:
        name = org.get("name")
        rows.append(
            {
                "name": name,
                "species": name,
                "ncbi_taxonomy_id": _taxon_id(org.get("accession")),
                "tissue": tissue,
                "disease": disease,
            }
        )
    return _clean_all(rows)


def _instruments(project: dict[str, Any]) -> list[dict[str, Any]]:
    """Map PRIDE ``instruments`` CV params into ``Instrument`` records."""
    rows = []
    for inst in project.get("instruments") or []:
        name = inst.get("name")
        rows.append(
            {
                "name": name,
                "cv_accession": inst.get("accession"),
                "cv_name": name,
            }
        )
    return _clean_all(rows)


def _modifications(project: dict[str, Any]) -> list[dict[str, Any]]:
    """Map PRIDE ``identifiedPTMStrings`` CV params into ``Modification``."""
    rows = []
    for mod in project.get("identifiedPTMStrings") or []:
        rows.append(
            {
                "name": mod.get("name"),
                "cv_accession": mod.get("accession"),
            }
        )
    return _clean_all(rows)


def _person_name(person: dict[str, Any]) -> str | None:
    """Build a display name from a PRIDE contact record."""
    name = person.get("name")
    if name:
        return str(name)
    parts = [person.get("firstName"), person.get("lastName")]
    joined = " ".join(p for p in parts if p)
    return joined or None


def _contacts(project: dict[str, Any]) -> list[dict[str, Any]]:
    """Map PRIDE ``submitters`` and ``labPIs`` into ``Contact`` records."""
    rows = []
    for sub in project.get("submitters") or []:
        rows.append(_contact(sub, "submitter"))
    for pi in project.get("labPIs") or []:
        rows.append(_contact(pi, "lab head"))
    return _clean_all(rows)


def _contact(person: dict[str, Any], role: str) -> dict[str, Any]:
    """Map a single PRIDE person record into a ``Contact`` row."""
    return {
        "name": _person_name(person),
        "email": person.get("email"),
        "affiliation": person.get("affiliation"),
        "orcid": person.get("orcid"),
        "role": role,
    }


def _publications(project: dict[str, Any]) -> list[dict[str, Any]]:
    """Map PRIDE ``references`` into ``Publication`` records."""
    rows = []
    for ref in project.get("references") or []:
        pubmed = ref.get("pubmedID")
        rows.append(
            {
                "doi": ref.get("doi"),
                "pubmed_id": str(pubmed) if pubmed is not None else None,
                "reference": ref.get("referenceLine"),
            }
        )
    return _clean_all(rows)


def _file_type(file: dict[str, Any]) -> str | None:
    """Resolve a PRIDE file category to a ``pride`` ``file_type`` value."""
    category = file.get("fileCategory") or {}
    value = category.get("value")
    return str(value) if value else None


def _file_format(filename: Any) -> str | None:
    """Derive a file format from a filename suffix (``.mzML`` -> ``mzML``)."""
    if not isinstance(filename, str) or "." not in filename:
        return None
    stem = filename.removesuffix(".gz")
    suffix = stem.rsplit(".", 1)[-1]
    return suffix or None


def _files(files: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Map PRIDE file records into referenced ``DataFile`` entries."""
    rows = []
    for file in files:
        filename = file.get("fileName")
        rows.append(
            {
                "filename": filename,
                "file_type": _file_type(file),
                "file_format": _file_format(filename),
                "checksum": file.get("checksum"),
                "file_size": file.get("fileSizeBytes"),
            }
        )
    return _clean_all(rows)


def build_dataset(
    project: dict[str, Any],
    files: list[dict[str, Any]],
    *,
    version: str = "1.0",
) -> MetaseedClient:
    """Build a ``pride``-profile dataset from PRIDE project metadata.

    Args:
        project: PRIDE Archive project record (``/projects/{accession}``).
        files: PRIDE Archive file records (``/projects/{accession}/files``).
        version: ``pride`` profile version.

    Returns:
        A MetaseedClient holding the single Dataset with its nested Species,
        Instruments, Modifications, Contacts, Publications, Samples, and
        referenced DataFiles. Empty if ``project`` is empty.
    """
    from metaseed import MetaseedClient

    client = MetaseedClient("pride", version)
    if not project:
        return client

    accession = project.get("accession")
    data = _clean(
        {
            "identifier": accession,
            "accession": accession,
            "title": project.get("title"),
            "description": project.get("projectDescription"),
            "sample_processing_protocol": project.get("sampleProcessingProtocol"),
            "data_processing_protocol": project.get("dataProcessingProtocol"),
            "submission_type": project.get("submissionType"),
            "announcement_date": project.get("publicationDate"),
            "keywords": list(project.get("keywords") or []),
            "species": _species(project),
            "instruments": _instruments(project),
            "modifications": _modifications(project),
            "contacts": _contacts(project),
            "publications": _publications(project),
            "samples": _samples(project),
            "files": _files(files),
        }
    )
    client.create_entity("Dataset", data, skip_validation=True)
    return client
