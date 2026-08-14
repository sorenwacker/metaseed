"""Creating the SEEK resource for one node of the dataset tree.

One function per ISA level. Each takes the sync's context, creates what SEEK
needs at that level, and records the ids the levels below it will need.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from metaseed.seek.context import SyncContext
from metaseed.seek.isa_types import (
    PROTOCOL_ATTRIBUTE,
    sample_type_attribute_plans,
    sample_type_attributes,
)
from metaseed.seek.payloads import ASSAY_CLASS_IDS, sample_attribute
from metaseed.seek.provision import cv_ids_for_entity
from metaseed.seek.roles import jerm_class_in_profile
from metaseed.seek.templates import CHAIN_LEVELS, seek_level_for, template_title
from metaseed.seek.values import sample_data, title_of

if TYPE_CHECKING:
    from collections.abc import Mapping

    from metaseed.seek.ports import IsaWriter
    from metaseed.specs.schema import EntityDefSpec


def place_node(
    ctx: SyncContext,
    node: Any,
    investigation_id: str | None,
    study_id: str | None,
    assay_id: str | None = None,
    parent_sample_id: str | None = None,
    depth: int = 0,
) -> tuple[str | None, str | None, str | None, str | None, int]:
    """Create the SEEK resource for one node; return the ids to thread to children.

    ``parent_sample_id`` and ``depth`` carry the ISA material chain down the
    walk: each Sample-role node names the one above it as its input, and its
    depth decides which Sample Type it belongs to.
    """
    r = ctx.result
    values = ctx.values_by_node.get(node.id, {})
    jerm_class = jerm_class_in_profile(ctx.profile, node.entity_type, ctx.roles)
    title = title_of(node, values)
    description = values.get("description")
    next_investigation, next_study, next_assay = investigation_id, study_id, assay_id
    next_sample, next_depth = parent_sample_id, depth

    try:
        if jerm_class == "Investigation":
            # A second push of the same dataset used to create a second copy of
            # everything under it. What a previous push made is found by title
            # within the project and reused, the same rule the Sample Type
            # lookup already followed.
            #
            # By title, because SEEK's ids stay in SEEK: nothing here records
            # them. The cost is that renaming a record in the dataset makes the
            # next push create a new one and leave the old behind, which is a
            # rename to do in both places rather than state to keep in step.
            existing = ctx.client.find_investigation_id_by_title(
                title, project_id=ctx.project_id
            )
            if existing is not None:
                r.reused[node.id] = existing
                next_investigation = r.investigations[node.id] = existing
                return (
                    next_investigation,
                    next_study,
                    next_assay,
                    next_sample,
                    next_depth,
                )
            next_investigation = r.investigations[node.id] = (
                ctx.client.create_investigation(
                    title=title,
                    project_id=ctx.project_id,
                    description=description,
                    # Without this SEEK refuses to export the Investigation as
                    # ISA-JSON, whatever its Studies and Assays look like.
                    isa_json_compliant=True,
                    sharing=ctx.sharing,
                )
            )
        elif jerm_class == "Study":
            if investigation_id is None:
                r.skipped.append((node.id, "study has no investigation parent"))
            else:
                next_study = r.studies[node.id] = place_study(
                    ctx, title, investigation_id
                )
        elif jerm_class == "Assay":
            if study_id is None:
                r.skipped.append((node.id, "assay has no study parent"))
            else:
                next_assay = r.assays[node.id] = place_assay(
                    ctx, title, study_id, values
                )
        elif jerm_class == "Sample":
            # An assay material names the Assay that measured it rather than
            # descending from it, so ancestry plays no part here.
            next_sample = place_sample(
                ctx, node, values, title, study_id, parent_sample_id, depth
            )
            next_depth = depth + 1
        elif jerm_class == "DataFile":
            collect_file(ctx, node, values, study_id)
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
    return next_investigation, next_study, next_assay, next_sample, next_depth


def placeholder_sample_type_id(
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


def chain_entity(ctx: SyncContext, level: int) -> EntityDefSpec | None:
    """The profile entity describing the material chain at ``level`` (0 = Source)."""
    if level >= len(ctx.chain_entities):
        return None
    return ctx.profile.entities.get(ctx.chain_entities[level])


def chain_entity_name(ctx: SyncContext, level: int) -> str:
    """The chain entity's NAME at ``level``, or "" past the chain's end."""
    if level >= len(ctx.chain_entities):
        return ""
    return ctx.chain_entities[level]


def template_id_for(ctx: SyncContext, level: str) -> str | None:
    """The Template id for one level of the chain, or ``None`` with an error.

    Reported rather than skipped: without a Template the push still succeeds and
    the export then fails inside SEEK, naming nothing useful.
    """
    entity = chain_entity(ctx, CHAIN_LEVELS.index(level))
    plans = sample_type_attribute_plans(entity, level=level, linked=level != "source")
    title = template_title(ctx.profile, seek_level_for(level, plans))
    template_id = ctx.template_ids.get(title)
    if template_id is None:
        ctx.result.errors.append(
            (
                f"template:{level}",
                f"no ISA Template titled {title!r} on this SEEK — download the "
                "profile's templates from the SEEK page and have an "
                "administrator upload them under Templates, then re-run",
            )
        )
    return template_id


def place_study(ctx: SyncContext, title: str, investigation_id: str) -> str:
    """Reuse or create a compliant Study plus the assay stream its Assays hang off.

    A Study is ISA-JSON compliant only once it owns a Source and a Sample
    Collection Sample Type, in that order, the second linking back to the first.
    They are structural: the Assays' types chain to the Sample Collection type
    whether or not any Sample is stored in it.
    """
    existing = ctx.client.find_study_id_by_title(
        title, investigation_id=investigation_id
    )
    if existing is not None:
        # Recorded like every other reuse, so synced_count minus the ledger
        # says what this push actually created.
        ctx.result.reused[f"study:{title}"] = existing
        # Its Sample Types and stream already exist too; remember them so the
        # Assays and Samples below attach to what is there.
        types = ctx.client.study_sample_type_ids(existing)
        source_id = types.get(f"{title} - Source")
        if source_id is not None:
            ctx.study_source_type[existing] = source_id
        collection_id = types.get(f"{title} - Sample Collection")
        if collection_id is not None:
            ctx.study_collection_type[existing] = collection_id
        stream_id = ctx.client.find_assay_id_by_title(
            f"{title} - stream", study_id=existing
        )
        if stream_id is not None:
            ctx.study_stream[existing] = stream_id
            ctx.result.assay_streams[existing] = stream_id
        return existing

    source_entity = chain_entity(ctx, 0)
    collection_entity = chain_entity(ctx, 1)
    source_title = f"{title} - Source"
    collection_title = f"{title} - Sample Collection"
    study_id = ctx.client.create_isa_study(
        title=title,
        investigation_id=investigation_id,
        source_title=source_title,
        source_attributes=sample_type_attributes(
            source_entity,
            level="source",
            isa_tag_ids=ctx.isa_tag_ids,
            cv_ids=cv_ids_for_entity(ctx.cv_ids, chain_entity_name(ctx, 0)),
        ),
        sharing=ctx.sharing,
        source_template_id=template_id_for(ctx, "source"),
        collection_template_id=template_id_for(ctx, "sample_collection"),
        collection_title=collection_title,
        collection_attributes=sample_type_attributes(
            collection_entity,
            level="sample_collection",
            isa_tag_ids=ctx.isa_tag_ids,
            cv_ids=cv_ids_for_entity(ctx.cv_ids, chain_entity_name(ctx, 1)),
            linked_sample_type_id=ctx.placeholder_type_id,
        ),
    )
    types = ctx.client.study_sample_type_ids(study_id)
    source_id = types.get(source_title)
    if source_id is not None:
        ctx.study_source_type[study_id] = source_id
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


def place_assay(
    ctx: SyncContext, title: str, study_id: str, values: Mapping[str, Any]
) -> str:
    """Reuse or create an Assay inside its Study's stream, with its Sample Type."""
    existing = ctx.client.find_assay_id_by_title(title, study_id=study_id)
    if existing is not None:
        ctx.result.reused[f"assay:{title}"] = existing
        owned = ctx.client.assay_sample_type_ids(existing).get(f"{title} - Sample Type")
        if owned is not None:
            ctx.assay_sample_type[existing] = owned
        return existing

    entity = chain_entity(ctx, 2)
    collection_id = ctx.study_collection_type.get(study_id)
    sample_type_title = f"{title} - Sample Type"
    assay_id = ctx.client.create_isa_assay(
        title=title,
        study_id=study_id,
        assay_class_id=ASSAY_CLASS_IDS["EXP"],
        assay_stream_id=ctx.study_stream.get(study_id),
        input_sample_type_id=collection_id,
        sample_type_title=sample_type_title,
        sharing=ctx.sharing,
        sample_type_template_id=template_id_for(ctx, "assay"),
        sample_type_attributes=sample_type_attributes(
            entity,
            level="assay",
            isa_tag_ids=ctx.isa_tag_ids,
            cv_ids=cv_ids_for_entity(ctx.cv_ids, chain_entity_name(ctx, 2)),
            linked_sample_type_id=collection_id,
        ),
    )
    owned = ctx.client.assay_sample_type_ids(assay_id).get(sample_type_title)
    if owned is not None:
        ctx.assay_sample_type[assay_id] = owned
    ctx.assay_protocol[assay_id] = title
    # An AssayMaterial names its Assay by identifier, not by nesting under it.
    for key in ("identifier", "unique_id", "name", "title"):
        marker = values.get(key)
        if marker:
            ctx.assay_id_by_identifier.setdefault(str(marker), assay_id)
    return assay_id


