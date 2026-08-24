"""Creating the SEEK resource for one node of the dataset tree.

One function per ISA level. Each takes the sync's context, creates what SEEK
needs at that level, and records the ids the levels below it will need.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from metaseed.seek.context import SyncContext
from metaseed.seek.isa_types import (
    PROTOCOL_ATTRIBUTE,
    entity_level,
    input_field_of,
    is_template_bound,
    protocol_attribute_of,
    sample_type_attribute_plans,
    sample_type_attributes,
    title_attribute_of,
)
from metaseed.seek.payloads import ASSAY_CLASS_IDS, sample_attribute
from metaseed.seek.provision import cv_ids_for_entity
from metaseed.seek.roles import jerm_class_in_profile
from metaseed.seek.templates import (
    CHAIN_LEVELS,
    LEVEL_ORDER,
    seek_level_for,
    template_title,
)
from metaseed.seek.values import CORE_FIELDS, sample_data, title_of

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

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
                    ctx, title, investigation_id, node, values
                )
        elif jerm_class == "Assay":
            if study_id is None:
                r.skipped.append((node.id, "assay has no study parent"))
            else:
                next_assay = r.assays[node.id] = place_assay(
                    ctx, node, title, study_id, values
                )
        elif jerm_class == "Sample":
            next_sample = place_sample(
                ctx, node, values, title, study_id, assay_id, parent_sample_id, depth
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


def template_id_for(
    ctx: SyncContext, level: str, entity: EntityDefSpec | None
) -> str | None:
    """The Template id for one level of the chain, or ``None`` with an error.

    Reported rather than skipped: without a Template the push still succeeds and
    the export then fails inside SEEK, naming nothing useful.
    """
    plans = sample_type_attribute_plans(entity, level=level, linked=level != "source")
    title = template_title(ctx.profile, seek_level_for(level, plans), entity)
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


def _types_with_titles(
    fetch: Callable[[], dict[str, str]],
    *titles: str,
    delays: tuple[float, ...] = (0.2, 0.5, 1.0, 2.0),
) -> dict[str, str]:
    """Fetch a title -> Sample Type id map, waiting out a stale read.

    SEEK's list routes can momentarily omit a record that was just created (its
    authorization tables are maintained by background jobs, and heavy deletions
    queue behind them). One stale read right after ``create_isa_study`` would
    turn every Source under the Study into an unlinked sample, so the lookup
    retries briefly until the expected titles appear. The normal case sees them
    on the first read and never sleeps.
    """
    types = fetch()
    for delay in delays:
        if all(t in types for t in titles):
            break
        time.sleep(delay)
        types = fetch()
    return types


def _register_type(
    ctx: SyncContext,
    type_id: str,
    entity: EntityDefSpec | None,
    linked_to: str | None,
) -> None:
    """Remember what the levels below need to know about a created type."""
    ctx.title_attribute_by_type[type_id] = title_attribute_of(entity)
    if linked_to is not None:
        ctx.linked_type_of[type_id] = linked_to


def _metadata_target(
    attributes_of: Callable[[str], dict[str, tuple[str | None, str]]],
    type_id: str,
    groups: Mapping[str, str],
    name: str,
) -> tuple[str | None, str, tuple[str | None, str]] | None:
    """Where a field lands in an Extended Metadata Type, or None if nowhere.

    Returns ``(nested attribute or None, attribute name, attribute info)``: a
    prefixed field (``site_latitude`` with ``{"site": "location"}``) lands in
    the nested type the prefix names, anything else on the type itself.
    """
    attributes = attributes_of(type_id)
    prefix = next((p for p in groups if name.startswith(p + "_")), None)
    if prefix is not None:
        nested_attribute = groups[prefix]
        nested_type = attributes.get(nested_attribute, (None, ""))[0]
        inner = name[len(prefix) + 1 :]
        nested = attributes_of(nested_type) if nested_type is not None else {}
        if inner in nested:
            return nested_attribute, inner, nested[inner]
        return None
    if name in attributes:
        return None, name, attributes[name]
    return None


def extended_metadata_for(
    ctx: SyncContext, node: Any, values: Mapping[str, Any]
) -> tuple[str, dict[str, Any]] | None:
    """The (type id, values) an Investigation/Study/Assay node pushes as metadata.

    The entity names the installed Extended Metadata Type; its scalar fields
    fill that type's attributes by name, and a prefix group (``site`` ->
    ``location``) fills a nested type from the ``site_*`` fields. Fields the
    type has no attribute for are reported rather than dropped silently; a
    type the instance does not have is an error, since the values cannot land.
    """
    entity = ctx.profile.entities.get(node.entity_type)
    if entity is None or entity.seek is None:
        return None
    config = entity.seek
    type_title = config.extended_metadata
    if not type_title:
        return None
    type_id = ctx.extended_metadata_type_ids.get(type_title)
    if type_id is None:
        ctx.result.errors.append(
            (
                node.id,
                f"no Extended Metadata Type titled {type_title!r} on this SEEK — "
                "an administrator installs it, then re-run",
            )
        )
        return None

    def attributes_of(some_type: str) -> dict[str, tuple[str | None, str]]:
        cache = ctx.extended_metadata_attribute_cache
        if some_type not in cache:
            cache[some_type] = ctx.client.extended_metadata_attributes(some_type)
        return cache[some_type]

    def takes_a_value(attribute: tuple[str | None, str]) -> bool:
        # A "Registered ..." attribute holds a reference to a SEEK record
        # (a data file, a sample, a strain), which no plain value can fill.
        return not attribute[1].startswith("Registered")

    groups = config.extended_metadata_groups or {}
    data: dict[str, Any] = {}
    unknown: list[str] = []
    references: list[str] = []
    for name, value in values.items():
        if name.startswith("_") or value in (None, "", [], {}):
            continue
        field = next((f for f in entity.fields if f.name == name), None)
        # Identity and description fields are the record itself (its title,
        # its description), not metadata attributes beside it.
        if field is None or field.is_nested() or name in CORE_FIELDS:
            continue
        target = _metadata_target(attributes_of, type_id, groups, name)
        if target is None:
            unknown.append(name)
        elif not takes_a_value(target[2]):
            references.append(name)
        elif target[0] is None:
            data[target[1]] = value
        else:
            data.setdefault(target[0], {})[target[1]] = value
    if unknown:
        ctx.result.skipped.append(
            (
                node.id,
                f"{type_title!r} has no attribute for: " + ", ".join(sorted(unknown)),
            )
        )
    if references:
        ctx.result.skipped.append(
            (
                node.id,
                f"{type_title!r} holds a reference to a SEEK record, not a value, "
                "for: " + ", ".join(sorted(references)) + " — not sent",
            )
        )
    return type_id, data


def place_study(
    ctx: SyncContext,
    title: str,
    investigation_id: str,
    node: Any,
    values: Mapping[str, Any],
) -> str:
    """Reuse or create a compliant Study plus the assay stream its Assays hang off.

    A Study is ISA-JSON compliant only once it owns a Source and a Sample
    Collection Sample Type, in that order, the second linking back to the first.
    They are structural: the Assays' types chain to the Sample Collection type
    whether or not any Sample is stored in it.
    """
    source_entity = chain_entity(ctx, 0)
    collection_entity = chain_entity(ctx, 1)
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
            _register_type(ctx, source_id, source_entity, None)
        collection_id = types.get(f"{title} - Sample Collection")
        if collection_id is not None:
            ctx.study_collection_type[existing] = collection_id
            _register_type(ctx, collection_id, collection_entity, source_id)
        stream_id = ctx.client.find_assay_id_by_title(
            f"{title} - stream", study_id=existing
        )
        if stream_id is not None:
            ctx.study_stream[existing] = stream_id
            ctx.result.assay_streams[existing] = stream_id
        return existing

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
        extended_metadata=extended_metadata_for(ctx, node, values),
        source_template_id=template_id_for(ctx, "source", source_entity),
        collection_template_id=template_id_for(
            ctx, "sample_collection", collection_entity
        ),
        collection_title=collection_title,
        collection_attributes=sample_type_attributes(
            collection_entity,
            level="sample_collection",
            isa_tag_ids=ctx.isa_tag_ids,
            cv_ids=cv_ids_for_entity(ctx.cv_ids, chain_entity_name(ctx, 1)),
            linked_sample_type_id=ctx.placeholder_type_id,
        ),
    )
    types = _types_with_titles(
        lambda: ctx.client.study_sample_type_ids(study_id),
        source_title,
        collection_title,
    )
    source_id = types.get(source_title)
    if source_id is not None:
        ctx.study_source_type[study_id] = source_id
        ctx.result.sample_types.append(source_id)
        _register_type(ctx, source_id, source_entity, None)
    collection_id = types.get(collection_title)
    if collection_id is not None:
        ctx.study_collection_type[study_id] = collection_id
        ctx.result.sample_types.append(collection_id)
        _register_type(ctx, collection_id, collection_entity, source_id)
    stream_id = ctx.client.create_isa_assay(
        title=f"{title} - stream",
        study_id=study_id,
        assay_class_id=ASSAY_CLASS_IDS["STREAM"],
    )
    ctx.study_stream[study_id] = stream_id
    ctx.result.assay_streams[study_id] = stream_id
    return study_id


def _input_reference(entity: EntityDefSpec) -> str | None:
    """The entity an ``Input`` field declares it references, if any."""
    for field in entity.fields:
        if field.isa_tag == "input" and field.reference:
            return field.reference.split(".")[0]
    return None


def _assay_chains(ctx: SyncContext, entity_names: list[str]) -> list[list[str]]:
    """Group assay-level entities into the linear chains SEEK can hold.

    An entity whose Input references another assay-level entity continues that
    entity's chain; one referencing a study-level entity (or nothing, at the
    material level) starts a new one; an unreferenced data-file entity joins
    the chain still ending in a material, else the last chain.
    """
    chains: list[list[str]] = []
    chain_of: dict[str, int] = {}
    for name in entity_names:
        reference = _input_reference(ctx.profile.entities[name])
        if reference in chain_of:
            index = chain_of[reference]
        elif (
            reference is None
            and chains
            and (entity_level(ctx.profile.entities[name]) == "assay")
        ):
            # Continue a chain still ending in a material, else the last one.
            open_chains = [
                i
                for i, c in enumerate(chains)
                if entity_level(ctx.profile.entities[c[-1]]) == "material"
            ]
            index = open_chains[0] if open_chains else len(chains) - 1
        else:
            chains.append([])
            index = len(chains) - 1
        chains[index].append(name)
        chain_of[name] = index
    return chains


def assay_level_entities_under(ctx: SyncContext, node: Any) -> list[str]:
    """Template-bound assay-level entities with nodes under this Assay, chain order.

    Each becomes its own SEEK Assay: SEEK gives an Assay exactly one Sample
    Type, so a profile Assay holding both a material and a data-file entity is
    two chained SEEK Assays. Empty for an untagged profile.
    """
    present = sorted({child.entity_type for child in node.children})
    ordered: list[str] = []
    for level in ("material", "assay"):
        for name in present:
            entity = ctx.profile.entities.get(name)
            if is_template_bound(entity) and entity_level(entity) == level:
                ordered.append(name)
    return ordered


def _create_assay(
    ctx: SyncContext,
    title: str,
    study_id: str,
    entity: EntityDefSpec | None,
    entity_name: str,
    level: str,
    input_type_id: str | None,
    extended_metadata: tuple[str, dict[str, Any]] | None = None,
    stream_id: str | None = None,
) -> tuple[str, str | None]:
    """Create one SEEK Assay in a stream (the Study's by default) with its type."""
    sample_type_title = f"{title} - Sample Type"
    assay_id = ctx.client.create_isa_assay(
        title=title,
        study_id=study_id,
        assay_class_id=ASSAY_CLASS_IDS["EXP"],
        assay_stream_id=stream_id or ctx.study_stream.get(study_id),
        input_sample_type_id=input_type_id,
        sample_type_title=sample_type_title,
        sharing=ctx.sharing,
        extended_metadata=extended_metadata,
        sample_type_template_id=template_id_for(ctx, level, entity),
        sample_type_attributes=sample_type_attributes(
            entity,
            level=level,
            isa_tag_ids=ctx.isa_tag_ids,
            cv_ids=cv_ids_for_entity(ctx.cv_ids, entity_name),
            linked_sample_type_id=input_type_id,
        ),
    )
    owned = _types_with_titles(
        lambda: ctx.client.assay_sample_type_ids(assay_id), sample_type_title
    ).get(sample_type_title)
    if owned is not None:
        ctx.assay_sample_type[assay_id] = owned
        _register_type(ctx, owned, entity, input_type_id)
    ctx.assay_protocol[assay_id] = title
    return assay_id, owned


def place_assay(
    ctx: SyncContext, node: Any, title: str, study_id: str, values: Mapping[str, Any]
) -> str:
    """Reuse or create an Assay inside its Study's stream, with its Sample Type.

    Returns the first SEEK Assay's id; a profile Assay that became several
    (one per assay-level entity under it) records the rest in
    ``ctx.assay_entity_types`` under that id.
    """
    existing = ctx.client.find_assay_id_by_title(title, study_id=study_id)
    if existing is not None:
        ctx.result.reused[f"assay:{title}"] = existing
        owned = ctx.client.assay_sample_type_ids(existing).get(f"{title} - Sample Type")
        if owned is not None:
            ctx.assay_sample_type[existing] = owned
        return existing

    collection_id = ctx.study_collection_type.get(study_id)
    entity_names = assay_level_entities_under(ctx, node)
    # The profile Assay's own fields; every SEEK Assay it becomes carries them.
    metadata = extended_metadata_for(ctx, node, values)
    if not entity_names:
        assay_id, _ = _create_assay(
            ctx,
            title,
            study_id,
            chain_entity(ctx, 2),
            chain_entity_name(ctx, 2),
            "assay",
            collection_id,
            metadata,
        )
    else:
        # SEEK Sample Type id per entity placed so far, so an entity whose
        # Input references another can link to that one's type.
        type_by_entity: dict[str, str] = {}
        if source_id := ctx.study_source_type.get(study_id):
            type_by_entity[chain_entity_name(ctx, 0)] = source_id
        if collection_id is not None:
            type_by_entity[chain_entity_name(ctx, 1)] = collection_id
        first_id: str | None = None
        for k, chain in enumerate(_assay_chains(ctx, entity_names)):
            # SEEK splices an assay whose input type another assay in the
            # stream already takes in FRONT of that assay: a stream is a line,
            # never a branch. Every chain beyond the first is its own stream.
            stream_id = ctx.study_stream.get(study_id)
            if k > 0:
                stream_id = ctx.client.create_isa_assay(
                    title=f"{title} - {chain[0]} stream",
                    study_id=study_id,
                    assay_class_id=ASSAY_CLASS_IDS["STREAM"],
                )
                ctx.result.assay_streams[f"{study_id}/{title}/{chain[0]}"] = stream_id
            last_type_at: dict[str, str | None] = {"sample_collection": collection_id}
            for name in chain:
                entity = ctx.profile.entities[name]
                level = entity_level(entity) or "assay"
                before = "material" if level == "assay" else "sample_collection"
                fallback = last_type_at.get(before) or collection_id
                input_type_id = type_by_entity.get(
                    _input_reference(entity) or "", fallback
                )
                template = entity.seek.template if entity.seek else None
                assay_title = (
                    title if len(entity_names) == 1 else f"{title} ({template or name})"
                )
                created_id, owned = _create_assay(
                    ctx,
                    assay_title,
                    study_id,
                    entity,
                    name,
                    level,
                    input_type_id,
                    metadata,
                    stream_id=stream_id,
                )
                if first_id is None:
                    first_id = created_id
                if owned is not None:
                    ctx.assay_entity_types.setdefault(first_id, {})[name] = (
                        created_id,
                        owned,
                    )
                    type_by_entity[name] = owned
                    last_type_at[level] = owned
        assert first_id is not None
        assay_id = first_id
    # An AssayMaterial names its Assay by identifier, not by nesting under it.
    for key in ("identifier", "unique_id", "name", "title"):
        marker = values.get(key)
        if marker:
            ctx.assay_id_by_identifier.setdefault(str(marker), assay_id)
    return assay_id


# An untagged Sample-role node's depth under its Study decides its place in the
# material chain, mirroring CHAIN_LEVELS: 0 = source, 1 = sample collection,
# 2+ = assay material. Named from the one list so the two cannot drift apart.
_ASSAY_DEPTH = CHAIN_LEVELS.index("assay")


def sample_level(ctx: SyncContext, entity_name: str, depth: int) -> str:
    """The chain level of a Sample-role node: from its tags, else its depth."""
    level = entity_level(ctx.profile.entities.get(entity_name))
    if level is not None:
        return level
    if depth >= _ASSAY_DEPTH:
        return "assay"
    return LEVEL_ORDER[depth]


def _input_key(ctx: SyncContext, sample_type_id: str) -> str:
    """The attribute SEEK names a type's input link by: its predecessor's title."""
    predecessor = ctx.linked_type_of.get(sample_type_id)
    title_attribute = ctx.title_attribute_by_type.get(predecessor or "", "Title")
    return f"Input ({title_attribute})"


def _assay_target(
    ctx: SyncContext, entity_name: str, referenced_assay: str | None
) -> tuple[str | None, str | None]:
    """(SEEK assay id, its Sample Type id) a material belongs to."""
    if referenced_assay is None:
        return None, None
    per_entity = ctx.assay_entity_types.get(referenced_assay)
    if per_entity and entity_name in per_entity:
        return per_entity[entity_name]
    return referenced_assay, ctx.assay_sample_type.get(referenced_assay)


def place_sample(
    ctx: SyncContext,
    node: Any,
    values: Mapping[str, Any],
    title: str,
    study_id: str | None = None,
    assay_id: str | None = None,
    parent_sample_id: str | None = None,
    depth: int = 0,
) -> str | None:
    """Create one Sample at its place in the ISA material chain.

    The chain SEEK's ISA-JSON exporter walks is Source -> Sample -> assay
    material, each naming its predecessor. Which Sample Type a node belongs to
    follows from its level -- its title tag when the entity is template-bound,
    else how deep it sits in the nesting:

    - depth 0 (directly under a Study) -> the Study's Source type
    - depth 1 (under a Source) -> the Study's Sample Collection type
    - depth 2+ (under a Sample) -> the Sample Type owned by the Assay it names

    A node *nested under an Assay* (``assay_id``) sits outside the chain —
    profiles without the material levels hang Samples off Assays directly, the
    shape SEEK itself models. Such a Sample goes in that Assay's own type,
    linked to it; a declared assay reference still wins, because explicit data
    beats tree position.

    Returns the created SEEK sample id, so the next level down can name it.
    """
    r = ctx.result
    entity = ctx.profile.entities.get(node.entity_type)
    level = sample_level(ctx, node.entity_type, depth)
    referenced_assay = referenced_assay_id(ctx, node.entity_type, values) or assay_id
    if level in ("material", "assay") or referenced_assay is not None:
        linked_assay, sample_type_id = _assay_target(
            ctx, node.entity_type, referenced_assay
        )
        assay_ids = [linked_assay] if linked_assay else None
    elif level == "sample_collection":
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
    if assay_ids:
        # The post-walk reachability check reads this: a chain is reachable
        # from the Investigation once any node in it holds an Assay link.
        ctx.assay_linked_nodes.add(node.id)

    bound = is_template_bound(entity)
    data = sample_data(
        values,
        ctx.text_list_fields_by_entity.get(node.entity_type, frozenset()),
        route_core=not bound,
    )
    title_attribute = title_attribute_of(entity) if bound else "Title"
    # SEEK derives a Sample's title from its title attribute and rejects a
    # blank one; fall back to the same non-blank title the ISA levels use.
    data.setdefault(title_attribute, title)
    sample_title = str(data[title_attribute])

    input_field = input_field_of(entity) if bound else None
    predecessor_id = parent_sample_id
    if input_field is not None:
        # The profile references its predecessor by title instead of nesting;
        # resolve it among what is already placed in the predecessor type.
        named = data.pop(input_field, None)
        predecessor_type = ctx.linked_type_of.get(sample_type_id)
        names = named if isinstance(named, list) else [named] if named else []
        resolved = [
            ctx.sample_by_type_and_title.get((predecessor_type or "", str(n)))
            for n in names
        ]
        predecessor_id = next((s for s in resolved if s), None)
        if names and predecessor_id is None:
            # Not pushed: the chain is broken here whatever else is sent, and
            # the installed templates require the input, so SEEK would refuse
            # it anyway -- with a message naming the attribute, not the cause.
            r.unlinked.append(
                (
                    node.id,
                    f"{node.entity_type} names {named!r} as its input, but no "
                    "sample with that title was placed in the preceding level",
                )
            )
            return None
    if predecessor_id is not None:
        # The exporter reads this as the sample's input and fails without it.
        data.setdefault(_input_key(ctx, sample_type_id), [predecessor_id])
        ctx.successor_nodes.setdefault(predecessor_id, []).append(node.id)
    if level != "source" or referenced_assay is not None:
        # The exporter rejects a Sample with no protocol. The attribute stays
        # optional on the Sample Type -- a Sample created by other means must not
        # be refused -- but every Sample this sync creates names its step.
        protocol = (
            ctx.assay_protocol.get(referenced_assay, title)
            if referenced_assay
            else title
        )
        protocol_attribute = (
            protocol_attribute_of(entity) if bound else PROTOCOL_ATTRIBUTE
        )
        data.setdefault(protocol_attribute, protocol)

    # Reused when a previous push already created it, for the same reason the
    # containers above are: pushing twice made a second copy of every sample.
    existing = ctx.client.find_sample_id_by_title(
        sample_title, sample_type_id=sample_type_id
    )
    if existing is not None:
        r.reused[node.id] = existing
        r.samples[node.id] = existing
        ctx.sample_by_type_and_title[(sample_type_id, sample_title)] = existing
        return existing

    sample_id = r.samples[node.id] = ctx.client.create_sample(
        sample_type_id=sample_type_id,
        project_id=ctx.project_id,
        data=data,
        assay_ids=assay_ids,
        study_id=study_id,
    )
    ctx.sample_by_type_and_title[(sample_type_id, sample_title)] = sample_id
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
