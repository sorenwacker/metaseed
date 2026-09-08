"""Non-regression: the #137/#143/#98 markers must not perturb existing specs.

The new FieldSpec markers all default to ``None`` and SpecBuilder.to_yaml uses
``exclude_none``, so an un-migrated spec must round-trip with no ``owns: false``
churn, and any spec (migrated or not) must reload to an equal ProfileSpec.
"""

from __future__ import annotations

import pytest
import yaml

from metaseed.specs.builder import SpecBuilder
from metaseed.specs.loader import SpecLoader
from metaseed.specs.schema import ProfileSpec

_MARKER_CHURN = (
    "owns: false",
    "is_identifier: false",
    "is_label: false",
)


def _all_profile_versions() -> list[tuple[str, str]]:
    """Every profile the library ships, as (profile, version) pairs.

    Read from the built-in directory rather than through ``list_profiles``,
    which also returns the user's own specifications. Parametrisation happens at
    collection time, before the fixture that redirects the data directory, so
    going through the loader made the test set depend on which profiles the
    developer happened to have installed: locally it covered their cropxr
    profiles and on CI it did not, and the cases it invented for them then
    failed because the fixture had redirected the directory out from under them.

    What this test asserts -- that markers do not perturb a spec -- is a promise
    about the specs the library ships. A person's own specification is not the
    library's to guarantee, and cannot be, since it is not here to check.
    """
    from metaseed.paths import get_builtin_specs_dir

    builtin = get_builtin_specs_dir()
    pairs: list[tuple[str, str]] = []
    for profile_dir in sorted(p for p in builtin.iterdir() if p.is_dir()):
        for version_dir in sorted(v for v in profile_dir.iterdir() if v.is_dir()):
            if (version_dir / "profile.yaml").exists():
                pairs.append((profile_dir.name, version_dir.name))
    return pairs


@pytest.mark.parametrize(("profile", "version"), _all_profile_versions())
def test_profile_round_trips_without_marker_churn(profile: str, version: str) -> None:
    spec = SpecLoader(profile=profile).load_profile(version, profile)
    rendered = SpecBuilder(spec).to_yaml()

    # Bool|None markers must never serialize their falsey form (no owns: false).
    for churn in _MARKER_CHURN:
        assert churn not in rendered, f"{profile} v{version}: unexpected '{churn}'"

    # Full-fidelity round trip: reload the rendered YAML and compare specs.
    reloaded = ProfileSpec.model_validate(yaml.safe_load(rendered))
    assert reloaded == spec
