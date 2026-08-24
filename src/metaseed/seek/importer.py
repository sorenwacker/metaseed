"""Import a SEEK Investigation into a metaseed dataset (SEEK -> metaseed).

The mirror of :mod:`metaseed.seek.fairds` / :mod:`metaseed.seek.sync`, giving the
SEEK adapter a read direction so metaseed can round-trip content in and out of a
live instance (e.g. pull from FAIRDOMHub, edit, push to a local instance).

:func:`import_from_seek` walks a SEEK Investigation over the JSON:API
(Investigation -> Study -> ObservationUnit/Assay -> Sample), reads each Sample's
``attribute_map`` and the ISA core fields, and reconstructs a metaseed dataset.
Assay streams are skipped — they are sync plumbing, not Assays. An assay sample
naming an input is an assay material at the end of the ISA chain; its input
links are followed back to the collection Sample and the Source (stored in
Study-owned Sample Types no relationship walk reaches), and the chain comes
back nested Source -> Sample -> AssayMaterial. Because SEEK's Sample Types are
user-defined, the profile is **derived from the instance** rather than assumed:
one entity per ISA level, with fields (and their types) taken from the Sample
Types encountered at that level. The non-sample levels keep only
identifier/title/description — see ``docs/architecture/seek-export.md`` for the
current import scope.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from metaseed.api.client import MetaseedClient
from metaseed.seek.client import SeekApiError

if TYPE_CHECKING:
    from metaseed.seek.client import SeekClient

# SEEK core sample-attribute titles that map onto a metaseed entity's own
# title/description rather than a field of their own (the inverse of the mapping
# in :mod:`metaseed.seek.provision`).
_CORE_ATTRIBUTES = {"Title": "title", "Description": "description"}

# SEEK base sample-attribute type title -> metaseed field type. SEEK collapses
# several presentation variants onto one storage type; anything unrecognised
# falls back to ``string``. ``Controlled Vocabulary List`` and
# ``Registered Sample List`` carry an array of scalars, so they map to ``list``.
_SEEK_TYPE_TO_METASEED: dict[str, str] = {
    "String": "string",
    "Text": "string",
    "Controlled Vocabulary": "string",
    "Registered Sample": "string",
    "Integer": "integer",
    "Real number": "float",
    "Float": "float",
    "Date": "date",
    "Date time": "datetime",
    "DateTime": "datetime",
    "Boolean": "boolean",
    "Web link": "uri",
}
_SEEK_LIST_TYPES = {"Controlled Vocabulary List", "Registered Sample List"}


def _core_fields(*with_children: str | None) -> list[dict[str, Any]]:
    """The identifier/title/description fields every imported entity carries.

    Each name in ``with_children`` becomes a nested ``list`` field, so the derived
    profile expresses the ISA hierarchy. A Study takes two: samples reach SEEK
    either through an ObservationUnit (the FAIR Data Station import) or through an
    Assay (the API sync), and an imported Study may hold both.
    """
    fields: list[dict[str, Any]] = [
        {"name": "identifier", "type": "string", "required": True},
        {"name": "title", "type": "string"},
        {"name": "description", "type": "string"},
    ]
    for child in with_children:
        if child is not None:
            fields.append({"name": child.lower() + "s", "type": "list", "items": child})
    return fields


def _assays(client: SeekClient, study_id: str) -> list[dict[str, Any]]:
    """A study's Assay refs, or ``[]`` when the instance does not serve them."""
    try:
        data = client.get(f"/studies/{study_id}/assays").get("data", [])
    except SeekApiError as exc:
        if 400 <= exc.status_code < 500:
            return []
        raise
    return data if isinstance(data, list) else []


def _observation_units(client: SeekClient, study_id: str) -> list[dict[str, Any]]:
    """A study's ObservationUnit refs, or ``[]`` on instances without them.

    ObservationUnits require SEEK's ISA-JSON compliance; an instance without it
    answers the sub-route with a 4xx, so the study imports with no samples rather
    than aborting the whole import.

    ``SeekApiError`` is what :class:`SeekClient` raises — this caught
    ``httpx.HTTPStatusError``, which the client never lets escape, so the
    degradation could not fire and every instance without ISA-JSON aborted the
    whole import.
    """
    try:
        data = client.get(f"/studies/{study_id}/observation_units").get("data", [])
    except SeekApiError as exc:
        # A 4xx means the instance has no ISA-JSON observation-unit route — degrade
        # to "no observation units". Any other status (5xx) or a connect/timeout
        # error is a real failure and must not masquerade as an empty study.
        if 400 <= exc.status_code < 500:
            return []
        raise
    return data if isinstance(data, list) else []


