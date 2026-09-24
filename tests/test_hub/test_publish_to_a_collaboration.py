"""Publishing a profile to one collaboration rather than to the whole hub.

The hub lets a specification be released to a single SRAM collaboration. A
push that could only say "publish" left the client able to make one kind of
release, so the narrower one was reachable only from the hub's own browser.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from metaseed.hub.profiles import ProfileRef, push_profile

PREFIX = "urn:mace:surf.nl:sram:group:"
CROPXR = PREFIX + "tudelft:cropxr"

PROFILE_YAML = """
name: audience-probe
version: "1.0"
display_name: Audience probe
description: A profile
ontology: T
root_entity: Sample
entities:
  Sample:
    description: a sample
    fields:
      - name: alias
        type: string
        required: true
"""


class _Hub:
    """A hub that records the push it was given."""

    def __init__(self, row: dict | None = None) -> None:
        self.pushed: dict = {}
        self._row = row or {
            "visibility": "published",
            "content_hash": "sha256:abc",
            "audience": CROPXR,
        }

    def list_specs(self) -> list[dict]:
        return []

    def get_spec(self, name: str, version: str) -> str:
        return ""

    def push_spec(
        self, yaml_text: str, *, publish: bool = False, audience: str | None = None
    ) -> tuple[dict, bool]:
        self.pushed = {"publish": publish, "audience": audience}
        return self._row, True

    def unpublish_spec(self, spec_id: str) -> dict:
        return {}


@pytest.fixture
def specs_dir(tmp_path: Path) -> Path:
    target = tmp_path / "audience-probe" / "1.0"
    target.mkdir(parents=True)
    (target / "profile.yaml").write_text(PROFILE_YAML)
    return tmp_path


def test_a_push_can_name_the_collaboration(specs_dir: Path) -> None:
    hub = _Hub()

    outcome = push_profile(
        hub,
        specs_dir,
        ProfileRef("audience-probe", "1.0"),
        publish=True,
        audience=CROPXR,
    )

    assert hub.pushed == {"publish": True, "audience": CROPXR}
    assert outcome.audience == CROPXR


def test_publishing_without_a_collaboration_still_reaches_everyone(
    specs_dir: Path,
) -> None:
    hub = _Hub(
        {"visibility": "published", "content_hash": "sha256:abc", "audience": None}
    )

    outcome = push_profile(
        hub, specs_dir, ProfileRef("audience-probe", "1.0"), publish=True
    )

    assert hub.pushed == {"publish": True, "audience": None}
    assert outcome.audience is None


def test_an_audience_without_publishing_is_refused(specs_dir: Path) -> None:
    """A draft is private; naming an audience for one would be ignored by the
    hub, so it is refused here rather than sent and silently dropped."""
    hub = _Hub()

    with pytest.raises(ValueError, match="publish"):
        push_profile(
            hub, specs_dir, ProfileRef("audience-probe", "1.0"), audience=CROPXR
        )

    assert hub.pushed == {}


# --- the settings page ------------------------------------------------------


def test_the_profiles_panel_offers_the_collaborations() -> None:
    """A capability reachable only from the CLI is half a feature."""
    from pathlib import Path

    panel = Path("src/metaseed/ui/templates/hub/profiles.html").read_text()

    assert 'name="audience"' in panel
    assert "collaborations" in panel


# --- a collaboration, never one of its groups -------------------------------


def test_the_panel_offers_collaborations_without_their_groups() -> None:
    """The hub refuses a group URN for a publish: a release belongs to the
    collaboration. Offering one here would produce a refusal at the far end."""
    from pathlib import Path

    panel = Path("src/metaseed/ui/templates/hub/profiles.html").read_text()

    picker = panel[panel.index('name="audience"') :]
    picker = picker[: picker.index("</select>")]
    assert "collaboration.urn" in picker
    assert "collaboration.groups" not in picker


def test_the_cli_names_a_collaboration_not_a_group() -> None:
    from metaseed.cli.commands.hub import _audience_or_exit

    class _Hub:
        def collaborations(self):
            return [{"urn": CROPXR, "name": "cropxr", "groups": ["phenotyping"]}]

    assert _audience_or_exit(_Hub(), "cropxr") == CROPXR
    with pytest.raises(ValueError, match="group"):
        _audience_or_exit(_Hub(), "tudelft:cropxr:phenotyping")
