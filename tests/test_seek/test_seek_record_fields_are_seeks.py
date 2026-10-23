"""A SEEK record entity holds only fields SEEK has, or marks the rest ISA-only (#359).

SEEK's Investigation, Study and Assay have a fixed set of record attributes
(``investigationPost``, ``studyPost``, ``assayPost``). A field outside that set
reaches SEEK only inside the ISA-JSON export, unless the entity names an
Extended Metadata Type to carry it. Such a field is marked ``seek_isa_only`` so
that author and reader know it is not a SEEK attribute.
"""

from __future__ import annotations

import pytest
from tests.builtin_specs import builtin_only_loader

from metaseed.seek.roles import SEEK_RECORD_ATTRIBUTES


def _latest_shipped_profiles() -> list[tuple[str, str]]:
    loader = builtin_only_loader()
    latest: list[tuple[str, str]] = []
    for name in loader.list_profiles():
        versions = loader.list_versions(name)
        if versions:
            latest.append((name, versions[-1]))
    return latest


@pytest.mark.parametrize(("profile", "version"), _latest_shipped_profiles())
def test_record_fields_are_seek_attributes_or_marked(profile, version) -> None:
    spec = builtin_only_loader(profile).load_profile(version, profile)
    unmarked = []
    for name, entity in spec.entities.items():
        role = entity.seek.role if entity.seek else None
        if role not in SEEK_RECORD_ATTRIBUTES or entity.seek.extended_metadata:
            continue
        for field in entity.fields:
            if field.is_nested() or field.reference or field.seek_isa_only:
                continue
            if field.name not in SEEK_RECORD_ATTRIBUTES[role]:
                unmarked.append(f"{name}.{field.name}")
    assert not unmarked, (
        f"{profile} {version}: SEEK has no attribute for {unmarked}; "
        "mark them seek_isa_only or give the entity an Extended Metadata Type"
    )
