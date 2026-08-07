"""Tests for the pure SEEK JSON:API payload builders (no httpx needed)."""

from __future__ import annotations

from metaseed.seek import payloads


def test_investigation_payload_links_project():
    doc = payloads.investigation_payload(title="Inv", project_id=1, description="d")
    data = doc["data"]
    assert data["type"] == "investigations"
    assert data["attributes"] == {"title": "Inv", "description": "d"}
    assert data["relationships"]["projects"]["data"] == [
        {"type": "projects", "id": "1"}
    ]


def test_investigation_payload_omits_description_when_absent():
    doc = payloads.investigation_payload(title="Inv", project_id="7")
    assert "description" not in doc["data"]["attributes"]


def test_study_payload_links_investigation():
    doc = payloads.study_payload(title="S", investigation_id=3)
    assert doc["data"]["type"] == "studies"
    assert doc["data"]["relationships"]["investigation"]["data"] == {
        "type": "investigations",
        "id": "3",
    }


def test_assay_payload_carries_class_and_type():
    doc = payloads.assay_payload(title="A", study_id=5)
    attrs = doc["data"]["attributes"]
    assert attrs["assay_class"] == {"key": "EXP"}
    assert attrs["assay_type"]["uri"] == payloads.DEFAULT_ASSAY_TYPE_URI
    assert doc["data"]["relationships"]["study"]["data"] == {
        "type": "studies",
        "id": "5",
    }


def test_sample_type_payload_embeds_attributes():
    attr = payloads.sample_attribute(
        title="name", attribute_type_id=8, required=True, is_title=True
    )
    assert attr == {
        "title": "name",
        "required": True,
        "is_title": True,
        "sample_attribute_type": {"id": "8"},
    }
    doc = payloads.sample_type_payload(title="ST", project_id=1, attributes=[attr])
    assert doc["data"]["type"] == "sample_types"
    assert doc["data"]["attributes"]["sample_attributes"] == [attr]
    assert doc["data"]["relationships"]["projects"]["data"] == [
        {"type": "projects", "id": "1"}
    ]


def test_sample_payload_links_type_and_project():
    doc = payloads.sample_payload(sample_type_id=2, project_id=1, data={"name": "x"})
    assert doc["data"]["attributes"]["data"] == {"name": "x"}
    rels = doc["data"]["relationships"]
    assert rels["sample_type"]["data"] == {"type": "sample_types", "id": "2"}
    assert rels["projects"]["data"] == [{"type": "projects", "id": "1"}]


def test_sample_attribute_omits_cv_and_linked_by_default():
    # Back-compat: a plain attribute carries none of the optional keys.
    attr = payloads.sample_attribute(title="n", attribute_type_id=8)
    assert attr == {
        "title": "n",
        "required": False,
        "is_title": False,
        "sample_attribute_type": {"id": "8"},
    }


def test_sample_attribute_carries_pid_when_given():
    attr = payloads.sample_attribute(
        title="organism", attribute_type_id=8, pid="http://schema.org/organism"
    )
    assert attr["pid"] == "http://schema.org/organism"
    # ...and omits it entirely otherwise (blank PIDs are meaningless to SEEK).
    assert "pid" not in payloads.sample_attribute(title="n", attribute_type_id=8)


def test_sample_attribute_carries_cv_pos_and_linked():
    attr = payloads.sample_attribute(
        title="organism",
        attribute_type_id=14,
        required=True,
        pos=3,
        sample_controlled_vocab_id=9,
        allow_cv_free_text=True,
        linked_sample_type_id=2,
    )
    assert attr["pos"] == 3
    assert attr["sample_controlled_vocab_id"] == "9"
    assert attr["allow_cv_free_text"] is True
    assert attr["linked_sample_type_id"] == "2"


def test_controlled_vocab_payload_shape():
    doc = payloads.controlled_vocab_payload(
        title="Organism",
        terms=[{"label": "human", "iri": "NCBITaxon:9606", "parent_iri": None}],
        description="d",
        source_ontology="ncbitaxon",
        ols_root_term_uris="http://purl.obolibrary.org/obo/NCBITaxon_1",
    )
    data = doc["data"]
    assert data["type"] == "sample_controlled_vocabs"
    assert data["attributes"]["title"] == "Organism"
    assert data["attributes"]["source_ontology"] == "ncbitaxon"
    assert data["attributes"]["sample_controlled_vocab_terms_attributes"][0][
        "label"
    ] == ("human")
    assert "relationships" not in data  # CVs are not project-scoped in the payload


def test_controlled_vocab_payload_omits_optional_fields():
    doc = payloads.controlled_vocab_payload(title="Plain", terms=[])
    attrs = doc["data"]["attributes"]
    assert attrs == {"title": "Plain", "sample_controlled_vocab_terms_attributes": []}