def _is_input_attribute(title: str) -> bool:
    """Whether a sample attribute is the ISA chain's input link.

    SEEK names it ``Input (<predecessor title attribute>)`` on save. It carries
    the predecessor's row id — structure the importer expresses by nesting, not
    a field value to keep.
    """
    return title.startswith("Input (")


def _input_ref_ids(sample: dict[str, Any]) -> list[str]:
    """The SEEK sample ids a sample names as its ISA inputs, or ``[]``."""
    attribute_map = sample.get("attributes", {}).get("attribute_map") or {}
    for key, value in attribute_map.items():
        if _is_input_attribute(key) and isinstance(value, list):
            return [
                str(ref["id"])
                for ref in value
                if isinstance(ref, dict) and ref.get("id") is not None
            ]
    return []


def _is_assay_stream(assay: dict[str, Any]) -> bool:
    """Whether a SEEK assay is an assay stream rather than a real Assay.

    The stream is sync plumbing — every Assay under a compliant Study hangs off
    one — so reading it back as an Assay would double the count on every round
    trip.
    """
    assay_class = assay.get("attributes", {}).get("assay_class") or {}
    return assay_class.get("key") == "STREAM"


def _metaseed_field(attribute: dict[str, Any]) -> dict[str, Any]:
    """Map one SEEK Sample Type attribute onto a metaseed field spec.

    The SEEK base type (``sample_attribute_type.title``) sets the metaseed
    ``type`` so the round trip keeps dates, numbers and lists instead of
    collapsing everything to ``string`` (which the FDS re-export would then drop
    for list-valued attributes).
    """
    type_title = attribute.get("sample_attribute_type", {}).get("title", "")
    field: dict[str, Any] = {"name": attribute["title"]}
    if type_title in _SEEK_LIST_TYPES:
        field["type"] = "list"
        field["items"] = "string"
    else:
        field["type"] = _SEEK_TYPE_TO_METASEED.get(type_title, "string")
    return field


def _sample_type_fields(
    client: SeekClient, sample_type_id: str, cache: dict[str, list[dict[str, Any]]]
) -> list[dict[str, Any]]:
    """Field specs of a Sample Type (minus core fields), cached by type id.

    Caching by ``sample_type_id`` avoids a ``GET /sample_types/{id}`` per sample:
    thousands of samples sharing one type resolve their schema with a single
    request.
    """
    if sample_type_id in cache:
        return cache[sample_type_id]
    detail = client.get(f"/sample_types/{sample_type_id}").get("data", {})
    attributes = detail.get("attributes", {}).get("sample_attributes", [])
    fields = [
        _metaseed_field(a)
        for a in attributes
        if a.get("title")
        and a["title"] not in _CORE_ATTRIBUTES
        and not _is_input_attribute(a["title"])
    ]
    cache[sample_type_id] = fields
    return fields


class _SampleReader:
    """Fetches each sample once and accumulates the field union per ISA level.

    Plain samples (attached with no input link) share the "Sample" level's
    union; chain sources and assay materials each keep their own, because the
    three levels' Sample Types carry different fields.
    """

    def __init__(self, client: SeekClient) -> None:
        self._client = client
        self.sample_fields: dict[str, dict[str, Any]] = {}
        self.source_fields: dict[str, dict[str, Any]] = {}
        self.material_fields: dict[str, dict[str, Any]] = {}
        self._st_cache: dict[str, list[dict[str, Any]]] = {}
        self._fetched: dict[str, dict[str, Any]] = {}

    def fetch(self, sample_id: str) -> dict[str, Any]:
        if sample_id not in self._fetched:
            self._fetched[sample_id] = self._client.get(f"/samples/{sample_id}")["data"]
        return self._fetched[sample_id]

    def union(self, sample: dict[str, Any], into: dict[str, dict[str, Any]]) -> None:
        st_id = sample["relationships"]["sample_type"]["data"]["id"]
        for field in _sample_type_fields(self._client, st_id, self._st_cache):
            into.setdefault(field["name"], field)


