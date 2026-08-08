"""Map a MetaboLights study document into a ``metabolights``-profile dataset.

Pure and network-free: it takes an already-fetched MetaboLights study document
(as returned by :meth:`metaseed.metabolights.client.MetaboLightsClient.study`)
and builds a :class:`~metaseed.api.client.MetaseedClient` bound to the
``metabolights`` profile.

The document follows the ISA model the MetaboLights web service exposes: an
``isaInvestigation`` carrying people, publications, and one or more studies, each
with study-design descriptors, factors, protocols, samples, and assays. Raw
spectra are *referenced* — each assay data file becomes a ``DataFile`` entity
carrying a resolvable URL under the study's public download root — never
downloaded.

Entities are linked through ``parent_id`` to mirror the profile hierarchy
(Investigation -> Study -> {Factor, Protocol, Sample, Assay}, and so on) and are
created with ``skip_validation`` so a record that omits a field does not abort
the import; call :meth:`MetaseedClient.validate` to report gaps afterwards.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from metaseed.isatab import read_data_files, read_metabolites, read_samples
from metaseed.mapping import clean as _clean

if TYPE_CHECKING:
    from metaseed.api.client import MetaseedClient


def _term(value: Any) -> str | None:
    """Extract the human-readable label from an ISA annotation value.

    ISA ontology annotations are dicts carrying ``annotationValue`` (or ``name``
    for term sources). Plain strings are returned unchanged.

    Args:
        value: An ISA annotation dict or a plain value.

    Returns:
        The annotation label, or ``None`` when empty.
    """
    if isinstance(value, dict):
        label = value.get("annotationValue") or value.get("name")
        return label or None
    if isinstance(value, str):
        return value or None
    return None


def _study_download_root(document: dict[str, Any]) -> str | None:
    """Return the public download root for a study's raw files, if published."""
    mtbls = document.get("mtblsStudy") or {}
    root = mtbls.get("studyHttpUrl") or mtbls.get("studyFtpUrl")
    return root.rstrip("/") if isinstance(root, str) and root else None


def _isatab_for_prefix(files: dict[str, str], prefix: str) -> str | None:
    """The single ISA-Tab file text whose name starts with ``prefix``, or None."""
    matches = [text for name, text in files.items() if name.startswith(prefix)]
    return matches[0] if len(matches) == 1 else None


def _isatab_for_assay(files: dict[str, str], assay_filename: str | None) -> str | None:
    """The assay's ``a_*.txt`` text: exact name match, else the sole assay file."""
    if assay_filename and assay_filename in files:
        return files[assay_filename]
    return _isatab_for_prefix(files, "a_")


def _isatab_characteristic(
    characteristics: list[dict[str, Any]], category: str
) -> str | None:
    """Value of the ``category`` characteristic among parsed ISA-Tab rows."""
    return next(
        (c.get("value") for c in characteristics if c.get("category") == category),
        None,
    )


def _add_samples_from_isatab(
    client: MetaseedClient, study_file: str, *, parent_id: str
) -> None:
    """Create Samples (+ Characteristic/FactorValue children) from an s_ file."""
    for row in read_samples(study_file):
        characteristics = row.get("characteristics") or []
        sample_entity = client.create_entity(
            "Sample",
            _clean(
                {
                    "name": row.get("name"),
                    "organism": _isatab_characteristic(characteristics, "Organism"),
                    "organism_part": _isatab_characteristic(
                        characteristics, "Organism part"
                    ),
                    # organism_term intentionally left unset (see _add_sample).
                }
            ),
            parent_id=parent_id,
            skip_validation=True,
        )
        for characteristic in characteristics:
            client.create_entity(
                "Characteristic",
                _clean(
                    {
                        "category": characteristic.get("category"),
                        "value": characteristic.get("value"),
                    }
                ),
                parent_id=sample_entity.id,
                skip_validation=True,
            )
        for factor_value in row.get("factor_values") or []:
            client.create_entity(
                "FactorValue",
                _clean(
                    {
                        "factor_name": factor_value.get("category"),
                        "value": factor_value.get("value"),
                    }
                ),
                parent_id=sample_entity.id,
                skip_validation=True,
            )


