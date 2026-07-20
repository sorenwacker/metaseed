"""Project a metaseed ``ProfileSpec`` into a FAIRDOM-SEEK configuration.

Creates one SEEK **Sample Type** per profile entity, mapping each ``FieldSpec``
to a SEEK sample-type attribute. Fields with an enum constraint become
**Controlled Vocabularies**. After a push, the profile's schema exists in SEEK,
so users can register samples against it through SEEK's own frontend.

Scope/limitations (first increment): list/entity/reference fields map to plain
String attributes (proper "Registered Sample" links are deferred); the ISA
structural entities (Investigation/Study/Assay) are projected as Sample Types
too, which is a mechanical, complete projection rather than SEEK's native ISA
modelling.
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
    # list / entity references have no 1:1 SEEK attribute yet -> plain text.
    FieldType.LIST: "String",
    FieldType.ENTITY: "String",
}
_CV_TYPE_TITLE = "Controlled Vocabulary"
_TITLE_TYPES = ("String", "Text")
_PREFERRED_TITLE_NAMES = ("title", "name", "identifier", "unique_id", "alias")


def _field_enum(field: FieldSpec) -> list[str] | None:
    """Return the field's enum values (its fixed vocabulary), or None."""
    if field.constraints and field.constraints.enum:
        return list(field.constraints.enum)
    return None


def _title_index(fields: list[FieldSpec]) -> int:
    """Pick which field becomes the Sample Type's title attribute.

    Prefers a field named title/name/identifier/…; else the first string field;
    else the first field. SEEK requires exactly one title attribute.
    """
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
    """What a :func:`push_profile` run created (or skipped) in SEEK."""

    project: str
    sample_types: dict[str, str] = dc_field(default_factory=dict)
    controlled_vocabularies: dict[str, str] = dc_field(default_factory=dict)
    skipped: list[str] = dc_field(default_factory=list)


class _ProfilePush:
    """Per-run state for pushing a profile: id caches, CV dedup, and the result."""

    def __init__(self, client: SeekClient, project: str) -> None:
        self._client = client
        self._project = project
        self._type_ids: dict[str, str] = {}
        self._cv_by_values: dict[tuple[str, ...], str] = {}
        self.result = ProfilePushResult(project=project)

    def _type_id(self, title: str) -> str:
        """Resolve (and cache) a SEEK base attribute-type id by title."""
        if title not in self._type_ids:
            self._type_ids[title] = self._client.sample_attribute_type_id(title)
        return self._type_ids[title]

    def _cv_id(self, entity_title: str, field_name: str, values: tuple[str, ...]) -> str:
        """Create (once per distinct value-set) a Controlled Vocabulary; return id."""
        cv_id = self._cv_by_values.get(values)
        if cv_id is None:
            cv_title = f"{entity_title}.{field_name}"
            cv_id = self._client.create_controlled_vocabulary(
                title=cv_title, terms=list(values)
            )
            self._cv_by_values[values] = cv_id
            self.result.controlled_vocabularies[cv_title] = cv_id
        return cv_id

    def _attributes(
        self, entity: EntityDefSpec, entity_title: str
    ) -> list[dict[str, Any]]:
        """Build the ``sample_attributes`` list for one entity, creating CVs as needed."""
        title_idx = _title_index(entity.fields)
        attributes: list[dict[str, Any]] = []
        for i, field in enumerate(entity.fields):
            is_title = i == title_idx
            enum = _field_enum(field)
            # A field that is both the title and enum-constrained keeps its enum
            # only as plain text: SEEK requires the title attribute to be text.
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
                seek_title = _FIELD_TYPE_TO_SEEK.get(field.type, "String")
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
        """Create a Sample Type per entity, skipping titles that already exist."""
        existing_titles = self._client.list_sample_type_titles()
        for entity_name, entity in profile.entities.items():
            title = f"{profile.name}: {entity_name}"
            if not entity.fields or title in existing_titles:
                self.result.skipped.append(entity_name)
                continue
            sample_type_id = self._client.create_sample_type(
                title=title,
                project_id=self._project,
                attributes=self._attributes(entity, title),
            )
            self.result.sample_types[entity_name] = sample_type_id
        return self.result


def push_profile(
    client: SeekClient,
    profile: ProfileSpec,
    *,
    project_id: str | None = None,
) -> ProfilePushResult:
    """Create SEEK Sample Types (and Controlled Vocabularies) from a profile.

    Args:
        client: A configured :class:`~metaseed.seek.client.SeekClient`.
        profile: The metaseed profile whose entities become Sample Types.
        project_id: Project to attach the Sample Types to; defaults to the
            instance's first project.

    Returns:
        The ids SEEK assigned, plus the names of any entities skipped because a
        Sample Type of that title already existed (or the entity had no fields).
    """
    project = project_id or client.default_project_id()
    return _ProfilePush(client, project).run(profile)
