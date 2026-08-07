"""Projecting a profile entity onto an ISA-JSON compliant SEEK Sample Type.

A compliant Sample Type needs an ISA tag on every attribute, and the tag set is
constrained per ISA level. See docs/architecture/seek-isa-compliance.md.
"""

from __future__ import annotations

import pytest

from metaseed.seek.isa_types import sample_type_attributes
from metaseed.specs.schema import Constraints, EntityDefSpec, FieldSpec, FieldType

TAGS = {
    "source": "1",
    "source_characteristic": "2",
    "sample": "3",
    "sample_characteristic": "4",
    "protocol": "5",
    "other_material": "6",
    "other_material_characteristic": "7",
    "data_file": "8",
    "input": "11",
}


def _entity() -> EntityDefSpec:
    return EntityDefSpec(
        fields=[
            FieldSpec(name="sample_name", type=FieldType.STRING, required=True),
            FieldSpec(name="organism", type=FieldType.STRING),
            FieldSpec(name="collection_date", type=FieldType.DATE),
        ]
    )


def _titles(attributes):
    return [a["title"] for a in attributes]


def _tag_of(attributes, title):
    return next(a["isa_tag_id"] for a in attributes if a["title"] == title)


class TestSourceLevel:
    def test_has_exactly_one_title_attribute_tagged_source(self):
        attrs = sample_type_attributes(_entity(), level="source", isa_tag_ids=TAGS)
        titled = [a for a in attrs if a["is_title"]]
        assert len(titled) == 1
        assert titled[0]["isa_tag_id"] == TAGS["source"]

    def test_every_attribute_carries_a_tag(self):
        # SEEK rejects a compliant Sample Type with any untagged attribute.
        attrs = sample_type_attributes(_entity(), level="source", isa_tag_ids=TAGS)
        assert all(a.get("isa_tag_id") for a in attrs)

    def test_profile_fields_become_characteristics(self):
        attrs = sample_type_attributes(_entity(), level="source", isa_tag_ids=TAGS)
        assert _tag_of(attrs, "organism") == TAGS["source_characteristic"]

    def test_a_source_type_has_no_input_attribute(self):
        # Source is the head of the chain; nothing precedes it to link to.
        attrs = sample_type_attributes(_entity(), level="source", isa_tag_ids=TAGS)
        assert not any(a["isa_tag_id"] == TAGS["input"] for a in attrs)


class TestSampleCollectionLevel:
    def test_links_to_the_previous_type_through_an_input_attribute(self):
        attrs = sample_type_attributes(
            _entity(),
            level="sample_collection",
            isa_tag_ids=TAGS,
            linked_sample_type_id="42",
        )
        inputs = [a for a in attrs if a["isa_tag_id"] == TAGS["input"]]
        assert len(inputs) == 1
        assert inputs[0]["linked_sample_type_id"] == "42"
        # input_attribute? requires the title to contain "input" and the type to
        # be the multi registered-sample type.
        assert "input" in inputs[0]["title"].lower()

    def test_has_exactly_one_protocol_attribute(self):
        attrs = sample_type_attributes(
            _entity(),
            level="sample_collection",
            isa_tag_ids=TAGS,
            linked_sample_type_id="42",
        )
        assert sum(a["isa_tag_id"] == TAGS["protocol"] for a in attrs) == 1

    def test_title_attribute_is_tagged_sample(self):
        attrs = sample_type_attributes(
            _entity(),
            level="sample_collection",
            isa_tag_ids=TAGS,
            linked_sample_type_id="42",
        )
        titled = [a for a in attrs if a["is_title"]]
        assert len(titled) == 1
        assert titled[0]["isa_tag_id"] == TAGS["sample"]


