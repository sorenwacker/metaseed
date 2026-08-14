"""#210: the declarative field markers are reachable, and weak identity is reported.

Two halves, both at the engine level (the MCP surface is pinned in
tests/test_agent/test_mcp_spec_builder.py):

* ``FIELD_MARKER_NAMES`` / ``normalize_markers`` / ``validate_marker_values`` --
  the shared vocabulary an adapter mirrors instead of hardcoding marker names.
* ``SpecBuilder.warnings()`` -- the advisory that an entity's identifier is being
  inferred positionally onto an optional free-text field.
"""

from __future__ import annotations

import glob
from pathlib import Path

import pytest
import yaml

from metaseed.specs.builder import (
    FIELD_MARKER_NAMES,
    SpecBuilder,
    normalize_markers,
    validate_marker_values,
)
from metaseed.specs.schema import FieldSpec, ProfileSpec

_CORE_ARGUMENTS = {
    "name",
    "type",
    "required",
    "description",
    "items",
    "ontology_term",
    "reference",
    "parent_ref",
    "constraints",
}


class TestMarkerVocabulary:
    """The marker names are derived from the schema, not restated."""

    def test_covers_every_non_core_fieldspec_attribute(self) -> None:
        """A new FieldSpec attribute joins the markers without a second edit."""
        assert set(FIELD_MARKER_NAMES) == set(FieldSpec.model_fields) - _CORE_ARGUMENTS

    def test_no_core_authoring_argument_is_a_marker(self) -> None:
        assert set(FIELD_MARKER_NAMES).isdisjoint(_CORE_ARGUMENTS)

    def test_declared_identity_markers_are_present(self) -> None:
        """The markers issue #210 was filed about are in the set."""
        for name in ("is_identifier", "is_label", "owns", "tier", "options"):
            assert name in FIELD_MARKER_NAMES


class TestNormalizeMarkers:
    def test_omitted_marker_is_dropped(self) -> None:
        """None means 'not supplied', so the key must not reach update_field."""
        assert normalize_markers({"unit": None, "is_identifier": None}) == {}

    @pytest.mark.parametrize("empty", [False, "", []])
    def test_explicit_empty_value_unsets_the_marker(self, empty: object) -> None:
        """The empty value is the removal request; it must survive as None."""
        assert normalize_markers({"unit": empty}) == {"unit": None}

    def test_real_values_pass_through(self) -> None:
        assert normalize_markers(
            {"is_identifier": True, "unit": "cm", "options": ["a"]}
        ) == {"is_identifier": True, "unit": "cm", "options": ["a"]}

    def test_zero_is_a_value_not_an_empty(self) -> None:
        """0 == False in Python; a numeric example of 0 must not read as 'unset'."""
        assert normalize_markers({"example": 0}) == {"example": 0}


class TestValidateMarkerValues:
    def test_accepts_valid_values(self) -> None:
        assert validate_marker_values({"tier": "recommended"}) is None

    def test_rejects_a_bad_tier_naming_the_options(self) -> None:
        error = validate_marker_values({"tier": "mandatory"})
        assert error is not None
        assert "tier" in error

    def test_rejects_an_unknown_marker_name(self) -> None:
        error = validate_marker_values({"is_identifer": True})
        assert error is not None
        assert "is_identifer" in error


def _weak_draft(**marker: object) -> SpecBuilder:
    """A draft whose Assay identifier is inferred onto an optional free-text field."""
    builder = SpecBuilder.empty("p", "1.0")
    builder.add_entity("Assay")
    builder.add_field("Assay", "variable_name", "string", **marker)
    builder.set_root_entity("Assay")
    return builder


class TestWeakInferredIdentifierWarning:
    def test_fires_on_an_optional_free_text_inferred_identifier(self) -> None:
        warnings = _weak_draft().warnings()

        assert len(warnings) == 1
        assert "Assay" in warnings[0]
        assert "variable_name" in warnings[0]
        assert "is_identifier" in warnings[0]

    def test_silent_when_the_identifier_is_declared(self) -> None:
        assert _weak_draft(is_identifier=True).warnings() == []

    def test_silent_when_the_inferred_field_is_required(self) -> None:
        assert _weak_draft(required=True).warnings() == []

    def test_silent_when_the_inferred_field_is_not_text(self) -> None:
        builder = SpecBuilder.empty("p", "1.0")
        builder.add_entity("Assay")
        builder.add_field("Assay", "measured_on", "date")
        assert builder.warnings() == []

    @pytest.mark.parametrize(
        "narrowing",
        [
            {"options": ["a", "b"]},
            {"unique_within": "global"},
        ],
    )
    def test_silent_when_the_value_shape_is_pinned(
        self, narrowing: dict[str, object]
    ) -> None:
        assert _weak_draft(**narrowing).warnings() == []

    @pytest.mark.parametrize(
        "field_name", ["id", "sample_id", "locationID", "database_identifier"]
    )
    def test_silent_when_the_field_name_states_it_is_an_identifier(
        self, field_name: str
    ) -> None:
        builder = SpecBuilder.empty("p", "1.0")
        builder.add_entity("Assay")
        builder.add_field("Assay", field_name, "string")
        assert builder.warnings() == []

    def test_a_label_shaped_name_is_not_exempt(self) -> None:
        """`name`/`title` state a display label, which is not an identity claim."""
        builder = SpecBuilder.empty("p", "1.0")
        builder.add_entity("Assay")
        builder.add_field("Assay", "title", "string")
        assert len(builder.warnings()) == 1

    def test_a_parent_reference_is_skipped_like_the_facade_skips_it(self) -> None:
        """Inference must match EntityHelper.identifier_field: references do not count."""
        builder = SpecBuilder.empty("p", "1.0")
        builder.add_entity("Study")
        builder.add_entity("Assay")
        builder.add_field("Assay", "study_id", "string", reference="Study.identifier")
        builder.add_field("Assay", "variable_name", "string")

        warnings = builder.warnings()

        assert len(warnings) == 1
        assert "variable_name" in warnings[0]
        assert "study_id" not in warnings[0]

    def test_warnings_are_not_validation_issues(self) -> None:
        """The documented `validate()` return shape must not absorb advisories."""
        builder = _weak_draft()
        assert builder.validate() == []
        assert builder.warnings() != []


