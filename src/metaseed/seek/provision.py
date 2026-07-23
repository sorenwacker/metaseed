"""Provision a SEEK data model from a metaseed profile (Phase 1).

Two steps, deliberately split:

- :func:`build_provisioning_plan` — pure, deterministic projection of a
  :class:`~metaseed.specs.schema.ProfileSpec` onto the SEEK model surface the
  JSON:API actually lets a project member create: **Controlled Vocabularies**
  (from closed ``enum`` fields) and **Sample Types** (from the profile's
  sample-bearing entities). Optionally enriches CV terms with ontology IRIs via
  an injected :class:`~metaseed.services.ontology.OntologyService`.
- :func:`execute_provisioning_plan` — runs the plan against a
  :class:`~metaseed.seek.client.SeekClient`, **idempotently** (reuse a same-named
  CV/Sample Type instead of duplicating it).

Extended Metadata Types are NOT provisioned here — SEEK only allows those through
the admin web UI (no JSON:API); the hybrid flow generates a downloadable
definition for an admin separately.
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field as dc_field
from typing import TYPE_CHECKING

from metaseed.seek import payloads
from metaseed.seek.roles import sample_role_entities
from metaseed.specs.schema import FieldType

if TYPE_CHECKING:
    from metaseed.seek.client import SeekClient
    from metaseed.services.ontology import OntologyService
    from metaseed.specs.schema import FieldSpec, ProfileSpec

# metaseed scalar FieldType -> SEEK base sample-attribute-type title. Titles are
# resolved to instance ids at execution via ``client.sample_attribute_type_id``.
_ATTR_TYPE_TITLE: dict[FieldType, str] = {
    FieldType.STRING: "String",
    FieldType.INTEGER: "Integer",
    FieldType.FLOAT: "Real number",
    FieldType.BOOLEAN: "Boolean",
    FieldType.DATE: "Date",
    FieldType.DATETIME: "Date time",
    FieldType.URI: "Web link",
    # ontology_term is an open OLS lookup, not a closed set -> a plain string
    # attribute (a Controlled Vocabulary needs a fixed term list, which only an
    # ``enum`` field provides).
    FieldType.ONTOLOGY_TERM: "String",
}
_CV_TYPE_TITLE = "Controlled Vocabulary"
_CV_LIST_TYPE_TITLE = "Controlled Vocabulary List"
_LIST_FALLBACK_TITLE = "Text"  # a list of primitives with no enum -> free text

# Base of the property URI SEEK matches an FDS-imported sample to a Sample Type
# attribute by; must equal the ``schema:`` namespace the data RDF emits
# (:mod:`metaseed.seek.fairds`).
_PID_BASE = "http://schema.org/"

# Fields SEEK handles as a sample's core Title/Description rather than as a
# PID-matched attribute of their own: the identifier maps to the ``is_title``
# ``Title`` attribute, the description to ``Description``. Kept in sync with
# ``fairds._CORE_FIELDS``.
_CORE_FIELDS = frozenset({"identifier", "unique_id", "title", "name", "description"})


@dataclass(frozen=True)
class CvTermPlan:
    """One term of a Controlled Vocabulary."""

    label: str
    iri: str | None = None
    parent_iri: str | None = None


@dataclass(frozen=True)
class CvPlan:
    """A Controlled Vocabulary to create in SEEK."""

    title: str
    terms: tuple[CvTermPlan, ...]
    description: str | None = None
    source_ontology: str | None = None
    ols_root_term_uris: str | None = None


@dataclass(frozen=True)
class AttributePlan:
    """One attribute of a Sample Type."""

    title: str
    attribute_type_title: str
    required: bool
    is_title: bool
    pos: int
    pid: str | None = None  # property URI SEEK's FDS import matches samples by
    cv_title: str | None = None  # -> resolved to sample_controlled_vocab_id at exec
    allow_cv_free_text: bool = False


@dataclass(frozen=True)
class SampleTypePlan:
    """A Sample Type to create in SEEK, projected from one profile entity."""

    entity_type: str
    title: str
    attributes: tuple[AttributePlan, ...]


@dataclass(frozen=True)
class ProvisioningPlan:
    """The full model projection: CVs (created first) then Sample Types."""

    cvs: tuple[CvPlan, ...]
    sample_types: tuple[SampleTypePlan, ...]


@dataclass
class ProvisionResult:
    """Outcome of executing a plan against a SEEK instance."""

    cv_ids: dict[str, str] = dc_field(default_factory=dict)
    sample_type_ids: dict[str, str] = dc_field(default_factory=dict)
    created: list[str] = dc_field(default_factory=list)
    reused: list[str] = dc_field(default_factory=list)
    errors: list[str] = dc_field(default_factory=list)


def _is_cv_field(field: FieldSpec) -> bool:
    """A field becomes a Controlled Vocabulary iff it declares a closed enum."""
    return bool(field.constraints and field.constraints.enum)


def _attribute_type_title(field: FieldSpec) -> str:
    """SEEK base attribute-type title for a (non-nested) field."""
    if _is_cv_field(field):
        return _CV_LIST_TYPE_TITLE if field.type == FieldType.LIST else _CV_TYPE_TITLE
    if field.type == FieldType.LIST:
        return _LIST_FALLBACK_TITLE
    return _ATTR_TYPE_TITLE.get(field.type, "String")


def _cv_title(profile: ProfileSpec, entity: str, field: FieldSpec) -> str:
    """Namespaced CV title, so a field name reused across entities/profiles
    doesn't collide with an unrelated instance-global vocabulary."""
    return f"{profile.name} {entity}.{field.name}"


