"""The template-bound shape: entities that name an installed ISA Template.

A CropXR-style profile lists sources and samples as siblings under the Study,
materials and data files under the Assay, and links each level to its
predecessor through an ``Input`` field. Its entities carry ISA tags and name
the template installed on the target instance. See
``docs/architecture/seek-isa-compliance.md`` ("Two ways a profile can describe
the chain").
"""

from __future__ import annotations

from typing import Any

from tests.test_seek.test_sync import _FakeSeek, _of_kind

from metaseed import MetaseedClient
from metaseed.seek.isa_types import (
    entity_level,
    sample_type_attribute_plans,
    title_attribute_of,
)
from metaseed.seek.sync import sync_dataset_to_seek
from metaseed.seek.templates import sample_chain_entities, to_isa_template_json
from metaseed.specs.loader import SpecLoader


def _field(name: str, **extra: Any) -> dict[str, Any]:
    return {"name": name, "type": "string", **extra}


_SPEC: dict[str, Any] = {
    "name": "cropxr-mini",
    "version": "1.0",
    "root_entity": "Investigation",
    "entities": {
        "Investigation": {
            "fields": [
                _field("identifier"),
                _field("title"),
                {"name": "studies", "type": "list", "items": "Study"},
            ],
            "seek": {"role": "Investigation"},
        },
        "Study": {
            "fields": [
                _field("study_id"),
                _field("title"),
                {"name": "sources", "type": "list", "items": "Source"},
                {"name": "units", "type": "list", "items": "Unit"},
                {"name": "assays", "type": "list", "items": "Assay"},
            ],
            "seek": {"role": "Study"},
        },
        "Source": {
            "fields": [
                _field("Source Name", isa_tag="source", required=True),
                _field("country"),
            ],
            "seek": {"role": "Sample", "template": "CropXR source"},
        },
        "Unit": {
            # ``title`` is a core field name; on a template-bound entity it is a
            # literal column of the template, not the Sample's Title attribute.
            "fields": [
                _field("Input", isa_tag="input"),
                _field("subject_id", isa_tag="sample", required=True),
                _field("title"),
                _field("type", isa_tag="protocol"),
            ],
            "seek": {
                "role": "Sample",
                "template": "CropXR phenotyping observation unit",
            },
        },
        "Assay": {
            "fields": [
                _field("identifier"),
                _field("title"),
                _field("trait"),
                {"name": "materials", "type": "list", "items": "Material"},
                {"name": "files", "type": "list", "items": "File"},
            ],
            "seek": {"role": "Assay"},
        },
        "Material": {
            "fields": [
                _field("Input", isa_tag="input"),
                _field("experiment_id", isa_tag="other_material", required=True),
                _field("method", isa_tag="protocol"),
                _field("scale", isa_tag="parameter_value"),
            ],
            "seek": {"role": "Sample", "template": "CropXR phenotyping assay"},
        },
        "File": {
            "fields": [
                _field("Input", isa_tag="input"),
                _field("file_name", isa_tag="data_file", required=True),
                _field("protocol", isa_tag="protocol"),
            ],
            "seek": {"role": "Sample", "template": "CropXR phenotyping data file"},
        },
    },
}


def _profile():
    return MetaseedClient.from_spec(_SPEC).facade.profile_spec


