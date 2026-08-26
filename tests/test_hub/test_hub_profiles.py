"""A user-local profile goes to the hub as a published spec, and comes back the same."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from metaseed.hub.client import HubApiError
from metaseed.hub.profiles import (
    ProfileRef,
    local_hash,
    local_profiles,
    profile_pull_target,
    pull_profile,
    push_profile,
)

PROFILE = """\
spec_version: '0.1'
version: '1.0'
name: test-pushed
display_name: Pushed
description: A profile.
root_entity: Study
entities:
  Study:
    description: A study.
    fields:
      - name: identifier
        type: string
        required: true
        is_identifier: true
"""


class _FakeHub:
    def __init__(self) -> None:
        self.published: dict[tuple[str, str], tuple[str, str]] = {}
        self.refuse: str | None = None

    def list_specs(self) -> list[dict[str, Any]]:
        return [
            {
                "name": n,
                "version": v,
                "content_hash": h,
                "id": "s",
                "description": None,
                "tenant_id": "t",
            }
            for (n, v), (h, _text) in self.published.items()
        ]

    def get_spec(self, name: str, version: str) -> str:
        return self.published[(name, version)][1]

    def publish_spec(self, yaml_text: str) -> tuple[dict[str, Any], bool]:
        if self.refuse:
            raise HubApiError(409, self.refuse)
        import yaml

        from metaseed.specs import content_hash
        from metaseed.specs.schema import ProfileSpec

        spec = ProfileSpec.model_validate(yaml.safe_load(yaml_text))
        key = (spec.name, spec.version)
        digest = content_hash(spec)
        created = key not in self.published
        self.published.setdefault(key, (digest, yaml_text))
        return {
            "name": spec.name,
            "version": spec.version,
            "content_hash": digest,
        }, created


@pytest.fixture
def specs_dir(tmp_path: Path) -> Path:
    path = tmp_path / "specs" / "test-pushed" / "1.0" / "profile.yaml"
    path.parent.mkdir(parents=True)
    path.write_text(PROFILE)
    return tmp_path / "specs"


REF = ProfileRef("test-pushed", "1.0")


def test_a_pushed_profile_is_published_with_the_local_content_hash(
    specs_dir: Path,
) -> None:
    hub = _FakeHub()
    outcome = push_profile(hub, specs_dir, REF)
    assert outcome.kind == "published"
    assert outcome.content_hash == local_hash(specs_dir, REF)
    assert push_profile(hub, specs_dir, REF).kind == "identical"


def test_a_profile_that_is_not_local_cannot_be_pushed(specs_dir: Path) -> None:
    with pytest.raises(FileNotFoundError):
        push_profile(_FakeHub(), specs_dir, ProfileRef("test-pushed", "2.0"))


def test_the_hubs_refusal_reaches_the_caller(specs_dir: Path) -> None:
    hub = _FakeHub()
    hub.refuse = "'test-pushed' 1.0 is already published with different content"
    with pytest.raises(HubApiError, match="different content"):
        push_profile(hub, specs_dir, REF)


def test_a_pulled_profile_lands_in_the_specs_directory(tmp_path: Path) -> None:
    hub = _FakeHub()
    hub.publish_spec(PROFILE)
    specs = tmp_path / "specs"
    target = pull_profile(hub, specs, REF)
    assert target.kind == "new"
    assert (specs / "test-pushed" / "1.0" / "profile.yaml").read_text() == PROFILE


def test_a_local_profile_is_never_replaced_by_a_pull(specs_dir: Path) -> None:
    hub = _FakeHub()
    hub.publish_spec(PROFILE.replace("A profile.", "Another profile."))
    before = (specs_dir / "test-pushed" / "1.0" / "profile.yaml").read_text()
    target = pull_profile(hub, specs_dir, REF)
    assert target.kind == "differs"
    assert (specs_dir / "test-pushed" / "1.0" / "profile.yaml").read_text() == before


def test_an_identical_local_profile_is_reported_as_such(specs_dir: Path) -> None:
    hub = _FakeHub()
    hub.publish_spec(PROFILE)
    assert pull_profile(hub, specs_dir, REF).kind == "identical"
    assert profile_pull_target(specs_dir, REF, remote_hash=None).kind == "differs"


def test_local_profiles_are_the_profile_files_under_the_specs_directory(
    specs_dir: Path,
) -> None:
    (specs_dir / "test-other" / "2.1").mkdir(parents=True)
    (specs_dir / "test-other" / "2.1" / "profile.yaml").write_text(PROFILE)
    (specs_dir / "test-other" / "notes.txt").write_text("not a profile")
    assert local_profiles(specs_dir) == [
        ProfileRef("test-other", "2.1"),
        ProfileRef("test-pushed", "1.0"),
    ]
    assert local_profiles(specs_dir / "missing") == []
