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
from metaseed.seek.placement import (
    place_node,
    placeholder_sample_type_id,
    sample_level,
)
from metaseed.seek.roles import jerm_class_in_profile
from metaseed.seek.templates import LEVEL_ORDER, sample_chain_entities
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


def _jerm(ctx: SyncContext, node: Any) -> str | None:
    return jerm_class_in_profile(ctx.profile, node.entity_type, ctx.roles)


def _place_study_contents(
    ctx: SyncContext,
    study_node: Any,
    investigation_id: str | None,
    study_id: str | None,
) -> None:
    """Place everything under a Study in level order, not tree order.

    The SEEK Assays first (a material needs the Assay that measured it), then
    sources, samples, assay materials and assay data files, each level only
    after the one it takes its inputs from. A nested profile and one that
    references its predecessor through an ``Input`` field both satisfy every
    dependency under this order.
    """
    # (order, node, class, assay-ancestor node id, sample-ancestor node id,
    # sample depth) for every node below the Study.
    entries: list[tuple[int, Any, str | None, str | None, str | None, int]] = []

    def collect(
        node: Any, assay_anc: str | None, sample_anc: str | None, depth: int
    ) -> None:
        for child in node.children:
            cls = _jerm(ctx, child)
            entries.append((len(entries), child, cls, assay_anc, sample_anc, depth))
            collect(
                child,
                child.id if cls == "Assay" else assay_anc,
                child.id if cls == "Sample" else sample_anc,
                depth + 1 if cls == "Sample" else depth,
            )

    collect(study_node, None, None, 0)
    seek_assay_by_node: dict[str, str] = {}
    for _, node, cls, _, _, _ in entries:
        if cls == "Assay":
            _, _, seek_assay, _, _ = place_node(
                ctx, node, investigation_id, study_id, None
            )
            if seek_assay is not None:
                seek_assay_by_node[node.id] = seek_assay
    samples = sorted(
        (e for e in entries if e[2] == "Sample"),
        key=lambda e: (
            LEVEL_ORDER.index(sample_level(ctx, e[1].entity_type, e[5])),
            e[0],
        ),
    )
    for _, node, _, assay_anc, sample_anc, depth in samples:
        place_node(
            ctx,
            node,
            investigation_id,
            study_id,
            seek_assay_by_node.get(assay_anc or ""),
            ctx.result.samples.get(sample_anc or ""),
            depth,
        )
    for _, node, cls, _, _, _ in entries:
        if cls not in ("Assay", "Sample"):
            place_node(ctx, node, investigation_id, study_id, None)


def _walk(
    ctx: SyncContext, node: Any, investigation_id: str | None, study_id: str | None
) -> None:
    next_investigation, next_study, _, _, _ = place_node(
        ctx, node, investigation_id, study_id, None
    )
    if _jerm(ctx, node) == "Study":
        _place_study_contents(ctx, node, next_investigation, next_study)
        return
    for child in node.children:
        _walk(ctx, child, next_investigation, next_study)


def _report_unreachable(ctx: SyncContext, roots: list[Any]) -> None:
    """Report every pushed Sample the ISA tree cannot reach.

    A pushed Sample is reachable from the Investigation only through an Assay
    link somewhere down its material chain — SEEK derives Study and
    Investigation from that link and ignores everything else. The chain runs
    through nesting, or through the ``Input`` links the placement resolved;
    a Sample is reachable once any successor along either is. A chain that
    never reaches one is stored but invisible to the ISA tree, and a re-import
    drops it; that is a limitation to report, not to hide.
    """
    children: dict[str, list[str]] = {}
    stack = list(roots)
    while stack:
        node = stack.pop()
        children[node.id] = [c.id for c in node.children]
        stack.extend(node.children)
    reachable = set(ctx.assay_linked_nodes)
    pending = [n for n in ctx.result.samples if n not in reachable]
    changed = True
    while changed:
        changed = False
        for node_id in list(pending):
            successors = children.get(node_id, []) + ctx.successor_nodes.get(
                ctx.result.samples[node_id], []
            )
            if any(s in reachable for s in successors):
                reachable.add(node_id)
                pending.remove(node_id)
                changed = True
    entity_type = {}
    stack = list(roots)
    while stack:
        node = stack.pop()
        entity_type[node.id] = node.entity_type
        stack.extend(node.children)
    for node_id in pending:
        ctx.result.unlinked.append(
            (
                node_id,
                f"{entity_type.get(node_id, 'Sample')} was created, but its "
                "material chain reaches no Assay, so nothing walking the ISA "
                "tree from the Investigation finds it — nest it under an Assay, "
                "or end the chain in a material that names one",
            )
        )


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
        cv_ids: ``"Entity.field" -> Controlled Vocabulary id`` for the
            dataset's enum fields, as ``resolve_cv_ids`` produces them
            (``cv_ids_for_entity`` narrows to bare field names per entity;
            bare keys are accepted for backward compatibility). An enum field
            with no entry here is an error: SEEK rejects a CV attribute with
            no vocabulary.
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

    if any(e.seek and e.seek.extended_metadata for e in profile.entities.values()):
        ctx.extended_metadata_type_ids = client.extended_metadata_type_ids()

    roots = list(metaseed_client.get_tree())
    for root in roots:
        _walk(ctx, root, None, None)
    _report_unreachable(ctx, roots)

    # One remote DataFile per study, pointing at the study's external storage.
    study_id_to_node = {sid: nid for nid, sid in result.studies.items()}
    for study_id, files in files_by_study.items():
        _create_study_data_file(
            client, project_id, study_id_to_node.get(study_id, study_id), files, result
        )

    return result