def _shipped_profiles() -> list[tuple[str, Path]]:
    root = Path(__file__).resolve().parents[2]
    paths = sorted(glob.glob(str(root / "src/metaseed/specs/*/*/profile.yaml")))
    return [(f"{Path(p).parts[-3]}/{Path(p).parts[-2]}", Path(p)) for p in paths]


_SHIPPED = _shipped_profiles()

# Recorded state of every shipped profile under the rule. The advisory fired five
# times when it was introduced; three of those entities have since declared the
# identifier they were already keyed by (#212). The two left are not oversights:
# SpatialDistribution is a value object with no identity of its own, and PRIDE
# Publication is identified by its doi, which is a different field from the one
# inference picks and so cannot move before a MAJOR version.
_EXPECTED_WARNING_TARGETS: dict[str, set[str]] = {
    "miappe-htp/1.0": {"SpatialDistribution.description"},
    "pride/1.0": {"Publication.title"},
    # Recorded, not fixed: declaring identifiers re-keys datasets written
    # against these versions (the pride/2.0 lesson), so it belongs in an
    # 0.3, not an edit in place. 0.2's shorter list is the reconciliation
    # dropping Location and MaterialSource.
    "isa-miappe-combined/0.1": {
        "BiologicalMaterial.accession_number",
        "Factor.description",
        "Location.abbreviation",
        "MaterialSource.address",
        "ObservationUnit.entry_type",
        "ObservedVariable.method",
        "Person.address",
        "Publication.author_list",
    },
    "isa-miappe-combined/0.2": {
        "BiologicalMaterial.accession_number",
        "Factor.description",
        "ObservationUnit.entry_type",
        "ObservedVariable.method",
        "Person.address",
        "Publication.author_list",
    },
}

# Entity -> the identifier it now declares, per profile. Each must be the field
# inference already resolved to: that is what makes declaring it a compatible
# change rather than a MAJOR bump, and what stops the declaration re-keying a
# dataset that was written before it.
_DECLARED_IDENTIFIERS: dict[str, dict[str, str]] = {
    "isa/1.0": {"Process": "name"},
    "miappe-htp/1.0": {"Location": "name", "ObservationLevelHierarchy": "name"},
}


@pytest.mark.parametrize(
    ("label", "path"), _SHIPPED, ids=[label for label, _ in _SHIPPED]
)
def test_a_declared_identifier_is_the_one_inference_would_pick(
    label: str, path: Path
) -> None:
    """Recording an inference, not overriding it."""
    spec = ProfileSpec.model_validate(yaml.safe_load(path.read_text()))

    for entity_name, expected in _DECLARED_IDENTIFIERS.get(label, {}).items():
        fields = spec.entities[entity_name].fields
        declared = next(f.name for f in fields if f.is_identifier)
        inferred = next(f.name for f in fields if not f.reference)

        assert declared == expected
        assert declared == inferred, (
            f"{label} {entity_name}: declaring {declared!r} moves the identifier "
            f"off {inferred!r}, which re-keys existing data"
        )


@pytest.mark.parametrize(
    ("label", "path"), _SHIPPED, ids=[label for label, _ in _SHIPPED]
)
def test_shipped_profile_has_no_blocking_issue(label: str, path: Path) -> None:
    """The advisory must never make a shipped profile invalid."""
    spec = ProfileSpec.model_validate(yaml.safe_load(path.read_text()))
    assert SpecBuilder(spec).validate() == []


@pytest.mark.parametrize(
    ("label", "path"), _SHIPPED, ids=[label for label, _ in _SHIPPED]
)
def test_shipped_profile_warnings_are_the_recorded_ones(label: str, path: Path) -> None:
    """Pins the advisory across all ten so a profile edit cannot add one unnoticed."""
    spec = ProfileSpec.model_validate(yaml.safe_load(path.read_text()))
    warnings = SpecBuilder(spec).warnings()

    expected = _EXPECTED_WARNING_TARGETS.get(label, set())
    assert len(warnings) == len(expected)
    for target in expected:
        entity, field = target.split(".")
        assert any(
            w.startswith(f"{entity}:") and f"'{field}'" in w for w in warnings
        ), f"{label}: expected a warning for {target}, got {warnings}"