_DATA_FILE_TYPES = (
    ("Raw", "Raw Data File"),
    ("Derived", "Derived Data File"),
    ("Acquisition", "Acquisition Parameter Data File"),
    ("Free Induction", "Free Induction Decay Data File"),
)


def _file_type_from_column(column: str) -> str:
    """Map an assay data-file column header to a DataFile ``file_type`` value."""
    for needle, file_type in _DATA_FILE_TYPES:
        if needle in column:
            return file_type
    return column


def _add_data_files_from_isatab(
    client: MetaseedClient, assay_file: str, *, parent_id: str
) -> None:
    """Create DataFiles from an assay (``a_*.txt``) file's data-file columns."""
    for data_file in read_data_files(assay_file):
        client.create_entity(
            "DataFile",
            _clean(
                {
                    "filename": data_file.get("name"),
                    "file_type": _file_type_from_column(data_file.get("kind", "")),
                }
            ),
            parent_id=parent_id,
            skip_validation=True,
        )


def _add_metabolites_from_isatab(
    client: MetaseedClient, maf_file: str, *, parent_id: str
) -> None:
    """Create Metabolites from a MAF (``m_*.tsv``) file."""
    for metabolite in read_metabolites(maf_file):
        client.create_entity(
            "Metabolite",
            _clean(dict(metabolite)),
            parent_id=parent_id,
            skip_validation=True,
        )


def build_dataset(
    study: dict[str, Any],
    *,
    version: str = "1.0",
    isatab_files: dict[str, str] | None = None,
) -> MetaseedClient:
    """Build a ``metabolights``-profile dataset from a MetaboLights document.

    Args:
        study: A MetaboLights study metadata document (the value returned by
            :meth:`MetaboLightsClient.study`).
        version: ``metabolights`` profile version.
        isatab_files: Optional ``{filename: text}`` of the study's ISA-Tab files
            (from :meth:`MetaboLightsClient.study_files`). The ISA-JSON payload
            leaves ``samples``/``dataFiles`` empty, so Samples, DataFiles and
            Metabolites are recovered from these ``s_``/``a_``/``m_`` files.

    Returns:
        A MetaseedClient holding the Investigation and its Contacts,
        Publications, Studies, and each study's Factors, Protocols, Samples, and
        Assays (with referenced DataFiles and Metabolites). Empty if no
        investigation is present.
    """
    from metaseed import MetaseedClient

    client = MetaseedClient("metabolights", version)
    investigation = study.get("isaInvestigation") or {}
    if not investigation:
        return client

    isatab_files = isatab_files or {}

    download_root = _study_download_root(study)

    identifier = investigation.get("identifier")
    inv = client.create_entity(
        "Investigation",
        _clean(
            {
                "identifier": identifier,
                "accession": identifier,
                "title": investigation.get("title"),
                "description": investigation.get("description"),
                "submission_date": investigation.get("submissionDate"),
                "public_release_date": investigation.get("publicReleaseDate"),
            }
        ),
        skip_validation=True,
    )

    for person in investigation.get("people") or []:
        _add_person(client, person, parent_id=inv.id)

    for publication in investigation.get("publications") or []:
        _add_publication(client, publication, parent_id=inv.id)

    for study_record in investigation.get("studies") or []:
        _add_study(
            client,
            study_record,
            download_root,
            parent_id=inv.id,
            isatab_files=isatab_files,
        )

    return client


def _add_person(
    client: MetaseedClient, person: dict[str, Any], *, parent_id: str
) -> None:
    """Create a Person entity from an ISA person record."""
    roles = [r for r in (_term(role) for role in person.get("roles") or []) if r]
    client.create_entity(
        "Person",
        _clean(
            {
                "first_name": person.get("firstName"),
                "last_name": person.get("lastName"),
                "email": person.get("email"),
                "affiliation": person.get("affiliation"),
                "orcid": person.get("orcid"),
                "roles": roles,
            }
        ),
        parent_id=parent_id,
        skip_validation=True,
    )


