"""Regression tests for ENA Sample field requirements.

In the ENA metadata model, ``collection_date`` and
``geographic_location_country`` are checklist-level attributes (e.g. checklist
ERC000011), not properties of the base Sample object. They must therefore be
optional so that valid public ENA/DDBJ records that omit them can be imported.

See: https://github.com/sorenwacker/metaseed/issues/20
"""

from metaseed.models import get_model


class TestEnaSampleOptionalChecklistFields:
    """Checklist-level Sample attributes must not be universally required."""

    def test_sample_validates_without_checklist_level_fields(self) -> None:
        """A Sample mirroring public record SAMD00012930 validates.

        SAMD00012930 (BioProject PRJDA51199, study DRP000209) exposes neither
        ``collection_date`` nor ``geographic_location_country``; the model must
        accept it without injecting INSDC missing-value placeholders.
        """
        Sample = get_model("Sample", "1.0", profile="ena")

        sample = Sample(
            alias="SAMD00012930",
            accession="SAMD00012930",
            title="Arabidopsis thaliana sample",
            taxon_id=3702,
            scientific_name="Arabidopsis thaliana",
            common_name="thale cress",
        )

        assert sample.collection_date is None
        assert sample.geographic_location_country is None

    def test_checklist_level_fields_are_optional_in_spec(self) -> None:
        """The spec marks both checklist-level fields as not required."""
        Sample = get_model("Sample", "1.0", profile="ena")

        for field_name in ("collection_date", "geographic_location_country"):
            assert field_name in Sample.model_fields
            assert Sample.model_fields[field_name].is_required() is False, (
                f"{field_name} must be optional on the base ENA Sample"
            )
