"""Extended Metadata and registered-file values for the records a sync creates.

A Study or Assay entity that names an installed Extended Metadata Type
(``seek.extended_metadata``) has its scalar field values pushed into that type
on creation; a prefix group (``seek.extended_metadata_groups``) fills a nested
type. A ``Registered Data file`` attribute -- here or on a Sample Type column --
holds a reference to a SEEK DataFile, so the field's URL is registered as a
remote data file and the record receives its id. See
``docs/architecture/seek-isa-compliance.md``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from metaseed.seek.values import CORE_FIELDS

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from metaseed.seek.context import SyncContext

REGISTERED_DATA_FILE = "Registered Data file"
_URL_SCHEMES = ("http://", "https://")


def registered_data_file(
    ctx: SyncContext, node_id: str, value: Any, title: str
) -> str | None:
    """The SEEK DataFile id a ``Registered Data file`` column holds for ``value``.

    SEEK stores such a column as a reference to a DataFile record, so a URL is
    registered as a remote data file (once per URL) and its id is what the
    column receives. A value that is not a URL cannot be registered; it is
    reported, not sent. Returns None when nothing can be sent.
    """
    if not isinstance(value, str) or not value.startswith(_URL_SCHEMES):
        ctx.result.notes.append(
            (
                node_id,
                f"{title!r} is a Registered Data file column and {value!r} is "
                "not a URL SEEK can register — not sent",
            )
        )
        return None
    if value not in ctx.data_file_by_url:
        basename = value.rstrip("/").rsplit("/", 1)[-1] or value
        # A previous push registered it already: reuse, as every other record.
        existing = ctx.client.find_data_file_id_by_title(
            basename, project_id=ctx.project_id
        )
        if existing is not None:
            ctx.data_file_by_url[value] = existing
            ctx.result.reused[f"{node_id}:{title}"] = existing
            return existing
        try:
            ctx.data_file_by_url[value] = ctx.client.create_data_file(
                title=basename,
                project_id=ctx.project_id,
                url=value,
                original_filename=basename,
            )
        except Exception as exc:
            # SEEK checks the URL when registering a remote file; one it cannot
            # reach is a value not sent, not a record not created.
            ctx.result.notes.append(
                (node_id, f"{title!r}: SEEK could not register {value!r} — {exc}")
            )
            return None
        ctx.result.data_files[f"{node_id}:{title}"] = ctx.data_file_by_url[value]
    return ctx.data_file_by_url[value]


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
    metadata_fields = {
        f.name for f in entity.fields if not f.is_nested() and f.name not in CORE_FIELDS
    }
    for name, value in values.items():
        # Identity and description fields are the record itself (its title,
        # its description), not metadata attributes beside it.
        if name not in metadata_fields or value in (None, "", [], {}):
            continue
        target = _metadata_target(attributes_of, type_id, groups, name)
        if target is None:
            unknown.append(name)
            continue
        nested, attribute, info = target
        if info[1] == REGISTERED_DATA_FILE:
            value = registered_data_file(ctx, node.id, value, name)
            if value is None:
                continue
        elif not takes_a_value(info):
            references.append(name)
            continue
        if nested is None:
            data[attribute] = value
        else:
            data.setdefault(nested, {})[attribute] = value
    _note_metadata_gaps(ctx, node.id, type_title, unknown, references)
    return type_id, data


def _note_metadata_gaps(
    ctx: SyncContext,
    node_id: str,
    type_title: str,
    unknown: list[str],
    references: list[str],
) -> None:
    """Report the values an Extended Metadata Type could not take."""
    if unknown:
        ctx.result.notes.append(
            (
                node_id,
                f"{type_title!r} has no attribute for: " + ", ".join(sorted(unknown)),
            )
        )
    if references:
        ctx.result.notes.append(
            (
                node_id,
                f"{type_title!r} holds a reference to a SEEK record, not a value, "
                "for: " + ", ".join(sorted(references)) + " — not sent",
            )
        )