def _add_publication(
    client: MetaseedClient, publication: dict[str, Any], *, parent_id: str
) -> None:
    """Create a Publication entity from an ISA publication record."""
    client.create_entity(
        "Publication",
        _clean(
            {
                "title": publication.get("title"),
                "authors": publication.get("authorList"),
                "doi": publication.get("doi"),
                "pubmed_id": publication.get("pubMedID"),
                "status": _term(publication.get("status")),
            }
        ),
        parent_id=parent_id,
        skip_validation=True,
    )


def _add_study(
    client: MetaseedClient,
    study: dict[str, Any],
    download_root: str | None,
    *,
    parent_id: str,
    isatab_files: dict[str, str] | None = None,
) -> None:
    """Create a Study entity and its factors, protocols, samples, and assays."""
    isatab_files = isatab_files or {}
    descriptors = [
        d
        for d in (_term(item) for item in study.get("studyDesignDescriptors") or [])
        if d
    ]
    study_entity = client.create_entity(
        "Study",
        _clean(
            {
                "identifier": study.get("identifier"),
                "title": study.get("title"),
                "description": study.get("description"),
                "study_design_descriptors": descriptors,
            }
        ),
        parent_id=parent_id,
        skip_validation=True,
    )

    # MetaboLights records people and publications on the study, not the
    # investigation (where ISA also allows them); map both levels.
    for person in study.get("people") or []:
        _add_person(client, person, parent_id=study_entity.id)

    for publication in study.get("publications") or []:
        _add_publication(client, publication, parent_id=study_entity.id)

    for factor in study.get("factors") or []:
        client.create_entity(
            "Factor",
            _clean(
                {
                    "name": factor.get("factorName"),
                    "factor_type": _term(factor.get("factorType")),
                }
            ),
            parent_id=study_entity.id,
            skip_validation=True,
        )

    for protocol in study.get("protocols") or []:
        _add_protocol(client, protocol, parent_id=study_entity.id)

    json_samples = study.get("samples") or []
    for sample in json_samples:
        _add_sample(client, sample, parent_id=study_entity.id)

    # The ISA-JSON payload leaves ``samples`` empty for every study; fall back to
    # the study's ``s_*.txt`` ISA-Tab file when present (#146).
    if not json_samples:
        study_file = _isatab_for_prefix(isatab_files, "s_")
        if study_file:
            _add_samples_from_isatab(client, study_file, parent_id=study_entity.id)

    for assay in study.get("assays") or []:
        _add_assay(
            client,
            assay,
            download_root,
            parent_id=study_entity.id,
            isatab_files=isatab_files,
        )


def _add_protocol(
    client: MetaseedClient, protocol: dict[str, Any], *, parent_id: str
) -> None:
    """Create a Protocol entity and its parameters."""
    protocol_entity = client.create_entity(
        "Protocol",
        _clean(
            {
                "name": protocol.get("name"),
                "protocol_type": _term(protocol.get("protocolType")),
                "description": protocol.get("description"),
                "uri": protocol.get("uri"),
            }
        ),
        parent_id=parent_id,
        skip_validation=True,
    )

    for parameter in protocol.get("parameters") or []:
        name = _term(parameter.get("parameterName"))
        if not name:
            continue
        client.create_entity(
            "ProtocolParameter",
            _clean({"name": name}),
            parent_id=protocol_entity.id,
            skip_validation=True,
        )


def _characteristic_value(characteristics: list[Any], category: str) -> str | None:
    """Return the value of a named sample characteristic, if present."""
    for characteristic in characteristics:
        if not isinstance(characteristic, dict):
            continue
        name = _term((characteristic.get("category") or {}).get("characteristicType"))
        if name == category:
            return _term(characteristic.get("value"))
    return None


