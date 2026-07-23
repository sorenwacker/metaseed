"""Import a SEEK Investigation into a metaseed dataset (SEEK -> metaseed).

The mirror of :mod:`metaseed.seek.fairds` / :mod:`metaseed.seek.sync`, giving the
SEEK adapter a read direction so metaseed can round-trip content in and out of a
live instance (e.g. pull from FAIRDOMHub, edit, push to a local instance).

:func:`import_from_seek` walks a SEEK Investigation over the JSON:API
(Investigation -> Study -> ObservationUnit -> Sample), reads each Sample's
``attribute_map`` and the ISA core fields, and reconstructs a metaseed dataset.
Because SEEK's Sample Types are user-defined, the profile is **derived from the
instance** rather than assumed: one entity per ISA level, with Sample fields (and
their types) taken from the Sample Types encountered. The non-Sample levels keep
only identifier/title/description, and Assays are not imported — see
``docs/architecture/seek-export.md`` for the current import scope.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from metaseed.api.client import MetaseedClient

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


def _core_fields(with_children: str | None) -> list[dict[str, Any]]:
    """The identifier/title/description fields every imported entity carries.

    ``with_children`` is the child entity type an entity nests as a ``list`` field
    (``None`` for a leaf), so the derived profile expresses the ISA hierarchy.
    """
    fields: list[dict[str, Any]] = [
        {"name": "identifier", "type": "string", "required": True},
        {"name": "title", "type": "string"},
        {"name": "description", "type": "string"},
    ]
    if with_children is not None:
        fields.append(
            {
                "name": with_children.lower() + "s",
                "type": "list",
                "items": with_children,
            }
        )
    return fields


def _observation_units(client: SeekClient, study_id: str) -> list[dict[str, Any]]:
    """A study's ObservationUnit refs, or ``[]`` on instances without them.

    ObservationUnits require SEEK's ISA-JSON compliance; an instance without it
    answers the sub-route with a 4xx, so the study imports with no samples rather
    than aborting the whole import.
    """
    import httpx

    try:
        data = client.get(f"/studies/{study_id}/observation_units").get("data", [])
    except httpx.HTTPStatusError as exc:
        # A 4xx means the instance has no ISA-JSON observation-unit route — degrade
        # to "no observation units". Any other status (5xx) or a connect/timeout
        # error is a real failure and must not masquerade as an empty study.
        if 400 <= exc.response.status_code < 500:
            return []
        raise
    return data if isinstance(data, list) else []


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
        if a.get("title") and a["title"] not in _CORE_ATTRIBUTES
    ]
    cache[sample_type_id] = fields
    return fields


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

    # -- pass 1: walk the tree, collecting nodes and the Sample field union -----
    studies: list[dict[str, Any]] = []
    sample_fields: dict[str, dict[str, Any]] = {}  # ordered: field name -> spec
    st_cache: dict[str, list[dict[str, Any]]] = {}  # sample_type_id -> field specs
    for study_ref in inv.get("relationships", {}).get("studies", {}).get("data", []):
        study = client.get(f"/studies/{study_ref['id']}")["data"]
        ous: list[dict[str, Any]] = []
        for ou_ref in _observation_units(client, study_ref["id"]):
            ou = client.get(f"/observation_units/{ou_ref['id']}")["data"]
            samples: list[dict[str, Any]] = []
            for sample_ref in ou["relationships"].get("samples", {}).get("data", []):
                sample = client.get(f"/samples/{sample_ref['id']}")["data"]
                st_id = sample["relationships"]["sample_type"]["data"]["id"]
                for field in _sample_type_fields(client, st_id, st_cache):
                    sample_fields.setdefault(field["name"], field)
                samples.append(sample)
            ou["_samples"] = samples
            ous.append(ou)
        study["_ous"] = ous
        studies.append(study)

    # -- derive the profile from what the instance actually holds ---------------
    sample_type_fields = list(sample_fields.values())
    spec = {
        "name": profile_name,
        "version": "1.0",
        "root_entity": "Investigation",
        "entities": {
            "Investigation": {"fields": _core_fields("Study")},
            "Study": {"fields": _core_fields("ObservationUnit")},
            "ObservationUnit": {"fields": _core_fields("Sample")},
            "Sample": {"fields": _core_fields(None) + sample_type_fields},
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
        if value in (None, ""):
            continue
        data[_CORE_ATTRIBUTES.get(key, key)] = value
    return data
