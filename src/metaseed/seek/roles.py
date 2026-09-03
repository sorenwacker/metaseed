"""Entity → JERM/ISA role mapping, shared by the SEEK exporters and provisioner.

Kept free of ``rdflib``/``httpx`` so both the RDF export (:mod:`metaseed.seek.fairds`)
and the API provisioner (:mod:`metaseed.seek.provision`) can import it without
pulling either optional extra.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

    from metaseed.specs.schema import ProfileSpec

SEEK_ROLES: tuple[str, ...] = (
    "Investigation",
    "Study",
    "ObservationUnit",
    "Sample",
    "Assay",
    "DataFile",
)
"""The object types a metaseed entity may declare as its SEEK ``role``.

Lives here, with the exporter that honours it, rather than in the generic spec
schema: it is SEEK vocabulary, and keeping it beside :data:`JERM_CLASSES` is
what stops the two drifting. ``metaseed.specs.schema`` validates against it
through a local import, so the core schema does not depend on this package at
import time.

Note it is NOT the same set as :data:`JERM_CLASSES`, and deliberately so today:
``DataFile`` is a declarable role handled by ``placement``, while the material
classes (``Source``, ``Extract``, ``LabeledExtract``, ``OtherMaterial``) are
inferred rather than declared. Any change to either belongs in one review of
both.
"""

# metaseed entity type -> (JERM class, URI id-prefix). Only ISA-structural and
# sample-bearing entities become SEEK/FDS resources; other entities are skipped.
JERM_CLASSES: dict[str, tuple[str, str]] = {
    "Investigation": ("Investigation", "inv"),
    "Study": ("Study", "stu"),
    "ObservationUnit": ("ObservationUnit", "obs"),
    "Assay": ("Assay", "assay"),
    "Sample": ("Sample", "sample"),
    "Source": ("Sample", "source"),
    "Extract": ("Sample", "extract"),
    "LabeledExtract": ("Sample", "lextract"),
    "OtherMaterial": ("Sample", "material"),
}

SAMPLE_CLASS = "Sample"

JERM_ONTOLOGY_URL = "https://jermontology.org/ontology/JERMOntology"
"""Where the class names below were read from, and what the gate re-reads."""

ANNOTATION_CLASSES: dict[str, str] = {
    # JERM's four placeable classes, and the three subclasses of Assay it
    # declares.
    "Investigation": "Investigation",
    "Study": "Study",
    "Assay": "Assay",
    "experimental_assay": "Assay",
    "informatics_analysis": "Assay",
    "modelling_analysis": "Assay",
    "Sample": "Sample",
    # Not JERM: SEEK types the observation-unit level from PPEO, and so does
    # this exporter. ``ObservationUnit`` is SEEK's own name for that resource.
    "observation_unit": "ObservationUnit",
    "ObservationUnit": "ObservationUnit",
}
"""The class an annotation may name, and the role this exporter places it as.

Read from the ontologies rather than assumed. JERM names all 294 of its classes
and holds no numeric accession at all, so ``JERM:00021`` names nothing in it and
stays unmapped; a table of accession numbers would be inventing identifiers.

