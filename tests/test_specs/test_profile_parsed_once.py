"""A profile file is parsed once per process, not once per loader (#311).

Validation builds a ``SpecLoader`` for every nested entity it checks, and each
loader kept its own cache, so a dataset of N records parsed the profile about N
times. On a 1.2 MB profile that was about 4 s per record and hours per dataset.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

import metaseed.specs.loader as loader_module
from metaseed.specs.loader import SpecLoader
from metaseed.specs.schema import ProfileSpec
from metaseed.validators.api import validate

PROFILE = """\
version: "1.0"
name: parse-count-probe
root_entity: Study
entities:
  Study:
    fields:
      - name: unique_id
        type: string
        required: true
      - name: samples
        type: list
        items: Sample
  Sample:
    fields:
      - name: unique_id
        type: string
        required: true
      - name: title
        type: string
        required: true
"""


@pytest.fixture
def profile_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A private profile, so the shared cache starts cold for it."""
    path = tmp_path / "parse-count-probe" / "1.0" / "profile.yaml"
    path.parent.mkdir(parents=True)
    path.write_text(PROFILE, encoding="utf-8")
    monkeypatch.setattr(loader_module, "get_user_specs_dir", lambda: tmp_path)
    return path


@pytest.fixture
def parses(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """Count the profiles the loader builds from a parsed file."""
    calls: list[int] = []
    original = ProfileSpec.model_validate

    def counting(data, *args, **kwargs):
        calls.append(1)
        return original(data, *args, **kwargs)

    monkeypatch.setattr(ProfileSpec, "model_validate", counting)
    return calls


def test_separate_loaders_share_one_parse(
    profile_file: Path, parses: list[int]
) -> None:
    first = SpecLoader().load_profile("1.0", "parse-count-probe")
    second = SpecLoader().load_profile("1.0", "parse-count-probe")

    assert first is second
    assert len(parses) == 1


def test_validating_many_nested_records_parses_the_profile_once(
    profile_file: Path, parses: list[int]
) -> None:
    study = {
        "unique_id": "S1",
        "samples": [{"unique_id": f"SA{i}", "title": "t"} for i in range(20)],
    }

    errors = validate(study, "Study", version="1.0", profile="parse-count-probe")

    assert errors == []
    assert len(parses) == 1


def test_an_edited_file_is_parsed_again(profile_file: Path, parses: list[int]) -> None:
    SpecLoader().load_profile("1.0", "parse-count-probe")
    profile_file.write_text(
        PROFILE.replace(
            "name: parse-count-probe", "name: parse-count-probe\ndescription: edited"
        ),
        encoding="utf-8",
    )

    reloaded = SpecLoader().load_profile("1.0", "parse-count-probe")

    assert reloaded.description == "edited"
    assert len(parses) == 2


@pytest.mark.skipif(not yaml.__with_libyaml__, reason="PyYAML built without libyaml")
def test_the_libyaml_parser_is_used_when_available() -> None:
    assert loader_module.YAML_LOADER is yaml.CSafeLoader
