"""The seek-ready-template profile exists so a dataset built on it uploads to SEEK whole.

That promise is only worth making if it is enforced: a future edit that gives an
entity no role, or nests something SEEK cannot place, must fail here rather than
silently start leaving data behind on upload. The check needs no live SEEK -- it
asserts the mapping the sync uses, not the network call.

These run against the current version. 1.0 is deliberately not covered: it nests
Samples under Study, which is the one place SEEK cannot store them, so its samples
upload attached to nothing. Testing it as though it were sound is what let that
defect stand -- the role mapping it asserted was correct while the tree was not.
"""

from __future__ import annotations

from metaseed.seek.roles import entity_jerm_class
from metaseed.specs.loader import SpecLoader

SYNCABLE = {"Investigation", "Study", "Assay", "Sample"}


VERSION = "2.0"


def _spec():
    return SpecLoader().load_profile(VERSION, "seek-ready-template")


def _role(entity) -> str | None:
    return entity.seek.role if entity.seek else None


def _parents(spec) -> dict[str, str]:
    """Child entity name -> its nesting parent, from the profile's list fields."""
    parents: dict[str, str] = {}
    for name, entity in spec.entities.items():
        for field in entity.fields:
            if field.items:
                parents[field.items] = name
    return parents


def test_every_entity_maps_to_a_role_sync_can_place() -> None:
    spec = _spec()
    unmapped = []
    for name, entity in spec.entities.items():
        role = entity.seek.role if entity.seek else None
        jerm = entity_jerm_class(name, role)
        if jerm not in SYNCABLE:
            unmapped.append(f"{name} (role={role!r} -> {jerm!r})")
    assert not unmapped, (
        "seek-ready-template must leave nothing behind on sync; these entities do not map "
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


def test_every_sample_has_an_assay_ancestor() -> None:
    """A Sample must nest under an Assay, or it uploads attached to nothing.

    SEEK has no Sample-to-Study association -- it accepts one and silently drops
    it -- so the sync links a Sample by finding its Assay ancestor. A Sample
    placed anywhere else is created in SEEK reachable only by listing the
    project's samples: absent from the Investigation and lost on re-import.

    The role check above passes regardless, because every entity maps to a valid
    role whatever the tree looks like. That is exactly how 1.0 shipped a profile
    whose samples did not arrive.
    """
    spec = _spec()
    parents = _parents(spec)
    orphans = []
    for name, entity in spec.entities.items():
        if entity_jerm_class(name, _role(entity)) != "Sample":
            continue
        cursor, seen = parents.get(name), {name}
        while cursor and cursor not in seen:
            if entity_jerm_class(cursor, _role(spec.entities[cursor])) == "Assay":
                break
            seen.add(cursor)
            cursor = parents.get(cursor)
        else:
            orphans.append(f"{name} (nested under {parents.get(name)!r})")
    assert not orphans, (
        "these Sample-role entities have no Assay-role ancestor, so a dataset "
        f"built on this profile uploads them attached to nothing: {orphans}"
    )
