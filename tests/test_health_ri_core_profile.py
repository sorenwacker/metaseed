"""Health-RI core 2.0 ships as a built-in profile, with its example and accessor.

Generated from the Health-RI metadata SHACL shapes and requirement sheet; the
authored copy carried two identifier flags on Agent and a literal "None"
pattern on two list fields, which the current loader and model factory refuse.
This pins that the shipped copy loads, that the example is a consistent
catalogue, and that ``metaseed.health_ri_core()`` is the way in.
"""

from __future__ import annotations

import copy
from pathlib import Path

import yaml

from metaseed import MetaseedClient, health_ri_core
from metaseed.profiles import ProfileFactory
from tests.builtin_specs import builtin_only_loader

EXAMPLE = (
    Path(__file__).resolve().parents[1] / "src/metaseed/examples/health-ri-core/2.0"
)


def test_the_profile_is_built_in_with_catalog_as_its_root() -> None:
    spec = builtin_only_loader().load_profile("2.0", "health-ri-core")
    assert spec.root_entity == "Catalog"
    assert {
        "Catalog",
        "Dataset",
        "Distribution",
        "DataService",
        "Agent",
        "Kind",
    } <= set(spec.entities)
    agent = spec.entities["Agent"]
    assert [f.name for f in agent.fields if f.is_identifier] == ["agent_identifier"]


def test_the_accessor_opens_the_profile() -> None:
    facade = health_ri_core()
    assert facade.profile == "health-ri-core" and facade.version == "2.0"
    assert facade.Catalog.identifier_field == "identifier"


def test_the_example_is_a_consistent_catalogue() -> None:
    facade = ProfileFactory().create("health-ri-core", "2.0")
    facade.load_nested(
        copy.deepcopy(yaml.safe_load(next(EXAMPLE.glob("*.yaml")).read_text())),
        "Catalog",
    )
    result = MetaseedClient.from_facade(facade).validate()

    assert result.valid, [f"{i.field}: {i.message}" for i in result.issues]
