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

from collections.abc import Mapping, Sequence
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
    *,
    title: str,
    project_id: str | int,
    description: str | None = None,
    isa_json_compliant: bool = False,
) -> dict[str, Any]:
    """Build a POST body for ``/investigations`` (belongs to a project).

    ``isa_json_compliant`` marks the Investigation as ISA-JSON compliant. Without
    it SEEK refuses to export the Investigation as ISA-JSON at all, whatever its
    Studies and Assays look like.
    """
    attributes: dict[str, Any] = {"title": title}
    if isa_json_compliant:
        attributes["is_isa_json_compliant"] = True
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
    assay_ids: Sequence[str | int] | None = None,
    study_id: str | int | None = None,
) -> dict[str, Any]:
    """Build a POST body for ``/samples`` (an instance of a sample type).

    ``data`` maps each of the sample type's attribute titles to a value.

    ``assay_ids`` associates the Sample with those Assays, and ``study_id``
    accompanies them as SEEK requires. Without it the Sample
    is reachable only by listing the project's samples: it is attached to its
    Sample Type and Project and to no ISA level, so nothing walking down from an
    Investigation finds it and a re-import drops it. SEEK derives the Sample's
    Study and Investigation from the Assay, and ignores a ``studies``
    relationship supplied here, so the Assay is the association to set.
    """
    attributes: dict[str, Any] = {"data": data}
    if study_id is not None:
        # SEEK rejects a Sample carrying an ``assays`` link unless ``study_id``
        # is also given as an attribute, and ignores it when there is no link.
        attributes["study_id"] = study_id
    relationships: dict[str, Any] = {
        "sample_type": _to_one("sample_types", sample_type_id),
        "projects": _to_many("projects", [project_id]),
    }
    if assay_ids:
        relationships["assays"] = _to_many("assays", list(assay_ids))
    return _document("samples", attributes, relationships)


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


def isa_sample_attribute(
    *,
    title: str,
    isa_tag_id: str | int,
    attribute_type_id: str | int | None = None,
    attribute_type_title: str | None = None,
    required: bool = False,
    is_title: bool = False,
    pos: int | None = None,
    linked_sample_type_id: str | int | None = None,
    sample_controlled_vocab_id: str | int | None = None,
    allow_cv_free_text: bool = False,
) -> dict[str, Any]:
    """One Sample Type attribute for an ISA form body.

    Every attribute of an ISA-JSON compliant Sample Type carries an ``isa_tag_id``,
    so it is required here rather than optional. ``linked_sample_type_id`` is
    omitted unless given: SEEK rejects a link on an attribute whose type is not a
    registered-sample type.

    The attribute type is given either by id or by title — SEEK resolves both
    (``sample_attribute_type[id]`` or ``[title]``). Title is what the profile
    projection already speaks, and unlike the ids it is stable across instances.
    """
    if (attribute_type_id is None) == (attribute_type_title is None):
        raise ValueError(
            "pass exactly one of attribute_type_id or attribute_type_title"
        )
    attribute: dict[str, Any] = {
        "title": title,
        "required": required,
        "is_title": is_title,
        "isa_tag_id": isa_tag_id,
    }
    if attribute_type_id is not None:
        attribute["attribute_type_id"] = attribute_type_id
    else:
        attribute["attribute_type_title"] = attribute_type_title
    if pos is not None:
        attribute["pos"] = pos
    if linked_sample_type_id is not None:
        attribute["linked_sample_type_id"] = linked_sample_type_id
    if sample_controlled_vocab_id is not None:
        # SEEK's resolve_inconsistencies nulls a vocab id on a non-CV attribute,
        # so callers pass one only alongside a CV attribute type.
        attribute["sample_controlled_vocab_id"] = sample_controlled_vocab_id
        attribute["allow_cv_free_text"] = allow_cv_free_text
    return attribute


