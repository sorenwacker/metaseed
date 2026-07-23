"""Push a loaded metaseed dataset into SEEK over the JSON:API (Phase 2).

Walks the dataset's ISA tree and creates the matching SEEK resources —
Investigation → Study → Assay and Samples (into Sample Types provisioned in
Phase 1, see :mod:`metaseed.seek.provision`) — threading the ids SEEK returns so
the hierarchy links up. Per-node failures are collected rather than aborting the
whole sync, so one bad sample doesn't lose the rest.
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field as dc_field
from typing import TYPE_CHECKING, Any

from metaseed.seek.roles import entity_jerm_class
from metaseed.specs.loader import SpecLoader

if TYPE_CHECKING:
    from collections.abc import Mapping

    from metaseed.api.client import MetaseedClient
    from metaseed.seek.client import SeekClient


@dataclass
class SyncResult:
    """Outcome of pushing a dataset to SEEK (node id -> created SEEK id)."""

    investigations: dict[str, str] = dc_field(default_factory=dict)
    studies: dict[str, str] = dc_field(default_factory=dict)
    assays: dict[str, str] = dc_field(default_factory=dict)
    samples: dict[str, str] = dc_field(default_factory=dict)
    skipped: list[tuple[str, str]] = dc_field(default_factory=list)
    errors: list[tuple[str, str]] = dc_field(default_factory=list)

    @property
    def created_count(self) -> int:
        """Total SEEK resources created."""
        return sum(
            len(d)
            for d in (self.investigations, self.studies, self.assays, self.samples)
        )


# Core identity/description fields map onto the provisioned Sample Type's
# built-in Title/Description attributes (see :mod:`metaseed.seek.provision`);
# every other scalar field keeps its own name. Kept in sync with
# ``provision._CORE_FIELDS``.
_CORE_TO_ATTRIBUTE = {
    "identifier": "Title",
    "unique_id": "Title",
    "name": "Title",
    "title": "Title",
    "description": "Description",
}


def _sample_data(values: Mapping[str, Any]) -> dict[str, Any]:
    """The postable attribute map for a Sample: drop metadata keys and empties.

    Core identity/description fields are routed onto the Sample Type's ``Title`` /
    ``Description`` attributes so the keys match what
    :func:`metaseed.seek.provision.build_provisioning_plan` provisions. Scalars
    pass through; a list of scalars is kept (a Controlled Vocabulary List
    attribute expects an array); other structures (nested dicts) are dropped.
    """
    data: dict[str, Any] = {}
    for key, value in values.items():
        if key.startswith("_") or value in (None, "", [], {}):
            continue
        if isinstance(value, (str, int, float, bool)) or (
            isinstance(value, list)
            and all(isinstance(v, (str, int, float, bool)) for v in value)
        ):
            attribute = _CORE_TO_ATTRIBUTE.get(key, key)
            data.setdefault(attribute, value)
    return data


def sync_dataset_to_seek(
    client: SeekClient,
    metaseed_client: MetaseedClient,
    *,
    project_id: str,
    sample_type_ids: Mapping[str, str],
) -> SyncResult:
    """Create Investigations/Studies/Assays/Samples in SEEK from a dataset.

    Args:
        client: An authenticated SEEK client.
        metaseed_client: The metaseed client holding the loaded dataset.
        project_id: SEEK project to attach the created content to.
        sample_type_ids: ``entity_type -> SEEK Sample Type id`` (from a Phase-1
            provisioning run) used to place Samples.

    Returns:
        A :class:`SyncResult` mapping each source node to its created SEEK id,
        plus any skipped/errored nodes.
    """
    profile = SpecLoader().load_profile(
        metaseed_client.version, metaseed_client.profile
    )
    roles = {
        name: entity.seek.role
        for name, entity in profile.entities.items()
        if entity.seek and entity.seek.role
    }
    values_by_node = {
        e.get("_node_id"): e for e in metaseed_client.serialize().get("entities", [])
    }
    result = SyncResult()

    def title_of(node: Any, values: Mapping[str, Any]) -> str:
        raw = values.get("title") or node.label or node.id
        return str(raw)

    def walk(node: Any, investigation_id: str | None, study_id: str | None) -> None:
        values = values_by_node.get(node.id, {})
        jerm_class = entity_jerm_class(node.entity_type, roles.get(node.entity_type))
        title = title_of(node, values)
        description = values.get("description")
        next_investigation, next_study = investigation_id, study_id

        try:
            if jerm_class == "Investigation":
                new_id = client.create_investigation(
                    title=title, project_id=project_id, description=description
                )
                result.investigations[node.id] = new_id
                next_investigation = new_id
            elif jerm_class == "Study":
                if investigation_id is None:
                    result.skipped.append(
                        (node.id, "study has no investigation parent")
                    )
                else:
                    new_id = client.create_study(
                        title=title,
                        investigation_id=investigation_id,
                        description=description,
                    )
                    result.studies[node.id] = new_id
                    next_study = new_id
            elif jerm_class == "Assay":
                if study_id is None:
                    result.skipped.append((node.id, "assay has no study parent"))
                else:
                    result.assays[node.id] = client.create_assay(
                        title=title, study_id=study_id
                    )
            elif jerm_class == "Sample":
                sample_type_id = sample_type_ids.get(node.entity_type)
                if sample_type_id is None:
                    result.skipped.append(
                        (node.id, f"no provisioned Sample Type for {node.entity_type}")
                    )
                else:
                    result.samples[node.id] = client.create_sample(
                        sample_type_id=sample_type_id,
                        project_id=project_id,
                        data=_sample_data(values),
                    )
            else:
                result.skipped.append(
                    (node.id, f"entity type {node.entity_type} is not ISA-mapped")
                )
        except Exception as exc:  # one bad node must not abort the batch
            result.errors.append((node.id, str(exc)))

        for child in node.children:
            walk(child, next_investigation, next_study)

    for root in metaseed_client.get_tree():
        walk(root, None, None)

    return result
