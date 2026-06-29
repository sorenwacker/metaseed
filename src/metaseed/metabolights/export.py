"""Export a ``metabolights`` dataset to the MetaboLights submission format.

MetaboLights archives are ISA-Tab plus one MetaboLights-specific file per
assay: the Metabolite Assignment File (MAF, ``m_*.txt``). This module reuses the
shared :func:`metaseed.isatab.to_isatab` writer for the ISA-Tab documents and
adds a MAF skeleton (the standard column header) for each assay. Pure and
dependency-free; it references files, never reads or writes spectra.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from metaseed.isatab import to_isatab

if TYPE_CHECKING:
    from metaseed.api.client import MetaseedClient

# Standard MetaboLights Metabolite Assignment File (MAF) column header.
_MAF_HEADER: tuple[str, ...] = (
    "database_identifier",
    "chemical_formula",
    "smiles",
    "inchi",
    "metabolite_identification",
    "mass_to_charge",
    "fragmentation",
    "modifications",
    "charge",
    "retention_time",
    "taxid",
    "species",
    "database",
    "database_version",
    "reliability",
    "uri",
    "search_engine",
    "search_engine_score",
)


def _maf_filename(assay: dict[str, Any]) -> str:
    """Return the MAF file name for an assay (declared, or derived)."""
    declared = assay.get("metabolite_assignment_file")
    if declared:
        return str(declared)
    ident = assay.get("identifier") or assay.get("filename") or "assay"
    slug = "".join(c if c.isalnum() or c in "-_." else "_" for c in str(ident))
    return f"m_{slug}_v2_maf.tsv"


def to_metabolights(client: MetaseedClient) -> dict[str, str]:
    """Render a ``metabolights`` dataset as ISA-Tab plus a MAF per assay.

    Args:
        client: A MetaseedClient bound to the ``metabolights`` profile.

    Returns:
        Mapping of document name to text — the ISA-Tab files from
        :func:`metaseed.isatab.to_isatab` plus one ``m_*.txt`` MAF (column
        header only) per Assay.
    """
    documents = dict(to_isatab(client))
    assays = [e for e in client.serialize()["entities"] if e["_type"] == "Assay"]
    for assay in assays:
        documents[_maf_filename(assay)] = "\t".join(_MAF_HEADER) + "\n"
    return documents
