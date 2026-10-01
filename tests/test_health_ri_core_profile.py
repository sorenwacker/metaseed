"""Health-RI core 2.0 ships as a built-in profile, with its example and accessor.

Generated from the Health-RI metadata SHACL shapes and requirement sheet; the
authored copy carried two identifier flags on Agent and a literal "None"
pattern on two list fields, which the current loader and model factory refuse.
This pins that the shipped copy loads, that the example is a consistent
catalogue, and that ``metaseed.health_ri_core()`` is the way in.
"""

from __future__ import annotations

import copy
import re
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


# --- fidelity to the recorded shapes -------------------------------------------

SHAPES = Path(__file__).resolve().parent / "fixtures" / "health_ri_shapes"

#: Where the profile names a property differently from the shape's label: the
#: RDF property's own name where the label is a phrase, and one typo in the
#: shapes ("infividuals").
ALIASES = {
    "Agent": {"identifier": "agent_identifier", "url": "homepage"},
    "Catalog": {
        "home_page": "homepage",
        "licence": "license",
        "themes": "theme_taxonomy",
    },
    "DataService": {
        "application_profile": "conforms_to",
        "end_point_description": "endpoint_description",
        "end_point_url": "endpoint_url",
    },
    "Dataset": {"number_of_unique_infividuals": "number_of_unique_individuals"},
}


def _shape_properties(shape: Path) -> dict[str, int]:
    """Each property the shape names, by its label, with its minimum count."""
    props: dict[str, int] = {}
    pattern = r"^<[^>]+#[^>]+>\s+sh:path\s+([a-zA-Z0-9]+:[A-Za-z0-9]+);(.*?)(?=^\S|\Z)"
    for m in re.finditer(
        pattern, shape.read_text(encoding="utf-8"), re.MULTILINE | re.DOTALL
    ):
        local, block = m.group(1), m.group(2)
        label = re.search(r'sh:name\s+"([^"]+)"', block)
        name = label.group(1) if label else local.split(":")[1]
        key = re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_")
        mc = re.search(r"sh:minCount\s+(\d+)", block)
        props[key] = int(mc.group(1)) if mc else 0
    return props


def test_every_shape_property_is_a_field_with_the_shapes_cardinality() -> None:
    spec = builtin_only_loader().load_profile("2.0", "health-ri-core")
    problems: list[str] = []
    for shape in sorted(SHAPES.glob("*.ttl")):
        entity = spec.entities[shape.stem]
        fields = {f.name: f for f in entity.fields}
        aliases = ALIASES.get(shape.stem, {})
        for key, minimum in _shape_properties(shape).items():
            name = aliases.get(key, key)
            if name not in fields:
                problems.append(f"{shape.stem}: shape property {key!r} has no field")
            elif bool(fields[name].required) != (minimum >= 1):
                problems.append(
                    f"{shape.stem}.{name}: shape minCount {minimum}, "
                    f"profile required={fields[name].required}"
                )
    assert problems == []
