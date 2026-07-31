"""Filesystem persistence for user-created specifications.

User specs are stored under the platform data directory, separate from the
built-in specs shipped in ``src/metaseed/specs/<profile>/<version>/``. This
module is independent of the UI and MCP layers so either interface can save,
list, or delete a draft.

See `docs/architecture/spec-builder.md`.
"""

from __future__ import annotations

import shutil
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from metaseed.specs.builder import SpecBuilder

if TYPE_CHECKING:
    from metaseed.specs.schema import ProfileSpec


def _specs_subpath(*parts: str) -> Path:
    """Resolve a path under the custom-specs dir, rejecting escapes.

    ``name`` and ``version`` components flow from user/model input into
    filesystem paths (and, on delete, into ``shutil.rmtree``). A component like
    ``../../.config/autostart`` or an absolute path would otherwise escape the
    specs directory. Resolve the full path and require it to stay within the
    (resolved) base; also reject empty components.

    Raises:
        ValueError: If any component is empty or the result escapes the base.
    """
    base = get_custom_specs_dir()
    for part in parts:
        if not part or not str(part).strip():
            raise ValueError("path component cannot be empty")
    candidate = base.joinpath(*parts).resolve()
    if not candidate.is_relative_to(base.resolve()):
        raise ValueError(f"path component escapes the specs directory: {parts!r}")
    return candidate


def get_custom_specs_dir() -> Path:
    """Return the directory for user-created specs (created if needed).

    Locations:
    - Linux/macOS: ``~/.local/share/metaseed/specs/``
    - Windows: ``%LOCALAPPDATA%/metaseed/specs/``
    """
    from metaseed.paths import get_user_specs_dir

    return get_user_specs_dir()


def _normalize_profile_name(name: str) -> str:
    """Normalize a profile name to its on-disk directory form.

    Lowercases, strips, and replaces every non ``alnum``/``-``/``_`` character
    with ``-`` -- the identical transform ``save_spec`` applies, so a name saved
    under one form is found by the same name on delete rather than silently
    missing.

    Raises:
        ValueError: If the name is empty after stripping.
    """
    normalized = name.lower().strip()
    if not normalized:
        raise ValueError("Profile name cannot be empty")
    return "".join(c if c.isalnum() or c in "-_" else "-" for c in normalized)


def save_spec(spec: ProfileSpec, name: str | None = None) -> Path:
    """Save a spec to ``specs/<name>/<version>/profile.yaml``.

    Args:
        spec: The ProfileSpec to save.
        name: Profile name override. Uses ``spec.name`` if not provided.

    Returns:
        Path to the saved ``profile.yaml`` file.

    Raises:
        ValueError: If the name is empty, the version is not ``MAJOR.MINOR``,
            or the name conflicts with a built-in spec.
    """
    from metaseed.specs.loader import SpecLoader
    from metaseed.specs.versioning import require_profile_version

    # Checked before touching the filesystem: the version is also the directory
    # name, and a spec written with a malformed version could not be loaded back.
    require_profile_version(spec.version)

    safe_name = _normalize_profile_name(name or spec.name)

    loader = SpecLoader()
    builtin_profiles = [
        p.lower() for p in loader.list_profiles() if not loader.is_user_defined(p)
    ]
    if safe_name in builtin_profiles:
        raise ValueError(
            f"Cannot save with name '{safe_name}' - conflicts with built-in spec. "
            f"Please choose a different name."
        )

    version_dir = _specs_subpath(safe_name, spec.version)
    version_dir.mkdir(parents=True, exist_ok=True)

    profile_path = version_dir / "profile.yaml"
    profile_path.write_text(SpecBuilder.from_spec(spec).to_yaml(), encoding="utf-8")
    return profile_path


def _list_specs(
    include_user_defined: bool, default_display_name_fn: Callable[[str], str]
) -> list[dict[str, Any]]:
    """Shared logic for listing built-in or user specs."""
    from metaseed.specs.loader import SpecLoader, SpecLoadError

    loader = SpecLoader()
    result: list[dict[str, Any]] = []
    for profile_name in loader.list_profiles():
        if loader.is_user_defined(profile_name) != include_user_defined:
            continue

        versions = loader.list_versions(profile_name)
        if not versions:
            continue

        try:
            spec = loader.load_profile(version=versions[-1], profile=profile_name)
            result.append(
                {
                    "name": profile_name,
                    "display_name": spec.display_name
                    or spec.name
                    or default_display_name_fn(profile_name),
                    "description": spec.description or "",
                    "versions": versions,
                }
            )
        except SpecLoadError:
            result.append(
                {
                    "name": profile_name,
                    "display_name": default_display_name_fn(profile_name),
                    "description": "",
                    "versions": versions,
                }
            )

    return result


def list_available_templates() -> list[dict[str, Any]]:
    """List built-in profiles usable as templates."""
    return _list_specs(
        include_user_defined=False,
        default_display_name_fn=lambda name: name.upper(),
    )


def list_user_specs() -> list[dict[str, Any]]:
    """List user-created specifications."""
    return _list_specs(
        include_user_defined=True,
        default_display_name_fn=lambda name: name,
    )


def delete_user_spec(name: str, version: str | None = None) -> bool:
    """Delete a user-created spec (all versions if ``version`` is None).

    Args:
        name: The profile name to delete.
        version: Specific version to delete, or None for all versions.

    Returns:
        True if something was deleted, False if nothing matched.

    Raises:
        ValueError: If the spec is built-in.
    """
    from metaseed.specs.loader import SpecLoader

    # Match save_spec's on-disk naming so a delete by the original name is not a
    # silent no-op against a differently-cased/sanitized directory.
    name = _normalize_profile_name(name)

    loader = SpecLoader()
    if not loader.is_user_defined(name):
        raise ValueError(f"Cannot delete built-in specification: {name}")

    # Containment-check before any rmtree: name/version must not escape the base.
    profile_dir = _specs_subpath(name)
    if not profile_dir.exists():
        return False

    if version:
        version_dir = _specs_subpath(name, version)
        if not version_dir.exists():
            return False
        shutil.rmtree(version_dir)
        if not list(profile_dir.iterdir()):
            profile_dir.rmdir()
        return True

    shutil.rmtree(profile_dir)
    return True