def _cv_terms(
    field: FieldSpec, ontology: OntologyService | None
) -> tuple[CvTermPlan, ...]:
    """Build CV terms from a field's enum, optionally resolving IRIs via OLS."""
    enum = (
        list(field.constraints.enum)
        if field.constraints and field.constraints.enum
        else []
    )
    ols_id = field.ontologies[0] if field.ontologies else None
    terms: list[CvTermPlan] = []
    for value in enum:
        iri: str | None = None
        if ontology is not None and ols_id:
            hits = ontology.search_sync(value, ontology=ols_id, rows=1, exact=True)
            if hits:
                iri = hits[0].iri
        terms.append(CvTermPlan(label=value, iri=iri))
    return tuple(terms)


def build_provisioning_plan(
    profile: ProfileSpec, *, ontology: OntologyService | None = None
) -> ProvisioningPlan:
    """Project ``profile`` onto SEEK CVs + Sample Types (pure, deterministic).

    Every Sample Type leads with a ``Title`` (``is_title``) and ``Description``
    attribute — the two SEEK's FAIR-Data-Station importer populates from a
    sample's core annotations — followed by one PID-carrying attribute per
    non-core scalar field. A field's PID is ``http://schema.org/<field>``, the
    same URI :func:`metaseed.seek.fairds.to_fair_data_station_rdf` emits, so an
    imported sample matches the provisioned type by attribute PID.

    Args:
        profile: The metaseed profile to provision.
        ontology: Optional OLS service; when given, CV terms from enum fields that
            also declare ``ontologies`` are enriched with their ontology IRIs.

    Returns:
        A :class:`ProvisioningPlan` (CVs are ordered before the Sample Types that
        reference them).
    """
    cvs: dict[str, CvPlan] = {}  # dedup by title
    sample_types: list[SampleTypePlan] = []

    for entity_name in sorted(sample_role_entities(profile)):
        entity = profile.entities[entity_name]

        attributes: list[AttributePlan] = [
            AttributePlan(
                title="Title",
                attribute_type_title="String",
                required=True,
                is_title=True,
                pos=1,
            ),
            AttributePlan(
                title="Description",
                attribute_type_title="String",
                required=False,
                is_title=False,
                pos=2,
            ),
        ]
        # Non-core, non-nested (scalar/list-of-scalar) fields become PID-matched
        # attributes; core identity/description fields are carried by Title /
        # Description above.
        field_idx = [
            i
            for i, f in enumerate(entity.fields)
            if not f.is_nested() and f.name not in _CORE_FIELDS
        ]
        for pos, i in enumerate(field_idx, start=len(attributes) + 1):
            field = entity.fields[i]
            cv_title: str | None = None
            if _is_cv_field(field):
                cv_title = _cv_title(profile, entity_name, field)
                if cv_title not in cvs:
                    cvs[cv_title] = CvPlan(
                        title=cv_title,
                        terms=_cv_terms(field, ontology),
                        source_ontology=(
                            field.ontologies[0] if field.ontologies else None
                        ),
                    )
            attributes.append(
                AttributePlan(
                    title=field.name,
                    attribute_type_title=_attribute_type_title(field),
                    required=field.required,
                    is_title=False,
                    pos=pos,
                    pid=f"{_PID_BASE}{field.name}",
                    cv_title=cv_title,
                )
            )

        sample_types.append(
            SampleTypePlan(
                entity_type=entity_name,
                title=sample_type_title(profile, entity_name),
                attributes=tuple(attributes),
            )
        )

    return ProvisioningPlan(cvs=tuple(cvs.values()), sample_types=tuple(sample_types))


