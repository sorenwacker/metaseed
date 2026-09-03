"""A PRIDE submission must be parseable and carry every column SDRF requires.

Two defects motivated these gates.

``submission.px`` is line-based and has no continuation syntax, but nothing
collapsed newlines inside a value. A description of two lines — the ordinary
case for an abstract — emitted its second line as a bare record the
px-submission-tool cannot read. The shipped example already carried a trailing
newline, so the file it produced had a stray blank line in the MTD block.

The SDRF table omitted five columns the SDRF-Proteomics specification marks
REQUIRED. The specification is explicit that a mandatory column whose value is
unknown is written ``not available`` rather than dropped, so the column must be
present either way.
"""

from __future__ import annotations

from metaseed import MetaseedClient
from metaseed.pride.export import to_pride_sdrf, to_pride_submission

#: Every column SDRF-Proteomics marks REQUIRED, in the order the specification's
#: own example lays them out (sample metadata, then data-file metadata).
REQUIRED_SDRF_COLUMNS = (
    "source name",
    "characteristics[organism]",
    "characteristics[organism part]",
    "characteristics[disease]",
    "characteristics[biological replicate]",
    "assay name",
    "technology type",
    "comment[proteomics data acquisition method]",
    "comment[label]",
    "comment[instrument]",
    "comment[cleavage agent details]",
    "comment[fraction identifier]",
    "comment[technical replicate]",
    "comment[data file]",
)

_VALID_RECORD_PREFIXES = ("#", "MTD\t", "FMH\t", "FME\t")


def _client(**dataset: object) -> MetaseedClient:
    client = MetaseedClient("pride", "2.0")
    client.create_entity(
        "Dataset",
        {
            "identifier": "PXD999999",
            "title": "T",
            "submission_type": "COMPLETE",
            **dataset,
        },
        skip_validation=True,
    )
    return client


def _px_lines(client: MetaseedClient) -> list[str]:
    return to_pride_submission(client)["submission.px"].splitlines()


class TestTheFileStaysLineBased:
    def test_a_multiline_description_does_not_emit_a_bare_line(self) -> None:
        client = _client(description="First line of the abstract.\nSecond line of it.")

        lines = _px_lines(client)

        stray = [
            line
            for line in lines
            if line and not line.startswith(_VALID_RECORD_PREFIXES)
        ]
        assert not stray, f"not valid px records: {stray}"

    def test_the_whole_description_survives_on_one_record(self) -> None:
        """Collapsing newlines must not truncate the text."""
        client = _client(description="First line of the abstract.\nSecond line of it.")

        description = [
            line
            for line in _px_lines(client)
            if line.startswith("MTD\tproject_description")
        ]

        assert description == [
            "MTD\tproject_description\tFirst line of the abstract. Second line of it."
        ]

    def test_a_trailing_newline_leaves_no_blank_line(self) -> None:
        client = _client(description="An abstract that ends in a newline.\n")

        body = _px_lines(client)

        assert "" not in body, "a blank line is not a px record"


class TestThePublicationIsNotLost:
    def test_pubmed_id_and_doi_reach_the_file(self) -> None:
        client = _client(
            publications=[
                {
                    "title": "A paper",
                    "pubmed_id": "38765432",
                    "doi": "10.1016/j.jprot.2024.104567",
                }
            ]
        )

        px = to_pride_submission(client)["submission.px"]

        assert "MTD\tpubmed_id\t38765432" in px
        assert "MTD\tdoi\t10.1016/j.jprot.2024.104567" in px

    def test_a_dataset_without_a_publication_says_nothing(self) -> None:
        px = to_pride_submission(_client())

        assert "pubmed_id" not in px["submission.px"]


class TestTheSdrfCarriesEveryRequiredColumn:
    def _sdrf_rows(self) -> list[list[str]]:
        client = _client(
            instruments=[{"name": "Orbitrap Fusion Lumos"}],
            samples=[
                {
                    "name": "S1",
                    "species": "Homo sapiens",
                    "tissue": "cervix",
                    "cell_type": "epithelial",
                    "disease": "normal",
                }
            ],
            files=[{"filename": "run1.raw", "file_type": "RAW", "sample_refs": ["S1"]}],
        )
        text = to_pride_sdrf(client)["sdrf.tsv"]
        return [line.split("\t") for line in text.splitlines()]

    def test_no_required_column_is_missing(self) -> None:
        header = self._sdrf_rows()[0]

        missing = [c for c in REQUIRED_SDRF_COLUMNS if c not in header]

        assert not missing, f"SDRF is missing required columns: {missing}"

    def test_the_required_columns_keep_the_specified_order(self) -> None:
        """Sample metadata first, then data-file metadata."""
        header = self._sdrf_rows()[0]

        positions = [header.index(c) for c in REQUIRED_SDRF_COLUMNS if c in header]

        assert positions == sorted(positions), header

    def test_a_column_the_profile_cannot_fill_says_not_available(self) -> None:
        header, row = self._sdrf_rows()[0], self._sdrf_rows()[1]
        cell = dict(zip(header, row, strict=True))

        assert cell["comment[cleavage agent details]"] == "not available"
        assert cell["comment[label]"] == "not available"
        assert cell["comment[proteomics data acquisition method]"] == "not available"

    def test_replicate_and_fraction_default_to_one(self) -> None:
        """The specification's own value when nothing is replicated or fractionated."""
        header, row = self._sdrf_rows()[0], self._sdrf_rows()[1]
        cell = dict(zip(header, row, strict=True))

        assert cell["characteristics[biological replicate]"] == "1"
        assert cell["comment[technical replicate]"] == "1"
        assert cell["comment[fraction identifier]"] == "1"

    def test_the_values_it_does_know_are_still_written(self) -> None:
        header, row = self._sdrf_rows()[0], self._sdrf_rows()[1]
        cell = dict(zip(header, row, strict=True))

        assert cell["source name"] == "S1"
        assert cell["characteristics[organism]"] == "Homo sapiens"
        assert cell["comment[instrument]"] == "Orbitrap Fusion Lumos"
        assert cell["comment[data file]"] == "run1.raw"

    def test_every_row_has_a_cell_for_every_column(self) -> None:
        rows = self._sdrf_rows()

        assert len({len(row) for row in rows}) == 1, "ragged table"
