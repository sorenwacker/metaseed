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
    data_files: dict[str, str] = dc_field(default_factory=dict)
    skipped: list[tuple[str, str]] = dc_field(default_factory=list)
    errors: list[tuple[str, str]] = dc_field(default_factory=list)
    # Created in SEEK but attached to no ISA level, so unreachable from the
    # Investigation and dropped on re-import. Counted in ``created_count``
    # because the resource does exist -- listed here because it is not findable.
    unlinked: list[tuple[str, str]] = dc_field(default_factory=list)
    # Sample Type id -> the Assays it was associated with, so an Assay created
    # here can actually hold Samples. Without the link SEEK accepts a Sample of
    # that type but the Assay never shows it.
    sample_type_assays: dict[str, list[str]] = dc_field(default_factory=dict)

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

    client: SeekClient
    project_id: str
    sample_type_ids: Mapping[str, str]
    roles: dict[str, str]
    values_by_node: dict[str, Any]
    text_list_fields_by_entity: dict[str, frozenset[str]]
    file_fields_by_entity: dict[str, tuple[str | None, str | None]]
    files_by_study: dict[str, list[tuple[str, str]]]
    # Sample Type id -> Assay ids that need it, gathered during the walk and
    # applied once afterwards: SEEK replaces the association on each write, so
    # patching per sample would leave only the last one.
    sample_type_assays: dict[str, set[str]]
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
                    title=title, project_id=ctx.project_id, description=description
                )
            )
        elif jerm_class == "Study":
            if investigation_id is None:
                r.skipped.append((node.id, "study has no investigation parent"))
            else:
                next_study = r.studies[node.id] = ctx.client.create_study(
                    title=title,
                    investigation_id=investigation_id,
                    description=description,
                )
        elif jerm_class == "Assay":
            if study_id is None:
                r.skipped.append((node.id, "assay has no study parent"))
            else:
                next_assay = r.assays[node.id] = ctx.client.create_assay(
                    title=title, study_id=study_id
                )
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


def _place_sample(
    ctx: _SyncContext,
    node: Any,
    values: Mapping[str, Any],
    title: str,
    assay_id: str | None = None,
    study_id: str | None = None,
) -> None:
    sample_type_id = ctx.sample_type_ids.get(node.entity_type)
    if sample_type_id is None:
        ctx.result.skipped.append(
            (node.id, f"no provisioned Sample Type for {node.entity_type}")
        )
        return
    data = _sample_data(
        values, ctx.text_list_fields_by_entity.get(node.entity_type, frozenset())
    )
    # SEEK derives a Sample's title from its Title attribute and rejects a blank
    # one; fall back to the same non-blank title the ISA levels use.
    data.setdefault("Title", title)
    if assay_id:
        ctx.sample_type_assays.setdefault(sample_type_id, set()).add(assay_id)
    ctx.result.samples[node.id] = ctx.client.create_sample(
        sample_type_id=sample_type_id,
        project_id=ctx.project_id,
        data=data,
        assay_ids=[assay_id] if assay_id else None,
        study_id=study_id,
    )
    if assay_id is None:
        # SEEK hangs Samples off Assays and ignores a `studies` relationship, so
        # a Sample with no Assay ancestor cannot be linked into the ISA tree at
        # all. Say so rather than report a clean push: it exists in SEEK but
        # nothing walking down from the Investigation will find it.
        ctx.result.unlinked.append(
            (
                node.id,
                f"{node.entity_type} has no Assay ancestor, so it is reachable "
                "only through the project's sample list — nest it under an "
                "Assay-role entity to link it into the ISA tree",
            )
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
    client: SeekClient,
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

    ctx = _SyncContext(
        client=client,
        project_id=project_id,
        sample_type_ids=sample_type_ids,
        roles=roles,
        values_by_node=values_by_node,
        text_list_fields_by_entity=text_list_fields_by_entity,
        file_fields_by_entity=file_fields_by_entity,
        files_by_study=files_by_study,
        sample_type_assays={},
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

    # Associate each Sample Type with the Assays that use it. This is the only
    # supported direction: sending ``sample_types`` on an Assay is answered 200
    # and discarded, so without this an Assay created here holds no Samples.
    for sample_type_id, assay_ids in ctx.sample_type_assays.items():
        try:
            result.sample_type_assays[sample_type_id] = (
                client.add_assays_to_sample_type(
                    sample_type_id=sample_type_id, assay_ids=sorted(assay_ids)
                )
            )
        except Exception as exc:  # one failed link must not abort the batch
            result.errors.append((f"sample_type:{sample_type_id}", str(exc)))

    # One remote DataFile per study, pointing at the study's external storage.
    study_id_to_node = {sid: nid for nid, sid in result.studies.items()}
    for study_id, files in files_by_study.items():
        _create_study_data_file(
            client, project_id, study_id_to_node.get(study_id, study_id), files, result
        )

    return result
