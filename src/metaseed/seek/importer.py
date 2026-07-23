"""Import a SEEK Investigation into a metaseed dataset (SEEK -> metaseed).

The mirror of :mod:`metaseed.seek.fairds` / :mod:`metaseed.seek.sync`, giving the
SEEK adapter a read direction so metaseed can round-trip content in and out of a
live instance (e.g. pull from FAIRDOMHub, edit, push to a local instance).

:func:`import_from_seek` walks a SEEK Investigation over the JSON:API
(Investigation -> Study -> ObservationUnit -> Sample), reads each Sample's
``attribute_map`` and the ISA core fields, and reconstructs a metaseed dataset.
Because SEEK's Sample Types and Extended Metadata are user-defined, the profile is
**derived from the instance** rather than assumed: one entity per ISA level, with
Sample fields taken from the Sample Types encountered — so no field is dropped.
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


def _sample_field_names(client: SeekClient, sample_type_id: str) -> list[str]:
    """Attribute titles of a Sample Type, minus the ones carried as core fields."""
    detail = client.get(f"/sample_types/{sample_type_id}").get("data", {})
    attributes = detail.get("attributes", {}).get("sample_attributes", [])
    return [
        a["title"]
        for a in attributes
        if a.get("title") and a["title"] not in _CORE_ATTRIBUTES
    ]


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
    sample_fields: dict[str, None] = {}  # ordered set of Sample field names
    for study_ref in inv["relationships"]["studies"]["data"]:
        study = client.get(f"/studies/{study_ref['id']}")["data"]
        ous: list[dict[str, Any]] = []
        for ou_ref in _observation_units(client, study_ref["id"]):
            ou = client.get(f"/observation_units/{ou_ref['id']}")["data"]
            samples: list[dict[str, Any]] = []
            for sample_ref in ou["relationships"].get("samples", {}).get("data", []):
                sample = client.get(f"/samples/{sample_ref['id']}")["data"]
                st_id = sample["relationships"]["sample_type"]["data"]["id"]
                for name in _sample_field_names(client, st_id):
                    sample_fields.setdefault(name, None)
                samples.append(sample)
            ou["_samples"] = samples
            ous.append(ou)
        study["_ous"] = ous
        studies.append(study)

    # -- derive the profile from what the instance actually holds ---------------
    sample_type_fields = [{"name": name, "type": "string"} for name in sample_fields]
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
