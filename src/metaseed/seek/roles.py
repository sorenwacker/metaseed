"""Entity → JERM/ISA role mapping, shared by the SEEK exporters and provisioner.

Kept free of ``rdflib``/``httpx`` so both the RDF export (:mod:`metaseed.seek.fairds`)
and the API provisioner (:mod:`metaseed.seek.provision`) can import it without
pulling either optional extra.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from metaseed.specs.schema import ProfileSpec

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

#: The JERM classes an entity's annotation may name directly. Deliberately the
#: values of :data:`JERM_CLASSES` plus nothing invented: these are the classes
#: this exporter knows how to place.
KNOWN_JERM_CLASSES: frozenset[str] = frozenset(
    {jerm for jerm, _prefix in JERM_CLASSES.values()}
)


def jerm_class_from_annotation(ontology_term: str | None) -> str | None:
    """The JERM class an entity's own annotation names, if it names one.

    Read from the annotation's local name only — ``JERM:Assay``,
    ``http://.../JERM.owl#Assay`` — never from a numeric accession. JERM is
    carried by no source we can reach (it is not in OLS), so an accession such
    as ``JERM:00021`` cannot be resolved to a class here, and guessing a table
    of accession numbers would be inventing identifiers rather than reading
    them.

    Returns:
        The class, or ``None`` when the annotation names no known one.
    """
    if not ontology_term:
        return None
    local = ontology_term.rsplit("#", 1)[-1].rsplit("/", 1)[-1].rsplit(":", 1)[-1]
    return local if local in KNOWN_JERM_CLASSES else None


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
    annotated = jerm_class_from_annotation(ontology_term)
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