def _read_observation_units(
    client: SeekClient, study_id: str, reader: _SampleReader
) -> list[dict[str, Any]]:
    """A study's ObservationUnits, each with its samples under ``_samples``."""
    ous: list[dict[str, Any]] = []
    for ou_ref in _observation_units(client, study_id):
        ou = client.get(f"/observation_units/{ou_ref['id']}")["data"]
        samples: list[dict[str, Any]] = []
        for sample_ref in ou["relationships"].get("samples", {}).get("data", []):
            sample = reader.fetch(sample_ref["id"])
            reader.union(sample, reader.sample_fields)
            samples.append(sample)
        ou["_samples"] = samples
        ous.append(ou)
    return ous


def _read_assays_and_chain(
    client: SeekClient, study_id: str, reader: _SampleReader
) -> tuple[
    list[dict[str, Any]],
    dict[str, dict[str, Any]],
    dict[str, tuple[dict[str, Any], str | None]],
    list[tuple[dict[str, Any], str]],
]:
    """A study's Assays plus the ISA material chain recovered from their samples.

    The API sync attaches Samples to an Assay, not to an ObservationUnit, so a
    dataset pushed that way is invisible to the ObservationUnit walk. Assay
    streams are skipped — they are sync plumbing, not Assays. A sample naming an
    input is an assay material at the end of the ISA chain; following its input
    links back recovers the collection Sample and the Source, which SEEK stores
    in Study-owned Sample Types no relationship walk reaches.

    Returns:
        ``(assays, chain_sources, chain_samples, materials)`` — assays with
        their inputless samples under ``_samples``; chain sources by SEEK id;
        chain samples by SEEK id as ``(resource, source id or None)``; materials
        as ``(resource, parent chain-sample id)``.
    """
    assays: list[dict[str, Any]] = []
    chain_sources: dict[str, dict[str, Any]] = {}
    chain_samples: dict[str, tuple[dict[str, Any], str | None]] = {}
    materials: list[tuple[dict[str, Any], str]] = []
    for assay_ref in _assays(client, study_id):
        assay = client.get(f"/assays/{assay_ref['id']}")["data"]
        if _is_assay_stream(assay):
            continue
        a_samples: list[dict[str, Any]] = []
        refs = (assay.get("relationships") or {}).get("samples", {}).get("data") or []
        for sample_ref in refs:
            sample = reader.fetch(sample_ref["id"])
            input_ids = _input_ref_ids(sample)
            if not input_ids:
                reader.union(sample, reader.sample_fields)
                a_samples.append(sample)
                continue
            reader.union(sample, reader.material_fields)
            parent_id = input_ids[0]
            materials.append((sample, parent_id))
            if parent_id not in chain_samples:
                parent = reader.fetch(parent_id)
                reader.union(parent, reader.sample_fields)
                grandparent_ids = _input_ref_ids(parent)
                source_id = grandparent_ids[0] if grandparent_ids else None
                chain_samples[parent_id] = (parent, source_id)
                if source_id is not None and source_id not in chain_sources:
                    source = reader.fetch(source_id)
                    reader.union(source, reader.source_fields)
                    chain_sources[source_id] = source
        assay["_samples"] = a_samples
        assays.append(assay)
    return assays, chain_sources, chain_samples, materials


