"""Generating the ISA Template file SEEK needs before it can export ISA-JSON.

``ISAExporter`` reads each Sample Type's ISA Template to decide whether an assay
material is a ``data_file`` or an ``other_material``
(``isa_exporter.rb:750``), and ``SampleType#is_isa_json_compliant?`` requires a
template to be present. A Sample Type built attribute-by-attribute has none, so a
structurally correct push still fails to export.

Templates are installed by an administrator: ``POST /templates/populate_template``
is admin-only and takes a ``template_json_file``. metaseed emits that file here,
the same division as the Extended Metadata Types flow
(:func:`metaseed.seek.fairds.to_fair_data_station_model_rdf`).

The attribute rules are not restated here. They come from
:func:`metaseed.seek.isa_types.sample_type_attribute_plans`, the same projection
the ISA form bodies are rendered from; this module only renders those plans in
the file's own vocabulary, where the attribute type and ISA tag are named by
title and the title flag is ``title`` rather than ``is_title``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from metaseed.seek.isa_types import sample_type_attribute_plans
from metaseed.seek.roles import sample_role_entities

if TYPE_CHECKING:
    from metaseed.seek.isa_types import AttributePlan
    from metaseed.specs.schema import ProfileSpec

# metaseed's internal level name -> the ``level`` SEEK stores on a Template.
# The assay level is not in here: it is always "assay - data file", which
# seek_level_for explains.
_SEEK_LEVELS: dict[str, str] = {
    "source": "study source",
    "sample_collection": "study sample",
}

# The levels of the material chain, in order. Only the first heads the chain.
CHAIN_LEVELS: tuple[str, ...] = ("source", "sample_collection", "assay")


def template_title(profile: ProfileSpec, seek_level: str) -> str:
    """The Template title for ``seek_level``, derivable without the file.

    The sync looks templates up by this title to attach them to the Sample Types
    it creates, so it must be reproducible from the profile alone.
    """
    return f"{profile.name} {seek_level}"


def sample_chain_entities(profile: ProfileSpec) -> list[str]:
    """Sample-role entity names down the material chain, Source level first.

    Followed through the profile's own nesting rather than guessed, because the
    chain is what SEEK's ISA-JSON exporter walks: a Source yields Samples, a
    Sample yields the materials measured from it.
    """
    roles = {
        name: entity.seek.role
        for name, entity in profile.entities.items()
        if entity.seek and entity.seek.role
    }
    sample_roles = sample_role_entities(profile)

    def first_sample_child(entity_name: str) -> str | None:
        entity = profile.entities.get(entity_name)
        if entity is None:
            return None
        for f in entity.fields:
            if f.items in sample_roles:
                return f.items
        return None

    start = next(
        (name for name, role in roles.items() if role == "Study"),
        profile.root_entity,
    )
    chain: list[str] = []
    current = first_sample_child(start)
    while current is not None and current not in chain:
        chain.append(current)
        current = first_sample_child(current)
    return chain


def seek_level_for(level: str, plans: list[AttributePlan]) -> str:
    """The SEEK template ``level`` for one level of the chain.

    An assay level is always ``assay - data file``: `isa_types` marks exactly
    one plan as the title and, for the assay level, tags it ``data_file``
    (`_LEVEL_TAGS`). This used to read the tag off the plans and map it, with
    an ``other_material`` entry that nothing could reach — a flexibility the
    code did not have. If a profile ever plans a material-tagged title, that is
    a decision to make here deliberately.

    Args:
        level: The chain level.
        plans: The level's attribute plans, unused for the assay level but kept
            so callers need not know which levels consult them.

    Returns:
        The ``level`` string SEEK stores on a Template.
    """
    del plans  # the assay level is not variable; see above
    if level in _SEEK_LEVELS:
        return _SEEK_LEVELS[level]
    return "assay - data file"


def _attribute(plan: AttributePlan) -> dict[str, Any]:
    """Render one attribute plan in the template file's vocabulary."""
    attribute: dict[str, Any] = {
        "name": plan.title,
        "description": "",
        "dataType": plan.attribute_type_title,
        "required": plan.required,
        "isaTag": plan.isa_tag,
    }
    if plan.is_title:
        attribute["title"] = True
    if plan.enum:
        # A closed vocabulary is inline here, so an enum field needs no
        # separately provisioned Controlled Vocabulary on this route.
        attribute["CVList"] = list(plan.enum)
    return attribute


def to_isa_template_json(profile: ProfileSpec) -> dict[str, Any]:
    """Build the ``template_json_file`` document for ``profile``.

    One template per level of the profile's material chain, named so the sync can
    find it again with :func:`template_title`.

    Args:
        profile: The profile whose Sample-role entities describe the chain.

    Returns:
        A document ready to serialise as the file an administrator uploads under
        *Templates -> populate*.
    """
    chain = sample_chain_entities(profile)
    templates: list[dict[str, Any]] = []

    for order, level in enumerate(CHAIN_LEVELS, start=1):
        entity_name = chain[order - 1] if order - 1 < len(chain) else None
        entity = profile.entities.get(entity_name) if entity_name else None
        plans = sample_type_attribute_plans(
            entity, level=level, linked=level != "source"
        )
        seek_level = seek_level_for(level, plans)
        templates.append(
            {
                "metadata": {
                    "name": template_title(profile, seek_level),
                    "group": profile.name,
                    "group_order": order,
                    "temporary_name": f"{order}_{profile.name}_{level}",
                    "version": profile.version,
                    "organism": "any",
                    "level": seek_level,
                },
                "data": [_attribute(plan) for plan in plans],
            }
        )

    return {"data": templates}
