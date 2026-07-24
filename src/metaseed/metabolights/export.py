"""Export a ``metabolights`` dataset to the MetaboLights submission format.

MetaboLights archives are ISA-Tab plus one MetaboLights-specific file per
assay: the Metabolite Assignment File (MAF, ``m_*.tsv``). This module reuses the
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
        :func:`metaseed.isatab.to_isatab` plus one ``m_*.tsv`` MAF per Assay,
        with the standard header followed by one row per identified metabolite
        (an assay with no metabolites yields a header-only MAF).
    """
    documents = dict(to_isatab(client))
    assays = [e for e in client.serialize()["entities"] if e["_type"] == "Assay"]
    # Metabolites may be embedded on the assay (authored datasets) or attached as
    # child nodes (imported from a MAF, #146); fall back to the children so the
    # round trip re-emits a populated MAF either way.
    children = _metabolite_children_by_assay(client)
    for assay in assays:
        metabolites = assay.get("metabolites") or children.get(
            str(assay.get("_node_id")), []
        )
        documents[_maf_filename(assay)] = _maf_content(
            {**assay, "metabolites": metabolites}
        )
    return documents


def _metabolite_children_by_assay(client: MetaseedClient) -> dict[str, list[Any]]:
    """Map each Assay node id to its child Metabolite entity dicts."""
    parent: dict[str, str] = {}

    def descend(node: Any) -> None:
        for child in node.children:
            parent[child.id] = node.id
            descend(child)

    for root in client.get_tree():
        descend(root)

    result: dict[str, list[Any]] = {}
    for entity in client.serialize()["entities"]:
        if entity["_type"] != "Metabolite":
            continue
        assay_id = parent.get(str(entity.get("_node_id")))
        if assay_id:
            result.setdefault(assay_id, []).append(entity)
    return result


def _maf_row(metabolite: dict[str, Any]) -> str:
    """Render one MAF data row for a metabolite.

    The MAF column names match the ``Metabolite`` entity field names, so each
    column is a direct lookup; columns the profile does not model (e.g.
    ``fragmentation``, ``taxid``, ``search_engine``) render empty.
    """
    values = []
    for column in _MAF_HEADER:
        value = metabolite.get(column)
        values.append("" if value is None else str(value))
    return "\t".join(values)


def _maf_content(assay: dict[str, Any]) -> str:
    """Render an assay's MAF: the header row plus one row per metabolite."""
    lines = ["\t".join(_MAF_HEADER)]
    for metabolite in assay.get("metabolites") or []:
        lines.append(_maf_row(metabolite))
    return "\n".join(lines) + "\n"
