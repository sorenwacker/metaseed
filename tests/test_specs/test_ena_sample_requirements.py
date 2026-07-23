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


class TestEnaAccessionAcceptsAllInsdcArchives:
    """Accession patterns must accept ENA (E), NCBI (S) and DDBJ (D) variants.

    INSDC mirrors every record across its three partners with a leading letter
    for the originating archive, so a valid public record from any partner (e.g.
    the DDBJ project PRJDA51199 with DRR runs) must import. Accessions are also
    only assigned on submission, so an entity being authored (no accession yet)
    must validate too.
    """

    def _accession_error(self, entity_type: str, other: dict, value) -> bool:
        from pydantic import ValidationError

        model = get_model(entity_type, "1.0", profile="ena")
        kwargs = dict(other)
        if value is not None:
            kwargs["accession"] = value
        try:
            model(**kwargs)
        except ValidationError as exc:
            return any(e["loc"] == ("accession",) for e in exc.errors())
        return False

    def test_run_accepts_each_archive_and_authoring_without_accession(self) -> None:
        other = {"alias": "r", "experiment_ref": "DRX000621"}
        for accession in (None, "ERR000621", "SRR000621", "DRR000621"):
            assert not self._accession_error("Run", other, accession), (
                f"Run accession {accession!r} must be accepted"
            )
        assert self._accession_error("Run", other, "RUN-1")  # not an INSDC run

    def test_experiment_and_study_accept_ddbj_and_ncbi(self) -> None:
        assert not self._accession_error(
            "Experiment", {"alias": "x", "study_ref": "DRP000209"}, "DRX000621"
        )
        # DDBJ BioProject (PRJDA...) and secondary study (DRP...) both valid
        for accession in ("PRJDA51199", "DRP000209", "SRP000209"):
            assert not self._accession_error("Study", {"alias": "s"}, accession), (
                f"Study accession {accession!r} must be accepted"
            )
