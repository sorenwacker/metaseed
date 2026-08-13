"""A browsable projection of what a profile becomes in SEEK, before any upload.

The SEEK page shows this so a user can see, for the profile and version they
picked, exactly which **Sample Types** (with their columns) provisioning will
create and which **Extended Metadata** attributes the Investigation, Study and
Assay records will carry — without writing anything to SEEK.

Sample Types are read from the same :func:`~metaseed.seek.provision.build_provisioning_plan`
that provisioning executes, so the preview cannot drift from what is created.
Extended Metadata is derived from the non-core fields of the ISA-native
entities, matching what the model TTL carries for the admin flow.
"""

from __future__ import annotations

from dataclasses import dataclass

from metaseed.seek.provision import build_provisioning_plan
from metaseed.seek.roles import entity_jerm_class
from metaseed.seek.values import CORE_FIELDS as _CORE_FIELDS
from metaseed.specs.schema import FieldSpec, ProfileSpec

# ISA-native records that carry Extended Metadata rather than becoming Sample
# Types. ObservationUnit is included: when it keeps its native role it is an ISA
# record, and when a profile re-roles it to Sample it appears under Sample Types
# instead (it is never both, because the role decides which list it lands in).
_EXTENDED_METADATA_ROLES = ("Investigation", "Study", "ObservationUnit", "Assay")


@dataclass(frozen=True)
class PreviewAttribute:
    """One column/attribute as it will appear in SEEK."""

    name: str
    type: str
    required: bool
    controlled_vocabulary: bool = False


@dataclass(frozen=True)
class PreviewSampleType:
    """A Sample Type provisioning will create, and its columns."""

    entity_type: str
    title: str
    attributes: tuple[PreviewAttribute, ...]


@dataclass(frozen=True)
class PreviewExtendedMetadata:
    """An ISA record (Investigation/Study/Assay/ObservationUnit) and the custom
    attributes it carries as SEEK Extended Metadata."""

    role: str
    entity_type: str
    attributes: tuple[PreviewAttribute, ...]


@dataclass(frozen=True)
class ModelPreview:
    """What a profile becomes in SEEK: Sample Types and Extended Metadata."""

    sample_types: tuple[PreviewSampleType, ...]
    extended_metadata: tuple[PreviewExtendedMetadata, ...]


def _field_is_cv(field: FieldSpec) -> bool:
    constraints = field.constraints
    return bool(constraints and getattr(constraints, "enum", None))


def _type_name(field_type: object) -> str:
    """Plain string for a field's type, whether a FieldType enum or a str."""
    return str(getattr(field_type, "value", field_type))


def _extended_metadata(profile: ProfileSpec) -> list[PreviewExtendedMetadata]:
    records: list[PreviewExtendedMetadata] = []
    for name in sorted(profile.entities):
        entity = profile.entities[name]
        role = entity.seek.role if entity.seek else None
        jerm = entity_jerm_class(name, role, entity.ontology_term)
        if jerm not in _EXTENDED_METADATA_ROLES:
            continue
        # Core identity fields are SEEK's own record fields; nested fields are
        # structure. Neither is Extended Metadata.
        attributes = tuple(
            PreviewAttribute(
                name=f.name,
                type=_type_name(f.type),
                required=f.required,
                controlled_vocabulary=_field_is_cv(f),
            )
            for f in entity.fields
            if not f.is_nested() and f.name not in _CORE_FIELDS
        )
        records.append(
            PreviewExtendedMetadata(role=jerm, entity_type=name, attributes=attributes)
        )
    return records


def build_model_preview(profile: ProfileSpec) -> ModelPreview:
    """Project a profile into the SEEK model a user can browse before uploading.

    Args:
        profile: The loaded profile specification.

    Returns:
        The Sample Types (with columns) and Extended Metadata records SEEK will
        hold once the profile is provisioned.
    """
    plan = build_provisioning_plan(profile)
    sample_types = tuple(
        PreviewSampleType(
            entity_type=st.entity_type,
            title=st.title,
            attributes=tuple(
                PreviewAttribute(
                    name=a.title,
                    type=a.attribute_type_title,
                    required=a.required,
                    controlled_vocabulary=a.cv_title is not None,
                )
                for a in st.attributes
            ),
        )
        for st in plan.sample_types
    )
    return ModelPreview(
        sample_types=sample_types,
        extended_metadata=tuple(_extended_metadata(profile)),
    )