def _dataset() -> MetaseedClient:
    c = MetaseedClient.from_spec(_SPEC)
    inv = c.create_entity(
        "Investigation", {"identifier": "I1", "title": "inv"}, skip_validation=True
    )
    study = c.create_entity(
        "Study",
        {"study_id": "S1", "title": "study"},
        parent_id=inv.id,
        skip_validation=True,
    )
    # Deliberately created before its Source: the walk must order by level,
    # not by the order the dataset lists its children in.
    c.create_entity(
        "Unit",
        {"Input": "SRC-1", "subject_id": "OU-1", "title": "unit one", "type": "plot"},
        parent_id=study.id,
        skip_validation=True,
    )
    c.create_entity(
        "Source",
        {"Source Name": "SRC-1", "country": "NL"},
        parent_id=study.id,
        skip_validation=True,
    )
    assay = c.create_entity(
        "Assay",
        {"identifier": "A1", "title": "assay one", "trait": "height"},
        parent_id=study.id,
        skip_validation=True,
    )
    c.create_entity(
        "Material",
        {"Input": "OU-1", "experiment_id": "EXP-1", "method": "ruler"},
        parent_id=assay.id,
        skip_validation=True,
    )
    c.create_entity(
        "File",
        {"Input": "EXP-1", "file_name": "heights.csv", "protocol": "export"},
        parent_id=assay.id,
        skip_validation=True,
    )
    return c


class TestTheProfileDescribesTheTemplate:
    def test_the_level_follows_from_the_title_tag(self) -> None:
        p = _profile()
        assert entity_level(p.entities["Source"]) == "source"
        assert entity_level(p.entities["Unit"]) == "sample_collection"
        assert entity_level(p.entities["Material"]) == "material"
        assert entity_level(p.entities["File"]) == "assay"
        assert entity_level(p.entities["Study"]) is None

    def test_the_title_attribute_is_the_title_tagged_field(self) -> None:
        p = _profile()
        assert title_attribute_of(p.entities["Source"]) == "Source Name"
        assert title_attribute_of(p.entities["Unit"]) == "subject_id"
        assert title_attribute_of(p.entities["File"]) == "file_name"

    def test_a_template_bound_entity_plans_exactly_its_own_columns(self) -> None:
        # No synthesized Title/Input/Protocol: the entity's fields ARE the
        # template's columns, carrying their declared tags.
        p = _profile()
        plans = sample_type_attribute_plans(
            p.entities["Unit"], level="sample_collection", linked=True
        )
        assert [(x.title, x.isa_tag, x.is_title) for x in plans] == [
            ("Input", "input", False),
            ("subject_id", "sample", True),
            ("title", "sample_characteristic", False),
            ("type", "protocol", False),
        ]
        assert plans[0].attribute_type_title == "Registered Sample List"

    def test_the_chain_is_found_by_level_not_by_nesting(self) -> None:
        assert sample_chain_entities(_profile()) == ["Source", "Unit"]

    def test_the_template_file_reproduces_the_installed_templates(self) -> None:
        # The same plan renders the download, so a fresh instance can be
        # provisioned with the templates this profile expects to find.
        doc = to_isa_template_json(_profile())
        by_title = {t["metadata"]["name"]: t for t in doc["data"]}
        assert set(by_title) == {
            "CropXR source",
            "CropXR phenotyping observation unit",
            "CropXR phenotyping assay",
            "CropXR phenotyping data file",
        }
        assert (
            by_title["CropXR phenotyping assay"]["metadata"]["level"]
            == "assay - material"
        )
        assert [a["name"] for a in by_title["CropXR source"]["data"]] == [
            "Source Name",
            "country",
        ]
        assert by_title["CropXR source"]["data"][0]["title"] is True