Only four JERM classes have a place in the chain SEEK's reader walks
(Investigation → Study → ObservationUnit → Sample → Assay). ``treatment`` is a
real JERM class — a subclass of ``process``, sibling to ``Assay``, ``Study`` and
``Investigation`` — but that chain has no slot for it, so an entity annotated
with it is reported by :func:`unmapped_entities` rather than placed as something
it is not. The same holds for JERM's asset classes (``Data``, ``Model``,
``SOP``, ``Publication``): real classes, no position in this export.
"""


def role_from_annotation(ontology_term: str | None) -> str | None:
    """The role an entity's own annotation names, if it names one.

    Read from the annotation's local name, however it is written —
    ``JERM:Assay``, ``http://jermontology.org/ontology/JERMOntology#Assay`` —
    and matched against :data:`ANNOTATION_CLASSES`, which holds only class names
    that exist in the ontologies concerned.

    Returns:
        The role, or ``None`` when the annotation names no class this exporter
        can place.
    """
    if not ontology_term:
        return None
    local = ontology_term.rsplit("#", 1)[-1].rsplit("/", 1)[-1].rsplit(":", 1)[-1]
    return ANNOTATION_CLASSES.get(local)


def jerm_class_in_profile(
    profile: ProfileSpec, entity_type: str, roles: Mapping[str, str | None]
) -> str | None:
    """`entity_jerm_class` with the entity's own annotation supplied.

    The sync computed the class from the NAME alone at three sites while
    every other path passed ``entity.ontology_term`` — so an annotation-only
    entity was planned into the Sample Type chain and exported by FDS, then
    skipped by the very sync that planned it.
    """
    entity = profile.entities.get(entity_type)
    ontology_term = entity.ontology_term if entity is not None else None
    return entity_jerm_class(entity_type, roles.get(entity_type), ontology_term)


def entity_jerm_class(
    entity_type: str, role: str | None, ontology_term: str | None = None
) -> str | None:
    """The JERM class an entity maps to.

    In order: an explicit ``seek.role``; the class the entity's own
    ``ontology_term`` names; then the entity's *name*. Reading the annotation
    matters because the name map holds nine strings, so a profile derived
    faithfully from JERM exported almost nothing — an entity called
    ``Experiment`` annotated as an Assay was skipped, while one merely *named*
    ``Assay`` and annotated with nothing was exported (#234).

    Returns ``None`` for an entity that maps to nothing (it is not exported).
    Use :func:`unmapped_entities` to report those rather than dropping them
    silently.
    """
    if role:
        return role
    annotated = role_from_annotation(ontology_term)
    if annotated:
        return annotated
    mapping = JERM_CLASSES.get(entity_type)
    return mapping[0] if mapping else None


def unmapped_entities(profile: ProfileSpec) -> list[str]:
    """The entities that will be skipped, so a caller can say so.

    The damage in #234 was silence: an export that produces less than its
    author expects, without failing. Naming what was left out lets the caller
    report it.
    """
    return sorted(
        name
        for name, entity in profile.entities.items()
        if entity_jerm_class(
            name,
            entity.seek.role if entity.seek else None,
            entity.ontology_term,
        )
        is None
    )


def sample_role_entities(profile: ProfileSpec) -> set[str]:
    """Entity type names that map to a JERM ``Sample`` (become SEEK Sample Types).

    An entity is Sample-role when its profile ``seek.role`` is ``Sample`` or,
    absent a role, its name maps to the JERM ``Sample`` class in
    :data:`JERM_CLASSES`. Investigation/Study/Assay/ObservationUnit are ISA-native
    and never become Sample Types.
    """
    result: set[str] = set()
    for name, entity in profile.entities.items():
        role = entity.seek.role if entity.seek else None
        if entity_jerm_class(name, role, entity.ontology_term) == SAMPLE_CLASS:
            result.add(name)
    return result


def fair_ds_package_name(name: str, version: str) -> str:
    """The FAIR Data Station package name metaseed stamps on each ISA level.

    SEEK titles a FAIR-DS-imported Extended Metadata Type after this package
    name, so it names the model: ``"<profile name> <version>"``.
    """
    return f"{name} {version}"


def fair_ds_extended_metadata_title(jerm_level: str, name: str, version: str) -> str:
    """The title SEEK gives a FAIR-DS-imported Extended Metadata Type for a level.

    SEEK builds it as ``"FDS <humanized supported_type> - <packageName>"``; the
    supported type is the JERM level (Investigation, Study, Assay), which
    humanizes to itself. The sync looks Extended Metadata Types up by this title
    so a type created by uploading the model TTL is found without a manual
    rename -- the whole reason the sync and the TTL must derive it from one
    place. See ``tests/test_seek/test_extended_metadata_title_agrees.py``.
    """
    return f"FDS {jerm_level} - {fair_ds_package_name(name, version)}"
