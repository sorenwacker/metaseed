"""Projecting a profile entity onto an ISA-JSON compliant SEEK Sample Type.

A compliant Sample Type carries an ISA tag on *every* attribute, and the tag set
is constrained per ISA level: a Source type heads the chain, a Sample Collection
type links back to it, and each Assay's type links back to the Sample Collection
type. See ``docs/architecture/seek-isa-compliance.md``.

Kept separate from :mod:`metaseed.seek.provision` because these Sample Types are
built per *dataset node* rather than per profile entity — an assay stream chains
its types together, so two assays of the same entity need two types with
different links, which a profile-time projection cannot express.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from metaseed.seek.payloads import isa_sample_attribute
from metaseed.seek.provision import _attribute_type_title

if TYPE_CHECKING:
    from collections.abc import Mapping

    from metaseed.specs.schema import EntityDefSpec

# ISA level -> (tag on the title attribute, default tag on the other fields).
# The title tag is what SEEK's validation counts: a Sample Collection type needs
# exactly one `sample`, an assay type exactly one `data_file` or `other_material`.
_LEVEL_TAGS: dict[str, tuple[str, str]] = {
    "source": ("source", "source_characteristic"),
    "sample_collection": ("sample", "sample_characteristic"),
    "assay": ("data_file", "other_material_characteristic"),
}

# Levels whose type sits downstream of another and must link back to it.
_LEVELS_NEEDING_A_LINK = frozenset({"sample_collection", "assay"})

_SEEK_SAMPLE_MULTI_TITLE = "Registered Sample List"
_PROTOCOL_TITLE = "Protocol"
_INPUT_TITLE = "Input"


def sample_type_attributes(
    entity: EntityDefSpec,
    *,
    level: str,
    isa_tag_ids: Mapping[str, str],
    linked_sample_type_id: str | None = None,
) -> list[dict[str, Any]]:
    """Attributes for the Sample Type ``entity`` becomes at ``level``.

    Args:
        entity: The profile entity whose scalar fields become attributes.
        level: One of ``source``, ``sample_collection`` or ``assay``.
        isa_tag_ids: ISA tag title -> id, read from the target instance.
        linked_sample_type_id: The Sample Type this one takes its inputs from.
            Required for every level except ``source``.

    Returns:
        Attribute dicts ready for :func:`metaseed.seek.payloads.isa_study_form`
        or :func:`~metaseed.seek.payloads.isa_assay_form`.

    Raises:
        ValueError: If ``level`` is unknown, or a level that chains was given no
            ``linked_sample_type_id`` — the resulting type would break the chain
            and SEEK would reject it only once the request reached the server.
        KeyError: If a tag is not present on the instance.
    """
    if level not in _LEVEL_TAGS:
        raise ValueError(f"level must be one of {sorted(_LEVEL_TAGS)}, got {level!r}")
    if level in _LEVELS_NEEDING_A_LINK and linked_sample_type_id is None:
        raise ValueError(f"level {level!r} must link to the preceding Sample Type")

    def tag(name: str) -> str:
        try:
            return isa_tag_ids[name]
        except KeyError:
            raise KeyError(
                f"the SEEK instance has no ISA tag {name!r}; "
                f"it offers {sorted(isa_tag_ids)}"
            ) from None

    title_tag, default_tag = _LEVEL_TAGS[level]
    attributes: list[dict[str, Any]] = []
    position = 1

    # The input attribute must come first: ISAStudy/ISAAssay find it with
    # `detect(&:seek_sample_multi?)`, and `input_attribute?` additionally
    # requires the title to contain "input".
    if linked_sample_type_id is not None:
        attributes.append(
            isa_sample_attribute(
                title=_INPUT_TITLE,
                attribute_type_title=_SEEK_SAMPLE_MULTI_TITLE,
                isa_tag_id=tag("input"),
                required=True,
                linked_sample_type_id=linked_sample_type_id,
                pos=position,
            )
        )
        position += 1
        # Only a chained type describes a step, so only it carries a protocol.
        attributes.append(
            isa_sample_attribute(
                title=_PROTOCOL_TITLE,
                attribute_type_title="String",
                isa_tag_id=tag("protocol"),
                required=True,
                pos=position,
            )
        )
        position += 1

    # Exactly one title attribute, tagged for the level. SEEK derives a Sample's
    # name from it and rejects a blank one, so it is always required.
    attributes.append(
        isa_sample_attribute(
            title="Title",
            attribute_type_title="String",
            isa_tag_id=tag(title_tag),
            required=True,
            is_title=True,
            pos=position,
        )
    )
    position += 1

    for field in entity.fields:
        if field.is_nested():
            continue
        attributes.append(
            isa_sample_attribute(
                title=field.name,
                attribute_type_title=_attribute_type_title(field),
                isa_tag_id=tag(field.isa_tag or default_tag),
                required=field.required,
                pos=position,
            )
        )
        position += 1
    return attributes
