"""Project a metaseed ``ProfileSpec`` into a FAIRDOM-SEEK configuration.

Routing is driven by explicit ``seek`` blocks on the profile (see
``SeekEntityConfig``/``SeekFieldConfig`` in ``metaseed.specs.schema``):

- entities tagged ``artifact: sample_type`` → a SEEK **Sample Type** created via
  the JSON:API (enum fields become **Controlled Vocabularies**);
- entities tagged ``artifact: extended_metadata`` → a **JSON artifact** the SEEK
  admin uploads (SEEK's API cannot create Extended Metadata Types — ``POST
  /extended_metadata_types`` redirects to the HTML admin form);
- entities with **no** ``seek`` block are **skipped** (e.g. structural ISA
  objects that are native in SEEK).

Only sample types and controlled vocabularies are pushed live; the extended
metadata is returned as JSON for manual upload.
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field as dc_field
from typing import TYPE_CHECKING, Any

from metaseed.seek import payloads
from metaseed.specs.schema import FieldType

if TYPE_CHECKING:
    from metaseed.seek.client import SeekClient
    from metaseed.specs.schema import EntityDefSpec, FieldSpec, ProfileSpec

# metaseed field type -> SEEK base sample-attribute-type title.
_FIELD_TYPE_TO_SEEK: dict[FieldType, str] = {
    FieldType.STRING: "String",
    FieldType.INTEGER: "Integer",
    FieldType.FLOAT: "Real number",
    FieldType.BOOLEAN: "Boolean",
    FieldType.DATE: "Date",
    FieldType.DATETIME: "Date time",
    FieldType.URI: "Web link",
    FieldType.ONTOLOGY_TERM: "Text",
    FieldType.LIST: "String",
    FieldType.ENTITY: "String",
}
_CV_TYPE_TITLE = "Controlled Vocabulary"
_TITLE_TYPES = ("String", "Text")
_PREFERRED_TITLE_NAMES = ("title", "name", "identifier", "unique_id", "alias")


def _field_enum(field: FieldSpec) -> list[str] | None:
    if field.constraints and field.constraints.enum:
        return list(field.constraints.enum)
    return None


def _seek_type_title(field: FieldSpec) -> str:
    return _FIELD_TYPE_TO_SEEK.get(field.type, "String")


def _title_index(fields: list[FieldSpec]) -> int:
    """Pick which field becomes the Sample Type's title attribute."""
    for name in _PREFERRED_TITLE_NAMES:
        for i, f in enumerate(fields):
            if f.name == name:
                return i
    for i, f in enumerate(fields):
        if f.type == FieldType.STRING:
            return i
    return 0


@dataclass(frozen=True)
class ProfilePushResult:
    """What a :func:`push_profile` run created live and generated for upload."""

    project: str
    sample_types: dict[str, str] = dc_field(default_factory=dict)
    controlled_vocabularies: dict[str, str] = dc_field(default_factory=dict)
    # Extended Metadata Type JSON artifacts (admin uploads these; not API-created).
    extended_metadata: list[dict[str, Any]] = dc_field(default_factory=list)
    skipped: list[str] = dc_field(default_factory=list)


def _extended_metadata_json(
    profile: ProfileSpec, entity_name: str, entity: EntityDefSpec
) -> dict[str, Any]:
    """Build the Extended Metadata Type JSON for one ``extended_metadata`` entity."""
    attributes: list[dict[str, Any]] = []
    for field in entity.fields:
        enum = _field_enum(field)
        attr: dict[str, Any] = {
            "title": field.name,
            "label": (field.seek.label if field.seek else None) or field.name,
            "required": field.required,
            "type": _CV_TYPE_TITLE if enum else _seek_type_title(field),
        }
        if enum:
            attr["controlled_vocabulary"] = {
                "name": f"{entity_name}.{field.name}",
                "terms": enum,
            }
        if field.seek and field.seek.isa_tag:
            attr["isa_tag"] = field.seek.isa_tag
        attributes.append(attr)
    supported = entity.seek.supported_type if entity.seek else None
    return {
        "title": f"{profile.name}: {entity_name}",
        "supported_type": supported or entity_name,
        "enabled": True,
        "attributes": attributes,
    }


