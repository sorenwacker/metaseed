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

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from metaseed.seek.attribute_types import attribute_type_title, is_cv_field
from metaseed.seek.payloads import isa_sample_attribute

if TYPE_CHECKING:
    from collections.abc import Mapping

    from metaseed.specs.schema import EntityDefSpec, FieldSpec

# ISA level -> (tag on the title attribute, default tag on the other fields).
# The title tag is what SEEK's validation counts: a Sample Collection type needs
# exactly one `sample`, an assay type exactly one `data_file` or `other_material`.
_LEVEL_TAGS: dict[str, tuple[str, str]] = {
    "source": ("source", "source_characteristic"),
    "sample_collection": ("sample", "sample_characteristic"),
    # A data-file level comments its attributes; a material level describes
    # them. Mixing the two families against the title tag is what SEEK's own
    # templates never do.
    "assay": ("data_file", "data_file_comment"),
}

# Levels whose type sits downstream of another and must link back to it.
_LEVELS_NEEDING_A_LINK = frozenset({"sample_collection", "assay"})

_SEEK_SAMPLE_MULTI_TITLE = "Registered Sample List"
PROTOCOL_ATTRIBUTE = "Protocol"
_PROTOCOL_TITLE = PROTOCOL_ATTRIBUTE
_INPUT_TITLE = "Input"


@dataclass(frozen=True)
class AttributePlan:
    """One attribute of a Sample Type, before it is rendered for a destination.

    Carries tag and type *names* rather than instance ids, so the same plan can
    be rendered as ISA form parameters (ids resolved against the target SEEK) or
    into an ISA Template file (which names both by title). The tag rules live
    here once; a second projection would drift from this one.
    """

    title: str
    attribute_type_title: str
    isa_tag: str
    required: bool = False
    is_title: bool = False
    pos: int = 1
    field_name: str | None = None  # the profile field this came from, if any
    enum: tuple[str, ...] = ()


def sample_type_attribute_plans(
    entity: EntityDefSpec | None, *, level: str, linked: bool
) -> list[AttributePlan]:
    """Plan the attributes of the Sample Type ``entity`` becomes at ``level``.

    Args:
        entity: The profile entity whose scalar fields become attributes, or
            ``None`` for a profile with no Sample-role entity at this level --
            the structural attributes every level needs are still planned.
        level: One of ``source``, ``sample_collection`` or ``assay``.
        linked: Whether this level chains to a preceding Sample Type. A Source
            heads the chain and has neither an input nor a protocol attribute.

    Raises:
        ValueError: If ``level`` is unknown.
    """
    if level not in _LEVEL_TAGS:
        raise ValueError(f"level must be one of {sorted(_LEVEL_TAGS)}, got {level!r}")

    title_tag, default_tag = _LEVEL_TAGS[level]
    plans: list[AttributePlan] = []
    position = 1

    if linked:
        # The input attribute must come first: ISAStudy/ISAAssay find it with
        # `detect(&:seek_sample_multi?)`, and `input_attribute?` additionally
        # requires the title to contain "input". Not required: the chain is
        # structural, so demanding a value per Sample would reject every Sample
        # that does not name its predecessor.
        plans.append(
            AttributePlan(
                title=_INPUT_TITLE,
                attribute_type_title=_SEEK_SAMPLE_MULTI_TITLE,
                isa_tag="input",
                pos=position,
            )
        )
        position += 1
        # Only a chained type describes a step, so only it carries a protocol.
        # Optional for the same reason: compliance needs exactly one
        # protocol-tagged attribute, not a value on every Sample.
        plans.append(
            AttributePlan(
                title=_PROTOCOL_TITLE,
                attribute_type_title="String",
                isa_tag="protocol",
                pos=position,
            )
        )
        position += 1

    # Exactly one title attribute, tagged for the level. SEEK derives a Sample's
    # name from it and rejects a blank one, so it is always required.
    plans.append(
        AttributePlan(
            title="Title",
            attribute_type_title="String",
            isa_tag=title_tag,
            required=True,
            is_title=True,
            pos=position,
        )
    )
    position += 1

    for field in entity.fields if entity is not None else ():
        if field.is_nested():
            continue
        plans.append(
            AttributePlan(
                title=field.name,
                attribute_type_title=attribute_type_title(field),
                isa_tag=field.isa_tag or default_tag,
                required=field.required,
                pos=position,
                field_name=field.name,
                enum=_enum_of(field),
            )
        )
        position += 1
    return plans


def _enum_of(field: FieldSpec) -> tuple[str, ...]:
    """The field's closed vocabulary, empty when it declares none."""
    if not is_cv_field(field) or field.constraints is None:
        return ()
    return tuple(field.constraints.enum or ())


def sample_type_attributes(
    entity: EntityDefSpec | None,
    *,
    level: str,
    isa_tag_ids: Mapping[str, str],
    cv_ids: Mapping[str, str] | None = None,
    linked_sample_type_id: str | None = None,
) -> list[dict[str, Any]]:
    """Render the level's plans as ISA form parameters for a target instance.

    Args:
        entity: The profile entity whose scalar fields become attributes.
        level: One of ``source``, ``sample_collection`` or ``assay``.
        isa_tag_ids: ISA tag title -> id, read from the target instance.
        cv_ids: Field name -> Controlled Vocabulary id, for the entity's enum
            fields. Provisioned separately (see
            :func:`metaseed.seek.provision.execute_provisioning_plan`).
        linked_sample_type_id: The Sample Type this one takes its inputs from.
            Required for every level except ``source``.

    Returns:
        Attribute dicts ready for :func:`metaseed.seek.payloads.isa_study_form`
        or :func:`~metaseed.seek.payloads.isa_assay_form`.

    Raises:
        ValueError: If ``level`` is unknown, or a level that chains was given no
            ``linked_sample_type_id`` -- the resulting type would break the chain
            and SEEK would reject it only once the request reached the server.
        KeyError: If a tag is not present on the instance, or an enum field has
            no provisioned Controlled Vocabulary -- SEEK would reject the
            attribute, by which point the field name is no longer in hand.
    """
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

    vocabularies = cv_ids or {}
    attributes: list[dict[str, Any]] = []
    for plan in sample_type_attribute_plans(
        entity, level=level, linked=linked_sample_type_id is not None
    ):
        vocabulary_id: str | None = None
        if plan.enum:
            try:
                vocabulary_id = vocabularies[plan.field_name or plan.title]
            except KeyError:
                raise KeyError(
                    f"field {plan.title!r} declares an enum but has no provisioned "
                    "Controlled Vocabulary; run the provisioning step first"
                ) from None
        attributes.append(
            isa_sample_attribute(
                title=plan.title,
                attribute_type_title=plan.attribute_type_title,
                isa_tag_id=tag(plan.isa_tag),
                required=plan.required,
                is_title=plan.is_title,
                pos=plan.pos,
                linked_sample_type_id=(
                    linked_sample_type_id
                    if plan.isa_tag == "input" and plan.pos == 1
                    else None
                ),
                sample_controlled_vocab_id=vocabulary_id,
            )
        )
    return attributes