class TestIsaFormPayloads:
    """The ISA endpoints take form-encoded bodies, not JSON:API documents.

    ``/isa_studies`` and ``/isa_assays`` back SEEK's web forms; their JSON
    branches are unreachable (``check_json_id_type`` demands a JSON:API ``data``
    member, then ``convert_json_params`` drops the ``isa_*`` key). See
    ``docs/architecture/seek-isa-compliance.md``.
    """

    def test_repeated_attribute_keys_use_empty_brackets_not_indices(self):
        # Numeric indices parse as a Hash, which the controller iterates as an
        # Array and dies with a TypeError 500. This is the whole reason the
        # builder returns ordered pairs rather than a dict.
        pairs = payloads.isa_study_form(
            title="S",
            investigation_id=1,
            source_title="Src",
            source_attributes=[
                payloads.isa_sample_attribute(
                    title="Source Name",
                    attribute_type_id=8,
                    isa_tag_id=1,
                    is_title=True,
                )
            ],
            collection_title="Coll",
            collection_attributes=[
                payloads.isa_sample_attribute(
                    title="Sample Name",
                    attribute_type_id=8,
                    isa_tag_id=3,
                    is_title=True,
                )
            ],
        )
        keys = [k for k, _ in pairs]
        assert any(k.endswith("[sample_attributes][][title]") for k in keys)
        assert not any("[sample_attributes][0]" in k for k in keys)

    def test_study_form_carries_both_sample_types_in_order(self):
        pairs = payloads.isa_study_form(
            title="S",
            investigation_id=7,
            source_title="Src",
            source_attributes=[
                payloads.isa_sample_attribute(
                    title="Source Name",
                    attribute_type_id=8,
                    isa_tag_id=1,
                    is_title=True,
                )
            ],
            collection_title="Coll",
            collection_attributes=[
                payloads.isa_sample_attribute(
                    title="Sample Name",
                    attribute_type_id=8,
                    isa_tag_id=3,
                    is_title=True,
                )
            ],
        )
        as_dict = dict(pairs)
        assert as_dict["isa_study[study][title]"] == "S"
        assert as_dict["isa_study[study][investigation_id]"] == "7"
        assert as_dict["isa_study[source_sample_type][title]"] == "Src"
        assert as_dict["isa_study[sample_collection_sample_type][title]"] == "Coll"

    def test_an_attribute_omits_keys_it_has_no_value_for(self):
        # A blank linked_sample_type_id on a non-link attribute is rejected by
        # SEEK's consistency check, so absent must mean absent.
        attr = payloads.isa_sample_attribute(
            title="Protocol", attribute_type_id=8, isa_tag_id=5
        )
        assert "linked_sample_type_id" not in attr
        assert attr["is_title"] is False

    def test_assay_stream_form_carries_no_sample_type(self):
        # An assay stream owns no Sample Type; ISAAssay only builds one for a
        # non-stream assay, and sending one would be discarded at best.
        pairs = payloads.isa_assay_form(title="Stream", study_id=3, assay_class_id=3)
        keys = [k for k, _ in pairs]
        assert dict(pairs)["isa_assay[assay][assay_class_id]"] == "3"
        assert not any("sample_type" in k for k in keys)
        assert not any("assay_stream_id" in k for k in keys)

    def test_child_assay_form_carries_stream_link_and_input_type(self):
        pairs = payloads.isa_assay_form(
            title="Child",
            study_id=3,
            assay_class_id=1,
            assay_stream_id=81,
            input_sample_type_id=89,
            sample_type_title="Child type",
            sample_type_attributes=[
                payloads.isa_sample_attribute(
                    title="Input",
                    attribute_type_id=19,
                    isa_tag_id=11,
                    linked_sample_type_id=89,
                ),
                payloads.isa_sample_attribute(
                    title="Data File", attribute_type_id=8, isa_tag_id=8, is_title=True
                ),
            ],
        )
        as_dict = dict(pairs)
        assert as_dict["isa_assay[assay][assay_stream_id]"] == "81"
        assert as_dict["isa_assay[input_sample_type_id]"] == "89"
        assert as_dict["isa_assay[sample_type][title]"] == "Child type"

    def test_attribute_type_is_rendered_as_a_nested_object(self):
        # SEEK's sample_type_params reads sample_attribute_type[id]; a flat
        # attribute_type_id is silently ignored and the attribute gets no type.
        pairs = payloads.isa_assay_form(
            title="A",
            study_id=1,
            assay_class_id=1,
            sample_type_title="T",
            sample_type_attributes=[
                payloads.isa_sample_attribute(
                    title="Data File", attribute_type_id=8, isa_tag_id=8, is_title=True
                )
            ],
        )
        keys = [k for k, _ in pairs]
        assert (
            "isa_assay[sample_type][sample_attributes][][sample_attribute_type][id]"
            in keys
        )
        assert not any(k.endswith("[][attribute_type_id]") for k in keys)