def import_from_seek(
    client: SeekClient, investigation_id: str, *, profile_name: str = "seek-imported"
) -> MetaseedClient:
    """Import a SEEK Investigation into a metaseed dataset.

    Args:
        client: An authenticated (or public-read) :class:`SeekClient`.
        investigation_id: The SEEK Investigation id to import.
        profile_name: Name for the derived profile.

    Returns:
        A :class:`~metaseed.api.client.MetaseedClient` holding the imported
        Investigation -> Study -> ObservationUnit -> Sample tree, on a profile
        derived from the Sample Types encountered.
    """
    inv = client.get(f"/investigations/{investigation_id}")["data"]

    # -- pass 1: walk the tree, collecting nodes and the field union per level --
    studies: list[dict[str, Any]] = []
    reader = _SampleReader(client)
    for study_ref in inv.get("relationships", {}).get("studies", {}).get("data", []):
        study = client.get(f"/studies/{study_ref['id']}")["data"]
        study["_ous"] = _read_observation_units(client, study_ref["id"], reader)
        assays, chain_sources, chain_samples, materials = _read_assays_and_chain(
            client, study_ref["id"], reader
        )
        study["_assays"] = assays
        study["_chain_sources"] = chain_sources
        study["_chain_samples"] = chain_samples
        study["_materials"] = materials
        studies.append(study)

    sample_fields = reader.sample_fields
    source_fields = reader.source_fields
    material_fields = reader.material_fields

    # -- derive the profile from what the instance actually holds ---------------
    spec = {
        "name": profile_name,
        "version": "1.0",
        "root_entity": "Investigation",
        "entities": {
            "Investigation": {"fields": _core_fields("Study")},
            "Study": {
                # "Sample" directly under Study catches a chain sample whose
                # input names no Source, so a partial chain still nests.
                "fields": _core_fields("ObservationUnit", "Assay", "Source", "Sample")
            },
            "ObservationUnit": {"fields": _core_fields("Sample")},
            "Assay": {"fields": _core_fields("Sample")},
            "Source": {"fields": _core_fields("Sample") + list(source_fields.values())},
            "Sample": {
                "fields": _core_fields("AssayMaterial") + list(sample_fields.values())
            },
            "AssayMaterial": {
                "fields": _core_fields() + list(material_fields.values())
            },
        },
    }
    dataset = MetaseedClient.from_spec(spec)

    # -- pass 2: build the entities ---------------------------------------------
    def core(node: dict[str, Any]) -> dict[str, Any]:
        attrs = node["attributes"]
        # Use the FDS external identifier, not SEEK's internal row id: it is what a
        # re-export emits as schema:identifier and what "Update from FAIR Data
        # Station" matches on, so the round trip updates rather than duplicates.
        external = attrs.get("external_identifier") or attrs.get("title")
        return {
            "identifier": str(external or node["id"]),
            "title": attrs.get("title") or "",
            "description": attrs.get("description") or "",
        }

    inv_entity = dataset.create_entity("Investigation", core(inv), skip_validation=True)
    for study in studies:
        study_entity = dataset.create_entity(
            "Study", core(study), parent_id=inv_entity.id, skip_validation=True
        )
        for ou in study["_ous"]:
            ou_entity = dataset.create_entity(
                "ObservationUnit",
                core(ou),
                parent_id=study_entity.id,
                skip_validation=True,
            )
            for sample in ou["_samples"]:
                dataset.create_entity(
                    "Sample",
                    _sample_data(sample),
                    parent_id=ou_entity.id,
                    skip_validation=True,
                )
        # The ISA material chain, top down: Source under Study, collection
        # Sample under its Source, assay material under its Sample — the
        # inverse of the input links the sync wrote.
        source_entity_ids: dict[str, str] = {}
        for seek_id, source in study["_chain_sources"].items():
            entity = dataset.create_entity(
                "Source",
                _sample_data(source),
                parent_id=study_entity.id,
                skip_validation=True,
            )
            source_entity_ids[seek_id] = entity.id
        chain_sample_entity_ids: dict[str, str] = {}
        for seek_id, (sample, source_id) in study["_chain_samples"].items():
            entity = dataset.create_entity(
                "Sample",
                _sample_data(sample),
                parent_id=source_entity_ids.get(source_id or "", study_entity.id),
                skip_validation=True,
            )
            chain_sample_entity_ids[seek_id] = entity.id
        for material, parent_id in study["_materials"]:
            dataset.create_entity(
                "AssayMaterial",
                _sample_data(material),
                parent_id=chain_sample_entity_ids[parent_id],
                skip_validation=True,
            )
        for assay in study["_assays"]:
            assay_entity = dataset.create_entity(
                "Assay", core(assay), parent_id=study_entity.id, skip_validation=True
            )
            for sample in assay["_samples"]:
                dataset.create_entity(
                    "Sample",
                    _sample_data(sample),
                    parent_id=assay_entity.id,
                    skip_validation=True,
                )
    return dataset


def _sample_data(sample: dict[str, Any]) -> dict[str, Any]:
    """Reconstruct a Sample's field values from its ``attribute_map``.

    ``Title``/``Description`` route back onto the entity's title/description;
    every other non-empty attribute keeps its name.
    """
    attribute_map = sample["attributes"].get("attribute_map", {})
    # A sample's FDS external identifier is its Title attribute (schema:identifier),
    # not the instance row id — use it so a re-export matches the same resource.
    external = attribute_map.get("Title") or sample["attributes"].get("title")
    data: dict[str, Any] = {"identifier": str(external or sample["id"])}
    for key, value in attribute_map.items():
        if value in (None, "") or _is_input_attribute(key):
            continue
        data[_CORE_ATTRIBUTES.get(key, key)] = value
    return data
