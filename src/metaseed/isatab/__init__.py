"""Render an ISA-shaped metaseed dataset as ISA-Tab documents.

ISA-Tab is the tab-delimited serialization of the ISA (Investigation / Study /
Assay) model. A dataset becomes a labeled-section investigation file
(``i_Investigation.txt``) plus one study file (``s_<study>.txt``) and one assay
file (``a_<assay>.txt``) per study and assay.

This writer is pure and dependency-free (stdlib tab-delimited text). It emits
the metadata structure and *references* raw data files by name; it never reads
or writes spectra. It reads the ISA entity types Investigation, Study, Person,
Publication, Factor, Protocol, and Assay using the field codenames of the
``metabolights`` profile; other ISA-shaped profiles (e.g. ``isa``) work only
where their field codenames match.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from metaseed.isatab.reader import (
    read_data_files,
    read_metabolites,
    read_rows,
    read_samples,
)

if TYPE_CHECKING:
    from metaseed.api.client import MetaseedClient

__all__ = [
    "assay_filename",
    "read_data_files",
    "read_metabolites",
    "read_rows",
    "read_samples",
    "study_filename",
    "to_isatab",
]

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
        # Consumers locate the study table through this field; without it the
        # emitted s_*.txt files are orphans and the archive is incomplete.
        _line("Study File Name", [study_filename(study)]),
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


def _sample_qualifiers(sample: dict[str, Any]) -> list[tuple[str, str, str, str]]:
    """The sample's ISA-Tab qualified columns as ``(kind, category, value, accession)``.

    Promotes the dedicated ``organism`` / ``organism_part`` fields (which the
    MetaboLights importer recovers from ``Characteristics[Organism]`` /
    ``Characteristics[Organism part]``) back to those standard columns, then
    appends generic ``characteristics`` and ``factor_values`` list entries. This
    is the inverse of :func:`metaseed.isatab.reader.read_samples`, so authored
    sample content -- including the required organism -- survives export.
    """
    quals: list[tuple[str, str, str, str]] = []
    organism = sample.get("organism")
    if organism:
        term = sample.get("organism_term")
        accession = term.get("term_accession", "") if isinstance(term, dict) else ""
        quals.append(("Characteristics", "Organism", str(organism), str(accession)))
    organism_part = sample.get("organism_part")
    if organism_part:
        quals.append(("Characteristics", "Organism part", str(organism_part), ""))
    for kind, key in (
        ("Characteristics", "characteristics"),
        ("Factor Value", "factor_values"),
    ):
        for item in sample.get(key) or []:
            quals.append(
                (
                    kind,
                    str(item.get("category", "")),
                    str(item.get("value", "")),
                    str(item.get("term_accession", "")),
                )
            )
    return quals


def _study_file(samples: list[dict[str, Any]]) -> str:
    """Build a study (``s_*.txt``) file: header row plus one row per Sample.

    Beyond Source/Sample Name, each sample's characteristics and factor values
    become ``Characteristics[...]`` / ``Factor Value[...]`` columns (with a
    trailing ``Term Source REF`` + ``Term Accession Number`` pair when any sample
    supplies an accession). Columns are the union across samples in first-seen
    order so rows stay aligned.
    """
    columns: list[tuple[str, str]] = []  # (kind, category), first-seen order
    has_accession: dict[tuple[str, str], bool] = {}
    per_sample: list[dict[tuple[str, str], tuple[str, str]]] = []
    for sample in samples:
        mapping: dict[tuple[str, str], tuple[str, str]] = {}
        for kind, category, value, accession in _sample_qualifiers(sample):
            col = (kind, category)
            if col not in has_accession:
                columns.append(col)
                has_accession[col] = False
            if accession:
                has_accession[col] = True
            mapping[col] = (value, accession)
        per_sample.append(mapping)

    header = ["Source Name", "Sample Name"]
    for kind, category in columns:
        header.append(f"{kind}[{category}]")
        if has_accession[(kind, category)]:
            header += ["Term Source REF", "Term Accession Number"]

    rows = [TAB.join(header)]
    for sample, mapping in zip(samples, per_sample, strict=True):
        name = sample.get("name") or ""
        cells = [str(name), str(name)]
        for col in columns:
            value, accession = mapping.get(col, ("", ""))
            cells.append(value)
            if has_accession[col]:
                cells += ["", accession]
        rows.append(TAB.join(cells))
    return "\n".join(rows) + "\n"


def _assay_file(assay: dict[str, Any], data_files: list[dict[str, Any]]) -> str:
    """Build an assay (``a_*.txt``) file: a header row plus one row per DataFile.

    Each DataFile row links the assay's sample (positionally, falling back to the
    first) to the data file name, so the material→data linkage round-trips with
    :func:`metaseed.isatab.reader.read_data_files`. The header carries a
    ``Metabolite Assignment File`` column when the assay declares a MAF.

    Args:
        assay: An Assay entity dict.
        data_files: The assay's DataFile entity dicts.

    Returns:
        Tab-delimited text: header plus one row per data file.
    """
    maf = assay.get("metabolite_assignment_file")
    header = ["Sample Name", "Assay Name", "Raw Data File"]
    if maf:
        header.append("Metabolite Assignment File")

    sample_names = [str(s) for s in assay.get("samples") or []]
    assay_name = str(assay.get("filename") or assay.get("identifier") or "")
    rows = [TAB.join(header)]
    for index, data_file in enumerate(data_files):
        sample = ""
        if sample_names:
            sample = (
                sample_names[index] if index < len(sample_names) else sample_names[0]
            )
        cells = [sample, assay_name, str(data_file.get("filename") or "")]
        if maf:
            cells.append(str(maf))
        rows.append(TAB.join(cells))
    return "\n".join(rows) + "\n"


def _direct_parent_map(client: MetaseedClient) -> dict[str, str]:
    """Map each node id to its direct parent node id, from the dataset tree."""
    parent: dict[str, str] = {}

    def descend(node: Any) -> None:
        for child in node.children:
            parent[child.id] = node.id
            descend(child)

    for root in client.get_tree():
        descend(root)
    return parent


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
    data_files = by_type.get("DataFile", [])

    # Each entity's owning study (None = directly under the Investigation), so a
    # multi-study investigation routes factors/protocols/assays/samples and
    # study- vs investigation-level people/publications to the right place
    # instead of duplicating every child into every study.
    owner = _parent_study_map(client)

    def of(items: list[dict[str, Any]], study_id: str | None) -> list[dict[str, Any]]:
        return [e for e in items if owner.get(str(e.get("_node_id"))) == study_id]

    lines = _ontology_source_section()
    investigation = investigations[0] if investigations else {}
    lines += _investigation_section(investigation)
    lines += _publication_section(
        "INVESTIGATION PUBLICATIONS", "Investigation", of(publications, None)
    )
    lines += _contacts_section(
        "INVESTIGATION CONTACTS", "Investigation", of(people, None)
    )

    for study in studies:
        sid = study.get("_node_id")
        lines += _study_sections(
            study,
            of(factors, sid),
            of(assays, sid),
            of(protocols, sid),
            of(publications, sid),
            of(people, sid),
        )

    documents: dict[str, str] = {"i_Investigation.txt": "\n".join(lines) + "\n"}
    for study in studies:
        documents[study_filename(study)] = _study_file(
            of(samples, study.get("_node_id"))
        )
    direct_parent = _direct_parent_map(client)
    for assay in assays:
        assay_id = str(assay.get("_node_id"))
        assay_data_files = [
            df
            for df in data_files
            if direct_parent.get(str(df.get("_node_id"))) == assay_id
        ]
        documents[assay_filename(assay)] = _assay_file(assay, assay_data_files)
    return documents


def _parent_study_map(client: MetaseedClient) -> dict[str, str | None]:
    """Map each entity's node id to the node id of the Study that owns it.

    Entities directly under the Investigation (e.g. investigation-level people
    or publications) map to ``None``. Built from the dataset tree, since the flat
    serialization does not carry parent links.
    """
    owner: dict[str, str | None] = {}

    def descend(node: Any, study_id: str | None) -> None:
        for child in node.children:
            owner[child.id] = study_id
            next_study = child.id if child.entity_type == "Study" else study_id
            descend(child, next_study)

    for root in client.get_tree():
        descend(root, None)
    return owner
