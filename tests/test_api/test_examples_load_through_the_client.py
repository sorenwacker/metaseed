"""Every shipped example loads through the client API.

The ``examples/`` datasets are the natural source of realistic data for anyone
building on metaseed, and none of them could be loaded by a consumer:
``load_yaml`` returned **0** for every one of them, silently.

The cause was a format mismatch that nothing reported. ``load_from_dict`` reads
the store's own serialization, where each dict carries a ``_type`` key; the
examples are natural nested documents — an Investigation with ``studies:``
inside it — which carry no such key, so every entity was skipped and the count
came back zero. The knowledge of how to walk a nested document lived in a UI
route, so the application could load an example and a library consumer could
not (#246).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from metaseed.api.client import MetaseedClient

EXAMPLES = Path("src/metaseed/examples")


def _examples() -> list[tuple[str, str, Path]]:
    found = []
    for profile_dir in sorted(EXAMPLES.iterdir()):
        if not profile_dir.is_dir():
            continue
        for version_dir in sorted(profile_dir.iterdir()):
            for path in sorted(version_dir.glob("*.yaml")):
                found.append((profile_dir.name, version_dir.name, path))
    return found


@pytest.mark.parametrize(
    ("profile", "version", "path"),
    _examples(),
    ids=[f"{p}-{v}" for p, v, _ in _examples()],
)
def test_an_example_loads_with_its_whole_tree(
    profile: str, version: str, path: Path
) -> None:
    client = MetaseedClient(profile=profile, version=version)

    loaded = client.load_yaml(str(path))

    assert loaded > 1, (
        f"{path} loaded {loaded} entities: a consumer cannot use the shipped examples"
    )
    assert len(client.get_roots()) == 1, "an example has exactly one root"


def test_the_children_are_reachable_from_the_root() -> None:
    """Loaded is not the same as connected: a flat pile of entities is no use."""
    client = MetaseedClient(profile="miappe", version="1.1")
    client.load_yaml("src/metaseed/examples/miappe/1.1/wheat-drought-study.yaml")

    root = client.get_roots()[0]
    children = client.get_children(root.id)

    assert children, "the root has no children; the tree was not reconstructed"
    assert {c.entity_type for c in children} & {"Study", "Contact"}


def test_the_serialized_format_still_loads() -> None:
    """The format ``serialize()`` writes must keep loading, unchanged."""
    client = MetaseedClient(profile="miappe", version="1.1")
    client.create_entity("Investigation", {"unique_id": "INV-1", "title": "T"})
    serialized = client.serialize()

    reloaded = MetaseedClient(profile="miappe", version="1.1")

    assert reloaded.load(serialized) == 1


class TestALoadThatDropsEverythingSaysSo:
    """Returning 0 quietly is how a whole dataset went missing unnoticed."""

    def test_dropping_every_entity_is_logged(self, caplog) -> None:
        from metaseed.facade import ProfileFacade

        facade = ProfileFacade("miappe", "1.1")

        with caplog.at_level("WARNING"):
            loaded = facade.load_from_dict(
                [{"unique_id": "INV-1", "title": "no _type here"}]
            )

        assert loaded == 0
        assert "Loaded 0 of 1 entities" in caplog.text
        assert "load_yaml" in caplog.text, (
            "the warning must name the way that does work"
        )

    def test_a_successful_load_says_nothing(self, caplog) -> None:
        from metaseed.facade import ProfileFacade

        facade = ProfileFacade("miappe", "1.1")

        with caplog.at_level("WARNING"):
            facade.load_from_dict(
                [{"_type": "Investigation", "unique_id": "INV-1", "title": "T"}]
            )

        assert "Loaded 0" not in caplog.text


class TestLoadNestedIsUsableOnItsOwn:
    """A consumer holding a parsed document should not have to write it to disk."""

    def test_a_document_loads_without_a_file(self) -> None:
        from metaseed.facade import ProfileFacade

        facade = ProfileFacade("miappe", "1.1")

        loaded = facade.load_nested(
            {
                "unique_id": "INV-1",
                "title": "T",
                "studies": [{"unique_id": "STU-1", "title": "S"}],
            }
        )

        assert loaded == 2
        assert len(facade.get_roots()) == 1

    def test_a_string_in_a_child_field_is_a_reference_not_a_child(self) -> None:
        from metaseed.facade import ProfileFacade

        facade = ProfileFacade("miappe", "1.1")

        loaded = facade.load_nested(
            {"unique_id": "INV-1", "title": "T", "studies": ["STU-1"]}
        )

        assert loaded == 1, "a plain string names a study, it does not embed one"
