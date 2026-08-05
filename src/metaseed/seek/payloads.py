"""Pure JSON:API payload builders for FAIRDOM-SEEK resources.

No I/O and no ``httpx`` — importable without the ``metaseed[seek]`` extra. Each
function returns a JSON:API document (``{"data": {"type", "attributes",
"relationships"}}``) ready to POST to the matching SEEK resource root. The
shapes here were verified against a live SEEK 1.17 instance (JSON:API
``api_version`` 0.3).

Resources are linked by threading the ids SEEK returns: an Investigation POST
returns an id, which becomes the Study's ``investigation`` relationship, whose
id becomes the Assay's ``study`` relationship, and so on.
"""

from __future__ import annotations

from typing import Any

# A JERM assay type that always resolves on a stock SEEK; callers may override.
DEFAULT_ASSAY_TYPE_URI = (
    "http://jermontology.org/ontology/JERMOntology#Experimental_assay_type"
)


def _to_one(resource_type: str, resource_id: str | int) -> dict[str, Any]:
    """Build a JSON:API to-one relationship object."""
    return {"data": {"type": resource_type, "id": str(resource_id)}}


def _to_many(resource_type: str, ids: list[str | int]) -> dict[str, Any]:
    """Build a JSON:API to-many relationship object."""
    return {"data": [{"type": resource_type, "id": str(i)} for i in ids]}