def extended_metadata_json(
    profile: ProfileSpec, entity_name: str
) -> dict[str, Any] | None:
    """Public helper: the Extended Metadata JSON for one entity, or ``None``.

    Pure (no I/O). Returns ``None`` unless the entity exists and is tagged
    ``artifact: extended_metadata``.
    """
    entity = profile.entities.get(entity_name)
    if (
        entity is None
        or entity.seek is None
        or entity.seek.artifact != "extended_metadata"
    ):
        return None
    return _extended_metadata_json(profile, entity_name, entity)


class _ProfilePush:
    """Per-run state: id caches, CV dedup, and the accumulating result."""

    def __init__(self, client: SeekClient, project: str) -> None:
        self._client = client
        self._project = project
        self._type_ids: dict[str, str] = {}
        self._cv_by_values: dict[tuple[str, ...], str] = {}
        self.result = ProfilePushResult(project=project)

    def _type_id(self, title: str) -> str:
        if title not in self._type_ids:
            self._type_ids[title] = self._client.sample_attribute_type_id(title)
        return self._type_ids[title]

    def _cv_id(self, entity_title: str, field_name: str, values: tuple[str, ...]) -> str:
        cv_id = self._cv_by_values.get(values)
        if cv_id is None:
            cv_title = f"{entity_title}.{field_name}"
            cv_id = self._client.create_controlled_vocabulary(
                title=cv_title, terms=list(values)
            )
            self._cv_by_values[values] = cv_id
            self.result.controlled_vocabularies[cv_title] = cv_id
        return cv_id

    def _sample_type_attributes(
        self, entity: EntityDefSpec, entity_title: str
    ) -> list[dict[str, Any]]:
        title_idx = _title_index(entity.fields)
        attributes: list[dict[str, Any]] = []
        for i, field in enumerate(entity.fields):
            is_title = i == title_idx
            enum = _field_enum(field)
            if enum and not is_title:
                attributes.append(
                    payloads.sample_attribute(
                        title=field.name,
                        attribute_type_id=self._type_id(_CV_TYPE_TITLE),
                        required=field.required,
                        controlled_vocab_id=self._cv_id(
                            entity_title, field.name, tuple(enum)
                        ),
                    )
                )
            else:
                seek_title = _seek_type_title(field)
                if is_title and seek_title not in _TITLE_TYPES:
                    seek_title = "String"
                attributes.append(
                    payloads.sample_attribute(
                        title=field.name,
                        attribute_type_id=self._type_id(seek_title),
                        required=field.required,
                        is_title=is_title,
                    )
                )
        return attributes

    def run(self, profile: ProfileSpec) -> ProfilePushResult:
        existing_titles = self._client.list_sample_type_titles()
        for entity_name, entity in profile.entities.items():
            seek = entity.seek
            if seek is None or not entity.fields:
                self.result.skipped.append(entity_name)
                continue
            title = f"{profile.name}: {entity_name}"
            if seek.artifact == "extended_metadata":
                self.result.extended_metadata.append(
                    _extended_metadata_json(profile, entity_name, entity)
                )
            elif seek.artifact == "sample_type":
                if title in existing_titles:
                    self.result.skipped.append(entity_name)
                    continue
                sample_type_id = self._client.create_sample_type(
                    title=title,
                    project_id=self._project,
                    attributes=self._sample_type_attributes(entity, title),
                )
                self.result.sample_types[entity_name] = sample_type_id
        return self.result


def push_profile(
    client: SeekClient,
    profile: ProfileSpec,
    *,
    project_id: str | None = None,
) -> ProfilePushResult:
    """Push a profile's SEEK-annotated entities into a SEEK instance.

    Sample-type entities (and their enum controlled vocabularies) are created via
    the API; extended-metadata entities are returned as JSON artifacts for the
    admin to upload; unannotated entities are skipped.
    """
    project = project_id or client.default_project_id()
    return _ProfilePush(client, project).run(profile)