def _add_sample(
    client: MetaseedClient, sample: dict[str, Any], *, parent_id: str
) -> None:
    """Create a Sample entity and its characteristics and factor values.

    The ``organism_term`` field is intentionally left unset: it is typed as an
    ``ontology_term`` whose coercion resolves the value against OLS4, which would
    make this otherwise network-free mapper issue a request per sample.
    """
    characteristics = sample.get("characteristics") or []
    sample_entity = client.create_entity(
        "Sample",
        _clean(
            {
                "name": sample.get("name"),
                "organism": _characteristic_value(characteristics, "Organism"),
                "organism_part": _characteristic_value(
                    characteristics, "Organism part"
                ),
            }
        ),
        parent_id=parent_id,
        skip_validation=True,
    )

    for characteristic in characteristics:
        if not isinstance(characteristic, dict):
            continue
        client.create_entity(
            "Characteristic",
            _clean(
                {
                    "category": _term(
                        (characteristic.get("category") or {}).get("characteristicType")
                    ),
                    "value": _term(characteristic.get("value")),
                }
            ),
            parent_id=sample_entity.id,
            skip_validation=True,
        )

    for factor_value in sample.get("factorValues") or []:
        if not isinstance(factor_value, dict):
            continue
        client.create_entity(
            "FactorValue",
            _clean(
                {
                    "factor_name": (factor_value.get("category") or {}).get(
                        "factorName"
                    ),
                    "value": _term(factor_value.get("value")),
                    "unit": _term(factor_value.get("unit")),
                }
            ),
            parent_id=sample_entity.id,
            skip_validation=True,
        )


def _maf_from_comments(comments: list[Any]) -> str | None:
    """Return the metabolite assignment file name from an assay's comments."""
    for comment in comments:
        if not isinstance(comment, dict):
            continue
        if "Metabolite Assignment File" in (comment.get("name") or ""):
            return comment.get("value") or None
    return None


def _add_assay(
    client: MetaseedClient,
    assay: dict[str, Any],
    download_root: str | None,
    *,
    parent_id: str,
    isatab_files: dict[str, str] | None = None,
) -> None:
    """Create an Assay entity and its referenced data files and metabolites."""
    isatab_files = isatab_files or {}
    filename = assay.get("filename")
    sample_names = [
        s.get("name")
        for s in assay.get("samples") or []
        if isinstance(s, dict) and s.get("name")
    ]
    assay_entity = client.create_entity(
        "Assay",
        _clean(
            {
                "identifier": filename,
                "filename": filename,
                "technology_type": _term(assay.get("technologyType")),
                "technology_platform": assay.get("technologyPlatform"),
                "measurement_type": _term(assay.get("measurementType")),
                "samples": sample_names,
                "metabolite_assignment_file": _maf_from_comments(
                    assay.get("comments") or []
                ),
            }
        ),
        parent_id=parent_id,
        skip_validation=True,
    )

    json_data_files = assay.get("dataFiles") or []
    for data_file in json_data_files:
        if not isinstance(data_file, dict):
            continue
        name = data_file.get("filename") or data_file.get("name")
        if not name:
            continue
        reference = f"{download_root}/{name}" if download_root else name
        client.create_entity(
            "DataFile",
            _clean(
                {
                    "filename": reference,
                    "file_type": data_file.get("label") or data_file.get("type"),
                }
            ),
            parent_id=assay_entity.id,
            skip_validation=True,
        )

    # The ISA-JSON payload leaves ``dataFiles`` empty; recover DataFiles from the
    # assay's ``a_*.txt`` file and Metabolites from its MAF (``m_*.tsv``) (#146).
    if not json_data_files:
        assay_file = _isatab_for_assay(isatab_files, filename)
        if assay_file:
            _add_data_files_from_isatab(client, assay_file, parent_id=assay_entity.id)
    maf_file = _isatab_for_prefix(isatab_files, "m_")
    if maf_file:
        _add_metabolites_from_isatab(client, maf_file, parent_id=assay_entity.id)
