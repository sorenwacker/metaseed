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
_NO_EXAMPLE_PROFILES = ("metabolights", "seek", "miappe-htp")


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


def test_isa_example_is_a_single_tree_without_value_object_orphans() -> None:
    """Value-objects stay inline; the example loads as one Investigation tree.

    ISA nests OntologyAnnotation and Comment as property values across nearly
    every entity. Materializing those as separate nodes gave them no parent to
    link back to, so they orphaned at the root (the example showed 13 roots).
    With ownership declared they stay inline and the tree has a single root.
    """
    state = AppState()
    client = TestClient(create_app(state), follow_redirects=True)

    response = client.get("/load-example/isa/1.0")
    assert response.status_code == 200

    roots = [n for n in state.nodes_by_id.values() if not getattr(n, "parent_id", None)]
    assert [r.entity_type for r in roots] == ["Investigation"]

    types = {n.entity_type for n in state.nodes_by_id.values()}
    assert "OntologyAnnotation" not in types, "value-objects must stay inline"
    assert "Comment" not in types
    # Real structural entities are still materialized.
    assert {"Study", "Assay", "Sample", "Protocol"} <= types


def test_profile_descriptions_carry_their_full_text_as_a_tooltip() -> None:
    """The picker clamps descriptions (CSS), so the full text must survive
    somewhere reachable -- the data attribute the title's hover tooltip renders from.
    Without it, a wordy profile's description is cut off with no way to read
    the rest."""
    client = TestClient(create_app(AppState()))
    html = client.get("/new-dataset").text
    # seek-ready-template's description is several sentences; the first is
    # enough to prove the attribute carries it.
    assert 'data-description="An ISA-shaped template' in html


def test_a_long_optional_section_gets_a_filter_and_a_short_one_does_not() -> None:
    """43 optional fields are unfindable by eye, four are not. The filter only
    appears where it earns its place."""
    client = TestClient(create_app(AppState()))
    long_form = client.get("/form/Location?profile=darwin-core&version=1.0").text
    assert 'data-testid="optional-filter"' in long_form
    short_form = client.get("/form/Investigation?profile=isa&version=1.0").text
    assert 'data-testid="optional-filter"' not in short_form


def test_an_example_under_the_user_data_dir_loads_for_a_user_profile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Profiles installed under the user data dir (specs/) keep their examples
    # beside them (examples/<profile>/<version>/*.yaml). The loader used to
    # look only in the packaged directory, so a user profile could never be
    # loaded with example data from the UI.
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    example_dir = tmp_path / "metaseed" / "examples" / "seek-ready-template" / "3.0"
    example_dir.mkdir(parents=True)
    (example_dir / "demo.yaml").write_text(
        "identifier: INV-demo\ntitle: demo\ndescription: d\nstudies: []\n"
    )
    from metaseed.ui.routes.examples import example_exists

    assert example_exists("seek-ready-template", "3.0")
    client = TestClient(create_app(AppState()))
    response = client.get(
        "/load-example/seek-ready-template/3.0", follow_redirects=False
    )
    assert response.status_code in (302, 303, 307), response.text
