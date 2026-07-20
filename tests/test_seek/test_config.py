"""Hermetic tests for the profile -> SEEK Sample Types configurator."""

from __future__ import annotations

from typing import Any

from metaseed.seek.config import _title_index, push_profile
from metaseed.specs.schema import (
    Constraints,
    EntityDefSpec,
    FieldSpec,
    FieldType,
    ProfileSpec,
)


class FakeSeek:
    """A stand-in SeekClient recording the calls push_profile makes."""

    _TYPE_IDS = {"String": "8", "Integer": "4", "Text": "7", "Controlled Vocabulary": "20"}

    def __init__(self, existing: set[str] | None = None) -> None:
        self.existing = existing or set()
        self.sample_types: list[tuple[str, list[dict[str, Any]]]] = []
        self.cvs: list[tuple[str, list[str]]] = []
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
        self.cvs.append((title, terms))
        return str(self._cv)

    def create_sample_type(
        self, *, title: str, project_id: str, attributes: list[dict[str, Any]]
    ) -> str:
        self._st += 1
        self.sample_types.append((title, attributes))
        return str(self._st)


def _profile() -> ProfileSpec:
    return ProfileSpec(
        version="1.0",
        name="demo",
        entities={
            "Sample": EntityDefSpec(
                fields=[
                    FieldSpec(name="name", type=FieldType.STRING, required=True),
                    FieldSpec(name="count", type=FieldType.INTEGER),
                    FieldSpec(
                        name="status",
                        type=FieldType.STRING,
                        constraints=Constraints(enum=["draft", "final"]),
                    ),
                ]
            ),
            "Empty": EntityDefSpec(fields=[]),
        },
    )


def test_push_profile_creates_sample_type_per_entity():
    seek = FakeSeek()
    result = push_profile(seek, _profile())

    assert result.project == "1"
    assert "Sample" in result.sample_types
    assert "Empty" in result.skipped  # no fields -> skipped
    title, _attrs = seek.sample_types[0]
    assert title == "demo: Sample"


def test_enum_field_becomes_controlled_vocabulary():
    seek = FakeSeek()
    push_profile(seek, _profile())

    assert len(seek.cvs) == 1
    _title, attrs = seek.sample_types[0]
    status = next(a for a in attrs if a["title"] == "status")
    assert status["sample_attribute_type"]["id"] == "20"  # Controlled Vocabulary
    assert status["sample_controlled_vocab_id"] == "1"


def test_name_is_the_title_attribute():
    seek = FakeSeek()
    push_profile(seek, _profile())
    _title, attrs = seek.sample_types[0]
    assert [a["title"] for a in attrs if a["is_title"]] == ["name"]


def test_existing_sample_types_are_skipped():
    seek = FakeSeek(existing={"demo: Sample"})
    result = push_profile(seek, _profile())
    assert result.sample_types == {}
    assert "Sample" in result.skipped
    assert seek.sample_types == []


def test_title_index_prefers_named_field():
    fields = [
        FieldSpec(name="count", type=FieldType.INTEGER),
        FieldSpec(name="name", type=FieldType.STRING),
    ]
    assert _title_index(fields) == 1
