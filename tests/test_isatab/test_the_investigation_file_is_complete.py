"""The investigation file must carry every label ISA-Tab defines for a section.

ISA-Tab says each section "MUST contain the following labels"; the reference
investigation file published with the specification writes them all, many with
empty values. The writer emitted a subset, so:

* every ontology term went out without its ``Term Accession Number`` /
  ``Term Source REF`` pair, leaving a reader unable to tell an un-annotated
  value from a missing one;
* ``Study Protocol Parameters Name`` was absent, so a protocol's parameters --
  their own entities in the profile -- were dropped entirely, losing the only
  record of what the protocol was run with;
* the study table had no ``Protocol REF`` column, so the Source and Sample it
  lists were not linked by the process that MUST connect them.

Labels are expected even when the profile has no field to fill them: the
specification requires the label, and a consumer reads the file by its labels.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from metaseed import MetaseedClient
from metaseed.isatab import to_isatab
from metaseed.metabolights.mapper import build_dataset

FIXTURE = Path(__file__).resolve().parents[1] / "test_metabolights/fixtures/study.json"

#: Labels the specification's own reference investigation file carries, which
#: the writer omitted. Each is a row label, one per line of the file.
REQUIRED_LABELS = (
    "Study Submission Date",
    "Study Public Release Date",
    "Study Design Type Term Accession Number",
    "Study Design Type Term Source REF",
    "Study Publication Status Term Accession Number",
    "Study Publication Status Term Source REF",
    "Study Factor Type Term Accession Number",
    "Study Factor Type Term Source REF",
    "Study Assay Measurement Type Term Accession Number",
    "Study Assay Measurement Type Term Source REF",
    "Study Assay Technology Type Term Accession Number",
    "Study Assay Technology Type Term Source REF",
    "Study Protocol Type Term Accession Number",
    "Study Protocol Type Term Source REF",
    "Study Protocol URI",
    "Study Protocol Version",
    "Study Protocol Parameters Name",
    "Study Protocol Parameters Name Term Accession Number",
    "Study Protocol Parameters Name Term Source REF",
    "Study Protocol Components Name",
    "Study Protocol Components Type",
    "Study Protocol Components Type Term Accession Number",
    "Study Protocol Components Type Term Source REF",
    "Study Person Mid Initials",
    "Study Person Phone",
    "Study Person Fax",
    "Study Person Address",
    "Study Person Roles Term Accession Number",
    "Study Person Roles Term Source REF",
    "Investigation Publication Status Term Accession Number",
    "Investigation Publication Status Term Source REF",
    "Investigation Person Roles Term Accession Number",
    "Investigation Person Roles Term Source REF",
)


@pytest.fixture(scope="module")
def documents() -> dict[str, str]:
    return to_isatab(build_dataset(json.loads(FIXTURE.read_text())))


def _labels(investigation: str) -> list[str]:
    return [line.split("\t", 1)[0] for line in investigation.splitlines()]


def test_no_required_label_is_missing(documents: dict[str, str]) -> None:
    labels = set(_labels(documents["i_Investigation.txt"]))

    missing = [label for label in REQUIRED_LABELS if label not in labels]

    assert not missing, f"{len(missing)} labels missing: {missing}"


def test_a_term_is_followed_by_its_accession_then_its_source(
    documents: dict[str, str],
) -> None:
    """The investigation file orders the triplet term, accession, source.

    A table file orders its columns the other way round; getting them the same
    way round in both places is the mistake this pins down.
    """
    labels = _labels(documents["i_Investigation.txt"])

    for term in ("Study Design Type", "Study Factor Type", "Study Protocol Type"):
        start = labels.index(term)
        assert labels[start + 1] == f"{term} Term Accession Number"
        assert labels[start + 2] == f"{term} Term Source REF"


def test_a_protocols_parameters_are_written_against_that_protocol(
    documents: dict[str, str],
) -> None:
    """Parameters are their own entities; each belongs to one protocol."""
    row = next(
        line
        for line in documents["i_Investigation.txt"].splitlines()
        if line.startswith("Study Protocol Parameters Name")
    )
    names = row.split("\t")[1:]

    # The fixture's NMR protocol declares two parameters; sample collection none.
    assert "Instrument;NMR tube type" in names
    assert names.index("Instrument;NMR tube type") == 1, (
        "parameters landed against the wrong protocol"
    )


class TestTheStudyTableLinksSourceToSample:
    def test_a_protocol_ref_column_sits_between_the_two_materials(
        self, documents: dict[str, str]
    ) -> None:
        header = documents["s_MTBLS1.txt"].splitlines()[0].split("\t")

        assert header[:3] == ["Source Name", "Protocol REF", "Sample Name"]

    def test_it_names_the_sample_collection_protocol(
        self, documents: dict[str, str]
    ) -> None:
        """ISA-Tab requires the referenced protocol to be of that type."""
        rows = documents["s_MTBLS1.txt"].splitlines()
        assert rows[1].split("\t")[1] == "Sample collection"

    def test_a_study_without_such_a_protocol_leaves_the_cell_empty(self) -> None:
        """Better an empty cell than a reference to a protocol of another type."""
        from metaseed.isatab import sample_collection_protocol

        assert (
            sample_collection_protocol([{"name": "NMR", "protocol_type": "NMR"}]) == ""
        )


class TestAnAccessionNamesItsOntology:
    def test_the_source_is_read_back_from_the_accession(self) -> None:
        from metaseed.isatab import _term_source

        assert _term_source("PATO:0000461") == "PATO"
        assert _term_source("http://purl.obolibrary.org/obo/OBI_0500020") == "OBI"

    def test_a_value_that_names_no_ontology_gives_nothing(self) -> None:
        from metaseed.isatab import _term_source

        assert _term_source("") == ""
        assert _term_source("just free text") == ""

    def test_the_study_table_resolves_its_accessions(self) -> None:
        """The Term Source REF column was written blank even with an accession."""
        client = MetaseedClient("metabolights", "1.0")
        investigation = client.create_entity(
            "Investigation", {"identifier": "I1", "title": "t"}, skip_validation=True
        )
        study = client.create_entity(
            "Study",
            {"identifier": "S1", "title": "s"},
            parent_id=investigation.id,
            skip_validation=True,
        )
        client.create_entity(
            "Sample",
            {
                "name": "sample-1",
                "organism": "Homo sapiens",
                "organism_term": {"term_accession": "NCBITaxon:9606"},
            },
            parent_id=study.id,
            skip_validation=True,
        )

        table = to_isatab(client)["s_S1.txt"]
        header = table.splitlines()[0].split("\t")
        row = table.splitlines()[1].split("\t")
        cell = dict(zip(header, row, strict=True))

        assert cell["Term Source REF"] == "NCBITAXON"
        assert cell["Term Accession Number"] == "NCBITaxon:9606"

    def test_the_ontology_section_declares_what_the_export_uses(self) -> None:
        """A Term Source REF SHOULD match a name declared in this section."""
        client = MetaseedClient("metabolights", "1.0")
        investigation = client.create_entity(
            "Investigation", {"identifier": "I1", "title": "t"}, skip_validation=True
        )
        study = client.create_entity(
            "Study",
            {"identifier": "S1", "title": "s"},
            parent_id=investigation.id,
            skip_validation=True,
        )
        client.create_entity(
            "Sample",
            {
                "name": "sample-1",
                "organism": "Homo sapiens",
                "organism_term": {"term_accession": "NCBITaxon:9606"},
            },
            parent_id=study.id,
            skip_validation=True,
        )

        row = next(
            line
            for line in to_isatab(client)["i_Investigation.txt"].splitlines()
            if line.startswith("Term Source Name")
        )

        assert "NCBITAXON" in row.split("\t")[1:]
