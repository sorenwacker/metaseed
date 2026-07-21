"""Hermetic tests for the ISA-aware profile -> SEEK configurator."""

from __future__ import annotations

from typing import Any

from metaseed.seek.config import extended_metadata_json, push_profile
from metaseed.specs.schema import (
    Constraints,
    EntityDefSpec,
    FieldSpec,
    FieldType,
    ProfileSpec,
    SeekEntityConfig,
)


class FakeSeek:
    """A stand-in SeekClient recording the calls push_profile makes."""

    _TYPE_IDS = {"String": "8", "Integer": "4", "Text": "7", "Controlled Vocabulary": "20"}

    def __init__(self, existing: set[str] | None = None) -> None:
        self.existing = existing or set()
        self.sample_types: list[str] = []
        self.cvs: list[str] = []
        self._st = 0
        self._cv = 0

    def default_project_id(self) -> str:
        return "1"

    def list_sample_type_titles(self) -> set[str]:
        return set(self.existing)

    def sample_attribute_type_id(self, title: str) -> str:
        return self._TYPE_IDS.get(title, "8")

    def create_controlled_vocabulary(self, *, title: str, terms: list[str]) -> str:
        self._cv += 1
        self.cvs.append(title)
        return str(self._cv)

    def create_sample_type(
        self, *, title: str, project_id: str, attributes: list[dict[str, Any]]
    ) -> str:
        self._st += 1
        self.sample_types.append(title)
        return str(self._st)


def _profile() -> ProfileSpec:
    return ProfileSpec(
        version="1.0",
        name="demo",
        entities={
            "Study": EntityDefSpec(
                seek=SeekEntityConfig(
                    artifact="extended_metadata", supported_type="Study"
                ),
                fields=[
                    FieldSpec(name="identifier", type=FieldType.STRING, required=True),
                    FieldSpec(
                        name="design",
                        type=FieldType.STRING,
                        constraints=Constraints(enum=["a", "b"]),
                    ),
                ],
            ),
            "Sample": EntityDefSpec(
                seek=SeekEntityConfig(artifact="sample_type"),
                fields=[
                    FieldSpec(name="name", type=FieldType.STRING, required=True),
                    FieldSpec(
                        name="status",
                        type=FieldType.STRING,
                        constraints=Constraints(enum=["draft", "final"]),
                    ),
                ],
            ),
            "Person": EntityDefSpec(  # no seek block -> skipped
                fields=[FieldSpec(name="email", type=FieldType.STRING)]
            ),
        },
    )


def test_sample_entity_becomes_sample_type_structural_does_not():
    seek = FakeSeek()
    result = push_profile(seek, _profile())

    assert seek.sample_types == ["demo: Sample"]  # only the sample entity
    assert "Sample" in result.sample_types
    assert "Study" not in result.sample_types  # structural -> NOT a sample type


def test_structural_entity_becomes_extended_metadata_json():
    result = push_profile(FakeSeek(), _profile())
    assert len(result.extended_metadata) == 1
    emt = result.extended_metadata[0]
    assert emt["supported_type"] == "Study"
    assert emt["title"] == "demo: Study"
    design = next(a for a in emt["attributes"] if a["title"] == "design")
    assert design["type"] == "Controlled Vocabulary"
    assert design["controlled_vocabulary"]["terms"] == ["a", "b"]


def test_unannotated_entity_is_skipped():
    result = push_profile(FakeSeek(), _profile())
    assert "Person" in result.skipped


def test_sample_type_enum_creates_a_controlled_vocabulary():
    seek = FakeSeek()
    push_profile(seek, _profile())
    assert len(seek.cvs) == 1  # only the sample entity's enum, via API


def test_extended_metadata_json_helper_only_for_structural():
    profile = _profile()
    assert extended_metadata_json(profile, "Study") is not None
    assert extended_metadata_json(profile, "Sample") is None  # sample_type, not EMT
    assert extended_metadata_json(profile, "Person") is None  # unannotated
    assert extended_metadata_json(profile, "Nope") is None  # absent
