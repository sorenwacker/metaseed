"""Export an ``ena``-profile dataset to ENA submission XML.

Produces the ENA/SRA submission documents (STUDY_SET, SAMPLE_SET,
EXPERIMENT_SET, RUN_SET, ANALYSIS_SET and the driving SUBMISSION) from a
metaseed dataset. Pure and dependency-free (stdlib ``xml.etree``). Data files
are *referenced* in ``RUN > DATA_BLOCK > FILES``; this never uploads anything
(transferring files and authenticating to Webin are out of scope).

Every entity the profile defines is exported. The attribute objects
(``SampleAttribute`` and friends) become the ``TAG``/``VALUE``/``UNITS`` of an
attribute under the object that owns them, which is not optional detail: ENA
registers a sample against a *checklist*, and a checklist's mandatory fields are
carried as sample attributes, so a ``SAMPLE_SET`` without them is rejected.

Ownership comes from the entity tree, not from grouping a flat entity list by
type — a flat grouping cannot say which sample an attribute belongs to. See
``docs/architecture/ena-import.md``.

This is the round-trip partner of :func:`metaseed.ena.import_accession`.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any
from xml.etree import ElementTree as ET

if TYPE_CHECKING:
    from metaseed.api.client import MetaseedClient

_XML_DECLARATION = '<?xml version="1.0" encoding="UTF-8"?>'


class _Tree:
    """The dataset's entities indexed by node, so a child knows its parent.

    ``client.serialize()`` returns a flat entity list whose parent links live
    only in the node tree, and the parent's own nested list is emptied by that
    serialization. Both are consulted: the tree first, then the parent's
    embedded list, so a dataset built either way exports the same.
    """

    def __init__(self, client: MetaseedClient) -> None:
        self._client = client
        entities = client.serialize()["entities"]
        self._by_node: dict[str, dict[str, Any]] = {
            str(entity.get("_node_id")): entity for entity in entities
        }
        self._children: dict[str, dict[str, list[str]]] = {}
        self._by_type: dict[str, list[str]] = {}

        def descend(node: Any) -> None:
            node_id = str(node.id)
            self._by_type.setdefault(node.entity_type, []).append(node_id)
            bucket = self._children.setdefault(node_id, {})
            for child in node.children:
                bucket.setdefault(child.entity_type, []).append(str(child.id))
                descend(child)

        for root in client.get_tree():
            descend(root)

    def of_type(self, entity_type: str) -> list[tuple[str, dict[str, Any]]]:
        """Every ``(node id, entity)`` of ``entity_type``, in tree order."""
        return [
            (node_id, self._by_node[node_id])
            for node_id in self._by_type.get(entity_type, [])
            if node_id in self._by_node
        ]

    def children(self, node_id: str, entity_type: str) -> list[dict[str, Any]]:
        """The ``entity_type`` children of ``node_id``."""
        ids = self._children.get(node_id, {}).get(entity_type, [])
        found = [self._by_node[i] for i in ids if i in self._by_node]
        if found:
            return found
        return self._embedded(node_id, entity_type)

    def _embedded(self, node_id: str, entity_type: str) -> list[dict[str, Any]]:
        """Children the parent still carries inline, when it has no child nodes."""
        parent = self._by_node.get(node_id)
        if parent is None:
            return []
        helper = getattr(self._client.facade, str(parent.get("_type")), None)
        nested = getattr(helper, "nested_fields", {}) or {}
        field = next((f for f, t in nested.items() if t == entity_type), None)
        if field is None:
            return []
        return [item for item in (parent.get(field) or []) if isinstance(item, dict)]


def _text(parent: ET.Element, tag: str, value: Any) -> None:
    """Append ``<tag>value</tag>`` to ``parent`` when ``value`` is non-empty."""
    if value in (None, ""):
        return
    child = ET.SubElement(parent, tag)
    child.text = str(value)


def _attributes(
    parent: ET.Element, wrapper: str, item: str, rows: list[dict[str, Any]]
) -> None:
    """Append an ENA attribute block (``<X_ATTRIBUTES><X_ATTRIBUTE>...``).

    A row without a tag is skipped rather than emitted empty: ENA requires a
    TAG, and an attribute that has lost it cannot be what the submitter meant.
    """
    usable = [row for row in rows if row.get("tag") not in (None, "")]
    if not usable:
        return
    block = ET.SubElement(parent, wrapper)
    for row in usable:
        element = ET.SubElement(block, item)
        _text(element, "TAG", row.get("tag"))
        _text(element, "VALUE", row.get("value"))
        _text(element, "UNITS", row.get("units"))


def _serialize(root: ET.Element) -> str:
    ET.indent(root)
    return f"{_XML_DECLARATION}\n{ET.tostring(root, encoding='unicode')}"


def _study_set(studies: list[tuple[str, dict[str, Any]]], tree: _Tree) -> str:
    root = ET.Element("STUDY_SET")
    for node_id, s in studies:
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
        _study_links(study, tree.children(node_id, "ProjectLink"))
    return _serialize(root)


def _study_links(study: ET.Element, links: list[dict[str, Any]]) -> None:
    """Append ``<STUDY_LINKS>`` built from the study's ProjectLinks.

    A ProjectLink is a cross-reference to another database (``PUBMED``, ``DOI``),
    which ENA models as an ``XREF_LINK`` of a DB and an ID.
    """
    usable = [link for link in links if link.get("db") and link.get("id")]
    if not usable:
        return
    block = ET.SubElement(study, "STUDY_LINKS")
    for link in usable:
        xref = ET.SubElement(ET.SubElement(block, "STUDY_LINK"), "XREF_LINK")
        _text(xref, "DB", link.get("db"))
        _text(xref, "ID", link.get("id"))
        _text(xref, "LABEL", link.get("label"))


def _sample_set(samples: list[tuple[str, dict[str, Any]]], tree: _Tree) -> str:
    root = ET.Element("SAMPLE_SET")
    for node_id, s in samples:
        sample = ET.SubElement(
            root, "SAMPLE", _attrs(s, alias="alias", center_name="center_name")
        )
        _text(sample, "TITLE", s.get("title"))
        name = ET.SubElement(sample, "SAMPLE_NAME")
        _text(name, "TAXON_ID", s.get("taxon_id"))
        _text(name, "SCIENTIFIC_NAME", s.get("scientific_name"))
        _text(name, "COMMON_NAME", s.get("common_name"))
        _text(sample, "DESCRIPTION", s.get("description"))
        # The checklist's mandatory fields live here; without them ENA rejects
        # the sample, so these are not decoration.
        _attributes(
            sample,
            "SAMPLE_ATTRIBUTES",
            "SAMPLE_ATTRIBUTE",
            tree.children(node_id, "SampleAttribute"),
        )
    return _serialize(root)


def _tag_name(value: Any) -> str:
    """A well-formed XML element name for an enum-derived tag.

    ENA's schema spells these values as element names (``<PAIRED/>``,
    ``<ILLUMINA>``). A draft value like "Illumina HiSeq" used raw produced
    malformed XML with no error — ENA rejects that with no hint of the cause.
    Sanitizing keeps the document parseable; whether the VALUE is a legal ENA
    term stays the enum validation's job, where it is reported per field.
    """
    cleaned = re.sub(r"[^A-Za-z0-9_.-]", "_", str(value).strip().upper())
    if not cleaned or not (cleaned[0].isalpha() or cleaned[0] == "_"):
        cleaned = f"_{cleaned}"
    return cleaned


def _experiment_set(experiments: list[tuple[str, dict[str, Any]]], tree: _Tree) -> str:
    root = ET.Element("EXPERIMENT_SET")
    for node_id, e in experiments:
        exp = ET.SubElement(
            root, "EXPERIMENT", _attrs(e, alias="alias", center_name="center_name")
        )
        if e.get("study_ref"):
            ET.SubElement(exp, "STUDY_REF", {"refname": e["study_ref"]})
        design = ET.SubElement(exp, "DESIGN")
        # ENA's SRA.experiment schema makes DESIGN_DESCRIPTION the mandatory
        # first child of DESIGN, so it is written even with nothing to say.
        # Skipping it when empty put SAMPLE_DESCRIPTOR first and every such
        # experiment failed schema validation — at submission, not here.
        ET.SubElement(design, "DESIGN_DESCRIPTION").text = (
            str(e["design_description"]) if e.get("design_description") else ""
        )
        if e.get("sample_ref"):
            ET.SubElement(design, "SAMPLE_DESCRIPTOR", {"refname": e["sample_ref"]})
        lib = ET.SubElement(design, "LIBRARY_DESCRIPTOR")
        _text(lib, "LIBRARY_NAME", e.get("library_name"))
        _text(lib, "LIBRARY_STRATEGY", e.get("library_strategy"))
        _text(lib, "LIBRARY_SOURCE", e.get("library_source"))
        _text(lib, "LIBRARY_SELECTION", e.get("library_selection"))
        if e.get("library_layout"):
            layout = ET.SubElement(lib, "LIBRARY_LAYOUT")
            ET.SubElement(layout, _tag_name(e["library_layout"]))
        if e.get("platform"):
            platform = ET.SubElement(exp, "PLATFORM")
            model = ET.SubElement(platform, _tag_name(e["platform"]))
            _text(model, "INSTRUMENT_MODEL", e.get("instrument_model"))
        _attributes(
            exp,
            "EXPERIMENT_ATTRIBUTES",
            "EXPERIMENT_ATTRIBUTE",
            tree.children(node_id, "ExperimentAttribute"),
        )
    return _serialize(root)


def _file_elements(parent: ET.Element, files: list[dict[str, Any]]) -> None:
    """Append a ``<FILES>`` block listing each referenced data file."""
    block = ET.SubElement(parent, "FILES")
    for f in files:
        attrs = {
            "filename": f.get("filename", ""),
            "filetype": f.get("filetype", ""),
        }
        if f.get("checksum_method"):
            attrs["checksum_method"] = f["checksum_method"]
        if f.get("checksum"):
            attrs["checksum"] = f["checksum"]
        ET.SubElement(block, "FILE", attrs)


def _run_set(
    runs: list[tuple[str, dict[str, Any]]],
    tree: _Tree,
    loose_files: list[dict[str, Any]],
) -> str:
    # A File nested under its Run is the tree's answer; ``run_ref`` is the
    # fallback for a dataset whose files were built without that nesting.
    files_by_run: dict[str, list[dict[str, Any]]] = {}
    for f in loose_files:
        files_by_run.setdefault(f.get("run_ref", ""), []).append(f)

    root = ET.Element("RUN_SET")
    for node_id, r in runs:
        run = ET.SubElement(
            root, "RUN", _attrs(r, alias="alias", center_name="center_name")
        )
        if r.get("experiment_ref"):
            ET.SubElement(run, "EXPERIMENT_REF", {"refname": r["experiment_ref"]})
        run_files = tree.children(node_id, "File") or files_by_run.get(
            r.get("alias", ""), []
        )
        if run_files:
            _file_elements(ET.SubElement(run, "DATA_BLOCK"), run_files)
        _attributes(
            run,
            "RUN_ATTRIBUTES",
            "RUN_ATTRIBUTE",
            tree.children(node_id, "RunAttribute"),
        )
    return _serialize(root)


def _analysis_set(analyses: list[tuple[str, dict[str, Any]]], tree: _Tree) -> str:
    """Render ``ANALYSIS_SET`` — the derived results of a study (#ena-export)."""
    root = ET.Element("ANALYSIS_SET")
    for node_id, a in analyses:
        analysis = ET.SubElement(
            root, "ANALYSIS", _attrs(a, alias="alias", center_name="center_name")
        )
        _text(analysis, "TITLE", a.get("title"))
        _text(analysis, "DESCRIPTION", a.get("description"))
        if a.get("study_ref"):
            ET.SubElement(analysis, "STUDY_REF", {"refname": a["study_ref"]})
        for field, tag in (
            ("sample_refs", "SAMPLE_REF"),
            ("experiment_refs", "EXPERIMENT_REF"),
            ("run_refs", "RUN_REF"),
            ("analysis_refs", "ANALYSIS_REF"),
        ):
            for ref in a.get(field) or []:
                if ref:
                    ET.SubElement(analysis, tag, {"refname": str(ref)})
        if a.get("analysis_type"):
            # ENA spells the type as an element name, as with LIBRARY_LAYOUT.
            ET.SubElement(
                ET.SubElement(analysis, "ANALYSIS_TYPE"),
                _tag_name(a["analysis_type"]),
            )
        analysis_files = tree.children(node_id, "File")
        if analysis_files:
            _file_elements(analysis, analysis_files)
        _attributes(
            analysis,
            "ANALYSIS_ATTRIBUTES",
            "ANALYSIS_ATTRIBUTE",
            tree.children(node_id, "AnalysisAttribute"),
        )
    return _serialize(root)


#: Document name -> the ``schema`` ENA expects in a SUBMISSION ADD action.
_SUBMISSION_SCHEMAS: tuple[tuple[str, str], ...] = (
    ("study.xml", "study"),
    ("sample.xml", "sample"),
    ("experiment.xml", "experiment"),
    ("run.xml", "run"),
    ("analysis.xml", "analysis"),
)


def _submission(documents: dict[str, str], study: dict[str, Any]) -> str:
    """Render the ``SUBMISSION`` that tells Webin what to do with the rest.

    One ``ADD`` per emitted document. No ``HOLD`` action is written: the profile
    models no release date, and inventing a default would either publish data
    early or embargo it silently. Choosing a hold date belongs to the submission
    step, where the submitter states it.
    """
    root = ET.Element(
        "SUBMISSION", _attrs(study, alias="alias", center_name="center_name")
    )
    actions = ET.SubElement(root, "ACTIONS")
    for name, schema in _SUBMISSION_SCHEMAS:
        if name in documents:
            ET.SubElement(
                ET.SubElement(actions, "ACTION"),
                "ADD",
                {"source": name, "schema": schema},
            )
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
        "sample.xml": ...}``. Only non-empty sets are included, plus a
        ``submission.xml`` naming an ``ADD`` action for each of them.
    """
    tree = _Tree(client)
    studies = tree.of_type("Study")
    samples = tree.of_type("Sample")
    experiments = tree.of_type("Experiment")
    runs = tree.of_type("Run")
    analyses = tree.of_type("Analysis")
    loose_files = [entity for _, entity in tree.of_type("File")]

    documents: dict[str, str] = {}
    if studies:
        documents["study.xml"] = _study_set(studies, tree)
    if samples:
        documents["sample.xml"] = _sample_set(samples, tree)
    if experiments:
        documents["experiment.xml"] = _experiment_set(experiments, tree)
    if runs:
        documents["run.xml"] = _run_set(runs, tree, loose_files)
    if analyses:
        documents["analysis.xml"] = _analysis_set(analyses, tree)
    if documents:
        # Webin acts on the SUBMISSION; the content documents alone do nothing.
        documents["submission.xml"] = _submission(
            documents, studies[0][1] if studies else {}
        )
    return documents