class TestTheSyncHonoursTheTemplate:
    def test_study_types_attach_the_installed_templates(self) -> None:
        seek = _FakeSeek()
        result = sync_dataset_to_seek(seek, _dataset(), project_id="1")
        assert not result.errors, result.errors
        (study,) = _of_kind(seek, "study")
        assert study["source_template_id"] == "template-for-CropXR source"
        assert (
            study["collection_template_id"]
            == "template-for-CropXR phenotyping observation unit"
        )
        assert [a["title"] for a in study["source_attributes"]] == [
            "Source Name",
            "country",
        ]

    def test_each_assay_level_entity_becomes_its_own_chained_seek_assay(self) -> None:
        seek = _FakeSeek()
        result = sync_dataset_to_seek(seek, _dataset(), project_id="1")
        assays = _of_kind(seek, "assay")
        # Named after the template each is built from -- the model's own
        # words, not metaseed's entity names.
        assert [a["title"] for a in assays] == [
            "assay one (CropXR phenotyping assay)",
            "assay one (CropXR phenotyping data file)",
        ]
        assert [a["template_id"] for a in assays] == [
            "template-for-CropXR phenotyping assay",
            "template-for-CropXR phenotyping data file",
        ]
        material_type = next(
            iter(seek.assay_types[result.assays[next(iter(result.assays))]].values())
        )
        # The data-file assay takes its inputs from the material assay's type,
        # the material assay from the Study's Sample Collection type.
        assert assays[1]["input_sample_type_id"] == material_type
        collection_type = list(
            seek.study_types[next(iter(result.studies.values()))].values()
        )[1]
        assert assays[0]["input_sample_type_id"] == collection_type

    def test_samples_are_placed_by_level_with_inputs_resolved_by_title(self) -> None:
        seek = _FakeSeek()
        result = sync_dataset_to_seek(seek, _dataset(), project_id="1")
        assert not result.unlinked, result.unlinked
        samples = _of_kind(seek, "sample")
        titles = [s["data"] for s in samples]
        assert titles[0]["Source Name"] == "SRC-1", (
            "the Source is placed first, whatever the tree order"
        )
        unit = titles[1]
        assert unit["subject_id"] == "OU-1"
        assert unit["title"] == "unit one", (
            "a template column named title stays a column"
        )
        assert "Title" not in unit
        # The input is written under SEEK's key for it -- the predecessor
        # type's title attribute -- and holds the predecessor's SEEK id.
        source_id = next(iter(result.samples.values()))
        assert unit["Input (Source Name)"] == [source_id]
        assert "Input (subject_id)" in titles[2]
        assert "Input (experiment_id)" in titles[3]

    def test_the_protocol_lands_on_the_protocol_tagged_column(self) -> None:
        seek = _FakeSeek()
        sync_dataset_to_seek(seek, _dataset(), project_id="1")
        samples = _of_kind(seek, "sample")
        assert "Protocol" not in samples[1]["data"]
        assert samples[1]["data"]["type"] == "plot"

    def test_an_input_naming_nothing_placed_is_reported(self) -> None:
        c = _dataset()
        study = next(n for n in c.get_tree()[0].children)
        c.create_entity(
            "Unit",
            {"Input": "NO-SUCH", "subject_id": "OU-9"},
            parent_id=study.id,
            skip_validation=True,
        )
        result = sync_dataset_to_seek(_FakeSeek(), c, project_id="1")
        assert any("NO-SUCH" in msg for _, msg in result.unlinked), result.unlinked
        # Not pushed either: the installed templates require the input, so
        # SEEK would refuse it with a message naming the attribute, not the cause.
        assert len(result.samples) == 4


def test_input_is_an_isa_tag_a_field_may_carry() -> None:
    from metaseed.specs.schema import ISA_TAGS

    assert "input" in ISA_TAGS


def test_the_seek_ready_profile_is_the_untagged_case_of_the_same_rules() -> None:
    p = SpecLoader().load_profile(version="3.0", profile="seek-ready-template")
    assert entity_level(p.entities["Source"]) is None
    assert sample_chain_entities(p) == ["Source", "Sample", "AssayMaterial"]
    assert title_attribute_of(p.entities["Source"]) == "Title"  # synthesized


