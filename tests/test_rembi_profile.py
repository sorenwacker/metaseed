"""REMBI 1.5 ships as a built-in profile, with its example and its accessor.

Built with the specification tools against the BioImage Archive's REMBI
submission model; this pins that the shipped copy loads, that the example is a
complete, internally consistent submission, and that ``metaseed.rembi()`` is
the way in.
"""

from __future__ import annotations

import copy
from pathlib import Path

import yaml

from metaseed import MetaseedClient, rembi
from metaseed.profiles import ProfileFactory
from tests.builtin_specs import builtin_only_loader

EXAMPLE = Path(__file__).resolve().parents[1] / "src/metaseed/examples/rembi/1.5"


def test_the_profile_is_built_in_with_study_as_its_root() -> None:
    spec = builtin_only_loader().load_profile("1.5", "rembi")
    assert spec.root_entity == "Study"
    assert {
        "Study",
        "StudyComponent",
        "ImageFile",
        "Biosample",
        "Specimen",
        "ImageAcquisition",
        "FileLevelMetadata",
    } <= set(spec.entities)
    assert spec.entities["ImageAcquisition"].fields[2].name == "imaging_method"


def test_the_profile_follows_the_rembi_model_reference() -> None:
    """The three parts a field-by-field comparison with the BioImage Archive's
    model reference found missing: the version on every component, the
    annotation's own authors, and per-file annotation metadata."""
    spec = builtin_only_loader().load_profile("1.5", "rembi")
    component = {f.name: f for f in spec.entities["StudyComponent"].fields}
    assert component["rembi_version"].required
    annotation = {f.name: f for f in spec.entities["Annotation"].fields}
    assert annotation["authors"].items == "Author"
    assert annotation["file_metadata"].items == "FileLevelMetadata"
    file_level = {f.name: f for f in spec.entities["FileLevelMetadata"].fields}
    assert {
        "annotation_id",
        "source_image_id",
        "annotation_type",
        "transformations",
    } <= set(file_level)


def test_the_accessor_opens_the_profile() -> None:
    facade = rembi()
    assert facade.profile == "rembi" and facade.version == "1.5"
    assert facade.Study.identifier_field == "identifier"


def test_the_example_is_a_consistent_submission() -> None:
    """Every study component names a biosample, specimen and acquisition that
    exist; every child names its study; nothing required is missing."""
    facade = ProfileFactory().create("rembi", "1.5")
    facade.load_nested(
        copy.deepcopy(yaml.safe_load(next(EXAMPLE.glob("*.yaml")).read_text())), "Study"
    )
    result = MetaseedClient.from_facade(facade).validate()

    assert result.valid, [f"{i.field}: {i.message}" for i in result.issues]
