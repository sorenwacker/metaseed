"""Entity types are ordered so every container precedes the types it contains.

A profile lists its entities in authoring order. Consumers that iterate that
order -- the Excel export (one sheet per entity), the graph legend -- must never
meet a child type before the type that contains it, or the export puts the root
last and the hierarchy cannot be read. The invariant that holds for a tree and a
graph alike is *topological validity*: every container is declared before the
types it contains. ``containment_order`` produces such an order, preserving the
author's order wherever it is already valid; the loader warns when a spec is
not, and ``SpecBuilder.to_yaml`` saves it corrected.
"""

from __future__ import annotations

import logging

import pytest
import yaml

from metaseed.specs.builder import SpecBuilder
from metaseed.specs.loader import SpecLoader
from metaseed.specs.ordering import (
    containment_order,
    entity_order,
    is_in_containment_order,
)
from tests.builtin_specs import builtin_only_loader

# --- the algorithm ---------------------------------------------------------


def test_an_already_valid_order_is_returned_unchanged() -> None:
    names = ["Root", "Child", "Grandchild"]
    children = {"Root": ["Child"], "Child": ["Grandchild"], "Grandchild": []}
    assert containment_order(names, children) == names


def test_a_root_declared_last_moves_to_the_front() -> None:
    # The CropXR glitch: the tree is declared leaf-first, root last.
    names = ["Grandchild", "Child", "Root"]
    children = {"Root": ["Child"], "Child": ["Grandchild"], "Grandchild": []}
    assert containment_order(names, children) == ["Root", "Child", "Grandchild"]


def test_a_shared_child_lands_after_all_of_its_parents() -> None:
    # A DAG: one type contained by two parents must follow both, and the two
    # parents stay grouped rather than being split by their shared child.
    names = ["A", "B", "Shared", "Root"]
    children = {"Root": ["A", "B"], "A": ["Shared"], "B": ["Shared"], "Shared": []}
    order = containment_order(names, children)
    assert order[0] == "Root"
    assert order.index("A") < order.index("Shared")
    assert order.index("B") < order.index("Shared")


def test_a_containment_cycle_neither_hangs_nor_drops_a_member() -> None:
    order = containment_order(["A", "B"], {"A": ["B"], "B": ["A"]})
    assert set(order) == {"A", "B"}


def test_the_order_is_stable_where_no_constraint_applies() -> None:
    # Independent siblings keep their declared order.
    names = ["Root", "B", "A"]
    children = {"Root": ["A", "B"], "A": [], "B": []}
    assert containment_order(names, children) == ["Root", "B", "A"]


# --- the guarantee for the shipped profiles --------------------------------


def _builtin_profiles() -> list[tuple[str, str]]:
    loader = builtin_only_loader()
    return [
        (profile, version)
        for profile in loader.list_profiles()
        for version in loader.list_versions(profile)
    ]


@pytest.mark.parametrize("profile,version", _builtin_profiles())
def test_every_shipped_profile_declares_entities_in_containment_order(
    profile: str, version: str
) -> None:
    """No shipped profile may declare a child before the type that contains it.

    The gate that keeps the invariant true for the profiles metaseed ships:
    a future edit that lists an entity above its container fails here, naming
    the order it should have.
    """
    spec = builtin_only_loader(profile).load_profile(version=version, profile=profile)
    assert is_in_containment_order(spec), (
        f"{profile} {version} declares a child before its container; "
        f"expected order: {' > '.join(entity_order(spec))}"
    )


# --- save rewrites a mis-ordered spec --------------------------------------

_ROOT_LAST = {
    "name": "demo",
    "version": "1.0",
    "root_entity": "Investigation",
    "entities": {
        "Sample": {
            "fields": [{"name": "sample_id", "type": "string", "description": "d"}]
        },
        "Study": {
            "fields": [
                {"name": "study_id", "type": "string", "description": "d"},
                {
                    "name": "samples",
                    "type": "list",
                    "items": "Sample",
                    "description": "d",
                },
            ]
        },
        "Investigation": {
            "fields": [
                {"name": "identifier", "type": "string", "description": "d"},
                {
                    "name": "studies",
                    "type": "list",
                    "items": "Study",
                    "description": "d",
                },
            ]
        },
    },
}


def test_to_yaml_writes_entities_in_containment_order() -> None:
    from metaseed.specs.schema import ProfileSpec

    builder = SpecBuilder.from_spec(ProfileSpec.model_validate(_ROOT_LAST))
    written = yaml.safe_load(builder.to_yaml())
    assert list(written["entities"]) == ["Investigation", "Study", "Sample"]


# --- the loader warns on a mis-ordered spec --------------------------------


def test_loading_a_mis_ordered_spec_warns(tmp_path, monkeypatch, caplog) -> None:
    from metaseed.specs import loader as loader_module

    profile_dir = tmp_path / "rootlast" / "1.0"
    profile_dir.mkdir(parents=True)
    (profile_dir / "profile.yaml").write_text(
        yaml.safe_dump({**_ROOT_LAST, "name": "rootlast"}), encoding="utf-8"
    )
    monkeypatch.setattr(loader_module, "get_user_specs_dir", lambda: tmp_path)
    loader = SpecLoader(profile="rootlast")
    with caplog.at_level(logging.WARNING, logger="metaseed.specs.loader"):
        loader.load_profile(version="1.0", profile="rootlast")
    assert any("containment order" in record.message for record in caplog.records)
