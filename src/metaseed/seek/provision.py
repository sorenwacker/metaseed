"""Provision a SEEK data model from a metaseed profile (Phase 1).

Two steps, deliberately split:

- :func:`build_provisioning_plan` — pure, deterministic projection of a
  :class:`~metaseed.specs.schema.ProfileSpec` onto the SEEK model surface the
  JSON:API actually lets a project member create: **Controlled Vocabularies**
  (from closed ``enum`` fields) and **Sample Types** (from the profile's
  sample-bearing entities). Optionally enriches CV terms with ontology IRIs via
  an injected term source (the application's router, or any adapter).
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
from metaseed.seek.attribute_types import attribute_type_title, is_cv_field
from metaseed.seek.naming import property_uri
from metaseed.seek.ports import Provisioner
from metaseed.seek.roles import sample_role_entities

if TYPE_CHECKING:
    from collections.abc import Mapping

    from metaseed.services.term_check import TermSource
    from metaseed.specs.schema import FieldSpec, ProfileSpec


from metaseed.seek.values import CORE_FIELDS as _CORE_FIELDS


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
class SampleAttributePlan:
    """One attribute of a Sample Type, as the SEEK API will be asked for it.

    Renamed from ``AttributePlan``: the package already has one in
    ``isa_types`` with a different shape (tag/type NAMES for rendering), and
    two same-named dataclasses in one package made every import ambiguous.
    """

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
    attributes: tuple[SampleAttributePlan, ...]


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


def _cv_title(profile: ProfileSpec, entity: str, field: FieldSpec) -> str:
    """Namespaced CV title, so a field name reused across entities/profiles
    doesn't collide with an unrelated instance-global vocabulary."""
    return f"{profile.name} {entity}.{field.name}"


def _cv_terms(
    field: FieldSpec, term_source: TermSource | None
) -> tuple[CvTermPlan, ...]:
    """Build CV terms from a field's enum, optionally resolving IRIs.

    Asked of the term-source port rather than OLS directly, so a local
    vocabulary configured on the server enriches too, and a deployment with
    no network still provisions (label-only). A term is enriched only when a
    hit's label matches the enum value exactly — a fuzzy first hit would stamp
    the wrong IRI onto a CV term, which is worse than no IRI.
    """
    enum = (
        list(field.constraints.enum)
        if field.constraints and field.constraints.enum
        else []
    )
    ols_id = field.ontologies[0] if field.ontologies else None
    terms: list[CvTermPlan] = []
    for value in enum:
        iri: str | None = None
        if term_source is not None and ols_id:
            hits = term_source.search_sync(value, ontology=ols_id, limit=5)
            for hit in hits:
                if str(getattr(hit, "label", "")).lower() == value.lower():
                    iri = getattr(hit, "iri", None)
                    break
        terms.append(CvTermPlan(label=value, iri=iri))
    return tuple(terms)


def build_provisioning_plan(
    profile: ProfileSpec, *, term_source: TermSource | None = None
) -> ProvisioningPlan:
    """Project ``profile`` onto SEEK CVs + Sample Types.

    Deterministic in shape — the same profile plans the same types and
    attributes — but not pure: with a ``term_source`` supplied, CV terms are
    enriched with IRIs through it, which is network I/O when the source is
    OLS. Without one the plan is label-only and no request is made.

    Every Sample Type leads with a ``Title`` (``is_title``) and ``Description``
    attribute — the two SEEK's FAIR-Data-Station importer populates from a
    sample's core annotations — followed by one PID-carrying attribute per
    non-core scalar field. A field's PID is ``http://schema.org/<field>``, the
    same URI :func:`metaseed.seek.fairds.to_fair_data_station_rdf` emits, so an
    imported sample matches the provisioned type by attribute PID.

    Args:
        profile: The metaseed profile to provision.
        term_source: Optional term source (the application's router, or any
            adapter); when given, CV terms from enum fields that also declare
            ``ontologies`` are enriched with their ontology IRIs.

    Returns:
        A :class:`ProvisioningPlan` (CVs are ordered before the Sample Types that
        reference them).
    """
    cvs: dict[str, CvPlan] = {}  # dedup by title
    sample_types: list[SampleTypePlan] = []

    for entity_name in sorted(sample_role_entities(profile)):
        entity = profile.entities[entity_name]

        attributes: list[SampleAttributePlan] = [
            SampleAttributePlan(
                title="Title",
                attribute_type_title="String",
                required=True,
                is_title=True,
                pos=1,
            ),
            SampleAttributePlan(
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
            if is_cv_field(field):
                cv_title = _cv_title(profile, entity_name, field)
                if cv_title not in cvs:
                    cvs[cv_title] = CvPlan(
                        title=cv_title,
                        terms=_cv_terms(field, term_source),
                        source_ontology=(
                            field.ontologies[0] if field.ontologies else None
                        ),
                    )
            attributes.append(
                SampleAttributePlan(
                    title=field.name,
                    attribute_type_title=attribute_type_title(field),
                    required=field.required,
                    is_title=False,
                    pos=pos,
                    pid=property_uri(field.name),
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


def resolve_cv_ids(client: Provisioner, profile: ProfileSpec) -> dict[str, str]:
    """Look up already-provisioned Controlled Vocabulary ids by field name.

    The compliant sync builds its Sample Types per Assay, but the vocabularies
    their enum attributes bind to are instance-global and provisioned once, so
    they are resolved here rather than recreated per dataset.
    """
    ids: dict[str, str] = {}
    for entity_name in sample_role_entities(profile):
        for field in profile.entities[entity_name].fields:
            if not is_cv_field(field):
                continue
            existing = client.find_controlled_vocab_id_by_title(
                _cv_title(profile, entity_name, field)
            )
            if existing is not None:
                # Keyed "Entity.field", keeping the namespacing _cv_title
                # built: a bare field name reused across entities collapsed
                # two distinct SEEK CVs into whichever entity iterated last.
                ids[f"{entity_name}.{field.name}"] = existing
    return ids


def cv_ids_for_entity(cv_ids: Mapping[str, str], entity_name: str) -> dict[str, str]:
    """The one entity's slice of :func:`resolve_cv_ids`, keyed by bare field.

    ``sample_type_attributes`` renders one entity's fields, so it looks
    vocabularies up by field name; this narrows the namespaced mapping to
    that entity (passing bare legacy keys through unchanged).
    """
    narrowed: dict[str, str] = {}
    prefix = f"{entity_name}."
    for key, value in cv_ids.items():
        if key.startswith(prefix):
            narrowed[key[len(prefix) :]] = value
        elif "." not in key:
            narrowed.setdefault(key, value)
    return narrowed


def execute_provisioning_plan(
    client: Provisioner, plan: ProvisioningPlan, *, project_id: str
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
