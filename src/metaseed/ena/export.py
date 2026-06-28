"""Export an ``ena``-profile dataset to ENA submission XML.

Produces the ENA/SRA submission documents (STUDY_SET, SAMPLE_SET,
EXPERIMENT_SET, RUN_SET) from a metaseed dataset. Pure and dependency-free
(stdlib ``xml.etree``). Data files are *referenced* in ``RUN > DATA_BLOCK >
FILES``; this never uploads anything (submission/auth is out of scope).

This is the round-trip partner of :func:`metaseed.ena.import_accession`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from xml.etree import ElementTree as ET

if TYPE_CHECKING:
    from metaseed.api.client import MetaseedClient


def _text(parent: ET.Element, tag: str, value: Any) -> None:
    """Append ``<tag>value</tag>`` to ``parent`` when ``value`` is non-empty."""
    if value in (None, ""):
        return
    child = ET.SubElement(parent, tag)
    child.text = str(value)


def _serialize(root: ET.Element) -> str:
    ET.indent(root)
    return ET.tostring(root, encoding="unicode")


def _study_set(studies: list[dict[str, Any]]) -> str:
    root = ET.Element("STUDY_SET")
    for s in studies:
        study = ET.SubElement(
            root, "STUDY", _attrs(s, alias="alias", center_name="center_name")
        )
        descriptor = ET.SubElement(study, "DESCRIPTOR")
        _text(descriptor, "STUDY_TITLE", s.get("title"))
        ET.SubElement(
            descriptor,
            "STUDY_TYPE",
            {"existing_study_type": s.get("study_type") or "Other"},
        )
        _text(descriptor, "STUDY_ABSTRACT", s.get("description"))
    return _serialize(root)


def _sample_set(samples: list[dict[str, Any]]) -> str:
    root = ET.Element("SAMPLE_SET")
    for s in samples:
        sample = ET.SubElement(
            root, "SAMPLE", _attrs(s, alias="alias", center_name="center_name")
        )
        _text(sample, "TITLE", s.get("title"))
        name = ET.SubElement(sample, "SAMPLE_NAME")
        _text(name, "TAXON_ID", s.get("taxon_id"))
        _text(name, "SCIENTIFIC_NAME", s.get("scientific_name"))
        _text(name, "COMMON_NAME", s.get("common_name"))
        _text(sample, "DESCRIPTION", s.get("description"))
    return _serialize(root)


def _experiment_set(experiments: list[dict[str, Any]]) -> str:
    root = ET.Element("EXPERIMENT_SET")
    for e in experiments:
        exp = ET.SubElement(
            root, "EXPERIMENT", _attrs(e, alias="alias", center_name="center_name")
        )
        if e.get("study_ref"):
            ET.SubElement(exp, "STUDY_REF", {"refname": e["study_ref"]})
        design = ET.SubElement(exp, "DESIGN")
        _text(design, "DESIGN_DESCRIPTION", e.get("design_description"))
        if e.get("sample_ref"):
            ET.SubElement(design, "SAMPLE_DESCRIPTOR", {"refname": e["sample_ref"]})
        lib = ET.SubElement(design, "LIBRARY_DESCRIPTOR")
        _text(lib, "LIBRARY_NAME", e.get("library_name"))
        _text(lib, "LIBRARY_STRATEGY", e.get("library_strategy"))
        _text(lib, "LIBRARY_SOURCE", e.get("library_source"))
        _text(lib, "LIBRARY_SELECTION", e.get("library_selection"))
        if e.get("library_layout"):
            layout = ET.SubElement(lib, "LIBRARY_LAYOUT")
            ET.SubElement(layout, str(e["library_layout"]).upper())
        if e.get("platform"):
            platform = ET.SubElement(exp, "PLATFORM")
            model = ET.SubElement(platform, str(e["platform"]).upper())
            _text(model, "INSTRUMENT_MODEL", e.get("instrument_model"))
    return _serialize(root)


def _run_set(runs: list[dict[str, Any]], files: list[dict[str, Any]]) -> str:
    files_by_run: dict[str, list[dict[str, Any]]] = {}
    for f in files:
        files_by_run.setdefault(f.get("run_ref", ""), []).append(f)

    root = ET.Element("RUN_SET")
    for r in runs:
        run = ET.SubElement(
            root, "RUN", _attrs(r, alias="alias", center_name="center_name")
        )
        if r.get("experiment_ref"):
            ET.SubElement(run, "EXPERIMENT_REF", {"refname": r["experiment_ref"]})
        run_files = files_by_run.get(r.get("alias", ""), [])
        if run_files:
            block = ET.SubElement(run, "DATA_BLOCK")
            files_el = ET.SubElement(block, "FILES")
            for f in run_files:
                attrs = {
                    "filename": f.get("filename", ""),
                    "filetype": f.get("filetype", ""),
                }
                if f.get("checksum_method"):
                    attrs["checksum_method"] = f["checksum_method"]
                if f.get("checksum"):
                    attrs["checksum"] = f["checksum"]
                ET.SubElement(files_el, "FILE", attrs)
    return _serialize(root)


def _attrs(entity: dict[str, Any], **mapping: str) -> dict[str, str]:
    """Build an XML attribute dict from entity fields, skipping empties."""
    return {
        attr: str(entity[field])
        for attr, field in mapping.items()
        if entity.get(field) not in (None, "")
    }


def to_ena_xml(client: MetaseedClient) -> dict[str, str]:
    """Render an ``ena``-profile dataset as ENA submission XML.

    Args:
        client: A MetaseedClient bound to the ``ena`` profile.

    Returns:
        Mapping of document name to XML text, e.g. ``{"study.xml": ...,
        "sample.xml": ...}``. Only non-empty sets are included.
    """
    entities = client.serialize()["entities"]
    by_type: dict[str, list[dict[str, Any]]] = {}
    for e in entities:
        by_type.setdefault(e["_type"], []).append(e)

    documents: dict[str, str] = {}
    if by_type.get("Study"):
        documents["study.xml"] = _study_set(by_type["Study"])
    if by_type.get("Sample"):
        documents["sample.xml"] = _sample_set(by_type["Sample"])
    if by_type.get("Experiment"):
        documents["experiment.xml"] = _experiment_set(by_type["Experiment"])
    if by_type.get("Run"):
        documents["run.xml"] = _run_set(by_type["Run"], by_type.get("File", []))
    return documents
