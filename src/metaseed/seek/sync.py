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

from dataclasses import dataclass
from dataclasses import field as dc_field
from typing import TYPE_CHECKING, Any

from metaseed.seek.isa_types import PROTOCOL_ATTRIBUTE as _PROTOCOL_ATTRIBUTE
from metaseed.seek.isa_types import sample_type_attributes
from metaseed.seek.payloads import ASSAY_CLASS_IDS, sample_attribute
from metaseed.seek.roles import entity_jerm_class, sample_role_entities
from metaseed.specs.loader import SpecLoader

if TYPE_CHECKING:
    from collections.abc import Mapping

    from metaseed.api.client import MetaseedClient
    from metaseed.seek.ports import IsaWriter
    from metaseed.specs.schema import EntityDefSpec, ProfileSpec


@dataclass
class SyncResult:
    """Outcome of pushing a dataset to SEEK (node id -> created SEEK id)."""

    investigations: dict[str, str] = dc_field(default_factory=dict)
    studies: dict[str, str] = dc_field(default_factory=dict)
    assays: dict[str, str] = dc_field(default_factory=dict)
    samples: dict[str, str] = dc_field(default_factory=dict)
    data_files: dict[str, str] = dc_field(default_factory=dict)
    skipped: list[tuple[str, str]] = dc_field(default_factory=list)
    errors: list[tuple[str, str]] = dc_field(default_factory=list)
    # Not created: a Sample with no Assay ancestor has no Sample Type to go in,
    # since under ISA-JSON compliance an Assay owns the type its Samples use.
    unlinked: list[tuple[str, str]] = dc_field(default_factory=list)
    # Study id -> the assay stream created for it. Every Assay hangs off one:
    # an assay outside a stream does not render in SEEK's ISA study view.
    assay_streams: dict[str, str] = dc_field(default_factory=dict)

    @property
    def created_count(self) -> int:
        """Total SEEK resources created."""
        return sum(
            len(d)
            for d in (
                self.investigations,
                self.studies,
                self.assays,
                self.samples,
                self.data_files,
            )
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

# When several core fields collapse onto the same single-valued SEEK attribute
# (Title/Description), the winner is chosen by this priority rather than by dict
# insertion order — the most identity-bearing field wins deterministically.
_CORE_PRIORITY = {"unique_id": 0, "identifier": 1, "name": 2, "title": 3}


def _sample_data(
    values: Mapping[str, Any], text_list_fields: frozenset[str] = frozenset()
) -> dict[str, Any]:
    """The postable attribute map for a Sample: drop metadata keys and empties.

    Core identity/description fields are routed onto the Sample Type's ``Title`` /
    ``Description`` attributes so the keys match what
    :func:`metaseed.seek.provision.build_provisioning_plan` provisions. Scalars
    pass through; a list of scalars is kept (a Controlled Vocabulary List
    attribute expects an array); other structures (nested dicts) are dropped.

    Several core fields can map onto one attribute (e.g. ``identifier`` and
    ``title`` both onto ``Title``); the winner is picked deterministically by
    :data:`_CORE_PRIORITY`, not by dict order.

    A list field without an enum is provisioned as a scalar SEEK ``Text``
    attribute (see :data:`metaseed.seek.provision._LIST_FALLBACK_TITLE`), which
    cannot hold an array; ``text_list_fields`` names those fields so their value
    is joined into a string. A list field *with* an enum is a Controlled
    Vocabulary List and keeps its array.
    """
    data: dict[str, Any] = {}
    core_winner: dict[str, int] = {}  # attribute -> priority of the value it holds
    for key, value in values.items():
        if key.startswith("_") or value in (None, "", [], {}):
            continue
        if key in text_list_fields and isinstance(value, list):
            # A scalar Text attribute in SEEK, so collapse the list to a string.
            value = ", ".join(str(v) for v in value if v not in (None, ""))
            if not value:
                continue
        if not (
            isinstance(value, (str, int, float, bool))
            or (
                isinstance(value, list)
                and all(isinstance(v, (str, int, float, bool)) for v in value)
            )
        ):
            continue
        attribute = _CORE_TO_ATTRIBUTE.get(key, key)
        if key in _CORE_PRIORITY:
            rank = _CORE_PRIORITY[key]
            if attribute in core_winner and core_winner[attribute] <= rank:
                continue  # a higher-priority core field already claimed it
            core_winner[attribute] = rank
            data[attribute] = value
        else:
            data.setdefault(attribute, value)
    return data


def _file_fields(entity: Any) -> tuple[str | None, str | None]:
    """(filename field, url field) for a DataFile-role entity."""
    from metaseed.specs.schema import FieldType

    name_field = next(
        (f.name for f in entity.fields if f.name in ("file_name", "filename")),
        next((f.name for f in entity.fields if f.is_label), None),
    )
    url_field = next(
        (f.name for f in entity.fields if f.type == FieldType.URI),
        next(
            (
                f.name
                for f in entity.fields
                if f.name in ("file_location", "url", "location")
            ),
            None,
        ),
    )
    return name_field, url_field


def _base_url(locations: list[str]) -> str:
    """The common directory URL of a set of file locations (trailing slash)."""

    from os.path import commonprefix

    head, _, _ = commonprefix(locations).rpartition("/")
    return head + "/" if head else ""


@dataclass
class _SyncContext:
    """The shared state a node placement needs, so the walk stays a thin recursion."""

    client: IsaWriter
    project_id: str
    profile: ProfileSpec
    sample_entity: str | None
    isa_tag_ids: Mapping[str, str]
    cv_ids: Mapping[str, str]
    roles: dict[str, str]
    values_by_node: dict[str, Any]
    text_list_fields_by_entity: dict[str, frozenset[str]]
    file_fields_by_entity: dict[str, tuple[str | None, str | None]]
    files_by_study: dict[str, list[tuple[str, str]]]
    # SEEK study id -> the Sample Collection Sample Type it owns. Each Assay
    # under that Study chains its own type to this one.
    study_collection_type: dict[str, str]
    # SEEK study id -> its assay stream, which every Assay hangs off.
    study_stream: dict[str, str]
    # SEEK assay id -> the Sample Type that Assay owns, where its Samples go.
    assay_sample_type: dict[str, str]
    # SEEK assay id -> the protocol name its Samples record. The ISA-JSON
    # exporter refuses a Sample with no protocol ("has no protocol"), so every
    # Sample carries the name of the Assay that produced it.
    assay_protocol: dict[str, str]
    # A Sample Type that exists only to satisfy validation while creating a
    # Study; see ``_placeholder_sample_type_id``.
    placeholder_type_id: str
    result: SyncResult


def _title_of(node: Any, values: Mapping[str, Any]) -> str:
    return str(values.get("title") or node.label or node.id)


def _place_node(
    ctx: _SyncContext,
    node: Any,
    investigation_id: str | None,
    study_id: str | None,
    assay_id: str | None = None,
) -> tuple[str | None, str | None, str | None]:
    """Create the SEEK resource for one node; return the ids to thread to children."""
    r = ctx.result
    values = ctx.values_by_node.get(node.id, {})
    jerm_class = entity_jerm_class(node.entity_type, ctx.roles.get(node.entity_type))
    title = _title_of(node, values)
    description = values.get("description")
    next_investigation, next_study, next_assay = investigation_id, study_id, assay_id

    try:
        if jerm_class == "Investigation":
            next_investigation = r.investigations[node.id] = (
                ctx.client.create_investigation(
                    title=title,
                    project_id=ctx.project_id,
                    description=description,
                    # Without this SEEK refuses to export the Investigation as
                    # ISA-JSON, whatever its Studies and Assays look like.
                    isa_json_compliant=True,
                )
            )
        elif jerm_class == "Study":
            if investigation_id is None:
                r.skipped.append((node.id, "study has no investigation parent"))
            else:
                next_study = r.studies[node.id] = _place_study(
                    ctx, title, investigation_id
                )
        elif jerm_class == "Assay":
            if study_id is None:
                r.skipped.append((node.id, "assay has no study parent"))
            else:
                next_assay = r.assays[node.id] = _place_assay(ctx, title, study_id)
        elif jerm_class == "Sample":
            _place_sample(ctx, node, values, title, assay_id, study_id)
        elif jerm_class == "DataFile":
            _collect_file(ctx, node, values, study_id)
        else:
            r.skipped.append(
                (
                    node.id,
                    f"{node.entity_type} has no SEEK role, so it maps to no ISA "
                    "level — set one in the Spec Builder (Sample, Assay, Study or "
                    "Investigation) to include it",
                )
            )
    except Exception as exc:  # one bad node must not abort the batch
        r.errors.append((node.id, str(exc)))
    return next_investigation, next_study, next_assay


def _placeholder_sample_type_id(
    client: IsaWriter, profile_name: str, project_id: str
) -> str:
    """A Sample Type that exists only to get a new Study past validation.

    ``ISAStudy`` validates the Sample Collection type's input attribute *before*
    ``save`` assigns it the real Source type, and the check requires a link to a
    Sample Type that already exists. For a new Study the Source type does not
    exist yet, so any existing id serves; ``save`` then overwrites it. Reused by
    title so a re-sync does not accumulate copies.
    """
    title = f"{profile_name} ISA placeholder"
    existing = client.find_sample_type_id_by_title(title, project_id=project_id)
    if existing is not None:
        return existing
    return client.create_sample_type(
        title=title,
        project_id=project_id,
        attributes=[
            sample_attribute(
                title="Title",
                attribute_type_id=client.sample_attribute_type_id("String"),
                required=True,
                is_title=True,
                pos=1,
            )
        ],
    )


def _sample_entity_def(ctx: _SyncContext) -> EntityDefSpec | None:
    """The profile entity whose fields describe a Sample, if the profile has one."""
    if ctx.sample_entity is None:
        return None
    return ctx.profile.entities.get(ctx.sample_entity)


def _place_study(ctx: _SyncContext, title: str, investigation_id: str) -> str:
    """Create a compliant Study plus the assay stream its Assays hang off.

    A Study is ISA-JSON compliant only once it owns a Source and a Sample
    Collection Sample Type, in that order, the second linking back to the first.
    They are structural: the Assays' types chain to the Sample Collection type
    whether or not any Sample is stored in it.
    """
    entity = _sample_entity_def(ctx)
    source_title = f"{title} - Source"
    collection_title = f"{title} - Sample Collection"
    study_id = ctx.client.create_isa_study(
        title=title,
        investigation_id=investigation_id,
        source_title=source_title,
        source_attributes=sample_type_attributes(
            entity, level="source", isa_tag_ids=ctx.isa_tag_ids, cv_ids=ctx.cv_ids
        ),
        collection_title=collection_title,
        collection_attributes=sample_type_attributes(
            entity,
            level="sample_collection",
            isa_tag_ids=ctx.isa_tag_ids,
            cv_ids=ctx.cv_ids,
            linked_sample_type_id=ctx.placeholder_type_id,
        ),
    )
    types = ctx.client.study_sample_type_ids(study_id)
    collection_id = types.get(collection_title)
    if collection_id is not None:
        ctx.study_collection_type[study_id] = collection_id
    stream_id = ctx.client.create_isa_assay(
        title=f"{title} - stream",
        study_id=study_id,
        assay_class_id=ASSAY_CLASS_IDS["STREAM"],
    )
    ctx.study_stream[study_id] = stream_id
    ctx.result.assay_streams[study_id] = stream_id
    return study_id


def _place_assay(ctx: _SyncContext, title: str, study_id: str) -> str:
    """Create an Assay inside its Study's stream, owning its own Sample Type."""
    entity = _sample_entity_def(ctx)
    collection_id = ctx.study_collection_type.get(study_id)
    sample_type_title = f"{title} - Sample Type"
    assay_id = ctx.client.create_isa_assay(
        title=title,
        study_id=study_id,
        assay_class_id=ASSAY_CLASS_IDS["EXP"],
        assay_stream_id=ctx.study_stream.get(study_id),
        input_sample_type_id=collection_id,
        sample_type_title=sample_type_title,
        sample_type_attributes=sample_type_attributes(
            entity,
            level="assay",
            isa_tag_ids=ctx.isa_tag_ids,
            cv_ids=ctx.cv_ids,
            linked_sample_type_id=collection_id,
        ),
    )
    owned = ctx.client.assay_sample_type_ids(assay_id).get(sample_type_title)
    if owned is not None:
        ctx.assay_sample_type[assay_id] = owned
    ctx.assay_protocol[assay_id] = title
    return assay_id


def _place_sample(
    ctx: _SyncContext,
    node: Any,
    values: Mapping[str, Any],
    title: str,
    assay_id: str | None = None,
    study_id: str | None = None,
) -> None:
    sample_type_id = ctx.assay_sample_type.get(assay_id) if assay_id else None
    if sample_type_id is None:
        # SEEK hangs Samples off Assays, and under ISA-JSON compliance a Sample's
        # type is the one its Assay owns. With no Assay ancestor there is no type
        # to create it in, so it is reported rather than pushed somewhere it
        # would be unreachable from the Investigation.
        ctx.result.unlinked.append(
            (
                node.id,
                f"{node.entity_type} has no Assay ancestor, so there is no Sample "
                "Type to place it in — nest it under an Assay-role entity to "
                "link it into the ISA tree",
            )
        )
        return
    data = _sample_data(
        values, ctx.text_list_fields_by_entity.get(node.entity_type, frozenset())
    )
    # SEEK derives a Sample's title from its Title attribute and rejects a blank
    # one; fall back to the same non-blank title the ISA levels use.
    data.setdefault("Title", title)
    # The exporter rejects a Sample with no protocol. The attribute stays
    # optional on the Sample Type -- a Sample created by other means must not be
    # refused -- but every Sample this sync creates names its Assay as the step
    # that produced it.
    if assay_id is not None:
        data.setdefault(_PROTOCOL_ATTRIBUTE, ctx.assay_protocol.get(assay_id, title))
    ctx.result.samples[node.id] = ctx.client.create_sample(
        sample_type_id=sample_type_id,
        project_id=ctx.project_id,
        data=data,
        assay_ids=[assay_id] if assay_id else None,
        study_id=study_id,
    )


def _collect_file(
    ctx: _SyncContext, node: Any, values: Mapping[str, Any], study_id: str | None
) -> None:
    if study_id is None:
        ctx.result.skipped.append((node.id, "data file has no study parent"))
        return
    name_f, url_f = ctx.file_fields_by_entity.get(node.entity_type, (None, None))
    filename = str((name_f and values.get(name_f)) or node.label or node.id)
    location = str((url_f and values.get(url_f)) or "")
    ctx.files_by_study.setdefault(study_id, []).append((filename, location))


def _create_study_data_file(
    client: IsaWriter,
    project_id: str,
    node_id: str,
    files: list[tuple[str, str]],
    result: SyncResult,
) -> None:
    """Register a study's external files as one remote SEEK data file."""
    base_url = _base_url([loc for _, loc in files if loc])
    if not base_url:
        result.skipped.append(
            (node_id, f"{len(files)} data file(s) have no location URL to link to")
        )
        return
    try:
        result.data_files[node_id] = client.create_data_file(
            title=f"Data files ({len(files)})",
            project_id=project_id,
            url=base_url,
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

    Returns:
        A :class:`SyncResult` mapping each source node to its created SEEK id,
        plus any skipped/errored/unlinked nodes.
    """
    # A dataset built from a derived spec (e.g. imported via
    # ``metaseed.seek.importer``) carries its ProfileSpec in memory and has no
    # installed profile file to load; fall back to loading by name otherwise.
    # Kept in sync with ``fairds._profile_index``.
    in_memory = getattr(metaseed_client._facade, "_spec", None)
    profile = in_memory or SpecLoader().load_profile(
        metaseed_client.version, metaseed_client.profile
    )
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
        name: _file_fields(entity) for name, entity in profile.entities.items()
    }
    # study_id -> list of (filename, location) gathered from its DataFile nodes.
    files_by_study: dict[str, list[tuple[str, str]]] = {}

    values_by_node = {
        e.get("_node_id"): e for e in metaseed_client.serialize().get("entities", [])
    }
    result = SyncResult()

    # The entity whose fields describe a Sample. Its projection becomes the
    # Study's Source and Sample Collection types and each Assay's own type.
    sample_entities = sorted(sample_role_entities(profile))
    ctx = _SyncContext(
        client=client,
        project_id=project_id,
        profile=profile,
        sample_entity=sample_entities[0] if sample_entities else None,
        isa_tag_ids=client.isa_tag_ids(),
        cv_ids=cv_ids or {},
        roles=roles,
        values_by_node=values_by_node,
        text_list_fields_by_entity=text_list_fields_by_entity,
        file_fields_by_entity=file_fields_by_entity,
        files_by_study=files_by_study,
        study_collection_type={},
        study_stream={},
        assay_sample_type={},
        assay_protocol={},
        placeholder_type_id=_placeholder_sample_type_id(
            client, profile.name, project_id
        ),
        result=result,
    )

    def walk(
        node: Any,
        investigation_id: str | None,
        study_id: str | None,
        assay_id: str | None,
    ) -> None:
        next_investigation, next_study, next_assay = _place_node(
            ctx, node, investigation_id, study_id, assay_id
        )
        for child in node.children:
            walk(child, next_investigation, next_study, next_assay)

    for root in metaseed_client.get_tree():
        walk(root, None, None, None)

    # One remote DataFile per study, pointing at the study's external storage.
    study_id_to_node = {sid: nid for nid, sid in result.studies.items()}
    for study_id, files in files_by_study.items():
        _create_study_data_file(
            client, project_id, study_id_to_node.get(study_id, study_id), files, result
        )

    return result
