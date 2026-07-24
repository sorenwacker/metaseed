"""End-to-end UI tests for loading bundled example datasets.

Guards the full "Load Example" flow that broke silently before: clicking the
link must load the example into state AND render its entity tree (not dump the
user back on the empty datasets overview), for every bundled example. Also
guards the picker: the "Load Example" link appears only where an example exists,
and versions are listed newest-first.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from metaseed.ui.app import create_app
from metaseed.ui.state import AppState

_EXAMPLES_DIR = Path(__file__).resolve().parents[2] / "src" / "metaseed" / "examples"


def _bundled_examples() -> list[tuple[str, str]]:
    """(profile, version) pairs that ship at least one example YAML."""
    pairs: list[tuple[str, str]] = []
    if not _EXAMPLES_DIR.is_dir():
        return pairs
    for profile_dir in sorted(_EXAMPLES_DIR.iterdir()):
        if not profile_dir.is_dir():
            continue
        for version_dir in sorted(profile_dir.iterdir()):
            if version_dir.is_dir() and any(version_dir.glob("*.yaml")):
                pairs.append((profile_dir.name, version_dir.name))
    return pairs


_EXAMPLE_CASES = _bundled_examples()
# Profiles known to ship no example — the picker must NOT offer a link for them.
_NO_EXAMPLE_PROFILES = ("metabolights", "jerm", "miappe-htp")


@pytest.mark.parametrize(("profile", "version"), _EXAMPLE_CASES)
def test_every_example_loads_and_renders(profile: str, version: str) -> None:
    state = AppState()
    client = TestClient(create_app(state), follow_redirects=True)

    response = client.get(f"/load-example/{profile}/{version}")

    # The request must succeed (not 500) and actually populate the dataset.
    assert response.status_code == 200, f"{profile}/{version} -> {response.status_code}"
    assert state.nodes_by_id, f"{profile}/{version}: no entities loaded into state"

    # Every loaded entity — not just the root — must be listed in the rendered
    # page. This guards the regression where only the root showed and the nested
    # entities were invisible.
    for node in state.nodes_by_id.values():
        assert node.label, f"{profile}/{version}: node {node.entity_type} has no label"
        assert node.label in response.text, (
            f"{profile}/{version}: entity '{node.label}' ({node.entity_type}) "
            f"loaded but not rendered"
        )


def test_pride_example_materializes_all_entities() -> None:
    # PRIDE's Dataset owns Species/Instrument/Contact/Sample/DataFile/... as
    # nested lists; loading the example must surface every one as an entity, not
    # collapse them into the root.
    state = AppState()
    client = TestClient(create_app(state), follow_redirects=True)
    client.get("/load-example/pride/1.0")

    types = {n.entity_type for n in state.nodes_by_id.values()}
    assert {
        "Dataset",
        "Species",
        "Instrument",
        "Modification",
        "Contact",
        "Publication",
        "Sample",
        "DataFile",
    } <= types, f"missing entity types: {types}"
    # both example samples are present
    sample_labels = {
        n.label for n in state.nodes_by_id.values() if n.entity_type == "Sample"
    }
    assert sample_labels == {"HeLa-control-rep1", "HeLa-heatshock-rep1"}


def test_example_link_only_shown_when_example_exists() -> None:
    client = TestClient(create_app(AppState()))
    html = client.get("/new-dataset").text

    for profile, version in _EXAMPLE_CASES:
        assert f"example-{profile}-v{version}" in html, (
            f"missing example link for {profile} v{version}"
        )

    for profile in _NO_EXAMPLE_PROFILES:
        assert f"example-{profile}-v" not in html, (
            f"example link shown for {profile}, which has no example"
        )


def test_versions_listed_newest_first() -> None:
    # miappe ships 1.1 and 1.2; the newer version must appear first in the picker.
    client = TestClient(create_app(AppState()))
    html = client.get("/new-dataset").text
    assert "profile-miappe-v1.2" in html and "profile-miappe-v1.1" in html
    assert html.index("profile-miappe-v1.2") < html.index("profile-miappe-v1.1")


def test_example_materializes_nested_grandchildren() -> None:
    """Loading an example materializes the whole tree, not just depth 1.

    Regression: building the root model coerces the nested dicts in the example
    payload into model instances *in place*, and the tree walk only descends
    into dicts. Walking the mutated payload therefore stopped at the root's
    direct children and dropped every grandchild (miappe 1.2 surfaced 4 of ~50
    entities; isa 1.0 surfaced 6 of ~275).
    """
    state = AppState()
    client = TestClient(create_app(state), follow_redirects=True)

    response = client.get("/load-example/miappe/1.2")
    assert response.status_code == 200

    types = [node.entity_type for node in state.nodes_by_id.values()]
    assert "Study" in types  # direct child of the root
    # Grandchildren: these live under Study, one level deeper than the root.
    assert "ObservationUnit" in types, f"grandchildren dropped: {sorted(set(types))}"
    assert "BiologicalMaterial" in types, f"grandchildren dropped: {sorted(set(types))}"
    assert len(types) > 20, f"expected the full tree, materialized only {len(types)}"
