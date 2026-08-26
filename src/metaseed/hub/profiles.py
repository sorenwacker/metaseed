"""Profiles between the user's specs directory and a hub's published specs.

A profile lives locally as ``<specs dir>/<name>/<version>/profile.yaml``.
Pushing sends that document; the hub publishes it or refuses under its
version-bump gate. Pulling writes a published one to the same place, never
over a differing local one.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import yaml

from metaseed.specs.schema import ProfileSpec

# The specs directory profiles are pulled into and pushed from.
_PROFILE_FILE = "profile.yaml"


class HubSpecApi(Protocol):
    """What the profile exchange needs from a hub client."""

    def list_specs(self) -> list[dict[str, Any]]: ...

    def get_spec(self, name: str, version: str) -> str: ...

    def publish_spec(self, yaml_text: str) -> tuple[dict[str, Any], bool]: ...


@dataclass(frozen=True)
class ProfileRef:
    """A profile name and version, as both sides identify one."""

    name: str
    version: str


def profile_path(specs_dir: Path, ref: ProfileRef) -> Path:
    return specs_dir / ref.name / ref.version / _PROFILE_FILE


def local_profiles(specs_dir: Path) -> list[ProfileRef]:
    """Every ``<name>/<version>/profile.yaml`` under the user specs directory."""
    if not specs_dir.is_dir():
        return []
    return sorted(
        (
            ProfileRef(path.parent.parent.name, path.parent.name)
            for path in specs_dir.glob(f"*/*/{_PROFILE_FILE}")
        ),
        key=lambda r: (r.name, r.version),
    )


def local_hash(specs_dir: Path, ref: ProfileRef) -> str | None:
    """The content hash of the local profile, or None when there is none."""
    path = profile_path(specs_dir, ref)
    if not path.exists():
        return None
    from metaseed.specs import content_hash

    spec = ProfileSpec.model_validate(yaml.safe_load(path.read_text()))
    return content_hash(spec)


@dataclass(frozen=True)
class ProfilePushOutcome:
    kind: str
    """``published`` (new on the hub) or ``identical`` (already there)."""
    content_hash: str


def push_profile(
    hub: HubSpecApi, specs_dir: Path, ref: ProfileRef
) -> ProfilePushOutcome:
    """Publish the local profile on the hub.

    Raises:
        FileNotFoundError: If no such user-local profile exists.
        metaseed.hub.client.HubApiError: When the hub refuses (409 under its
            version-bump gate, 422 for a document it cannot read).
    """
    path = profile_path(specs_dir, ref)
    if not path.exists():
        raise FileNotFoundError(
            f"No user-local profile {ref.name} {ref.version} at {path}"
        )
    row, created = hub.publish_spec(path.read_text())
    return ProfilePushOutcome(
        "published" if created else "identical", str(row.get("content_hash") or "")
    )


@dataclass(frozen=True)
class ProfilePullTarget:
    """Where a pulled profile lands, or why it does not."""

    kind: str
    """``new``, ``identical``, or ``differs`` (present locally with other content)."""
    ref: ProfileRef


def profile_pull_target(
    specs_dir: Path, ref: ProfileRef, remote_hash: str | None
) -> ProfilePullTarget:
    """Decide whether the hub's ``ref`` can be written locally."""
    mine = local_hash(specs_dir, ref)
    if mine is None:
        return ProfilePullTarget("new", ref)
    if remote_hash is not None and mine == remote_hash:
        return ProfilePullTarget("identical", ref)
    return ProfilePullTarget("differs", ref)


def pull_profile(
    hub: HubSpecApi, specs_dir: Path, ref: ProfileRef
) -> ProfilePullTarget:
    """Write the hub's published ``ref`` into the specs directory.

    A local profile at that name and version is never replaced: the outcome
    says whether it is identical or differs, and nothing is written.
    """
    remote_hash = next(
        (
            s.get("content_hash")
            for s in hub.list_specs()
            if s["name"] == ref.name and s["version"] == ref.version
        ),
        None,
    )
    target = profile_pull_target(specs_dir, ref, remote_hash)
    if target.kind != "new":
        return target
    text = hub.get_spec(ref.name, ref.version)
    path = profile_path(specs_dir, ref)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return target