def sample_type_title(profile: ProfileSpec, entity_type: str) -> str:
    """The SEEK Sample Type title for a profile entity (single source of truth)."""
    return f"{profile.name} {entity_type}"


def resolve_sample_type_ids(
    client: SeekClient, profile: ProfileSpec, *, project_id: str
) -> dict[str, str]:
    """Look up already-provisioned Sample Type ids by entity type (for a sync).

    Only entities whose Sample Type currently exists in ``project_id`` are
    returned; a caller can compare against :func:`sample_role_entities` to see
    what still needs provisioning.
    """
    ids: dict[str, str] = {}
    for entity_type in sample_role_entities(profile):
        existing = client.find_sample_type_id_by_title(
            sample_type_title(profile, entity_type), project_id=project_id
        )
        if existing is not None:
            ids[entity_type] = existing
    return ids


def execute_provisioning_plan(
    client: SeekClient, plan: ProvisioningPlan, *, project_id: str
) -> ProvisionResult:
    """Create the plan's CVs then Sample Types in SEEK, idempotently.

    A CV/Sample Type whose title already exists (globally for CVs, within
    ``project_id`` for Sample Types) is reused, not duplicated.
    """
    result = ProvisionResult()
    type_id_cache: dict[str, str] = {}

    # Each create is isolated: one SEEK failure records an error and the rest of
    # the plan still runs (a rerun is idempotent, so it self-heals on retry).
    for cv in plan.cvs:
        try:
            existing = client.find_controlled_vocab_id_by_title(cv.title)
            if existing is not None:
                result.cv_ids[cv.title] = existing
                result.reused.append(f"CV: {cv.title}")
                continue
            cv_id = client.create_controlled_vocab(
                title=cv.title,
                terms=[
                    {"label": t.label, "iri": t.iri, "parent_iri": t.parent_iri}
                    for t in cv.terms
                ],
                description=cv.description,
                source_ontology=cv.source_ontology,
                ols_root_term_uris=cv.ols_root_term_uris,
            )
            result.cv_ids[cv.title] = cv_id
            result.created.append(f"CV: {cv.title}")
        except Exception as exc:
            result.errors.append(f"CV {cv.title}: {exc}")

    for st in plan.sample_types:
        try:
            attributes: list[dict[str, object]] = []
            for attr in st.attributes:
                if attr.attribute_type_title not in type_id_cache:
                    type_id_cache[attr.attribute_type_title] = (
                        client.sample_attribute_type_id(attr.attribute_type_title)
                    )
                attr_cv_id = result.cv_ids.get(attr.cv_title) if attr.cv_title else None
                attributes.append(
                    payloads.sample_attribute(
                        title=attr.title,
                        attribute_type_id=type_id_cache[attr.attribute_type_title],
                        required=attr.required,
                        is_title=attr.is_title,
                        pos=attr.pos,
                        pid=attr.pid,
                        sample_controlled_vocab_id=attr_cv_id,
                        allow_cv_free_text=attr.allow_cv_free_text,
                    )
                )

            existing = client.find_sample_type_id_by_title(
                st.title, project_id=project_id
            )
            if existing is not None:
                # Reuse an existing Sample Type as-is. Editing its attributes over
                # the API is not attempted: a PATCH replaces the whole attribute
                # list, which would drop fields SEEK sets that we do not read back
                # (allow_cv_free_text, description, unit, links) and can duplicate
                # is_title/pos. Adding a column to a provisioned type is left to a
                # SEEK admin.
                result.sample_type_ids[st.entity_type] = existing
                result.reused.append(f"Sample Type: {st.title}")
                continue

            st_id = client.create_sample_type(
                title=st.title, project_id=project_id, attributes=attributes
            )
            result.sample_type_ids[st.entity_type] = st_id
            result.created.append(f"Sample Type: {st.title}")
        except Exception as exc:
            result.errors.append(f"Sample Type {st.title}: {exc}")

    return result