# A Sample-role node's depth under its Study decides its place in the material
# chain, mirroring CHAIN_LEVELS: 0 = source, 1 = sample collection, 2+ = assay
# material. Named from the one list so the two cannot drift apart.
_SOURCE_DEPTH = CHAIN_LEVELS.index("source")
_COLLECTION_DEPTH = CHAIN_LEVELS.index("sample_collection")
_ASSAY_DEPTH = CHAIN_LEVELS.index("assay")

# SEEK renames a Sample Type's input attribute to ``Input (<predecessor title
# attribute>)`` on save. Every type this module builds names its title attribute
# ``Title``, so the key a Sample writes its input under is fixed.
_INPUT_ATTRIBUTE = "Input (Title)"


def place_sample(
    ctx: SyncContext,
    node: Any,
    values: Mapping[str, Any],
    title: str,
    study_id: str | None = None,
    parent_sample_id: str | None = None,
    depth: int = 0,
) -> str | None:
    """Create one Sample at its place in the ISA material chain.

    The chain SEEK's ISA-JSON exporter walks is Source -> Sample -> assay
    material, each naming its predecessor. Which Sample Type a node belongs to
    follows from how deep it sits in that chain, the same way SEEK reads the ISA
    hierarchy positionally:

    - depth 0 (directly under a Study) -> the Study's Source type
    - depth 1 (under a Source) -> the Study's Sample Collection type
    - depth 2+ (under a Sample) -> the Sample Type owned by the Assay it names

    Returns the created SEEK sample id, so the next level down can name it.
    """
    r = ctx.result
    referenced_assay = referenced_assay_id(ctx, node.entity_type, values)
    if depth >= _ASSAY_DEPTH:
        sample_type_id = (
            ctx.assay_sample_type.get(referenced_assay) if referenced_assay else None
        )
        assay_ids = [referenced_assay] if referenced_assay else None
    elif depth == _COLLECTION_DEPTH:
        sample_type_id = ctx.study_collection_type.get(study_id) if study_id else None
        assay_ids = None
    else:
        sample_type_id = ctx.study_source_type.get(study_id) if study_id else None
        assay_ids = None

    if sample_type_id is None:
        r.unlinked.append(
            (
                node.id,
                f"{node.entity_type} has no Sample Type to go in — an assay "
                "material must name an Assay that exists, and a Source or Sample "
                "must sit under a Study",
            )
        )
        return None

    data = sample_data(
        values, ctx.text_list_fields_by_entity.get(node.entity_type, frozenset())
    )
    # SEEK derives a Sample's title from its Title attribute and rejects a blank
    # one; fall back to the same non-blank title the ISA levels use.
    data.setdefault("Title", title)
    if parent_sample_id is not None:
        # The exporter reads this as the sample's input and fails without it.
        data.setdefault(_INPUT_ATTRIBUTE, [parent_sample_id])
    if depth >= _COLLECTION_DEPTH:
        # The exporter rejects a Sample with no protocol. The attribute stays
        # optional on the Sample Type -- a Sample created by other means must not
        # be refused -- but every Sample this sync creates names its step.
        protocol = (
            ctx.assay_protocol.get(referenced_assay, title)
            if referenced_assay
            else title
        )
        data.setdefault(PROTOCOL_ATTRIBUTE, protocol)

    # Reused when a previous push already created it, for the same reason the
    # containers above are: pushing twice made a second copy of every sample.
    existing = ctx.client.find_sample_id_by_title(title, sample_type_id=sample_type_id)
    if existing is not None:
        r.reused[node.id] = existing
        r.samples[node.id] = existing
        return existing

    sample_id = r.samples[node.id] = ctx.client.create_sample(
        sample_type_id=sample_type_id,
        project_id=ctx.project_id,
        data=data,
        assay_ids=assay_ids,
        study_id=study_id,
    )
    return sample_id


def referenced_assay_id(
    ctx: SyncContext, entity_type: str, values: Mapping[str, Any]
) -> str | None:
    """The SEEK Assay id a material names, if any.

    An Assay measures materials derived from many Samples, so a material names
    its Assay by reference rather than nesting under it — containment cannot
    express that shape.

    Only fields the profile declares as references to an Assay-role entity are
    read. Scanning every value would link a material whose *name* happens to
    equal some assay's identifier — silently, and to the wrong Assay.
    """
    for field_name in ctx.assay_reference_fields.get(entity_type, ()):
        value = values.get(field_name)
        if isinstance(value, str) and value in ctx.assay_id_by_identifier:
            return ctx.assay_id_by_identifier[value]
    return None


def collect_file(
    ctx: SyncContext, node: Any, values: Mapping[str, Any], study_id: str | None
) -> None:
    if study_id is None:
        ctx.result.skipped.append((node.id, "data file has no study parent"))
        return
    name_f, url_f = ctx.file_fields_by_entity.get(node.entity_type, (None, None))
    filename = str((name_f and values.get(name_f)) or node.label or node.id)
    location = str((url_f and values.get(url_f)) or "")
    ctx.files_by_study.setdefault(study_id, []).append((filename, location))
