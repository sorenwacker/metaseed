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


def entity_jerm_class(entity_type: str, role: str | None) -> str | None:
    """The JERM class an entity maps to — its ``seek.role`` wins, else the name map.

    Returns ``None`` for an unmapped entity with no role (it is not exported).
    """
    if role:
        return role
    mapping = JERM_CLASSES.get(entity_type)
    return mapping[0] if mapping else None


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
        if entity_jerm_class(name, role) == SAMPLE_CLASS:
            result.add(name)
    return result