def _document(
    resource_type: str,
    attributes: dict[str, Any],
    relationships: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Wrap attributes/relationships in a JSON:API request document."""
    data: dict[str, Any] = {"type": resource_type, "attributes": attributes}
    if relationships:
        data["relationships"] = relationships
    return {"data": data}


def investigation_payload(
    *, title: str, project_id: str | int, description: str | None = None
) -> dict[str, Any]:
    """Build a POST body for ``/investigations`` (belongs to a project)."""
    attributes: dict[str, Any] = {"title": title}
    if description is not None:
        attributes["description"] = description
    return _document(
        "investigations",
        attributes,
        {"projects": _to_many("projects", [project_id])},
    )


def study_payload(
    *, title: str, investigation_id: str | int, description: str | None = None
) -> dict[str, Any]:
    """Build a POST body for ``/studies`` (belongs to an investigation)."""
    attributes: dict[str, Any] = {"title": title}
    if description is not None:
        attributes["description"] = description
    return _document(
        "studies",
        attributes,
        {"investigation": _to_one("investigations", investigation_id)},
    )


def assay_payload(
    *,
    title: str,
    study_id: str | int,
    assay_class_key: str = "EXP",
    assay_type_uri: str = DEFAULT_ASSAY_TYPE_URI,
) -> dict[str, Any]:
    """Build a POST body for ``/assays`` (belongs to a study).

    SEEK requires an ``assay_class`` (``EXP`` experimental / ``MODEL`` modelling)
    and an ``assay_type`` ontology URI (from the JERM ontology by default).
    """
    attributes = {
        "title": title,
        "assay_class": {"key": assay_class_key},
        "assay_type": {"uri": assay_type_uri},
    }
    return _document("assays", attributes, {"study": _to_one("studies", study_id)})


def sample_attribute(
    *,
    title: str,
    attribute_type_id: str | int,
    required: bool = False,
    is_title: bool = False,
    pos: int | None = None,
    pid: str | None = None,
    sample_controlled_vocab_id: str | int | None = None,
    allow_cv_free_text: bool = False,
    linked_sample_type_id: str | int | None = None,
) -> dict[str, Any]:
    """Build one entry for a Sample Type's ``sample_attributes`` list.

    ``attribute_type_id`` is a SEEK base attribute-type id (e.g. 8 = String,
    4 = Integer, 7 = Text), as listed by ``GET /sample_attribute_types``.

    ``pid`` is the attribute's persistent identifier (a property URI). SEEK's
    FAIR-Data-Station import matches an RDF sample to a Sample Type by exact
    string equality of attribute PIDs, discarding blank ones — so an attribute a
    sample's field should populate on import must carry the *same* URI the data
    RDF emits for that field (``http://schema.org/<field>``).

    ``sample_controlled_vocab_id`` binds a Controlled Vocabulary to the attribute
    and ``linked_sample_type_id`` binds another Sample Type. SEEK's
    ``resolve_inconsistencies`` silently *nulls* these unless the attribute type
    is CV/CVList (for the vocab) or a registered-sample type (for the link), so
    callers must pass them only alongside a consistent ``attribute_type_id``.
    """
    attribute: dict[str, Any] = {
        "title": title,
        "required": required,
        "is_title": is_title,
        "sample_attribute_type": {"id": str(attribute_type_id)},
    }
    if pos is not None:
        attribute["pos"] = pos
    if pid is not None:
        attribute["pid"] = pid
    if sample_controlled_vocab_id is not None:
        attribute["sample_controlled_vocab_id"] = str(sample_controlled_vocab_id)
        attribute["allow_cv_free_text"] = allow_cv_free_text
    if linked_sample_type_id is not None:
        attribute["linked_sample_type_id"] = str(linked_sample_type_id)
    return attribute


def sample_type_payload(
    *,
    title: str,
    project_id: str | int,
    attributes: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build a POST body for ``/sample_types`` (a sample schema, per project).

    ``attributes`` is a list of :func:`sample_attribute` entries; exactly one
    should set ``is_title=True``. The Sample Type is created private (SEEK's
    default); its contributor can still view it, which is what the
    FAIR-Data-Station import — run by the same person who provisioned it —
    requires. Broader sharing is subject to the instance's sharing limits.
    """
    return _document(
        "sample_types",
        {"title": title, "sample_attributes": attributes},
        {"projects": _to_many("projects", [project_id])},
    )


def sample_payload(
    *,
    sample_type_id: str | int,
    project_id: str | int,
    data: dict[str, Any],
) -> dict[str, Any]:
    """Build a POST body for ``/samples`` (an instance of a sample type).

    ``data`` maps each of the sample type's attribute titles to a value.
    """
    return _document(
        "samples",
        {"data": data},
        {
            "sample_type": _to_one("sample_types", sample_type_id),
            "projects": _to_many("projects", [project_id]),
        },
    )


def controlled_vocab_payload(
    *,
    title: str,
    terms: list[dict[str, Any]],
    description: str | None = None,
    source_ontology: str | None = None,
    ols_root_term_uris: str | None = None,
) -> dict[str, Any]:
    """Build a POST body for ``/sample_controlled_vocabs``.

    ``terms`` is a list of ``{"label", "iri", "parent_iri"}`` dicts (SEEK does
    not expand an ontology on create — the caller supplies the terms). Setting
    ``source_ontology`` + ``ols_root_term_uris`` tags the vocabulary as
    ontology-backed.
    """
    attributes: dict[str, Any] = {
        "title": title,
        "sample_controlled_vocab_terms_attributes": terms,
    }
    if description is not None:
        attributes["description"] = description
    if source_ontology is not None:
        attributes["source_ontology"] = source_ontology
    if ols_root_term_uris is not None:
        attributes["ols_root_term_uris"] = ols_root_term_uris
    return _document("sample_controlled_vocabs", attributes)


def data_file_payload(
    *,
    title: str,
    project_id: str | int,
    url: str,
    original_filename: str,
    description: str | None = None,
    assay_ids: list[str | int] | None = None,
) -> dict[str, Any]:
    """Build a POST body for ``/data_files`` as a **remote** content blob.

    The file itself stays in external storage (an S3 bucket); SEEK registers a
    reference to it -- a ``url`` plus the ``original_filename`` -- rather than
    holding the bytes. This is SEEK's remote ContentBlob, the shape its API doc
    describes for "URI to the content's location". No upload follows.

    Args:
        title: Human-readable title for the data file.
        project_id: SEEK project it belongs to.
        url: The content's location (e.g. the study's S3 base URL).
        original_filename: The filename SEEK shows for it.
        description: Optional description (used to carry the file list).
        assay_ids: SEEK assay ids to associate the file with, if any.

    Returns:
        A JSON:API request document.
    """
    attributes: dict[str, Any] = {
        "title": title,
        "content_blobs": [{"url": url, "original_filename": original_filename}],
    }
    if description is not None:
        attributes["description"] = description
    relationships: dict[str, Any] = {"projects": _to_many("projects", [project_id])}
    if assay_ids:
        relationships["assays"] = _to_many("assays", assay_ids)
    return _document("data_files", attributes, relationships)
