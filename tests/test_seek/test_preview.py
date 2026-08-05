"""The browsable model preview shown on the SEEK page before an upload.

Projects the built-in ``seek-ready-template`` profile and asserts the Sample Types (with
columns) and Extended Metadata records match what provisioning would create.
"""

from __future__ import annotations

from metaseed.seek.preview import build_model_preview
from metaseed.specs.loader import SpecLoader


def _preview():
    spec = SpecLoader().load_profile(version="1.0", profile="seek-ready-template")
    return build_model_preview(spec)


def test_sample_types_list_the_sample_role_entity_with_its_columns():
    preview = _preview()
    by_entity = {st.entity_type: st for st in preview.sample_types}
    # seek-ready-template.s only Sample-role entity is Sample.
    assert "Sample" in by_entity
    assert "Study" not in by_entity  # Study is an ISA record, not a Sample Type
    cols = {a.name: a for a in by_entity["Sample"].attributes}
    # Its own columns are present (organism etc.); the identity column is carried
    # as the Sample's Title, not repeated as an attribute.
    assert "organism" in cols
    assert "collection_date" in cols


def test_extended_metadata_covers_the_isa_records():
    preview = _preview()
    roles = {em.role for em in preview.extended_metadata}
    assert {"Investigation", "Study", "Assay"} <= roles
    study = next(em for em in preview.extended_metadata if em.role == "Study")
    names = {a.name for a in study.attributes}
    # Custom Study fields appear; SEEK's own record fields (identifier, title,
    # description) and nested structure (samples, assays) do not.
    assert "study_design_type" in names
    assert "experimental_site" in names
    assert "identifier" not in names
    assert "title" not in names
    assert "samples" not in names


def test_types_are_plain_strings_not_enums():
    preview = _preview()
    study = next(em for em in preview.extended_metadata if em.role == "Study")
    start = next(a for a in study.attributes if a.name == "start_date")
    assert start.type == "date"  # not "FieldType.DATE"
    assert isinstance(start.type, str)
