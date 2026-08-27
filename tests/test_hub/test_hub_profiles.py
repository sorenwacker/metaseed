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
    unpublish_profile,
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
    """A hub that keeps drafts per caller and published specs for everyone."""

    def __init__(self) -> None:
        self.drafts: dict[tuple[str, str], tuple[str, str]] = {}
        self.published: dict[tuple[str, str], tuple[str, str]] = {}
        self.refuse: str | None = None
        self.unpublished: list[str] = []

    def list_specs(self) -> list[dict[str, Any]]:
        rows = [
            {
                "id": f"d-{n}-{v}",
                "name": n,
                "version": v,
                "content_hash": h,
                "description": None,
                "tenant_id": "t",
                "visibility": "draft",
                "mine": True,
            }
            for (n, v), (h, _text) in self.drafts.items()
        ]
        rows += [
            {
                "id": f"p-{n}-{v}",
                "name": n,
                "version": v,
                "content_hash": h,
                "description": None,
                "tenant_id": "t",
                "visibility": "published",
                "mine": True,
            }
            for (n, v), (h, _text) in self.published.items()
        ]
        return rows

    def get_spec(self, name: str, version: str) -> str:
        return (self.drafts.get((name, version)) or self.published[(name, version)])[1]

    def push_spec(
        self, yaml_text: str, *, publish: bool = False
    ) -> tuple[dict[str, Any], bool]:
        if self.refuse:
            raise HubApiError(409, self.refuse)
        import yaml

        from metaseed.specs import content_hash
        from metaseed.specs.schema import ProfileSpec

        spec = ProfileSpec.model_validate(yaml.safe_load(yaml_text))
        key = (spec.name, spec.version)
        digest = content_hash(spec)
        store = self.published if publish else self.drafts
        created = key not in store
        if publish and not created and store[key][0] != digest:
            raise HubApiError(409, "already published with different content")
        store[key] = (digest, yaml_text)
        return {
            "id": f"{'p' if publish else 'd'}-{spec.name}-{spec.version}",
            "name": spec.name,
            "version": spec.version,
            "content_hash": digest,
            "visibility": "published" if publish else "draft",
            "mine": True,
        }, created

    def unpublish_spec(self, spec_id: str) -> dict[str, Any]:
        self.unpublished.append(spec_id)
        key = next(k for k in self.published if f"p-{k[0]}-{k[1]}" == spec_id)
        self.drafts[key] = self.published.pop(key)
        return {"id": spec_id, "visibility": "draft"}


@pytest.fixture
def specs_dir(tmp_path: Path) -> Path:
    path = tmp_path / "specs" / "test-pushed" / "1.0" / "profile.yaml"
    path.parent.mkdir(parents=True)
    path.write_text(PROFILE)
    return tmp_path / "specs"


REF = ProfileRef("test-pushed", "1.0")


def test_a_push_is_a_private_draft_and_publishes_nothing(specs_dir: Path) -> None:
    # On the hub "published" means visible to everyone. A push must not decide
    # that for the author: the first version of this did, and three CropXR
    # profiles went hub-wide without anyone choosing it.
    hub = _FakeHub()
    outcome = push_profile(hub, specs_dir, REF)
    assert outcome.kind == "draft"
    assert outcome.visibility == "draft"
    assert outcome.content_hash == local_hash(specs_dir, REF)
    assert hub.published == {}, "nothing was published"
    assert list(hub.drafts) == [("test-pushed", "1.0")]


def test_pushing_again_updates_the_draft_rather_than_multiplying_it(
    specs_dir: Path,
) -> None:
    hub = _FakeHub()
    push_profile(hub, specs_dir, REF)
    (specs_dir / "test-pushed" / "1.0" / "profile.yaml").write_text(
        PROFILE.replace("A profile.", "A revised profile.")
    )
    outcome = push_profile(hub, specs_dir, REF)
    assert outcome.kind == "draft"
    assert len(hub.drafts) == 1
    assert hub.drafts[("test-pushed", "1.0")][0] == local_hash(specs_dir, REF)


def test_publishing_is_asked_for_explicitly(specs_dir: Path) -> None:
    hub = _FakeHub()
    outcome = push_profile(hub, specs_dir, REF, publish=True)
    assert (outcome.kind, outcome.visibility) == ("published", "published")
    assert list(hub.published) == [("test-pushed", "1.0")]
    assert push_profile(hub, specs_dir, REF, publish=True).kind == "identical"


def test_a_published_profile_can_be_withdrawn(specs_dir: Path) -> None:
    hub = _FakeHub()
    push_profile(hub, specs_dir, REF, publish=True)
    assert unpublish_profile(hub, REF) is True
    assert hub.unpublished == ["p-test-pushed-1.0"]
    assert hub.published == {} and list(hub.drafts) == [("test-pushed", "1.0")]
    assert unpublish_profile(hub, REF) is False, (
        "nothing published now, so nothing to withdraw"
    )


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
    hub.push_spec(PROFILE, publish=True)
    specs = tmp_path / "specs"
    target = pull_profile(hub, specs, REF)
    assert target.kind == "new"
    assert (specs / "test-pushed" / "1.0" / "profile.yaml").read_text() == PROFILE


def test_a_local_profile_is_never_replaced_by_a_pull(specs_dir: Path) -> None:
    hub = _FakeHub()
    hub.push_spec(PROFILE.replace("A profile.", "Another profile."), publish=True)
    before = (specs_dir / "test-pushed" / "1.0" / "profile.yaml").read_text()
    target = pull_profile(hub, specs_dir, REF)
    assert target.kind == "differs"
    assert (specs_dir / "test-pushed" / "1.0" / "profile.yaml").read_text() == before


def test_an_identical_local_profile_is_reported_as_such(specs_dir: Path) -> None:
    hub = _FakeHub()
    hub.push_spec(PROFILE, publish=True)
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
