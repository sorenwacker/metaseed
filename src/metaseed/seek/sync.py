"""Push a loaded metaseed dataset into SEEK as ISA-JSON compliant content.

Walks the dataset's ISA tree and creates the matching SEEK resources, threading
the ids SEEK returns so the hierarchy links up. Per-node failures are collected
rather than aborting the whole sync, so one bad sample doesn't lose the rest.

The structure built is the one SEEK can export as ISA-JSON: a compliant
Investigation, a Study owning a Source and a Sample Collection Sample Type, one
assay stream per Study, and one Sample Type per Assay chained to the Study's
Sample Collection type. Sample Types are therefore created *here*, per dataset
node, not in :mod:`metaseed.seek.provision` — a stream chains its types
together, so two assays of the same profile entity need two types with different
links, which a profile-time projection cannot express. Provisioning still builds
its own Sample Types for the FAIR-Data-Station file route, which matches samples
by attribute PID.

See ``docs/architecture/seek-isa-compliance.md``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from metaseed.seek.context import SyncContext, SyncResult
from metaseed.seek.placement import place_node, placeholder_sample_type_id
from metaseed.seek.roles import jerm_class_in_profile
from metaseed.seek.templates import sample_chain_entities
from metaseed.seek.values import base_url, file_fields, profile_of

if TYPE_CHECKING:
    from collections.abc import Mapping

    from metaseed.api.client import MetaseedClient
    from metaseed.seek.ports import IsaWriter


def _create_study_data_file(
    client: IsaWriter,
    project_id: str,
    node_id: str,
    files: list[tuple[str, str]],
    result: SyncResult,
) -> None:
    """Register a study's external files as one remote SEEK data file."""
    directory = base_url([loc for _, loc in files if loc])
    if not directory:
        result.skipped.append(
            (node_id, f"{len(files)} data file(s) have no location URL to link to")
        )
        return
    try:
        result.data_files[node_id] = client.create_data_file(
            title=f"Data files ({len(files)})",
            project_id=project_id,
            url=directory,
            original_filename=f"{len(files)} files in external storage",
            description="Files: " + ", ".join(fn for fn, _ in files),
        )
    except Exception as exc:  # one study's files must not abort the sync
        result.errors.append((node_id, str(exc)))


def sync_dataset_to_seek(
    client: IsaWriter,
    metaseed_client: MetaseedClient,
    *,
    project_id: str,
    cv_ids: Mapping[str, str] | None = None,
    sharing: str | None = None,
) -> SyncResult:
    """Create ISA-JSON compliant SEEK content from a loaded dataset.

    Args:
        client: Anything satisfying :class:`~metaseed.seek.ports.IsaWriter` — in
            production a :class:`~metaseed.seek.client.SeekClient`.
        metaseed_client: The metaseed client holding the loaded dataset.
        project_id: SEEK project to attach the created content to.
        cv_ids: ``field name -> Controlled Vocabulary id`` for the dataset's enum
            fields, from a provisioning run. An enum field with no entry here is
            an error: SEEK rejects a CV attribute with no vocabulary.
        sharing: The SEEK sharing level to apply -- one of
            :data:`~metaseed.seek.payloads.SHARING_LEVELS`. ``None`` leaves
            SEEK's own default, which is private to the contributor. Note that
            ISA-JSON export needs at least ``download``, because ``export_isa``
            authorizes as :download.

    Returns:
        A :class:`SyncResult` mapping each source node to its created SEEK id,
        plus any skipped/errored/unlinked nodes.
    """
    profile = profile_of(metaseed_client)
    roles = {
        name: entity.seek.role
        for name, entity in profile.entities.items()
        if entity.seek and entity.seek.role
    }
    # A list field with no enum is provisioned as a scalar SEEK Text attribute,
    # so its value must be a string, not an array. Mirrors provision's rule.
    from metaseed.specs.schema import FieldType

    text_list_fields_by_entity = {
        name: frozenset(
            f.name
            for f in entity.fields
            if f.type == FieldType.LIST and not (f.constraints and f.constraints.enum)
        )
        for name, entity in profile.entities.items()
    }

    file_fields_by_entity = {
        name: file_fields(entity) for name, entity in profile.entities.items()
    }
    # study_id -> list of (filename, location) gathered from its DataFile nodes.
    files_by_study: dict[str, list[tuple[str, str]]] = {}

    values_by_node = {
        e.get("_node_id"): e for e in metaseed_client.serialize().get("entities", [])
    }
    result = SyncResult()

    # Fields whose declared ``reference`` names an Assay-role entity are the
    # only way a material links to its Assay.
    assay_role_entities = {name for name, role in roles.items() if role == "Assay"} | {
        name
        for name in profile.entities
        if jerm_class_in_profile(profile, name, roles) == "Assay"
    }
    assay_reference_fields = {
        name: [
            f.name
            for f in entity.fields
            if f.reference and f.reference.split(".")[0] in assay_role_entities
        ]
        for name, entity in profile.entities.items()
    }

    ctx = SyncContext(
        client=client,
        project_id=project_id,
        profile=profile,
        chain_entities=sample_chain_entities(profile),
        assay_reference_fields=assay_reference_fields,
        isa_tag_ids=client.isa_tag_ids(),
        cv_ids=cv_ids or {},
        roles=roles,
        values_by_node=values_by_node,
        text_list_fields_by_entity=text_list_fields_by_entity,
        file_fields_by_entity=file_fields_by_entity,
        files_by_study=files_by_study,
        study_source_type={},
        study_collection_type={},
        study_stream={},
        assay_sample_type={},
        assay_protocol={},
        assay_id_by_identifier={},
        template_ids=client.template_ids_by_title(),
        sharing=sharing,
        placeholder_type_id=placeholder_sample_type_id(
            client, profile.name, project_id
        ),
        result=result,
    )

    def walk(
        node: Any,
        investigation_id: str | None,
        study_id: str | None,
        assay_id: str | None,
        parent_sample_id: str | None = None,
        depth: int = 0,
    ) -> None:
        placed = place_node(
            ctx, node, investigation_id, study_id, assay_id, parent_sample_id, depth
        )
        next_investigation, next_study, next_assay, next_sample, next_depth = placed
        # Assays first: a material names the Assay that measured it, so every
        # Assay under this node must exist before any material is placed.
        assay_children = [
            child
            for child in node.children
            if jerm_class_in_profile(ctx.profile, child.entity_type, ctx.roles)
            == "Assay"
        ]
        for child in [
            *assay_children,
            *(c for c in node.children if c not in assay_children),
        ]:
            walk(
                child,
                next_investigation,
                next_study,
                next_assay,
                next_sample,
                next_depth,
            )

    for root in metaseed_client.get_tree():
        walk(root, None, None, None)

    # One remote DataFile per study, pointing at the study's external storage.
    study_id_to_node = {sid: nid for nid, sid in result.studies.items()}
    for study_id, files in files_by_study.items():
        _create_study_data_file(
            client, project_id, study_id_to_node.get(study_id, study_id), files, result
        )

    return result
