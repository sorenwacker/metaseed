"""The seek-ready profile exists so a dataset built on it uploads to SEEK whole.

That promise is only worth making if it is enforced: a future edit that gives an
entity no role, or nests something SEEK cannot place, must fail here rather than
silently start leaving data behind on upload. The check needs no live SEEK -- it
asserts the mapping the sync uses, not the network call.
"""

from __future__ import annotations

from metaseed.seek.roles import entity_jerm_class
from metaseed.specs.loader import SpecLoader

SYNCABLE = {"Investigation", "Study", "Assay", "Sample"}


def _spec():
    return SpecLoader().load_profile("1.0", "seek-ready")


def test_every_entity_maps_to_a_role_sync_can_place() -> None:
    spec = _spec()
    unmapped = []
    for name, entity in spec.entities.items():
        role = entity.seek.role if entity.seek else None
        jerm = entity_jerm_class(name, role)
        if jerm not in SYNCABLE:
            unmapped.append(f"{name} (role={role!r} -> {jerm!r})")
    assert not unmapped, (
        "seek-ready must leave nothing behind on sync; these entities do not map "
        f"to a syncable SEEK role: {unmapped}"
    )


def test_it_has_no_observation_unit_level() -> None:
    """The template is deliberately the simplest ISA shape."""
    spec = _spec()
    roles = {e.seek.role for e in spec.entities.values() if e.seek and e.seek.role}
    assert "ObservationUnit" not in roles


def test_it_is_an_investigation_rooted_tree() -> None:
    spec = _spec()
    assert spec.root_entity == "Investigation"
    assert (
        entity_jerm_class("Investigation", spec.entities["Investigation"].seek.role)
        == "Investigation"
    )


def test_every_entity_has_an_identifier_and_a_label() -> None:
    """SEEK derives a resource's title from the label; an entity with neither can
    be rejected on upload."""
    spec = _spec()
    for name, entity in spec.entities.items():
        has_id = any(f.is_identifier for f in entity.fields)
        has_label = any(f.is_label for f in entity.fields)
        assert has_id, f"{name} has no is_identifier field"
        assert has_label, f"{name} has no is_label field"
