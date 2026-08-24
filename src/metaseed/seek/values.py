"""Turning dataset node values into what SEEK stores.

Pure functions: no client, no context, nothing to do with where a node sits in
the ISA tree. Kept apart from the walk so both the walk and the placement of an
individual node can use them without importing each other.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Mapping

    from metaseed.api.client import MetaseedClient
    from metaseed.specs.schema import ProfileSpec


# The one definition of SEEK's core fields: which metaseed field names map
# onto a Sample Type's built-in Title/Description attributes. Everything
# else derives from this mapping -- CORE_FIELDS below, the provisioning
# skip-list, the FDS export -- so the five names exist exactly once.
# Core identity/description fields map onto the provisioned Sample Type's
# built-in Title/Description attributes (see :mod:`metaseed.seek.provision`);
# every other scalar field keeps its own name.
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

#: Field names SEEK handles as a sample's core Title/Description rather than as
#: attributes of their own. Derived, not restated: the mapping above is the one
#: place the names live.
CORE_FIELDS = frozenset(_CORE_TO_ATTRIBUTE)


def sample_data(
    values: Mapping[str, Any],
    text_list_fields: frozenset[str] = frozenset(),
    *,
    route_core: bool = True,
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

    ``route_core=False`` keeps every field under its own name: a template-bound
    Sample Type has no built-in ``Title``/``Description`` -- a column called
    ``title`` there is a column of the installed template.
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
        attribute = _CORE_TO_ATTRIBUTE.get(key, key) if route_core else key
        if route_core and key in _CORE_PRIORITY:
            rank = _CORE_PRIORITY[key]
            if attribute in core_winner and core_winner[attribute] <= rank:
                continue  # a higher-priority core field already claimed it
            core_winner[attribute] = rank
            data[attribute] = value
        else:
            data.setdefault(attribute, value)
    return data


def file_fields(entity: Any) -> tuple[str | None, str | None]:
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


def base_url(locations: list[str]) -> str:
    """The common directory URL of a set of file locations (trailing slash)."""

    from os.path import commonprefix

    head, _, _ = commonprefix(locations).rpartition("/")
    return head + "/" if head else ""


def title_of(node: Any, values: Mapping[str, Any]) -> str:
    return str(values.get("title") or node.label or node.id)


def profile_of(client: MetaseedClient) -> ProfileSpec:
    """The ProfileSpec behind a metaseed client, wherever it lives.

    A dataset built from a derived spec (e.g. imported via
    :mod:`metaseed.seek.importer`) carries its ProfileSpec in memory and has no
    installed profile file to load; anything else loads by name. Both the SEEK
    sync and the FDS export need this fallback, so it lives once, here.
    """
    from metaseed.specs.loader import SpecLoader

    in_memory = client.facade.profile_spec
    return in_memory or SpecLoader().load_profile(client.version, client.profile)
