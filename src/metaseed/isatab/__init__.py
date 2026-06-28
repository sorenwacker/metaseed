"""Render an ISA-shaped metaseed dataset as ISA-Tab documents.

ISA-Tab is the tab-delimited serialization of the ISA (Investigation / Study /
Assay) model. A dataset becomes a labeled-section investigation file
(``i_Investigation.txt``) plus one study file (``s_<study>.txt``) and one assay
file (``a_<assay>.txt``) per study and assay.

This writer is pure and dependency-free (stdlib tab-delimited text). It emits
the metadata structure and *references* raw data files by name; it never reads
or writes spectra. It works for any ISA-shaped profile (e.g. ``isa`` or
``metabolights``) whose serialized entities use the ISA entity types
Investigation, Study, Person, Publication, Factor, Protocol, and Assay.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from metaseed.api.client import MetaseedClient

__all__ = ["assay_filename", "study_filename", "to_isatab"]

TAB = "\t"


def _flatten(value: Any) -> str:
    """Render a scalar or list field as a single tab-safe cell value."""
    if isinstance(value, list):
        return "; ".join(str(v) for v in value if v not in (None, ""))
    return str(value)


def _line(label: str, values: list[Any]) -> str:
    """Build one ``Label<TAB>value...`` row, dropping trailing empty cells.

    Args:
        label: The row label (the ISA-Tab field name).
        values: One cell per entity; empty values become blank cells so that
            columns stay aligned across rows of the same section.

    Returns:
        A single tab-delimited line.
    """
    cells = [label] + ["" if v in (None, "") else _flatten(v) for v in values]
    while len(cells) > 1 and cells[-1] == "":
        cells.pop()
    return TAB.join(cells)


def _slug(value: str) -> str:
    """Reduce a label to a filename-safe token."""
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in value)


def study_filename(study: dict[str, Any]) -> str:
    """Return the ISA-Tab study-file name for a Study entity."""
    name = study.get("identifier") or study.get("title") or "study"
    return f"s_{_slug(str(name))}.txt"


def assay_filename(assay: dict[str, Any]) -> str:
    """Return the ISA-Tab assay-file name for an Assay entity."""
    name = assay.get("filename")
    if name:
        return name if str(name).startswith("a_") else f"a_{name}"
    ident = assay.get("identifier") or "assay"
    return f"a_{_slug(str(ident))}.txt"


def _ontology_source_section() -> list[str]:
    """Emit the ONTOLOGY SOURCE REFERENCE section (declared but unpopulated)."""
    return [
        "ONTOLOGY SOURCE REFERENCE",
        _line("Term Source Name", []),
        _line("Term Source File", []),
        _line("Term Source Version", []),
        _line("Term Source Description", []),
    ]


def _publication_section(
    header: str, prefix: str, pubs: list[dict[str, Any]]
) -> list[str]:
    """Emit a publications section, one column per Publication entity."""
    return [
        header,
        _line(f"{prefix} PubMed ID", [p.get("pubmed_id") for p in pubs]),
        _line(f"{prefix} Publication DOI", [p.get("doi") for p in pubs]),
        _line(f"{prefix} Publication Author List", [p.get("authors") for p in pubs]),
        _line(f"{prefix} Publication Title", [p.get("title") for p in pubs]),
        _line(f"{prefix} Publication Status", [p.get("status") for p in pubs]),
    ]


def _contacts_section(
    header: str, prefix: str, people: list[dict[str, Any]]
) -> list[str]:
    """Emit a contacts section, one column per Person entity."""
    return [
        header,
        _line(f"{prefix} Person Last Name", [p.get("last_name") for p in people]),
        _line(f"{prefix} Person First Name", [p.get("first_name") for p in people]),
        _line(f"{prefix} Person Email", [p.get("email") for p in people]),
        _line(f"{prefix} Person Affiliation", [p.get("affiliation") for p in people]),
        _line(f"{prefix} Person Roles", [p.get("roles") for p in people]),
    ]


def _investigation_section(investigation: dict[str, Any]) -> list[str]:
    """Emit the INVESTIGATION section for the root Investigation entity."""
    return [
        "INVESTIGATION",
        _line("Investigation Identifier", [investigation.get("identifier")]),
        _line("Investigation Title", [investigation.get("title")]),
        _line("Investigation Description", [investigation.get("description")]),
        _line("Investigation Submission Date", [investigation.get("submission_date")]),
        _line(
            "Investigation Public Release Date",
            [investigation.get("public_release_date")],
        ),
    ]


def _study_sections(
    study: dict[str, Any],
    factors: list[dict[str, Any]],
    assays: list[dict[str, Any]],
    protocols: list[dict[str, Any]],
    publications: list[dict[str, Any]],
    people: list[dict[str, Any]],
) -> list[str]:
    """Emit the per-study labeled sections of the investigation file."""
    lines = [
        "STUDY",
        _line("Study Identifier", [study.get("identifier")]),
        _line("Study Title", [study.get("title")]),
        _line("Study Description", [study.get("description")]),
        "STUDY DESIGN DESCRIPTORS",
        _line("Study Design Type", study.get("study_design_descriptors") or []),
    ]
    lines += _publication_section("STUDY PUBLICATIONS", "Study", publications)
    lines += [
        "STUDY FACTORS",
        _line("Study Factor Name", [f.get("name") for f in factors]),
        _line("Study Factor Type", [f.get("factor_type") for f in factors]),
        "STUDY ASSAYS",
        _line(
            "Study Assay Measurement Type",
            [a.get("measurement_type") for a in assays],
        ),
        _line(
            "Study Assay Technology Type",
            [a.get("technology_type") for a in assays],
        ),
        _line(
            "Study Assay Technology Platform",
            [a.get("technology_platform") for a in assays],
        ),
        _line("Study Assay File Name", [assay_filename(a) for a in assays]),
        "STUDY PROTOCOLS",
        _line("Study Protocol Name", [p.get("name") for p in protocols]),
        _line("Study Protocol Type", [p.get("protocol_type") for p in protocols]),
        _line("Study Protocol Description", [p.get("description") for p in protocols]),
    ]
    lines += _contacts_section("STUDY CONTACTS", "Study", people)
    return lines


def _study_file(samples: list[dict[str, Any]]) -> str:
    """Build a study (``s_*.txt``) file: header row plus one row per Sample."""
    rows = ["Source Name" + TAB + "Sample Name"]
    for sample in samples:
        name = sample.get("name") or ""
        rows.append(f"{name}{TAB}{name}")
    return "\n".join(rows) + "\n"


def _assay_file(assay: dict[str, Any]) -> str:
    """Build an assay (``a_*.txt``) file as a header row.

    The header carries a ``Metabolite Assignment File`` column referencing the
    assay's MAF when the entity declares one (MetaboLights), keeping the assay
    file self-describing without making this writer profile-specific.

    Args:
        assay: An Assay entity dict.

    Returns:
        A single tab-delimited header row terminated by a newline.
    """
    header = ["Sample Name", "Assay Name", "Raw Data File"]
    if assay.get("metabolite_assignment_file"):
        header.append("Metabolite Assignment File")
    return TAB.join(header) + "\n"


def to_isatab(client: MetaseedClient) -> dict[str, str]:
    """Render an ISA-shaped dataset as ISA-Tab documents.

    Args:
        client: A MetaseedClient bound to an ISA-shaped profile (e.g. ``isa``
            or ``metabolights``).

    Returns:
        Mapping of document name to tab-delimited text: always an
        ``i_Investigation.txt``, plus one ``s_<study>.txt`` per Study and one
        ``a_<assay>.txt`` per Assay.
    """
    entities = client.serialize()["entities"]
    by_type: dict[str, list[dict[str, Any]]] = {}
    for entity in entities:
        by_type.setdefault(entity["_type"], []).append(entity)

    investigations = by_type.get("Investigation", [])
    studies = by_type.get("Study", [])
    people = by_type.get("Person", [])
    publications = by_type.get("Publication", [])
    factors = by_type.get("Factor", [])
    protocols = by_type.get("Protocol", [])
    assays = by_type.get("Assay", [])
    samples = by_type.get("Sample", [])

    lines = _ontology_source_section()
    investigation = investigations[0] if investigations else {}
    lines += _investigation_section(investigation)
    lines += _publication_section("INVESTIGATION PUBLICATIONS", "Investigation", [])
    lines += _contacts_section("INVESTIGATION CONTACTS", "Investigation", [])

    for study in studies:
        lines += _study_sections(
            study, factors, assays, protocols, publications, people
        )

    documents: dict[str, str] = {"i_Investigation.txt": "\n".join(lines) + "\n"}
    for study in studies:
        documents[study_filename(study)] = _study_file(samples)
    for assay in assays:
        documents[assay_filename(assay)] = _assay_file(assay)
    return documents