class TestAnInputReferenceChoosesThePredecessor:
    def test_an_assay_level_entity_links_to_the_entity_its_input_references(
        self,
    ) -> None:
        # A combined "assay with data file" takes its input from the study
        # sample, not from the material the level order would chain it to.
        import copy

        spec = copy.deepcopy(_SPEC)
        spec["entities"]["Combined"] = {
            "fields": [
                _field("Input", isa_tag="input", reference="Unit"),
                _field("file_name", isa_tag="data_file", required=True),
                _field("protocol", isa_tag="protocol"),
            ],
            "seek": {
                "role": "Sample",
                "template": "CropXR phenotyping assay with data file",
            },
        }
        spec["entities"]["Assay"]["fields"].append(
            {"name": "combined", "type": "list", "items": "Combined"}
        )
        c = MetaseedClient.from_spec(spec)
        inv = c.create_entity(
            "Investigation", {"identifier": "I1"}, skip_validation=True
        )
        study = c.create_entity(
            "Study", {"study_id": "S1"}, parent_id=inv.id, skip_validation=True
        )
        c.create_entity(
            "Source", {"Source Name": "SRC-1"}, parent_id=study.id, skip_validation=True
        )
        c.create_entity(
            "Unit",
            {"Input": ["SRC-1"], "subject_id": "OU-1"},
            parent_id=study.id,
            skip_validation=True,
        )
        assay = c.create_entity(
            "Assay",
            {"identifier": "A1", "title": "assay one"},
            parent_id=study.id,
            skip_validation=True,
        )
        c.create_entity(
            "Material",
            {"Input": ["OU-1"], "experiment_id": "EXP-1"},
            parent_id=assay.id,
            skip_validation=True,
        )
        c.create_entity(
            "File",
            {"Input": ["EXP-1"], "file_name": "a.csv"},
            parent_id=assay.id,
            skip_validation=True,
        )
        c.create_entity(
            "Combined",
            {"Input": ["OU-1"], "file_name": "b.zip"},
            parent_id=assay.id,
            skip_validation=True,
        )
        seek = _FakeSeek()
        result = sync_dataset_to_seek(seek, c, project_id="1")
        assert not result.unlinked, result.unlinked
        assays = {a["title"]: a for a in _of_kind(seek, "assay")}
        collection_type = list(
            seek.study_types[next(iter(result.studies.values()))].values()
        )[1]
        assert (
            assays["assay one (CropXR phenotyping assay with data file)"][
                "input_sample_type_id"
            ]
            == collection_type
        )
        combined = next(
            s for s in _of_kind(seek, "sample") if s["data"].get("file_name") == "b.zip"
        )
        assert "Input (subject_id)" in combined["data"]


class TestTheSeekPageReflectsTheTemplates:
    def test_provisioning_creates_no_sample_types_for_template_bound_entities(
        self,
    ) -> None:
        # The Sample Types come from the installed templates at sync time;
        # profile-named copies would sit unused beside them. The Controlled
        # Vocabularies are still needed, so those are planned.
        import copy

        from metaseed.seek.provision import build_provisioning_plan

        spec = copy.deepcopy(_SPEC)
        spec["entities"]["Source"]["fields"][1]["constraints"] = {"enum": ["NL", "DE"]}
        profile = MetaseedClient.from_spec(spec).facade.profile_spec
        plan = build_provisioning_plan(profile)
        assert not plan.sample_types
        assert [cv.title for cv in plan.cvs] == ["cropxr-mini Source.country"]

    def test_the_preview_shows_the_installed_templates_with_levels_and_tags(
        self,
    ) -> None:
        from metaseed.seek.preview import build_model_preview

        preview = build_model_preview(_profile())
        assert preview.template_bound
        by_entity = {st.entity_type: st for st in preview.sample_types}
        assert [st.entity_type for st in preview.sample_types] == [
            "Source",
            "Unit",
            "Material",
            "File",
        ], "chain order, not alphabetical"
        assert by_entity["Unit"].template == "CropXR phenotyping observation unit"
        assert by_entity["Unit"].level == "study sample"
        assert by_entity["Material"].level == "assay - material"
        cols = {a.name: a for a in by_entity["Unit"].attributes}
        assert "Title" not in cols, "nothing synthesized: the template's columns only"
        assert cols["Input"].isa_tag == "input"
        assert cols["subject_id"].isa_tag == "sample"
        assert cols["title"].isa_tag == "sample_characteristic"
