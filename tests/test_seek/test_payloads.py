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
    doc = payloads.sample_payload(
        sample_type_id=2, project_id=1, data={"name": "x"}
    )
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
    assert data["attributes"]["sample_controlled_vocab_terms_attributes"][0]["label"] == (
        "human"
    )
    assert "relationships" not in data  # CVs are not project-scoped in the payload


def test_controlled_vocab_payload_omits_optional_fields():
    doc = payloads.controlled_vocab_payload(title="Plain", terms=[])
    attrs = doc["data"]["attributes"]
    assert attrs == {"title": "Plain", "sample_controlled_vocab_terms_attributes": []}