class TestAssayLevel:
    def test_has_exactly_one_data_file_or_other_material_attribute(self):
        attrs = sample_type_attributes(
            _entity(), level="assay", isa_tag_ids=TAGS, linked_sample_type_id="7"
        )
        terminal = [
            a
            for a in attrs
            if a["isa_tag_id"] in (TAGS["data_file"], TAGS["other_material"])
        ]
        assert len(terminal) == 1

    def test_links_back_to_the_previous_type(self):
        attrs = sample_type_attributes(
            _entity(), level="assay", isa_tag_ids=TAGS, linked_sample_type_id="7"
        )
        inputs = [a for a in attrs if a["isa_tag_id"] == TAGS["input"]]
        assert inputs[0]["linked_sample_type_id"] == "7"

    def test_a_level_needing_a_link_rejects_a_missing_one(self):
        # Without the link the chain is broken and SEEK's validation fails only
        # once the request reaches the server.
        with pytest.raises(ValueError):
            sample_type_attributes(_entity(), level="assay", isa_tag_ids=TAGS)


class TestFieldDeclaredTags:
    def test_a_field_isa_tag_overrides_the_level_default(self):
        entity = EntityDefSpec(
            fields=[
                FieldSpec(name="sample_name", type=FieldType.STRING),
                FieldSpec(
                    name="instrument", type=FieldType.STRING, isa_tag="parameter_value"
                ),
            ]
        )
        attrs = sample_type_attributes(
            entity,
            level="assay",
            isa_tag_ids={**TAGS, "parameter_value": "10"},
            linked_sample_type_id="7",
        )
        assert _tag_of(attrs, "instrument") == "10"

    def test_an_unknown_tag_on_the_instance_is_reported_not_silently_dropped(self):
        entity = EntityDefSpec(
            fields=[
                FieldSpec(name="x", type=FieldType.STRING, isa_tag="parameter_value")
            ]
        )
        with pytest.raises(KeyError):
            sample_type_attributes(
                entity, level="assay", isa_tag_ids=TAGS, linked_sample_type_id="7"
            )


class TestControlledVocabularyFields:
    """An enum field becomes a CV attribute, which SEEK rejects without a vocab id."""

    def _entity(self) -> EntityDefSpec:
        return EntityDefSpec(
            fields=[
                FieldSpec(name="sample_name", type=FieldType.STRING),
                FieldSpec(
                    name="organism_part",
                    type=FieldType.STRING,
                    constraints=Constraints(enum=["leaf", "root"]),
                ),
            ]
        )

    def test_an_enum_field_carries_its_controlled_vocab_id(self):
        attrs = sample_type_attributes(
            self._entity(),
            level="source",
            isa_tag_ids=TAGS,
            cv_ids={"organism_part": "77"},
        )
        cv = next(a for a in attrs if a["title"] == "organism_part")
        assert cv["sample_controlled_vocab_id"] == "77"

    def test_a_non_enum_field_carries_no_vocab_id(self):
        # SEEK's resolve_inconsistencies nulls a vocab id on a non-CV attribute,
        # so sending one is at best noise and at worst a rejected write.
        attrs = sample_type_attributes(
            self._entity(),
            level="source",
            isa_tag_ids=TAGS,
            cv_ids={"organism_part": "77"},
        )
        plain = next(a for a in attrs if a["title"] == "sample_name")
        assert "sample_controlled_vocab_id" not in plain

    def test_an_enum_field_with_no_provisioned_vocab_is_reported(self):
        # Sending a CV attribute with no vocab id is rejected by SEEK with
        # "Controlled vocabulary must be set if attribute type is CV" -- fail
        # here instead, where the field name is still in hand.
        with pytest.raises(KeyError, match="organism_part"):
            sample_type_attributes(
                self._entity(), level="source", isa_tag_ids=TAGS, cv_ids={}
            )


class TestStructuralAttributesAreOptional:
    """The chain is structural, so it must not demand a value on every Sample."""

    def test_the_input_and_protocol_attributes_are_not_required(self):
        # Marking them required makes SEEK reject every Sample that does not
        # supply them: "/data/attributes/Input (Title): is required".
        attrs = sample_type_attributes(
            _entity(), level="assay", isa_tag_ids=TAGS, linked_sample_type_id="7"
        )
        structural = [
            a for a in attrs if a["isa_tag_id"] in (TAGS["input"], TAGS["protocol"])
        ]
        assert len(structural) == 2
        assert not any(a["required"] for a in structural)
