"""An entity annotated with the JERM class it represents is exported as it.

The map from entity name to JERM class holds nine strings, and nothing else was
consulted — so a profile derived faithfully from JERM exported almost nothing.
An entity called `Experiment` annotated as an Assay was skipped, while one
merely *named* `Assay` and annotated with nothing was exported (#234). The
annotations were decorative on this path.

What is read is the class the annotation *names*, never a numeric accession:
JERM is carried by no source we can reach, so `JERM:00021` cannot be resolved
to "Assay" here, and a hardcoded table of accession numbers would be inventing
identifiers rather than reading them.
"""

from __future__ import annotations

import pytest

from metaseed.seek.roles import (
    entity_jerm_class,
    jerm_class_from_annotation,
    unmapped_entities,
)


class TestReadingTheAnnotation:
    @pytest.mark.parametrize(
        "annotation",
        [
            "JERM:Assay",
            "http://jermontology.org/ontology/JERM.owl#Assay",
            "jerm/Assay",
        ],
    )
    def test_the_class_is_read_however_the_annotation_is_written(
        self, annotation: str
    ) -> None:
        assert entity_jerm_class("Experiment", None, annotation) == "Assay"

    def test_a_numeric_accession_is_not_guessed_at(self) -> None:
        """JERM is not resolvable from here, so this must stay unmapped rather
        than be matched against an invented table."""
        assert jerm_class_from_annotation("JERM:00021") is None

    def test_an_unknown_class_is_not_invented_either(self) -> None:
        assert jerm_class_from_annotation("JERM:Telescope") is None

    def test_an_explicit_role_still_wins(self) -> None:
        assert entity_jerm_class("Experiment", "Study", "JERM:Assay") == "Study"

    def test_the_name_map_still_applies_when_nothing_is_annotated(self) -> None:
        assert entity_jerm_class("Assay", None, None) == "Assay"

    def test_an_entity_that_maps_to_nothing_still_maps_to_nothing(self) -> None:
        assert entity_jerm_class("Telescope", None, None) is None


class TestSayingWhatWasSkipped:
    """The damage was silence: an export producing less than expected, without
    failing."""

    def _profile(self, **annotations: str | None):
        from metaseed.specs.schema import (
            EntityDefSpec,
            FieldSpec,
            FieldType,
            ProfileSpec,
        )

        return ProfileSpec(
            name="jermish",
            version="1.0",
            root_entity="Investigation",
            entities={
                name: EntityDefSpec(
                    ontology_term=term,
                    fields=[FieldSpec(name="unique_id", type=FieldType.STRING)],
                )
                for name, term in annotations.items()
            },
        )

    def test_unmapped_entities_are_named(self) -> None:
        profile = self._profile(Investigation=None, Treatment=None)

        assert unmapped_entities(profile) == ["Treatment"]

    def test_an_annotated_entity_is_not_reported_as_unmapped(self) -> None:
        profile = self._profile(Investigation=None, Treatment="JERM:Sample")

        assert unmapped_entities(profile) == []
