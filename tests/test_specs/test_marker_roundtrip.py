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
    loader = SpecLoader()
    pairs: list[tuple[str, str]] = []
    for profile in loader.list_profiles():
        for version in SpecLoader(profile=profile).list_versions(profile):
            pairs.append((profile, version))
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