def _attribute_pairs(
    prefix: str, attributes: Sequence[Mapping[str, Any]]
) -> list[tuple[str, str]]:
    """Form pairs for ``attributes`` under ``prefix``, using ``[]`` repetition.

    Rails builds an Array from repeated ``[]`` keys, starting a new element each
    time a key it has already seen reappears — so ``title`` must come first in
    every attribute. Numeric indices would instead build a Hash, which the
    controller iterates as an Array and dies on with a ``TypeError``.
    """
    pairs: list[tuple[str, str]] = []
    for attribute in attributes:
        for key, value in attribute.items():
            # SEEK takes the attribute type as a nested object, not a flat id.
            nested = {
                "attribute_type_id": "[sample_attribute_type][id]",
                "attribute_type_title": "[sample_attribute_type][title]",
            }
            suffix = nested.get(key, f"[{key}]")
            rendered = str(value).lower() if isinstance(value, bool) else str(value)
            pairs.append((f"{prefix}[]{suffix}", rendered))
    return pairs


def isa_study_form(
    *,
    title: str,
    investigation_id: str | int,
    source_title: str,
    source_attributes: Sequence[Mapping[str, Any]],
    collection_title: str,
    collection_attributes: Sequence[Mapping[str, Any]],
) -> list[tuple[str, str]]:
    """Form body for ``POST /isa_studies`` — a Study with its two Sample Types.

    A compliant Study owns a Source type and a Sample Collection type, in that
    order, the second linking back to the first. ``ISAStudy#save`` assigns that
    link itself, but validation runs first, so the caller must give the input
    attribute a ``linked_sample_type_id`` that already exists; ``save`` overwrites
    it with the Source type it just created.
    """
    pairs: list[tuple[str, str]] = [
        ("isa_study[study][title]", title),
        ("isa_study[study][investigation_id]", str(investigation_id)),
        ("isa_study[source_sample_type][title]", source_title),
    ]
    pairs += _attribute_pairs(
        "isa_study[source_sample_type][sample_attributes]", source_attributes
    )
    pairs.append(("isa_study[sample_collection_sample_type][title]", collection_title))
    pairs += _attribute_pairs(
        "isa_study[sample_collection_sample_type][sample_attributes]",
        collection_attributes,
    )
    return pairs


def isa_assay_form(
    *,
    title: str,
    study_id: str | int,
    assay_class_id: str | int,
    assay_type_uri: str = DEFAULT_ASSAY_TYPE_URI,
    position: int = 0,
    assay_stream_id: str | int | None = None,
    input_sample_type_id: str | int | None = None,
    sample_type_title: str | None = None,
    sample_type_attributes: Sequence[Mapping[str, Any]] | None = None,
) -> list[tuple[str, str]]:
    """Form body for ``POST /isa_assays`` — an assay stream, or an assay in one.

    An assay stream owns no Sample Type, so ``sample_type_*`` and
    ``assay_stream_id`` are all omitted for it. A child assay carries the stream
    it belongs to, the Sample Type its inputs come from, and its own Sample Type.
    """
    pairs: list[tuple[str, str]] = [
        ("isa_assay[assay][title]", title),
        ("isa_assay[assay][study_id]", str(study_id)),
        ("isa_assay[assay][assay_class_id]", str(assay_class_id)),
        ("isa_assay[assay][assay_type_uri]", assay_type_uri),
        ("isa_assay[assay][position]", str(position)),
    ]
    if assay_stream_id is not None:
        pairs.append(("isa_assay[assay][assay_stream_id]", str(assay_stream_id)))
    if input_sample_type_id is not None:
        pairs.append(("isa_assay[input_sample_type_id]", str(input_sample_type_id)))
    if sample_type_title is not None:
        pairs.append(("isa_assay[sample_type][title]", sample_type_title))
    if sample_type_attributes:
        pairs += _attribute_pairs(
            "isa_assay[sample_type][sample_attributes]", sample_type_attributes
        )
    return pairs


ASSAY_CLASS_IDS: dict[str, int] = {"EXP": 1, "MODEL": 2, "STREAM": 3}
"""SEEK's seeded Assay class ids, keyed by their ``key``.

``/isa_assays`` takes ``assay_class_id`` and SEEK exposes no endpoint for these
(``GET /assay_classes`` is a 404, and the ``assay_class`` on an assay resource
carries only ``title``/``key``). The ids are fixed in SEEK's own fixture,
``config/default_data/assay_classes.yml``, which pins them explicitly, so
reading them from there is as stable as the seed itself.
"""
