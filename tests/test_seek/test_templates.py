"""Generating the ISA Template file SEEK needs before it can export ISA-JSON.

The file's vocabulary differs from the API's: attribute types and ISA tags are
named by title, the title flag is ``title`` rather than ``is_title``, and a
closed vocabulary is inline as ``CVList``. See
``docs/architecture/seek-inventory.md``.
"""

from __future__ import annotations

import pytest

from metaseed.seek.isa_types import sample_type_attributes
from metaseed.seek.templates import (
    sample_chain_entities,
    template_title,
    to_isa_template_json,
)
from metaseed.specs.loader import SpecLoader

TAGS = {
    "source": "1",
    "source_characteristic": "2",
    "sample": "3",
    "sample_characteristic": "4",
    "protocol": "5",
    "parameter_value": "10",
    "other_material": "6",
    "other_material_characteristic": "7",
    "data_file": "8",
    "data_file_comment": "9",
    "input": "11",
}


@pytest.fixture
def profile():
    return SpecLoader().load_profile("3.0", "seek-ready-template")


@pytest.fixture
def document(profile):
    return to_isa_template_json(profile)


def _by_level(document):
    return {t["metadata"]["level"]: t for t in document["data"]}


class TestLevels:
    def test_one_template_per_level_of_the_material_chain(self, document):
        levels = [t["metadata"]["level"] for t in document["data"]]
        assert levels[0] == "study source"
        assert levels[1] == "study sample"
        assert levels[2].startswith("assay - ")
        assert len(levels) == len(set(levels)), "levels must not collide"

    def test_the_assay_level_follows_its_title_tag(self, document):
        # SEEK distinguishes an assay that yields a data file from one that
        # yields a material, and reads which from the template's level.
        assay = document["data"][2]
        title = next(a for a in assay["data"] if a.get("title"))
        expected = {
            "data_file": "assay - data file",
            "other_material": "assay - material",
        }[title["isaTag"]]
        assert assay["metadata"]["level"] == expected

    def test_group_order_follows_the_chain(self, document):
        orders = [t["metadata"]["group_order"] for t in document["data"]]
        assert orders == sorted(orders)


class TestAttributes:
    def test_the_source_level_heads_the_chain_with_no_input(self, document):
        source = _by_level(document)["study source"]
        assert not any(a["isaTag"] == "input" for a in source["data"])

    def test_every_other_level_names_its_predecessor(self, document):
        for template in document["data"][1:]:
            inputs = [a for a in template["data"] if a["isaTag"] == "input"]
            assert len(inputs) == 1, template["metadata"]["level"]
            assert "input" in inputs[0]["name"].lower()

    def test_each_level_has_exactly_one_title_attribute(self, document):
        for template in document["data"]:
            titled = [a for a in template["data"] if a.get("title")]
            assert len(titled) == 1, template["metadata"]["level"]

    def test_each_chained_level_has_exactly_one_protocol(self, document):
        for template in document["data"][1:]:
            protocols = [a for a in template["data"] if a["isaTag"] == "protocol"]
            assert len(protocols) == 1, template["metadata"]["level"]

    def test_every_attribute_carries_a_tag(self, document):
        # SEEK rejects a compliant Sample Type with any untagged attribute.
        for template in document["data"]:
            assert all(a.get("isaTag") for a in template["data"])

    def test_types_and_tags_are_named_by_title_not_id(self, document):
        # The file names both; the ids are per-instance and mean nothing here.
        for template in document["data"]:
            for attribute in template["data"]:
                assert not attribute["dataType"].isdigit()
                assert not attribute["isaTag"].isdigit()


class TestControlledVocabularies:
    def test_an_enum_field_carries_its_vocabulary_inline(self):
        # CVList removes the need for a separately provisioned Controlled
        # Vocabulary on this route.
        from metaseed.specs.schema import (
            Constraints,
            EntityDefSpec,
            FieldSpec,
            FieldType,
            ProfileSpec,
            SeekEntityConfig,
        )

        spec = ProfileSpec(
            name="cv-probe",
            version="1.0",
            root_entity="Study",
            entities={
                "Study": EntityDefSpec(
                    fields=[
                        FieldSpec(name="sources", type=FieldType.LIST, items="Src")
                    ],
                    seek=SeekEntityConfig(role="Study"),
                ),
                "Src": EntityDefSpec(
                    fields=[
                        FieldSpec(
                            name="country",
                            type=FieldType.STRING,
                            constraints=Constraints(enum=["NL", "DE"]),
                        )
                    ],
                    seek=SeekEntityConfig(role="Sample"),
                ),
            },
        )
        source = to_isa_template_json(spec)["data"][0]
        country = next(a for a in source["data"] if a["name"] == "country")
        assert country["CVList"] == ["NL", "DE"]

    def test_a_plain_field_carries_no_vocabulary(self, document):
        source = _by_level(document)["study source"]
        plain = next(a for a in source["data"] if a["name"] == "organism")
        assert "CVList" not in plain


class TestNaming:
    def test_the_title_is_derivable_without_the_file(self, profile, document):
        # The sync finds a template by this title to attach it to a Sample Type,
        # so it must be reproducible from the profile alone.
        for template in document["data"]:
            assert template["metadata"]["name"] == template_title(
                profile, template["metadata"]["level"]
            )

    def test_the_chain_is_read_from_the_profiles_own_nesting(self, profile):
        assert sample_chain_entities(profile) == ["Source", "Sample", "AssayMaterial"]


class TestRenderersAgree:
    """The file and the ISA form bodies are two renderings of one projection.

    They are written for different destinations, so nothing but this test stops
    them drifting -- and a template whose attributes disagree with the Sample
    Type it is attached to is exactly the mismatch SEEK cannot report usefully.
    """

    @pytest.mark.parametrize(
        ("index", "level", "linked"),
        [(0, "source", None), (1, "sample_collection", "7"), (2, "assay", "7")],
    )
    def test_the_same_attributes_in_the_same_order(
        self, profile, document, index, level, linked
    ):
        entity_name = sample_chain_entities(profile)[index]
        form = sample_type_attributes(
            profile.entities[entity_name],
            level=level,
            isa_tag_ids=TAGS,
            cv_ids={},
            linked_sample_type_id=linked,
        )
        file_attributes = document["data"][index]["data"]

        assert [a["title"] for a in form] == [a["name"] for a in file_attributes]
        assert [a["isa_tag_id"] for a in form] == [
            TAGS[a["isaTag"]] for a in file_attributes
        ]
        assert [a["is_title"] for a in form] == [
            bool(a.get("title")) for a in file_attributes
        ]
        assert [a["required"] for a in form] == [a["required"] for a in file_attributes]


class TestTagFamiliesAgree:
    def test_characteristic_tags_match_the_title_tags_family(self, document):
        # SEEK's own templates never mix them: a data-file level comments its
        # attributes, a material level describes them.
        families = {
            "data_file": {
                "data_file",
                "data_file_comment",
                "input",
                "protocol",
                "parameter_value",
            },
            "other_material": {
                "other_material",
                "other_material_characteristic",
                "input",
                "protocol",
                "parameter_value",
            },
        }
        assay = document["data"][2]
        title_tag = next(a["isaTag"] for a in assay["data"] if a.get("title"))
        allowed = families[title_tag]
        assert {a["isaTag"] for a in assay["data"]} <= allowed
